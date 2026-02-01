# -----------------------------------------------------------------------------
# THE FLEET MANAGER - ORCHESTRATOR (Self-Healing + V6.5 Consultation Loop)
# -----------------------------------------------------------------------------
# Responsibility: Orchestrates the complete mission pipeline with self-repair.
# Connects: Database -> Consultant -> Architect -> Policy -> Foundry -> Deploy
#
# V6.5 UPGRADE: The Consultation Loop
# Old Flow: Voice -> Build
# New Flow: Voice -> CTO Proposal -> User Feedback -> Final Spec -> "Proceed" -> Build
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

import base64
import os
import re
import threading
import time

from rich.console import Console

from src.core.architect import Architect, ArchitectError
from src.core.consultant import Consultant, ConsultantResponse
from src.core.db import (
    append_to_conversation,
    clear_pending_question,
    create_consultation,
    create_mission,
    get_active_consultation,
    get_mission,
    init_db,
    mark_ready_to_build,
    set_design_target,
    set_pending_question,
    update_mission_status,
)
from src.core.deployer import DeploymentError
from src.core.foundry import MISSIONS_DIR, AuditFailedError, BuildTimeoutError, Foundry
from src.core.policy import PolicyGate, SecurityViolation
from src.core.publisher import Publisher, PublishError, SecurityBlock

console = Console()

# Design reference image filename in mission folder and in built repo
DESIGN_REFERENCE_NAME = "design-reference"


def _save_design_image(mission_id: str, image_base64: str, image_filename: str) -> str | None:
    """
    Save uploaded design image to mission folder so it can be included in the built repo.

    Args:
        mission_id: Mission/consultation ID.
        image_base64: Base64-encoded image (with or without data URL prefix).
        image_filename: Original filename (e.g. mockup.png).

    Returns:
        Path to saved file relative to mission folder, or None on failure.
    """
    if not image_base64 or not image_filename:
        return None
    try:
        # Strip data URL prefix if present (e.g. data:image/png;base64,)
        raw = image_base64.strip()
        if raw.startswith("data:"):
            match = re.match(r"data:image/([^;]+);base64,", raw)
            ext = match.group(1).lower() if match else "png"
            raw = raw.split(",", 1)[1]
        else:
            ext = "png"
            for suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                if image_filename.lower().endswith(suffix):
                    ext = suffix.lstrip(".").lower()
                    break
        data = base64.b64decode(raw)
        mission_folder = MISSIONS_DIR / mission_id
        mission_folder.mkdir(parents=True, exist_ok=True)
        out_name = f"{DESIGN_REFERENCE_NAME}.{ext}"
        out_path = mission_folder / out_name
        out_path.write_bytes(data)
        console.print(f"[cyan][FLEET] Design image saved: {out_name}[/cyan]")
        return out_name
    except Exception as e:
        console.print(f"[yellow][FLEET] Could not save design image: {e}[/yellow]")
        return None


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
        self._thread: threading.Thread | None = None

    def _update_loop(self) -> None:
        """Background loop to push progress updates."""
        while not self._stop_event.wait(PROGRESS_UPDATE_SECONDS):
            elapsed = int(time.time() - self.start_time)
            update_mission_status(
                self.mission_id, self.phase, f"{self.phase}... ({elapsed}s elapsed)"
            )
            console.print(f"[dim][PROGRESS] {self.phase} - {elapsed}s elapsed[/dim]")

    def start(self) -> "ProgressTracker":
        """Start the progress tracker."""
        self._thread = threading.Thread(
            target=self._update_loop, daemon=True, name=f"progress-{self.mission_id[:8]}"
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

    V6.5 Pipeline: Voice -> Consult -> Confirm -> Build -> Deploy

    Old Pipeline: Voice Memo -> DB -> Architect -> Policy -> Foundry -> DB -> TTS
    New Pipeline: Voice -> Consultant -> [Loop] -> Architect -> Policy -> Foundry -> DB -> TTS

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
        self._architect: Architect | None = None
        self._consultant: Consultant | None = None  # V6.5

        console.print("[green][FLEET] Fleet Manager online (V6.5 Consultation Mode)[/green]")

    def _get_consultant(self) -> Consultant:
        """Lazy init Consultant (requires AWS creds)."""
        if self._consultant is None:
            self._consultant = Consultant()
        return self._consultant

    # =========================================================================
    # V6.5: CONSULTATION LOOP METHODS
    # =========================================================================

    def process_voice_input(
        self,
        user_input: str,
        deploy: bool = True,
        publish: bool = True,
        image_base64: str | None = None,
        image_filename: str | None = None,
    ) -> dict:
        """
        Process voice/chat input through the Consultation Loop.

        This is the V6.5 entry point that replaces direct dispatch_mission calls.

        Flow:
        1. Check if there's an active consultation (pending question)
        2. If yes: This input is the ANSWER, continue conversation
        3. If no: This is a NEW REQUEST, start consultation
        4. If consultant says READY_TO_BUILD: Trigger build
        5. Uploaded image is saved to mission folder and included in built repo.

        Args:
            user_input: The voice memo or chat message.
            deploy: Whether to deploy to Vercel.
            publish: Whether to publish to GitHub.
            image_base64: Optional base64-encoded design image (mockup/screenshot).
            image_filename: Optional original filename for the image.

        Returns:
            dict with:
            - status: CONSULTING | AWAITING_INPUT | BUILDING | etc.
            - speech: TTS-friendly response
            - mission_id: The consultation/mission ID
            - question: Optional question for user (if AWAITING_INPUT)
        """
        console.print(f"[cyan][FLEET] Processing: {user_input[:50]}...[/cyan]")

        # Check for active consultation
        active = get_active_consultation()

        if active and active.pending_question:
            # This is an ANSWER to a pending question
            console.print(f"[cyan][FLEET] Continuing consultation: {active.id[:8]}[/cyan]")
            return self._continue_consultation(
                active.id,
                user_input,
                deploy=deploy,
                publish=publish,
                image_base64=image_base64,
                image_filename=image_filename,
            )
        else:
            # This is a NEW REQUEST
            console.print("[cyan][FLEET] Starting new consultation[/cyan]")
            return self._start_consultation(
                user_input,
                deploy=deploy,
                publish=publish,
                image_base64=image_base64,
                image_filename=image_filename,
            )

    def _start_consultation(
        self,
        prompt: str,
        deploy: bool = True,
        publish: bool = True,
        image_base64: str | None = None,
        image_filename: str | None = None,
    ) -> dict:
        """
        Start a new consultation.

        Creates a consultation record and analyzes the request.
        Saves uploaded design image to mission folder for inclusion in built repo.
        """
        # Detect design target
        from src.core.architect import detect_design_target

        design_target = detect_design_target(prompt)

        # Create consultation in DB
        mission_id = create_consultation(prompt, design_target)

        # Save uploaded design image so it is included in the built repo
        if image_base64 and image_filename:
            _save_design_image(mission_id, image_base64, image_filename)

        # Build conversation
        conversation = [{"role": "user", "content": prompt}]

        # Get consultant analysis
        consultant = self._get_consultant()
        response = consultant.analyze(conversation)

        # Update design target if detected
        if response.design_target and not design_target:
            set_design_target(mission_id, response.design_target)
            design_target = response.design_target

        return self._handle_consultant_response(
            mission_id, response, conversation, deploy=deploy, publish=publish
        )

    def _continue_consultation(
        self,
        mission_id: str,
        user_input: str,
        deploy: bool = True,
        publish: bool = True,
        image_base64: str | None = None,
        image_filename: str | None = None,
    ) -> dict:
        """
        Continue an existing consultation with user's answer.
        Saves uploaded design image to mission folder if provided.
        """
        # Get current mission state
        mission = get_mission(mission_id)
        if not mission:
            return {
                "status": "error",
                "speech": "Session not found. Please start again.",
                "mission_id": None,
            }

        # Save uploaded design image so it is included in the built repo
        if image_base64 and image_filename:
            _save_design_image(mission_id, image_base64, image_filename)

        # Clear pending question
        clear_pending_question(mission_id)

        # Append user response to history
        append_to_conversation(mission_id, "user", user_input)

        # Build conversation from history
        conversation = mission.conversation_history or []
        conversation.append({"role": "user", "content": user_input})

        # Analyze with consultant
        consultant = self._get_consultant()
        response = consultant.analyze(conversation)

        return self._handle_consultant_response(
            mission_id, response, conversation, deploy=deploy, publish=publish
        )

    def _handle_consultant_response(
        self,
        mission_id: str,
        response: ConsultantResponse,
        conversation: list[dict],
        deploy: bool = True,
        publish: bool = True,
    ) -> dict:
        """
        Handle the consultant's response and decide next step.
        """
        # Append assistant response to history
        append_to_conversation(mission_id, "assistant", response.speech)

        if response.status == "READY_TO_BUILD":
            # User confirmed - proceed to build
            console.print(f"[green][FLEET] Ready to build: {mission_id[:8]}[/green]")
            mark_ready_to_build(mission_id)

            # Get build prompt from conversation
            consultant = self._get_consultant()
            build_prompt = consultant.get_build_prompt(conversation)
            design_target = consultant.get_design_target(conversation)

            # Dispatch the actual build
            self._dispatch_build(
                mission_id, build_prompt, design_target, deploy=deploy, publish=publish
            )

            return {
                "status": "BUILDING",
                "speech": response.speech,
                "mission_id": mission_id,
                "design_target": design_target,
            }

        elif response.status in ("NEEDS_INPUT", "NEEDS_CONFIRMATION"):
            # Ask user a question
            console.print(f"[yellow][FLEET] Awaiting input: {mission_id[:8]}[/yellow]")
            set_pending_question(
                mission_id, response.question or response.speech, response.proposed_stack
            )

            return {
                "status": "AWAITING_INPUT",
                "speech": response.speech,
                "mission_id": mission_id,
                "question": response.question or response.speech,
                "proposed_stack": response.proposed_stack,
                "design_target": response.design_target,
                "features": response.features,
                "confidence": response.confidence,
            }

        else:
            # Unknown status - treat as needs input
            return {
                "status": "AWAITING_INPUT",
                "speech": response.speech,
                "mission_id": mission_id,
                "question": response.question,
            }

    def _dispatch_build(
        self,
        mission_id: str,
        prompt: str,
        design_target: str | None = None,
        deploy: bool = True,
        publish: bool = True,
    ) -> None:
        """
        Dispatch the actual build after consultation is complete.

        Runs in background thread like the original dispatch_mission.
        """
        console.print(
            f"[cyan][FLEET] Dispatching build: {mission_id[:8]} (target={design_target})[/cyan]"
        )

        # Update status
        update_mission_status(mission_id, "BUILDING", "Clone protocol initiated.")

        # Spawn background thread
        thread = threading.Thread(
            target=self._run_mission_with_target,
            args=(mission_id, prompt, design_target, deploy, publish),
            name=f"mission-{mission_id[:8]}",
            daemon=True,
        )
        thread.start()

    def _run_mission_with_target(
        self,
        mission_id: str,
        prompt: str,
        design_target: str | None = None,
        deploy: bool = True,
        publish: bool = True,
    ) -> None:
        """
        Run mission with design target injection.

        V6.5: Passes design_target to the Architect for clone protocol.
        """
        progress: ProgressTracker | None = None

        try:
            # Phase 1: Architecting with design target
            console.print(f"[cyan][Mission {mission_id[:8]}] Drafting blueprint...[/cyan]")
            update_mission_status(
                mission_id,
                "ARCHITECTING",
                f"Drafting {design_target or 'custom'} blueprint. Stand by.",
            )

            progress = ProgressTracker(mission_id, "ARCHITECTING").start()
            architect = self._get_architect()

            # V6.5: Pass design target for clone protocol
            manifest = architect.draft_blueprint(prompt, design_target=design_target)
            progress.stop()

            # Continue with existing build pipeline (same as _run_mission)
            self._execute_build_pipeline(mission_id, manifest, deploy, publish, progress)

        except ArchitectError:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Architect failed[/red]")
            update_mission_status(
                mission_id, "FAILED", "Mission aborted. Blueprint generation failed."
            )
        except Exception as e:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Error: {e}[/red]")
            update_mission_status(mission_id, "FAILED", f"Mission aborted. Error: {str(e)[:100]}")

    def _execute_build_pipeline(
        self,
        mission_id: str,
        manifest,
        deploy: bool,
        publish: bool,
        progress: "ProgressTracker | None",
    ) -> None:
        """
        Execute the build/deploy/publish pipeline.

        Extracted from _run_mission to avoid code duplication.
        """
        import traceback

        architect = self._get_architect()

        try:
            # Phase 2: Policy Check
            console.print(f"[cyan][Mission {mission_id[:8]}] Policy check...[/cyan]")
            update_mission_status(mission_id, "VALIDATING", "Running security check.")
            self._policy.validate(manifest)

            # Phase 3: Build with Self-Healing Loop
            attempt = 0
            mission_complete = False
            result = None
            deploy_url = None

            while attempt < MAX_RETRIES and not mission_complete:
                attempt += 1

                console.print(
                    f"[cyan][Mission {mission_id[:8]}] Building (attempt {attempt})...[/cyan]"
                )
                update_mission_status(
                    mission_id,
                    "BUILDING",
                    f"Building {manifest.project_name}. Attempt {attempt}.",
                )

                progress = ProgressTracker(mission_id, "BUILDING").start()

                try:
                    result = self._foundry.build(manifest, mission_id, deploy=deploy)
                    progress.stop()
                    console.print(f"[green][Mission {mission_id[:8]}] Build PASSED[/green]")
                    deploy_url = result.deploy_url if result else None
                    mission_complete = True

                except AuditFailedError as e:
                    progress.stop()
                    if attempt < MAX_RETRIES:
                        self._heal_and_retry(
                            mission_id, architect, manifest, e.output, attempt, "Audit"
                        )
                        manifest = architect.heal_blueprint(manifest, e.output)
                    else:
                        console.print(f"[red][Mission {mission_id[:8]}] Exhausted[/red]")

                except DeploymentError as e:
                    progress.stop()
                    if attempt < MAX_RETRIES:
                        error_context = f"Deployment failed: {e!s}"
                        self._heal_and_retry(
                            mission_id, architect, manifest, error_context, attempt, "Deploy"
                        )
                        try:
                            manifest = architect.heal_blueprint(manifest, error_context)
                        except ArchitectError:
                            pass
                    else:
                        console.print(f"[red][Mission {mission_id[:8]}] Exhausted[/red]")

                except Exception:
                    progress.stop()
                    if attempt < MAX_RETRIES:
                        error_trace = traceback.format_exc()
                        self._heal_and_retry(
                            mission_id, architect, manifest, error_trace, attempt, "Build"
                        )
                        try:
                            manifest = architect.heal_blueprint(manifest, error_trace)
                        except ArchitectError:
                            pass

            # Check success
            if not mission_complete:
                update_mission_status(mission_id, "FAILED", f"Failed after {MAX_RETRIES} attempts.")
                return

            # Phase 4: Publishing
            pr_url = None
            should_skip = SKIP_PUBLISH or not publish
            if not should_skip and self._publisher.is_configured():
                console.print(f"[cyan][Mission {mission_id[:8]}] Opening PR...[/cyan]")
                update_mission_status(mission_id, "PUBLISHING", "Opening Pull Request.")

                progress = ProgressTracker(mission_id, "PUBLISHING").start()
                evidence_path = MISSIONS_DIR / mission_id
                try:
                    pr_url = self._publisher.publish_mission(
                        manifest, str(evidence_path), mission_id=mission_id
                    )
                except Exception as pub_err:
                    console.print(f"[red]Publishing error: {pub_err}[/red]")
                progress.stop()

            # Final status
            if deploy_url and pr_url:
                update_mission_status(mission_id, "DEPLOYED", f"Live at {deploy_url}. PR opened.")
            elif deploy_url:
                update_mission_status(mission_id, "DEPLOYED", f"Live at {deploy_url}")
            elif pr_url:
                update_mission_status(mission_id, "PR_OPENED", "PR opened for review.")
            else:
                update_mission_status(mission_id, "SUCCESS", "Build verified.")

        except SecurityViolation:
            if progress:
                progress.stop()
            update_mission_status(mission_id, "BLOCKED", "Policy violation.")

        except BuildTimeoutError:
            if progress:
                progress.stop()
            update_mission_status(mission_id, "TIMEOUT", "Dead man's switch triggered.")

        except SecurityBlock:
            if progress:
                progress.stop()
            update_mission_status(mission_id, "BLOCKED", "Green-only rule violation.")

        except PublishError:
            if progress:
                progress.stop()
            update_mission_status(mission_id, "PUBLISH_FAILED", "GitHub push failed.")

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
        error_type: str,
    ) -> None:
        """
        Common self-healing logic for both audit and deployment failures.

        Updates mission status and logs the healing attempt.
        """
        console.print(
            f"[yellow][Mission {mission_id[:8]}] Engaging self-repair for {error_type}...[/yellow]"
        )
        update_mission_status(
            mission_id,
            "HEALING",
            f"{error_type} failed. Self-repair attempt {attempt} of {MAX_RETRIES}.",
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

        console.print(
            f"[cyan][FLEET] Mission queued: {mission_id[:8]} (deploy={deploy}, publish={publish})[/cyan]"
        )

        # Spawn background thread
        thread = threading.Thread(
            target=self._run_mission,
            args=(mission_id, prompt, deploy, publish),
            name=f"mission-{mission_id[:8]}",
            daemon=True,
        )
        thread.start()

        return mission_id

    def _run_mission(
        self, mission_id: str, prompt: str, deploy: bool = True, publish: bool = True
    ) -> None:
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
        progress: ProgressTracker | None = None

        try:
            # Phase 1: Initial Architecting (with progress tracking)
            console.print(f"[cyan][Mission {mission_id[:8]}] Drafting blueprint...[/cyan]")
            update_mission_status(mission_id, "ARCHITECTING", "Drafting blueprint. Stand by.")

            progress = ProgressTracker(mission_id, "ARCHITECTING").start()
            architect = self._get_architect()
            manifest = architect.draft_blueprint(prompt)
            progress.stop()

            # Phase 2: Policy Check
            console.print(f"[cyan][Mission {mission_id[:8]}] Policy check...[/cyan]")
            update_mission_status(mission_id, "VALIDATING", "Running security check.")

            self._policy.validate(manifest)

            # Phase 3: Build + Deploy with UNIFIED Self-Healing Loop
            # This loop heals BOTH audit failures AND deployment failures
            attempt = 0
            mission_complete = False
            result = None
            deploy_url = None

            while attempt < MAX_RETRIES and not mission_complete:
                attempt += 1

                console.print(
                    f"[cyan][Mission {mission_id[:8]}] Building Pod (attempt {attempt}/{MAX_RETRIES})...[/cyan]"
                )
                update_mission_status(
                    mission_id,
                    "BUILDING",
                    f"Building {manifest.project_name}. Attempt {attempt} of {MAX_RETRIES}.",
                )

                # Start progress tracker for building
                progress = ProgressTracker(mission_id, "BUILDING").start()

                try:
                    result = self._foundry.build(manifest, mission_id, deploy=deploy)
                    progress.stop()
                    console.print(
                        f"[green][Mission {mission_id[:8]}] Build PASSED on attempt {attempt}[/green]"
                    )

                    # Deployment is part of build result
                    deploy_url = result.deploy_url if result else None

                    # If we got here without errors, mission is complete
                    mission_complete = True

                except AuditFailedError as e:
                    progress.stop()
                    console.print(
                        f"[yellow][Mission {mission_id[:8]}] Audit failed on attempt {attempt}[/yellow]"
                    )

                    if attempt < MAX_RETRIES:
                        self._heal_and_retry(
                            mission_id, architect, manifest, e.output, attempt, "Audit"
                        )
                        manifest = architect.heal_blueprint(manifest, e.output)
                    else:
                        console.print(
                            f"[red][Mission {mission_id[:8]}] Self-repair exhausted[/red]"
                        )

                except DeploymentError as e:
                    progress.stop()
                    console.print(
                        f"[yellow][Mission {mission_id[:8]}] Deployment failed on attempt {attempt}[/yellow]"
                    )

                    if attempt < MAX_RETRIES:
                        # Self-heal deployment errors (fix vercel.json, etc.)
                        error_context = f"Vercel deployment failed: {e!s}"
                        self._heal_and_retry(
                            mission_id, architect, manifest, error_context, attempt, "Deploy"
                        )

                        try:
                            manifest = architect.heal_blueprint(manifest, error_context)
                            console.print(
                                f"[cyan][Mission {mission_id[:8]}] Deployment fix received, retrying...[/cyan]"
                            )
                        except ArchitectError:
                            console.print(
                                f"[red][Mission {mission_id[:8]}] Deployment self-repair failed[/red]"
                            )
                    else:
                        console.print(
                            f"[red][Mission {mission_id[:8]}] Deployment self-repair exhausted[/red]"
                        )

                except Exception as e:
                    # EXPANDED: Catch ALL other exceptions and attempt self-healing
                    progress.stop()
                    import traceback

                    error_trace = traceback.format_exc()
                    console.print(
                        f"[yellow][Mission {mission_id[:8]}] Unexpected error on attempt {attempt}: {e}[/yellow]"
                    )

                    if attempt < MAX_RETRIES:
                        error_context = f"Build failed with unexpected error:\n{error_trace}"
                        self._heal_and_retry(
                            mission_id, architect, manifest, error_context, attempt, "Build"
                        )

                        try:
                            manifest = architect.heal_blueprint(manifest, error_context)
                            console.print(
                                f"[cyan][Mission {mission_id[:8]}] Fix received for unexpected error, retrying...[/cyan]"
                            )
                        except ArchitectError:
                            console.print(
                                f"[red][Mission {mission_id[:8]}] Self-repair for unexpected error failed[/red]"
                            )
                    else:
                        console.print(
                            f"[red][Mission {mission_id[:8]}] Self-repair exhausted for unexpected error[/red]"
                        )

            # Check if mission ultimately succeeded
            if not mission_complete:
                update_mission_status(
                    mission_id,
                    "FAILED",
                    f"Mission failed. Self-repair exhausted after {MAX_RETRIES} attempts.",
                )
                return

            # Phase 4: Publishing via Pull Request (if configured and not skipped)
            pr_url = None
            should_skip = SKIP_PUBLISH or not publish
            if should_skip:
                skip_reason = "GANTRY_SKIP_PUBLISH=true" if SKIP_PUBLISH else "publish=false"
                console.print(
                    f"[yellow][Mission {mission_id[:8]}] Publishing skipped ({skip_reason})[/yellow]"
                )
            elif self._publisher.is_configured():
                console.print(f"[cyan][Mission {mission_id[:8]}] Opening Pull Request...[/cyan]")
                update_mission_status(
                    mission_id, "PUBLISHING", "Build passed. Opening Pull Request."
                )

                progress = ProgressTracker(mission_id, "PUBLISHING").start()
                evidence_path = MISSIONS_DIR / mission_id
                try:
                    pr_url = self._publisher.publish_mission(
                        manifest, str(evidence_path), mission_id=mission_id
                    )
                except Exception as pub_err:
                    progress.stop()
                    # Log detailed error but don't fail the whole mission
                    console.print(
                        f"[red][Mission {mission_id[:8]}] Publishing error: {pub_err}[/red]"
                    )
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
                    f"Gantry successful. Live at {deploy_url}. PR opened for review.",
                )
            elif deploy_url:
                # Vercel only (no GitHub)
                console.print(f"[green][Mission {mission_id[:8]}] LIVE: {deploy_url}[/green]")
                update_mission_status(
                    mission_id, "DEPLOYED", f"Gantry successful. Live at {deploy_url}"
                )
            elif pr_url:
                # PR only (no Vercel)
                console.print(f"[green][Mission {mission_id[:8]}] PR OPENED[/green]")
                update_mission_status(
                    mission_id,
                    "PR_OPENED",
                    "Gantry successful. Pull Request opened for your review.",
                )
            else:
                # Success without any publishing
                console.print(f"[green][Mission {mission_id[:8]}] COMPLETE[/green]")
                update_mission_status(mission_id, "SUCCESS", "Gantry successful. Build verified.")

        except ArchitectError:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Architect failed[/red]")
            update_mission_status(
                mission_id, "FAILED", "Mission aborted. Blueprint generation failed."
            )

        except SecurityViolation:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Policy violation[/red]")
            update_mission_status(mission_id, "BLOCKED", "Request denied. Policy violation.")

        except BuildTimeoutError:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Timeout[/red]")
            update_mission_status(
                mission_id, "TIMEOUT", "Mission aborted. Dead man's switch triggered."
            )

        except SecurityBlock as e:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Security block: {e}[/red]")
            update_mission_status(
                mission_id, "BLOCKED", "Publishing blocked. Green-only rule violation."
            )

        except PublishError as e:
            if progress:
                progress.stop()
            console.print(f"[red][Mission {mission_id[:8]}] Publish failed: {e}[/red]")
            update_mission_status(
                mission_id, "PUBLISH_FAILED", "Build passed but GitHub push failed."
            )

        except Exception as e:
            if progress:
                progress.stop()
            # Log FULL traceback for debugging
            console.print(f"[red][Mission {mission_id[:8]}] Critical error: {e}[/red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            update_mission_status(
                mission_id, "CRITICAL_FAILURE", f"Mission aborted. Error: {str(e)[:100]}"
            )
