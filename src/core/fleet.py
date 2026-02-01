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
from datetime import datetime, timezone

# For Python 3.11+ compatibility, keep using timezone.utc instead of datetime.UTC
from rich.console import Console

from src.core.architect import Architect, ArchitectError
from src.core.consultant import Consultant, ConsultantResponse
from src.core.db import (
    append_to_conversation,
    clear_all_missions,
    clear_pending_question,
    create_consultation,
    create_mission,
    find_missions_by_prompt_hint,
    get_active_consultation,
    get_mission,
    init_db,
    list_missions,
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


# In-progress statuses (build is still running)
IN_PROGRESS_STATUSES = frozenset(
    {
        "PENDING",
        "READY_TO_BUILD",
        "ARCHITECTING",
        "VALIDATING",
        "BUILDING",
        "HEALING",
        "DEPLOYING",
        "PUBLISHING",
    }
)

# Human-readable stage labels for status responses
STATUS_STAGE_LABELS = {
    "PENDING": "Queued",
    "READY_TO_BUILD": "Ready to build",
    "CONSULTING": "In consultation",
    "AWAITING_INPUT": "Waiting for your confirmation",
    "ARCHITECTING": "Drafting blueprint",
    "VALIDATING": "Running security check",
    "BUILDING": "Building and running tests",
    "HEALING": "Self-healing (fixing issues)",
    "DEPLOYING": "Deploying to Vercel",
    "PUBLISHING": "Opening Pull Request",
    "DEPLOYED": "Live",
    "SUCCESS": "Complete",
    "PR_OPENED": "PR opened for review",
    "BLOCKED": "Blocked",
    "FAILED": "Failed",
    "TIMEOUT": "Timed out",
    "PUBLISH_FAILED": "Publish failed",
}

# Rough ETA / context per stage (for TTS/speech)
STATUS_ETA_HINTS = {
    "ARCHITECTING": "Usually 20–40 seconds for this step.",
    "VALIDATING": "A few seconds.",
    "BUILDING": "Typically 30–90 seconds.",
    "HEALING": "May take another 30–60 seconds per attempt.",
    "DEPLOYING": "Usually 15–30 seconds.",
    "PUBLISHING": "Usually 10–20 seconds.",
    "PENDING": "Build will start shortly.",
    "READY_TO_BUILD": "Build will start when triggered.",
}


def _is_clear_projects_intent(text: str) -> bool:
    """Return True if the message is a request to clear all projects from the database."""
    if not text or len(text.strip()) < 4:
        return False
    t = text.strip().lower()
    phrases = (
        "clear (all )?projects",
        "clear the (projects )?list",
        "clear (the )?database",
        "clear everything",
        "clear all",
        "clear projects",
        "clear missions",
    )
    return any(re.search(p, t) for p in phrases)


def _resolve_clear_projects_intent(user_input: str) -> dict | None:
    """
    If the user is asking to clear all projects, run clear_all_missions() and return
    a response. Otherwise return None.
    """
    if not _is_clear_projects_intent(user_input):
        return None
    try:
        n = clear_all_missions()
        return {
            "status": "STATUS_RESPONSE",
            "speech": f"Cleared {n} projects from the database. Click Refresh in the Projects panel to see the empty list.",
            "cleared": n,
        }
    except Exception as e:
        console.print(f"[red][FLEET] Clear projects failed: {e}[/red]")
        return {
            "status": "error",
            "speech": f"Could not clear projects: {e}. Try the Clear all button in the Projects panel, or run: python scripts/clear_missions.py",
        }


def _is_status_query(text: str) -> bool:
    """Return True if the message looks like a request for build status."""
    if not text or len(text.strip()) < 3:
        return False
    t = text.strip().lower()
    patterns = (
        "status",
        "how is",
        "how's",
        "how are",
        "how're",
        "what is the status",
        "what's the status",
        "whats the status",
        "is it done",
        "is it ready",
        "is it complete",
        "is it finished",
        "progress",
        "how long",
        "when will",
        "how much longer",
        "stauts",
        "statut",
        "statue ",  # common typos
    )
    return any(p in t for p in patterns)


def _extract_project_hint(text: str) -> str | None:
    """Extract a project/app hint from a status question for matching missions."""
    if not text or len(text.strip()) < 3:
        return None
    t = text.strip()
    # Remove common question prefixes (case-insensitive); include typo "stauts"
    prefixes = (
        r"what\s+is\s+the\s+sta(?:tu)?ts?\s+of\s+",
        r"what's\s+the\s+status\s+of\s+",
        r"whats\s+the\s+status\s+of\s+",
        r"how\s+is\s+(?:the\s+)?",
        r"how's\s+(?:the\s+)?",
        r"status\s+of\s+(?:the\s+)?",
        r"progress\s+of\s+(?:the\s+)?",
        r"how\s+is\s+(?:the\s+)?build\s+for\s+",
        r"is\s+(?:the\s+)?",
        r"when\s+will\s+(?:the\s+)?",
    )
    hint = t
    for p in prefixes:
        m = re.match(p, hint, re.IGNORECASE)
        if m:
            hint = hint[m.end() :].strip()
            break
    # Fallback: "X of Y" -> use Y (e.g. "what is the stauts of Linkedin website?" -> "Linkedin website")
    if len(hint) > 30 and " of " in hint:
        hint = hint.split(" of ", 1)[-1].strip()
    # Remove trailing question words
    hint = re.sub(r"\s*(?:\?|\.|!)\s*$", "", hint)
    generic = ("it", "that", "this", "build", "app", "build going", "going", "the build")
    if not hint or len(hint) < 2 or hint.lower() in generic or hint.lower().startswith("build "):
        return None
    return hint


def _format_status_stage(status: str) -> str:
    """Return human-readable stage label for a status."""
    return STATUS_STAGE_LABELS.get(status, status.replace("_", " ").title())


def _format_typical_eta(status: str) -> str:
    """Return rough ETA hint for in-progress status."""
    return STATUS_ETA_HINTS.get(status, "Builds usually take 1–3 minutes total.")


def _elapsed_seconds(created_at: str | None) -> int | None:
    """Return seconds since created_at, or None if not parseable."""
    if not created_at:
        return None
    try:
        # ISO format with or without Z
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - dt).total_seconds())
    except (ValueError, TypeError):
        return None


def _resolve_status_query(user_input: str) -> dict | None:
    """
    If the user is asking for build status, look up the matching mission and return
    a clear status response (stage, elapsed, ETA). Otherwise return None.
    """
    if not _is_status_query(user_input):
        return None

    hint = _extract_project_hint(user_input)
    missions = find_missions_by_prompt_hint(hint, limit=15) if hint else list_missions(limit=20)

    if not missions:
        return {
            "status": "STATUS_RESPONSE",
            "speech": "I don't see any build matching that. Start one from the chat or check the Projects panel.",
            "mission_id": None,
        }

    # Prefer in-progress build when user asks about status
    in_progress = [m for m in missions if m.status in IN_PROGRESS_STATUSES]
    mission = in_progress[0] if in_progress else missions[0]

    stage = _format_status_stage(mission.status)
    elapsed = _elapsed_seconds(mission.created_at)
    eta_text = _format_typical_eta(mission.status) if mission.status in IN_PROGRESS_STATUSES else ""

    # Friendly project label: use design_target (e.g. LINKEDIN -> "LinkedIn") or truncated prompt
    if getattr(mission, "design_target", None):
        project_label = mission.design_target.replace("_", " ").title()
    else:
        project_label = (mission.prompt[:40] + "…") if len(mission.prompt) > 40 else mission.prompt

    if mission.status in IN_PROGRESS_STATUSES:
        elapsed_part = f" In progress for {elapsed} seconds." if elapsed is not None else ""
        speech = (
            f'The build for "{project_label}" is currently {stage}. '
            f"{mission.speech_output or stage}.{elapsed_part} {eta_text}"
        ).strip()
    elif mission.status in ("DEPLOYED", "SUCCESS", "PR_OPENED"):
        speech = (
            f'The build for "{project_label}" is complete. '
            f"{mission.speech_output or 'Live and PR opened.'}"
        )
    else:
        speech = f'The build for "{project_label}" is {stage}. {mission.speech_output or stage}.'

    return {
        "status": "STATUS_RESPONSE",
        "speech": speech,
        "mission_id": mission.id,
        "stage": stage,
        "mission_status": mission.status,
        "elapsed_seconds": elapsed,
        "project_label": project_label,
    }


# Check if publishing should be skipped (for tests/CI)
SKIP_PUBLISH = os.getenv("GANTRY_SKIP_PUBLISH", "").lower() == "true"

# Self-Healing Configuration
MAX_RETRIES = 3  # Maximum heal attempts before giving up

# Progress Update Interval
PROGRESS_UPDATE_SECONDS = 5

# Resource Protection (prevents server exhaustion)
MAX_CONCURRENT_MISSIONS = 3  # Maximum parallel builds
MISSION_TIMEOUT_SECONDS = 600  # 10 minutes max per mission (including all retries)


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

    def __enter__(self) -> "ProgressTracker":
        """Context manager entry - start tracking."""
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - always stop tracking (prevents thread leak)."""
        self.stop()


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

        # Resource protection: limit concurrent missions to prevent server exhaustion
        self._mission_semaphore = threading.Semaphore(MAX_CONCURRENT_MISSIONS)
        self._active_missions: dict[str, float] = {}  # mission_id -> start_time

        console.print(
            f"[green][FLEET] Fleet Manager online (V6.5, max {MAX_CONCURRENT_MISSIONS} concurrent)[/green]"
        )

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

        # If user is asking to clear projects, do it and return (don't send to Consultant)
        clear_response = _resolve_clear_projects_intent(user_input)
        if clear_response is not None:
            console.print("[cyan][FLEET] Clear projects intent; clearing DB.[/cyan]")
            return clear_response

        # If user is asking for build status, answer from DB instead of Consultant
        status_response = _resolve_status_query(user_input)
        if status_response is not None:
            console.print("[cyan][FLEET] Status query detected; returning build status.[/cyan]")
            return status_response

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

    def retry_failed_mission(
        self,
        mission_id: str,
        deploy: bool = True,
        publish: bool = True,
    ) -> dict:
        """
        Re-run a failed mission from scratch (new blueprint, full self-healing again).

        Only missions with status FAILED, BLOCKED, TIMEOUT, or PUBLISH_FAILED can be retried.
        Runs in background thread; returns immediately with status BUILDING.
        """
        mission = get_mission(mission_id)
        if not mission:
            return {
                "status": "error",
                "speech": "Mission not found.",
                "mission_id": mission_id,
            }
        retryable = {"FAILED", "BLOCKED", "TIMEOUT", "PUBLISH_FAILED"}
        if mission.status not in retryable:
            return {
                "status": "error",
                "speech": f"Cannot retry: mission is {mission.status}. Only failed or blocked missions can be retried.",
                "mission_id": mission_id,
            }
        prompt = mission.prompt
        design_target = getattr(mission, "design_target", None) or None
        update_mission_status(
            mission_id,
            "BUILDING",
            "Retrying build from scratch. Drafting new blueprint.",
        )
        thread = threading.Thread(
            target=self._run_mission_with_target,
            args=(mission_id, prompt, design_target, deploy, publish),
            name=f"retry-{mission_id[:8]}",
            daemon=True,
        )
        thread.start()
        return {
            "status": "BUILDING",
            "speech": "Retrying build. Watch the Projects panel for progress.",
            "mission_id": mission_id,
        }

    def clear_projects(self) -> int:
        """Clear all missions from the database. Returns number cleared."""
        return clear_all_missions()

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
        Protected by semaphore to limit concurrent builds.
        Has overall mission timeout to prevent runaway builds.
        """
        # Acquire semaphore (blocks if MAX_CONCURRENT_MISSIONS already running)
        acquired = self._mission_semaphore.acquire(timeout=60)
        if not acquired:
            console.print(f"[red][Mission {mission_id[:8]}] Queue full, try again later[/red]")
            update_mission_status(
                mission_id, "FAILED", "Server busy. Too many concurrent builds. Try again later."
            )
            return

        # Track mission start time for overall timeout
        mission_start = time.time()
        self._active_missions[mission_id] = mission_start

        try:
            # Phase 1: Architecting with design target
            console.print(f"[cyan][Mission {mission_id[:8]}] Drafting blueprint...[/cyan]")
            update_mission_status(
                mission_id,
                "ARCHITECTING",
                f"Drafting {design_target or 'custom'} blueprint. Stand by.",
            )

            with ProgressTracker(mission_id, "ARCHITECTING"):
                architect = self._get_architect()
                # V6.5: Pass design target for clone protocol
                manifest = architect.draft_blueprint(prompt, design_target=design_target)

            # Check mission timeout before continuing
            if time.time() - mission_start > MISSION_TIMEOUT_SECONDS:
                raise BuildTimeoutError(f"Mission timeout exceeded ({MISSION_TIMEOUT_SECONDS}s)")

            # Continue with existing build pipeline (same as _run_mission)
            self._execute_build_pipeline(mission_id, manifest, deploy, publish, mission_start)

        except ArchitectError:
            console.print(f"[red][Mission {mission_id[:8]}] Architect failed[/red]")
            update_mission_status(
                mission_id, "FAILED", "Mission aborted. Blueprint generation failed."
            )
        except BuildTimeoutError as e:
            console.print(f"[red][Mission {mission_id[:8]}] Mission timeout: {e}[/red]")
            update_mission_status(
                mission_id, "TIMEOUT", f"Mission exceeded {MISSION_TIMEOUT_SECONDS}s limit."
            )
        except Exception as e:
            console.print(f"[red][Mission {mission_id[:8]}] Error: {e}[/red]")
            update_mission_status(mission_id, "FAILED", f"Mission aborted. Error: {str(e)[:100]}")
        finally:
            # Always release semaphore and clean up
            self._active_missions.pop(mission_id, None)
            self._mission_semaphore.release()
            console.print(f"[dim][Mission {mission_id[:8]}] Slot released[/dim]")

    def _execute_build_pipeline(
        self,
        mission_id: str,
        manifest,
        deploy: bool,
        publish: bool,
        mission_start: float,
    ) -> None:
        """
        Execute the build/deploy/publish pipeline.

        Extracted from _run_mission to avoid code duplication.
        Uses context managers for ProgressTracker to prevent thread leaks.
        Checks mission timeout to prevent runaway builds.
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
                # Check mission timeout before each attempt
                elapsed = time.time() - mission_start
                if elapsed > MISSION_TIMEOUT_SECONDS:
                    raise BuildTimeoutError(
                        f"Mission timeout ({int(elapsed)}s > {MISSION_TIMEOUT_SECONDS}s limit)"
                    )

                attempt += 1
                console.print(
                    f"[cyan][Mission {mission_id[:8]}] Building (attempt {attempt})...[/cyan]"
                )
                update_mission_status(
                    mission_id,
                    "BUILDING",
                    f"Building {manifest.project_name}. Attempt {attempt}.",
                )

                # Use context manager to ensure tracker is always stopped
                with ProgressTracker(mission_id, "BUILDING"):
                    try:
                        result = self._foundry.build(manifest, mission_id, deploy=deploy)
                        console.print(f"[green][Mission {mission_id[:8]}] Build PASSED[/green]")
                        deploy_url = result.deploy_url if result else None
                        mission_complete = True

                    except AuditFailedError as e:
                        if attempt < MAX_RETRIES:
                            self._heal_and_retry(
                                mission_id, architect, manifest, e.output, attempt, "Audit"
                            )
                            manifest = architect.heal_blueprint(manifest, e.output)
                        else:
                            console.print(f"[red][Mission {mission_id[:8]}] Exhausted[/red]")

                    except DeploymentError as e:
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

                    except BuildTimeoutError:
                        # Re-raise to outer handler
                        raise

                    except Exception:
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

                with ProgressTracker(mission_id, "PUBLISHING"):
                    evidence_path = MISSIONS_DIR / mission_id
                    try:
                        pr_url = self._publisher.publish_mission(
                            manifest, str(evidence_path), mission_id=mission_id
                        )
                    except Exception as pub_err:
                        console.print(f"[red]Publishing error: {pub_err}[/red]")

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
            update_mission_status(mission_id, "BLOCKED", "Policy violation.")

        except BuildTimeoutError:
            update_mission_status(mission_id, "TIMEOUT", "Build or mission timeout exceeded.")

        except SecurityBlock:
            update_mission_status(mission_id, "BLOCKED", "Green-only rule violation.")

        except PublishError:
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

        Protected by semaphore to limit concurrent builds.
        Has overall mission timeout to prevent runaway builds.

        Args:
            mission_id: The UUID of the mission.
            prompt: The voice memo.
            deploy: Whether to deploy to Vercel.
            publish: Whether to publish to GitHub after successful build.
        """
        import traceback

        # Acquire semaphore (blocks if MAX_CONCURRENT_MISSIONS already running)
        acquired = self._mission_semaphore.acquire(timeout=60)
        if not acquired:
            console.print(f"[red][Mission {mission_id[:8]}] Queue full, try again later[/red]")
            update_mission_status(
                mission_id, "FAILED", "Server busy. Too many concurrent builds. Try again later."
            )
            return

        # Track mission start time for overall timeout
        mission_start = time.time()
        self._active_missions[mission_id] = mission_start

        try:
            # Phase 1: Initial Architecting (with progress tracking)
            console.print(f"[cyan][Mission {mission_id[:8]}] Drafting blueprint...[/cyan]")
            update_mission_status(mission_id, "ARCHITECTING", "Drafting blueprint. Stand by.")

            with ProgressTracker(mission_id, "ARCHITECTING"):
                architect = self._get_architect()
                manifest = architect.draft_blueprint(prompt)

            # Check mission timeout before continuing
            if time.time() - mission_start > MISSION_TIMEOUT_SECONDS:
                raise BuildTimeoutError(f"Mission timeout exceeded ({MISSION_TIMEOUT_SECONDS}s)")

            # Delegate to shared build pipeline
            self._execute_build_pipeline(mission_id, manifest, deploy, publish, mission_start)

        except ArchitectError:
            console.print(f"[red][Mission {mission_id[:8]}] Architect failed[/red]")
            update_mission_status(
                mission_id, "FAILED", "Mission aborted. Blueprint generation failed."
            )

        except SecurityViolation:
            console.print(f"[red][Mission {mission_id[:8]}] Policy violation[/red]")
            update_mission_status(mission_id, "BLOCKED", "Request denied. Policy violation.")

        except BuildTimeoutError as e:
            console.print(f"[red][Mission {mission_id[:8]}] Timeout: {e}[/red]")
            update_mission_status(
                mission_id, "TIMEOUT", f"Mission exceeded {MISSION_TIMEOUT_SECONDS}s limit."
            )

        except SecurityBlock as e:
            console.print(f"[red][Mission {mission_id[:8]}] Security block: {e}[/red]")
            update_mission_status(
                mission_id, "BLOCKED", "Publishing blocked. Green-only rule violation."
            )

        except PublishError as e:
            console.print(f"[red][Mission {mission_id[:8]}] Publish failed: {e}[/red]")
            update_mission_status(
                mission_id, "PUBLISH_FAILED", "Build passed but GitHub push failed."
            )

        except Exception as e:
            console.print(f"[red][Mission {mission_id[:8]}] Critical error: {e}[/red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            update_mission_status(
                mission_id, "CRITICAL_FAILURE", f"Mission aborted. Error: {str(e)[:100]}"
            )

        finally:
            # Always release semaphore and clean up
            self._active_missions.pop(mission_id, None)
            self._mission_semaphore.release()
            console.print(f"[dim][Mission {mission_id[:8]}] Slot released[/dim]")
