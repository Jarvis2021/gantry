# -----------------------------------------------------------------------------
# THE FLEET MANAGER - ORCHESTRATOR
# -----------------------------------------------------------------------------
# Responsibility: Orchestrates the complete mission pipeline.
# Connects: Database -> Architect -> Policy -> Foundry
#
# Thread-based concurrency: Each mission runs in its own thread.
# Audio-first: Every outcome has a speech field for TTS.
# -----------------------------------------------------------------------------

import threading
from typing import Optional

from rich.console import Console

from src.core.architect import Architect, ArchitectError
from src.core.db import create_mission, update_mission_status, init_db
from src.core.foundry import Foundry, AuditFailedError, BuildTimeoutError, MISSIONS_DIR
from src.core.policy import PolicyGate, SecurityViolation
from src.core.publisher import Publisher, SecurityBlock, PublishError

console = Console()


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

    def dispatch_mission(self, prompt: str) -> str:
        """
        Dispatch a new mission.
        
        Creates DB entry (PENDING) and spawns background thread.
        Returns immediately with mission ID.
        
        Args:
            prompt: The voice memo / build request.
            
        Returns:
            Mission ID for tracking.
        """
        # Create DB entry
        mission_id = create_mission(prompt)
        
        console.print(f"[cyan][FLEET] Mission queued: {mission_id[:8]}[/cyan]")
        
        # Spawn background thread
        thread = threading.Thread(
            target=self._run_mission,
            args=(mission_id, prompt),
            name=f"mission-{mission_id[:8]}",
            daemon=True
        )
        thread.start()
        
        return mission_id

    def _run_mission(self, mission_id: str, prompt: str) -> None:
        """
        Execute the complete mission pipeline.
        
        Runs in background thread. All exceptions caught and logged.
        Updates DB with status and speech for TTS.
        
        Args:
            mission_id: The UUID of the mission.
            prompt: The voice memo.
        """
        try:
            # Phase 1: Architecting
            console.print(f"[cyan][Mission {mission_id[:8]}] Drafting blueprint...[/cyan]")
            update_mission_status(
                mission_id, 
                "ARCHITECTING",
                "Drafting blueprint. Stand by."
            )
            
            architect = self._get_architect()
            manifest = architect.draft_blueprint(prompt)
            
            # Phase 2: Policy Check
            console.print(f"[cyan][Mission {mission_id[:8]}] Policy check...[/cyan]")
            update_mission_status(
                mission_id,
                "VALIDATING",
                "Running security check."
            )
            
            self._policy.validate(manifest)
            
            # Phase 3: Building
            console.print(f"[cyan][Mission {mission_id[:8]}] Building Pod...[/cyan]")
            update_mission_status(
                mission_id,
                "BUILDING",
                f"Building {manifest.project_name}."
            )
            
            result = self._foundry.build(manifest, mission_id)
            
            # Check for live deployment URL from Vercel
            deploy_url = result.deploy_url
            
            # Phase 4: Publishing to GitHub (if configured)
            repo_url = None
            if self._publisher.is_configured():
                console.print(f"[cyan][Mission {mission_id[:8]}] Publishing to GitHub...[/cyan]")
                update_mission_status(
                    mission_id,
                    "PUBLISHING",
                    "Build passed. Pushing to GitHub."
                )
                
                evidence_path = MISSIONS_DIR / mission_id
                repo_url = self._publisher.publish_mission(manifest, str(evidence_path))
            
            # Determine final status and speech
            if deploy_url:
                # Full success: Build + Vercel deployment
                console.print(f"[green][Mission {mission_id[:8]}] LIVE: {deploy_url}[/green]")
                update_mission_status(
                    mission_id,
                    "DEPLOYED",
                    f"Gantry successful. Live at {deploy_url}"
                )
            elif repo_url:
                # Partial: Build + GitHub (no Vercel)
                console.print(f"[green][Mission {mission_id[:8]}] DEPLOYED to GitHub[/green]")
                update_mission_status(
                    mission_id,
                    "DEPLOYED",
                    f"Gantry successful. Code pushed to GitHub."
                )
            else:
                # Success without any publishing
                console.print(f"[green][Mission {mission_id[:8]}] COMPLETE[/green]")
                update_mission_status(
                    mission_id,
                    "SUCCESS",
                    "Gantry successful. Build verified."
                )
            
        except ArchitectError as e:
            console.print(f"[red][Mission {mission_id[:8]}] Architect failed[/red]")
            update_mission_status(
                mission_id,
                "FAILED",
                "Mission aborted. Blueprint generation failed."
            )
            
        except SecurityViolation as e:
            console.print(f"[red][Mission {mission_id[:8]}] Policy violation[/red]")
            update_mission_status(
                mission_id,
                "BLOCKED",
                "Request denied. Policy violation."
            )
            
        except AuditFailedError as e:
            console.print(f"[red][Mission {mission_id[:8]}] Audit failed[/red]")
            update_mission_status(
                mission_id,
                "FAILED",
                "Mission aborted. Check black box."
            )
            
        except BuildTimeoutError:
            console.print(f"[red][Mission {mission_id[:8]}] Timeout[/red]")
            update_mission_status(
                mission_id,
                "TIMEOUT",
                "Mission aborted. Dead man's switch triggered."
            )
            
        except SecurityBlock as e:
            console.print(f"[red][Mission {mission_id[:8]}] Security block: {e}[/red]")
            update_mission_status(
                mission_id,
                "BLOCKED",
                "Publishing blocked. Green-only rule violation."
            )
            
        except PublishError as e:
            console.print(f"[red][Mission {mission_id[:8]}] Publish failed: {e}[/red]")
            update_mission_status(
                mission_id,
                "PUBLISH_FAILED",
                "Build passed but GitHub push failed."
            )
            
        except Exception as e:
            console.print(f"[red][Mission {mission_id[:8]}] Critical error: {e}[/red]")
            update_mission_status(
                mission_id,
                "CRITICAL_FAILURE",
                "Mission aborted. System error."
            )
