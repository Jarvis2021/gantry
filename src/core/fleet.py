# -----------------------------------------------------------------------------
# THE FLEET MANAGER - ORCHESTRATOR (Self-Healing)
# -----------------------------------------------------------------------------
# Responsibility: Orchestrates the complete mission pipeline with self-repair.
# Connects: Database -> Architect -> Policy -> Foundry -> [Heal Loop] -> Deploy
#
# Self-Healing: When a build/deploy fails, the Architect analyzes the error and
# generates a fixed manifest. This loop repeats up to MAX_RETRIES times.
#
# Progress Updates: Status is pushed every few seconds during long operations.
# Thread-based concurrency: Each mission runs in its own thread.
# Audio-first: Every outcome has a speech field for TTS.
#
# Environment Variables:
# - GANTRY_SKIP_PUBLISH=true: Skip GitHub publishing (for tests/CI)
# -----------------------------------------------------------------------------

import os
import threading
import time
import traceback
from typing import Optional, Callable

from rich.console import Console

from src.core.architect import Architect, ArchitectError
from src.core.db import create_mission, update_mission_status, init_db
from src.core.foundry import Foundry, AuditFailedError, BuildTimeoutError, MISSIONS_DIR
from src.core.deployer import DeploymentError
from src.core.policy import PolicyGate, SecurityViolation
from src.core.publisher import Publisher, SecurityBlock, PublishError

console = Console()

# Check if publishing should be skipped (for tests/CI)
SKIP_PUBLISH = os.getenv("GANTRY_SKIP_PUBLISH", "").lower() == "true"

# Self-Healing Configuration
MAX_RETRIES = 3  # Maximum heal attempts before giving up

# Progress Update Interval
PROGRESS_UPDATE_SECONDS = 5


class ProgressTracker:
    """
    Tracks mission progress and sends periodic status updates.
    
    Purpose: Keep user informed during long-running operations.
    Updates DB every PROGRESS_UPDATE_SECONDS with elapsed time.
    """
    
    def __init__(self, mission_id: str, phase: str) -> None:
        self.mission_id = mission_id
        self.phase = phase
        self.start_time = time.time()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
    
    def _update_loop(self) -> None:
        """Background loop to push progress updates."""
        while not self._stop_event.wait(PROGRESS_UPDATE_SECONDS):
            elapsed = int(time.time() - self.start_time)
            update_mission_status(
                self.mission_id,
                self.phase,
                f"{self.phase}... ({elapsed}s elapsed)"
            )
            console.print(f"[dim][PROGRESS] {self.phase} - {elapsed}s elapsed[/dim]")
    
    def start(self) -> "ProgressTracker":
        """Start the progress tracker."""
        self._thread = threading.Thread(
            target=self._update_loop,
            daemon=True,
            name=f"progress-{self.mission_id[:8]}"
        )
        self._thread.start()
        return self
    
    def stop(self) -> None:
        """Stop the progress tracker."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
    
    def update_phase(self, new_phase: str) -> None:
        """Update the current phase."""
        self.phase = new_phase
        self.start_time = time.time()


class FleetManager:
    """
    The Fleet Orchestrator.
    
    Pipeline: Voice Memo -> DB -> Architect -> Policy -> Foundry -> DB -> TTS
    
    All operations run in background threads to keep Flask responsive.
    """

    def __init__(self) -> None:
        """Initialize the Fleet Manager."""
        # Initialize database
        init_db()
        
        # Initialize components
        self._foundry = Foundry()
        self._policy = PolicyGate()
        self._publisher = Publisher()
        self._architect: Optional[Architect] = None
        
        console.print("[green][FLEET] Fleet Manager online[/green]")

    def _get_architect(self) -> Architect:
        """Lazy init Architect (requires AWS creds)."""
        if self._architect is None:
            self._architect = Architect()
        return self._architect

    def _heal_and_retry(
        self, 
        mission_id: str, 
        architect: Architect, 
        manifest, 
        error_log: str, 
        attempt: int,
        error_type: str
    ) -> None:
        """
        Common self-healing logic for both audit and deployment failures.
        
        Updates mission status and logs the healing attempt.
        """
        console.print(f"[yellow][Mission {mission_id[:8]}] Engaging self-repair for {error_type}...[/yellow]")
        update_mission_status(
            mission_id,
            "HEALING",
            f"{error_type} failed. Self-repair attempt {attempt} of {MAX_RETRIES}."
        )

    def dispatch_mission(self, prompt: str, deploy: bool = True, publish: bool = True) -> str:
        """
        Dispatch a new mission.
        
        Creates DB entry (PENDING) and spawns background thread.
        Returns immediately with mission ID.
        
        Args:
            prompt: The voice memo / build request.
            deploy: Whether to deploy to Vercel (default True, set False for tests).
            publish: Whether to publish to GitHub (default True for real users,
                     set False for tests/CI).
            
        Returns:
            Mission ID for tracking.
        """
        # Create DB entry
        mission_id = create_mission(prompt)
        
        console.print(f"[cyan][FLEET] Mission queued: {mission_id[:8]} (deploy={deploy}, publish={publish})[/cyan]")
        
        # Spawn background thread
        thread = threading.Thread(
            target=self._run_mission,
            args=(mission_id, prompt, deploy, publish),
            name=f"mission-{mission_id[:8]}",
            daemon=True
        )
        thread.start()
        
        return mission_id

    def _run_mission(self, mission_id: str, prompt: str, deploy: bool = True, publish: bool = True) -> None:
        """
        Execute the complete mission pipeline with SELF-HEALING.
        
        When a build/deploy fails, the Architect analyzes the error and generates
        a fixed manifest. This loop repeats up to MAX_RETRIES times.
        
        Flow: Draft → Build → [Fail → Heal → Retry] → Deploy → Publish
        
        Args:
            mission_id: The UUID of the mission.
            prompt: The voice memo.
            deploy: Whether to deploy to Vercel.
            publish: Whether to publish to GitHub after successful build.
        """
        progress: Optional[ProgressTracker] = None
        
        try:
            # Phase 1: Initial Architecting (with progress tracking)
            console.print(f"[cyan][Mission {mission_id[:8]}] Drafting blueprint...[/cyan]")
            update_mission_status(
                mission_id, 
                "ARCHITECTING",
                "Drafting blueprint. Stand by."
            )
            
            progress = ProgressTracker(mission_id, "ARCHITECTING").start()
            architect = self._get_architect()
            manifest = architect.draft_blueprint(prompt)
            progress.stop()
            
            # Phase 2: Policy Check
            console.print(f"[cyan][Mission {mission_id[:8]}] Policy check...[/cyan]")
            update_mission_status(
                mission_id,
                "VALIDATING",
                "Running security check."
            )
            
            self._policy.validate(manifest)
            
            # Phase 3: Build + Deploy with UNIFIED Self-Healing Loop
            # This loop heals BOTH audit failures AND deployment failures
            attempt = 0
            mission_complete = False
            result = None
            deploy_url = None
            
            while attempt < MAX_RETRIES and not mission_complete:
                attempt += 1
                
                console.print(f"[cyan][Mission {mission_id[:8]}] Building Pod (attempt {attempt}/{MAX_RETRIES})...[/cyan]")
                update_mission_status(
                    mission_id,
                    "BUILDING",
                    f"Building {manifest.project_name}. Attempt {attempt} of {MAX_RETRIES}."
                )
                
                # Start progress tracker for building
                progress = ProgressTracker(mission_id, "BUILDING").start()
                
                try:
                    result = self._foundry.build(manifest, mission_id, deploy=deploy)
                    progress.stop()
                    console.print(f"[green][Mission {mission_id[:8]}] Build PASSED on attempt {attempt}[/green]")
                    
                    # Deployment is part of build result
                    deploy_url = result.deploy_url if result else None
                    
                    # If we got here without errors, mission is complete
                    mission_complete = True
                    
                except AuditFailedError as e:
                    progress.stop()
                    console.print(f"[yellow][Mission {mission_id[:8]}] Audit failed on attempt {attempt}[/yellow]")
                    
                    if attempt < MAX_RETRIES:
                        self._heal_and_retry(mission_id, architect, manifest, e.output, attempt, "Audit")
                        manifest = architect.heal_blueprint(manifest, e.output)
                    else:
                        console.print(f"[red][Mission {mission_id[:8]}] Self-repair exhausted[/red]")
                
                except DeploymentError as e:
                    progress.stop()
                    console.print(f"[yellow][Mission {mission_id[:8]}] Deployment failed on attempt {attempt}[/yellow]")
                    
                    if attempt < MAX_RETRIES:
                        # Self-heal deployment errors (fix vercel.json, etc.)
                        error_context = f"Vercel deployment failed: {str(e)}"
                        self._heal_and_retry(mission_id, architect, manifest, error_context, attempt, "Deploy")
                        
                        try:
                            manifest = architect.heal_blueprint(manifest, error_context)
                            console.print(f"[cyan][Mission {mission_id[:8]}] Deployment fix received, retrying...[/cyan]")
                        except ArchitectError:
                            console.print(f"[red][Mission {mission_id[:8]}] Deployment self-repair failed[/red]")
                    else:
                        console.print(f"[red][Mission {mission_id[:8]}] Deployment self-repair exhausted[/red]")
            
            # Check if mission ultimately succeeded
            if not mission_complete:
                update_mission_status(
                    mission_id,
                    "FAILED",
                    f"Mission failed. Self-repair exhausted after {MAX_RETRIES} attempts."
                )
                return
            
            # Phase 4: Publishing via Pull Request (if configured and not skipped)
            pr_url = None
            should_skip = SKIP_PUBLISH or not publish
            if should_skip:
                skip_reason = "GANTRY_SKIP_PUBLISH=true" if SKIP_PUBLISH else "publish=false"
                console.print(f"[yellow][Mission {mission_id[:8]}] Publishing skipped ({skip_reason})[/yellow]")
            elif self._publisher.is_configured():
                console.print(f"[cyan][Mission {mission_id[:8]}] Opening Pull Request...[/cyan]")
                update_mission_status(
                    mission_id,
                    "PUBLISHING",
                    "Build passed. Opening Pull Request."
                )
                
                progress = ProgressTracker(mission_id, "PUBLISHING").start()
                evidence_path = MISSIONS_DIR / mission_id
                try:
                    pr_url = self._publisher.publish_mission(
                        manifest, 
                        str(evidence_path),
                        mission_id=mission_id
                    )
                except Exception as pub_err:
                    progress.stop()
                    # Log detailed error but don't fail the whole mission
                    console.print(f"[red][Mission {mission_id[:8]}] Publishing error: {pub_err}[/red]")
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")
                    # Continue without PR - build still succeeded
                    pr_url = None
                progress.stop()
            
            # Determine final status and speech
            if deploy_url and pr_url:
                # Full success: Vercel deployment + PR opened
                console.print(f"[green][Mission {mission_id[:8]}] LIVE + PR: {pr_url}[/green]")
                update_mission_status(
                    mission_id,
                    "DEPLOYED",
                    f"Gantry successful. Live at {deploy_url}. PR opened for review."
                )
            elif deploy_url:
                # Vercel only (no GitHub)
                console.print(f"[green][Mission {mission_id[:8]}] LIVE: {deploy_url}[/green]")
                update_mission_status(
                    mission_id,
                    "DEPLOYED",
                    f"Gantry successful. Live at {deploy_url}"
                )
            elif pr_url:
                # PR only (no Vercel)
                console.print(f"[green][Mission {mission_id[:8]}] PR OPENED[/green]")
                update_mission_status(
                    mission_id,
                    "PR_OPENED",
                    f"Gantry successful. Pull Request opened for your review."
                )
            else:
                # Success without any publishing
                console.print(f"[green][Mission {mission_id[:8]}] COMPLETE[/green]")
                update_mission_status(
                    mission_id,
                    "SUCCESS",
                    "Gantry successful. Build verified."
                )
            
        except ArchitectError:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Architect failed[/red]")
            update_mission_status(
                mission_id,
                "FAILED",
                "Mission aborted. Blueprint generation failed."
            )
            
        except SecurityViolation:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Policy violation[/red]")
            update_mission_status(
                mission_id,
                "BLOCKED",
                "Request denied. Policy violation."
            )
            
        except BuildTimeoutError:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Timeout[/red]")
            update_mission_status(
                mission_id,
                "TIMEOUT",
                "Mission aborted. Dead man's switch triggered."
            )
            
        except SecurityBlock as e:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Security block: {e}[/red]")
            update_mission_status(
                mission_id,
                "BLOCKED",
                "Publishing blocked. Green-only rule violation."
            )
            
        except PublishError as e:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Publish failed: {e}[/red]")
            update_mission_status(
                mission_id,
                "PUBLISH_FAILED",
                "Build passed but GitHub push failed."
            )
            
        except Exception as e:
            if progress:
                progress.stop()
            # Log FULL traceback for debugging
            console.print(f"[red][Mission {mission_id[:8]}] Critical error: {e}[/red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            update_mission_status(
                mission_id,
                "CRITICAL_FAILURE",
                f"Mission aborted. Error: {str(e)[:100]}"
            )
