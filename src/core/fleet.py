# Copyright 2026 Pramod Kumar Voola
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# -----------------------------------------------------------------------------
# THE FLEET MANAGER - ASYNC ORCHESTRATOR
# -----------------------------------------------------------------------------
# Full async implementation with consultation loop, WebSocket support,
# and production architecture patterns (structured logging, resource protection).
#
# Features:
# - Async/await throughout (non-blocking)
# - Consultation Loop (voice -> consult -> confirm -> build)
# - WebSocket real-time updates
# - Semaphore-based concurrency limiting
# - Mission timeouts and self-healing
# - Status query detection (natural language)
# - Design image upload support
# -----------------------------------------------------------------------------

import asyncio
import base64
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from rich.console import Console

from src.core.architect import Architect, ArchitectError, detect_design_target
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
    search_missions,
    set_design_target,
    set_pending_question,
    update_mission_status,
)
from src.core.deployer import DeploymentError
from src.core.foundry import MISSIONS_DIR, AuditFailedError, BuildTimeoutError, Foundry
from src.core.policy import PolicyGate, SecurityViolation
from src.core.publisher import Publisher, PublishError, SecurityBlock
from src.domain.models import GantryManifest

if TYPE_CHECKING:
    from src.main_fastapi import ConnectionManager

console = Console()

# =============================================================================
# CONFIGURATION
# =============================================================================

MAX_RETRIES = 3
SKIP_PUBLISH = os.getenv("GANTRY_SKIP_PUBLISH", "").lower() == "true"
MAX_CONCURRENT_MISSIONS = 3
MISSION_TIMEOUT_SECONDS = 600  # 10 minutes
PROGRESS_UPDATE_SECONDS = 5
DESIGN_REFERENCE_NAME = "design-reference"

# Status labels for TTS
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


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _save_design_image(mission_id: str, image_base64: str, image_filename: str) -> str | None:
    """Save uploaded design image to mission folder."""
    if not image_base64 or not image_filename:
        return None
    try:
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


def _is_clear_projects_intent(text: str) -> bool:
    """Return True if the message is a request to clear all projects."""
    if not text or len(text.strip()) < 4:
        return False
    t = text.strip().lower()
    phrases = (
        r"clear (all )?projects",
        r"clear the (projects )?list",
        r"clear (the )?database",
        r"clear everything",
        r"clear all",
        r"clear projects",
        r"clear missions",
    )
    return any(re.search(p, t) for p in phrases)


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
    )
    return any(p in t for p in patterns)


def _extract_project_hint(text: str) -> str | None:
    """Extract a project hint from a status question."""
    if not text or len(text.strip()) < 3:
        return None
    t = text.strip()
    prefixes = (
        r"what\s+is\s+the\s+status\s+of\s+",
        r"what's\s+the\s+status\s+of\s+",
        r"how\s+is\s+(?:the\s+)?",
        r"how's\s+(?:the\s+)?",
        r"status\s+of\s+(?:the\s+)?",
    )
    hint = t
    for p in prefixes:
        m = re.match(p, hint, re.IGNORECASE)
        if m:
            hint = hint[m.end() :].strip()
            break
    hint = re.sub(r"\s*(?:\?|\.|!)\s*$", "", hint)
    generic = ("it", "that", "this", "build", "app", "going", "the build")
    if not hint or len(hint) < 2 or hint.lower() in generic:
        return None
    return hint


def _elapsed_seconds(created_at: str | None) -> int | None:
    """Return seconds since created_at."""
    if not created_at:
        return None
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - dt).total_seconds())
    except (ValueError, TypeError):
        return None


# =============================================================================
# ASYNC PROGRESS TRACKER
# =============================================================================


class AsyncProgressTracker:
    """Async progress tracker with WebSocket broadcast."""

    def __init__(
        self,
        mission_id: str,
        phase: str,
        ws_manager: "ConnectionManager | None" = None,
    ) -> None:
        self.mission_id = mission_id
        self.phase = phase
        self.start_time = time.time()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._ws_manager = ws_manager

    async def _update_loop(self) -> None:
        """Background loop to push progress updates."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=PROGRESS_UPDATE_SECONDS,
                )
                break
            except TimeoutError:
                elapsed = int(time.time() - self.start_time)
                update_mission_status(
                    self.mission_id, self.phase, f"{self.phase}... ({elapsed}s elapsed)"
                )
                if self._ws_manager:
                    await self._ws_manager.broadcast(
                        self.mission_id,
                        {"type": "progress", "phase": self.phase, "elapsed": elapsed},
                    )

    def start(self) -> "AsyncProgressTracker":
        """Start the progress tracker."""
        self._task = asyncio.create_task(self._update_loop())
        return self

    async def stop(self) -> None:
        """Stop the progress tracker."""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def __aenter__(self) -> "AsyncProgressTracker":
        return self.start()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()


# =============================================================================
# FLEET MANAGER V2 (ASYNC)
# =============================================================================


class FleetManager:
    """
    The Fleet Orchestrator v2 (Async).

    Pipeline: Voice -> Consult -> Confirm -> Build -> Deploy
    All operations are async for non-blocking execution.
    WebSocket support for real-time updates.
    """

    def __init__(self, ws_manager: "ConnectionManager | None" = None) -> None:
        """Initialize the Fleet Manager."""
        init_db()

        self._foundry = Foundry()
        self._policy = PolicyGate()
        self._publisher = Publisher()
        self._architect: Architect | None = None
        self._consultant: Consultant | None = None
        self._ws_manager = ws_manager

        # Async semaphore for concurrency control
        self._mission_semaphore = asyncio.Semaphore(MAX_CONCURRENT_MISSIONS)
        self._active_missions: dict[str, float] = {}

        console.print(
            f"[green][FLEET] Fleet Manager v2 (async) online "
            f"(max {MAX_CONCURRENT_MISSIONS} concurrent)[/green]"
        )

    def _get_architect(self) -> Architect:
        """Lazy init Architect."""
        if self._architect is None:
            self._architect = Architect()
        return self._architect

    def _get_consultant(self) -> Consultant:
        """Lazy init Consultant."""
        if self._consultant is None:
            self._consultant = Consultant()
        return self._consultant

    async def _broadcast(self, mission_id: str, status: str, message: str) -> None:
        """Broadcast status update via WebSocket."""
        if self._ws_manager:
            await self._ws_manager.broadcast(
                mission_id,
                {"type": "status", "mission_id": mission_id, "status": status, "message": message},
            )

    async def _update_status(self, mission_id: str, status: str, speech: str) -> None:
        """Update mission status in DB and broadcast via WebSocket."""
        update_mission_status(mission_id, status, speech)
        await self._broadcast(mission_id, status, speech)

    def _get_friendly_error(self, error_msg: str) -> str:
        """Convert technical error messages to user-friendly explanations."""
        error_lower = error_msg.lower()

        # Pattern-based error mapping (checked in order)
        error_patterns = [
            (
                "api error 400",
                "AI model unavailable. The model may not be enabled in your AWS region.",
            ),
            ("api error 401", "Authentication failed. Please check your AWS credentials."),
            ("unauthorized", "Authentication failed. Please check your AWS credentials."),
            ("api error 403", "Access denied. You may not have permission to use this AI model."),
            ("forbidden", "Access denied. You may not have permission to use this AI model."),
            ("api error 429", "Rate limited. Too many requests - please wait and try again."),
            ("rate limit", "Rate limited. Too many requests - please wait and try again."),
            (
                "api error 5",
                "AI service temporarily unavailable. Please try again in a few minutes.",
            ),
            (
                "server error",
                "AI service temporarily unavailable. Please try again in a few minutes.",
            ),
            ("timeout", "Request timed out. The AI took too long to respond."),
            ("no valid json", "AI response was malformed. Please try again."),
            ("api_key", "API key not configured. Please set BEDROCK_API_KEY."),
            ("bedrock_api_key", "API key not configured. Please set BEDROCK_API_KEY."),
            ("connection", "Network error. Please check your internet connection."),
            ("network", "Network error. Please check your internet connection."),
        ]

        for pattern, friendly_msg in error_patterns:
            if pattern in error_lower:
                return friendly_msg

        # Special case: all tiers failed
        if "all" in error_lower and "tier" in error_lower and "failed" in error_lower:
            return "All AI models failed to generate code. Try simplifying your request."

        # Default: truncate and show the actual error
        return error_msg[:147] + "..." if len(error_msg) > 150 else error_msg

    # =========================================================================
    # CONSULTATION LOOP
    # =========================================================================

    async def process_voice_input(
        self,
        user_input: str,
        deploy: bool = True,
        publish: bool = True,
        image_base64: str | None = None,
        image_filename: str | None = None,
    ) -> dict:
        """
        Process voice/chat input through the Consultation Loop.

        Flow:
        1. Check for clear projects intent
        2. Check for status query
        3. Check for active consultation
        4. Start new or continue existing consultation
        5. If ready to build, dispatch build
        """
        console.print(f"[cyan][FLEET] Processing: {user_input[:50]}...[/cyan]")

        # Handle clear projects intent
        if _is_clear_projects_intent(user_input):
            return self._handle_clear_projects()

        # Handle status query
        if _is_status_query(user_input):
            return self._handle_status_query(user_input)

        # Check for active consultation
        active = get_active_consultation()

        if active and active.pending_question:
            console.print(f"[cyan][FLEET] Continuing consultation: {active.id[:8]}[/cyan]")
            return await self._continue_consultation(
                active.id, user_input, deploy, publish, image_base64, image_filename
            )
        else:
            console.print("[cyan][FLEET] Starting new consultation[/cyan]")
            return await self._start_consultation(
                user_input, deploy, publish, image_base64, image_filename
            )

    def _handle_clear_projects(self) -> dict:
        """Handle clear projects intent."""
        try:
            n = clear_all_missions()
            return {
                "status": "STATUS_RESPONSE",
                "speech": f"Cleared {n} projects. Click Refresh to see the empty list.",
                "cleared": n,
            }
        except Exception as e:
            return {"status": "error", "speech": f"Could not clear projects: {e}"}

    def _handle_status_query(self, user_input: str) -> dict:
        """Handle status query from user."""
        hint = _extract_project_hint(user_input)
        missions = find_missions_by_prompt_hint(hint, limit=15) if hint else list_missions(limit=20)

        if not missions:
            return {
                "status": "STATUS_RESPONSE",
                "speech": "No builds found. Start one from the chat.",
                "mission_id": None,
            }

        in_progress = [m for m in missions if m.status in IN_PROGRESS_STATUSES]
        mission = in_progress[0] if in_progress else missions[0]

        stage = STATUS_STAGE_LABELS.get(mission.status, mission.status)
        elapsed = _elapsed_seconds(mission.created_at)
        project_label = getattr(mission, "design_target", None) or mission.prompt[:40]

        if mission.status in IN_PROGRESS_STATUSES:
            elapsed_part = f" In progress for {elapsed}s." if elapsed else ""
            speech = f'Building "{project_label}": {stage}.{elapsed_part}'
        else:
            speech = f'"{project_label}": {stage}. {mission.speech_output or ""}'

        return {
            "status": "STATUS_RESPONSE",
            "speech": speech,
            "mission_id": mission.id,
            "stage": stage,
            "mission_status": mission.status,
        }

    async def _start_consultation(
        self,
        prompt: str,
        deploy: bool,
        publish: bool,
        image_base64: str | None,
        image_filename: str | None,
    ) -> dict:
        """Start a new consultation."""
        design_target = detect_design_target(prompt)
        mission_id = create_consultation(prompt, design_target)

        if image_base64 and image_filename:
            _save_design_image(mission_id, image_base64, image_filename)

        conversation = [{"role": "user", "content": prompt}]
        consultant = self._get_consultant()
        response = consultant.analyze(conversation)

        if response.design_target and not design_target:
            set_design_target(mission_id, response.design_target)

        return await self._handle_consultant_response(
            mission_id, response, conversation, deploy, publish
        )

    async def _continue_consultation(
        self,
        mission_id: str,
        user_input: str,
        deploy: bool,
        publish: bool,
        image_base64: str | None,
        image_filename: str | None,
    ) -> dict:
        """Continue an existing consultation."""
        mission = get_mission(mission_id)
        if not mission:
            return {"status": "error", "speech": "Session not found.", "mission_id": None}

        if image_base64 and image_filename:
            _save_design_image(mission_id, image_base64, image_filename)

        clear_pending_question(mission_id)
        append_to_conversation(mission_id, "user", user_input)

        conversation = mission.conversation_history or []
        conversation.append({"role": "user", "content": user_input})

        consultant = self._get_consultant()
        response = consultant.analyze(conversation)

        return await self._handle_consultant_response(
            mission_id, response, conversation, deploy, publish
        )

    async def _handle_consultant_response(
        self,
        mission_id: str,
        response: ConsultantResponse,
        conversation: list[dict],
        deploy: bool,
        publish: bool,
    ) -> dict:
        """Handle the consultant's response."""
        append_to_conversation(mission_id, "assistant", response.speech)

        if response.status == "READY_TO_BUILD":
            console.print(f"[green][FLEET] Ready to build: {mission_id[:8]}[/green]")
            mark_ready_to_build(mission_id)

            consultant = self._get_consultant()
            build_prompt = consultant.get_build_prompt(conversation)
            design_target = consultant.get_design_target(conversation)

            # Dispatch async build (store reference to prevent GC)
            task = asyncio.create_task(
                self._run_mission_with_target(
                    mission_id, build_prompt, design_target, deploy, publish
                )
            )
            task.add_done_callback(lambda _: None)

            return {
                "status": "BUILDING",
                "speech": response.speech,
                "mission_id": mission_id,
                "design_target": design_target,
            }

        elif response.status in ("NEEDS_INPUT", "NEEDS_CONFIRMATION"):
            console.print(f"[yellow][FLEET] Awaiting input: {mission_id[:8]}[/yellow]")
            set_pending_question(
                mission_id, response.question or response.speech, response.proposed_stack
            )

            # Convert iterations to dict format for API
            iterations_data = None
            if response.iterations:
                iterations_data = [
                    {
                        "iteration": it.iteration,
                        "name": it.name,
                        "features": it.features,
                        "buildable_now": it.buildable_now,
                    }
                    for it in response.iterations
                ]

            return {
                "status": "AWAITING_INPUT",
                "speech": response.speech,
                "mission_id": mission_id,
                "question": response.question or response.speech,
                "proposed_stack": response.proposed_stack,
                "design_target": response.design_target,
                "features": response.features,
                "confidence": response.confidence,
                "iterations": iterations_data,
                "total_iterations": response.total_iterations,
                "current_iteration": response.current_iteration,
            }

        return {
            "status": "AWAITING_INPUT",
            "speech": response.speech,
            "mission_id": mission_id,
            "question": response.question,
        }

    # =========================================================================
    # MISSION MANAGEMENT
    # =========================================================================

    def clear_projects(self) -> int:
        """Clear all missions from the database."""
        return clear_all_missions()

    async def retry_failed_mission(
        self, mission_id: str, deploy: bool = True, publish: bool = True
    ) -> dict:
        """Retry a failed mission."""
        mission = get_mission(mission_id)
        if not mission:
            return {"status": "error", "speech": "Mission not found.", "mission_id": mission_id}

        retryable = {"FAILED", "BLOCKED", "TIMEOUT", "PUBLISH_FAILED"}
        if mission.status not in retryable:
            return {
                "status": "error",
                "speech": f"Cannot retry: mission is {mission.status}.",
                "mission_id": mission_id,
            }

        await self._update_status(mission_id, "BUILDING", "Retrying build from scratch.")

        # Store reference to prevent GC
        task = asyncio.create_task(
            self._run_mission_with_target(
                mission_id,
                mission.prompt,
                getattr(mission, "design_target", None),
                deploy,
                publish,
            )
        )
        task.add_done_callback(lambda _: None)

        return {
            "status": "BUILDING",
            "speech": "Retrying build. Watch for progress.",
            "mission_id": mission_id,
        }

    async def extend_mission(
        self,
        parent_mission_id: str,
        additional_features: str,
        deploy: bool = True,
        publish: bool = True,
    ) -> dict:
        """
        Extend an existing deployed mission with new features.

        Creates a new iteration linked to the parent mission, using the
        parent's manifest as context for the AI Architect.

        Args:
            parent_mission_id: The UUID of the mission to extend.
            additional_features: What to add (e.g., "add a dashboard with charts").
            deploy: Whether to deploy the extended version.
            publish: Whether to open a PR.

        Returns:
            dict with status, speech, mission_id (the new iteration's ID).
        """
        from src.core.db import create_mission, get_mission_manifest

        # Validate parent mission exists and is deployed
        parent = get_mission(parent_mission_id)
        if not parent:
            return {
                "status": "error",
                "speech": "Parent mission not found.",
                "parent_mission_id": parent_mission_id,
            }

        if parent.status != "DEPLOYED":
            return {
                "status": "error",
                "speech": f"Can only extend deployed projects. This one is {parent.status}.",
                "parent_mission_id": parent_mission_id,
            }

        # Get the parent's manifest for context
        parent_manifest = get_mission_manifest(parent_mission_id)
        if not parent_manifest:
            return {
                "status": "error",
                "speech": "Could not load parent project files. Try rebuilding first.",
                "parent_mission_id": parent_mission_id,
            }

        # Build the extended prompt with full context
        project_name = parent_manifest.get("project_name", "project")
        existing_files = [f.get("path", "") for f in parent_manifest.get("files", [])]

        extended_prompt = f"""EXTEND EXISTING PROJECT: {project_name}

ORIGINAL REQUEST: {parent.prompt}

EXISTING FILES: {", ".join(existing_files)}

EXISTING CODE CONTEXT:
```json
{json.dumps(parent_manifest, indent=2)[:3000]}
```

NEW FEATURES TO ADD: {additional_features}

IMPORTANT: 
- Keep all existing functionality
- Add the new features to the existing codebase
- Update tests to cover new features
- Maintain the same project structure and stack"""

        # Create new mission linked to parent
        new_mission_id = create_mission(extended_prompt, parent_mission_id=parent_mission_id)
        iteration_number = parent.iteration_number + 1 if hasattr(parent, "iteration_number") else 2

        await self._update_status(
            new_mission_id,
            "ARCHITECTING",
            f"Extending {project_name} (iteration {iteration_number}).",
        )

        # Run the build asynchronously
        task = asyncio.create_task(
            self._run_mission_with_target(
                new_mission_id,
                extended_prompt,
                parent.design_target,
                deploy,
                publish,
            )
        )
        task.add_done_callback(lambda _: None)

        return {
            "status": "BUILDING",
            "speech": f"Extending {project_name} with new features. This is iteration {iteration_number}.",
            "mission_id": new_mission_id,
            "parent_mission_id": parent_mission_id,
            "iteration_number": iteration_number,
        }

    def search_missions_by_keywords(self, keywords: list[str], limit: int = 5) -> list:
        """Search missions by keywords."""
        return search_missions(keywords, limit=limit)

    # =========================================================================
    # PUBLIC API: DISPATCH MISSION
    # =========================================================================

    async def dispatch_mission(self, prompt: str, deploy: bool = True, publish: bool = True) -> str:
        """
        Dispatch a new mission (direct build, bypassing consultation).

        Creates DB entry and spawns async task.
        Returns immediately with mission ID.
        """
        mission_id = create_mission(prompt)
        console.print(
            f"[cyan][FLEET] Mission queued: {mission_id[:8]} "
            f"(deploy={deploy}, publish={publish})[/cyan]"
        )

        # Store reference to prevent GC
        task = asyncio.create_task(self._run_mission(mission_id, prompt, deploy, publish))
        task.add_done_callback(lambda _: None)
        return mission_id

    # =========================================================================
    # MISSION EXECUTION
    # =========================================================================

    async def _run_mission(self, mission_id: str, prompt: str, deploy: bool, publish: bool) -> None:
        """Execute mission pipeline (direct build without design target)."""
        await self._run_mission_with_target(mission_id, prompt, None, deploy, publish)

    async def _run_mission_with_target(
        self,
        mission_id: str,
        prompt: str,
        design_target: str | None,
        deploy: bool,
        publish: bool,
    ) -> None:
        """Execute mission pipeline with design target."""
        async with self._mission_semaphore:
            mission_start = time.time()
            self._active_missions[mission_id] = mission_start

            try:
                # Phase 1: Architecting
                await self._update_status(
                    mission_id, "ARCHITECTING", f"Drafting {design_target or 'custom'} blueprint."
                )

                async with AsyncProgressTracker(mission_id, "ARCHITECTING", self._ws_manager):
                    architect = self._get_architect()
                    # Pass mission_id for vision/mockup support
                    manifest = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: architect.draft_blueprint(
                            prompt, design_target=design_target, mission_id=mission_id
                        ),
                    )

                if time.time() - mission_start > MISSION_TIMEOUT_SECONDS:
                    raise BuildTimeoutError("Mission timeout exceeded")

                # Phase 2: Validation
                await self._phase_validate(mission_id, manifest)

                # Phase 3: Build with self-healing
                result = await self._phase_build(mission_id, manifest, deploy, mission_start)
                if not result:
                    return

                # Phase 4: Publishing
                pr_url = await self._phase_publish(mission_id, manifest, publish, result.deploy_url)

                # Final status
                await self._finalize_mission(mission_id, result.deploy_url, pr_url)

            except ArchitectError as e:
                error_str = str(e).lower()
                console.print(f"[red][Mission {mission_id[:8]}] Architect failed: {e}[/red]")

                # Detect copyright/trademark issues and provide conversational guidance
                trademark_indicators = [
                    "copyright",
                    "trademark",
                    "brand",
                    "cannot create",
                    "cannot generate",
                    "proprietary",
                    "intellectual property",
                    "unable to replicate",
                    "cannot replicate",
                    "clone",
                    "cannot clone",
                ]
                brand_names = [
                    "tesla",
                    "apple",
                    "google",
                    "microsoft",
                    "amazon",
                    "meta",
                    "facebook",
                    "twitter",
                    "netflix",
                    "spotify",
                    "airbnb",
                    "uber",
                    "linkedin",
                    "instagram",
                ]

                is_trademark_issue = any(ind in error_str for ind in trademark_indicators)
                mentioned_brand = next((b for b in brand_names if b in prompt.lower()), None)

                if is_trademark_issue or mentioned_brand:
                    # Conversational response suggesting alternatives
                    if mentioned_brand:
                        suggestion = (
                            f"I can't directly clone {mentioned_brand.title()}'s website due to "
                            f"copyright protection. Try rephrasing like: 'Build a {mentioned_brand.title()}-inspired "
                            f"landing page' or 'Build a modern electric car company website with dark theme'. "
                            f"What would you like me to build instead?"
                        )
                    else:
                        suggestion = (
                            "I can't directly clone trademarked websites. Try describing the style you want "
                            "instead of naming a specific brand. For example: 'Build a modern SaaS landing page "
                            "with dark theme and gradient accents'. What would you like me to build?"
                        )
                    await self._update_status(mission_id, "AWAITING_INPUT", suggestion)
                else:
                    # Provide clear, user-friendly error reason
                    error_msg = str(e)
                    user_friendly_reason = self._get_friendly_error(error_msg)
                    await self._update_status(
                        mission_id, "FAILED", f"Blueprint failed: {user_friendly_reason}"
                    )

            except BuildTimeoutError:
                await self._update_status(mission_id, "TIMEOUT", "Mission timeout exceeded.")

            except SecurityViolation:
                await self._update_status(mission_id, "BLOCKED", "Policy violation.")

            except Exception as e:
                console.print(f"[red][Mission {mission_id[:8]}] Error: {e}[/red]")
                await self._update_status(mission_id, "FAILED", f"Error: {str(e)[:100]}")

            finally:
                self._active_missions.pop(mission_id, None)

    async def _phase_validate(self, mission_id: str, manifest: GantryManifest) -> bool:
        """Validate manifest against policy."""
        await self._update_status(mission_id, "VALIDATING", "Running security check.")

        try:
            self._policy.validate(manifest)
            return True
        except SecurityViolation as e:
            console.print(f"[red][Mission {mission_id[:8]}] Policy violation: {e}[/red]")
            await self._update_status(mission_id, "BLOCKED", "Policy violation.")
            return False

    async def _phase_build(
        self,
        mission_id: str,
        manifest: GantryManifest,
        deploy: bool,
        mission_start: float,
    ):
        """Build with self-healing loop."""
        architect = self._get_architect()
        current_manifest = manifest

        for attempt in range(1, MAX_RETRIES + 1):
            if time.time() - mission_start > MISSION_TIMEOUT_SECONDS:
                raise BuildTimeoutError("Mission timeout during build")

            await self._update_status(
                mission_id,
                "BUILDING",
                f"Building {current_manifest.project_name}. Attempt {attempt}.",
            )

            async with AsyncProgressTracker(mission_id, "BUILDING", self._ws_manager):
                try:
                    # Capture current_manifest by value using default arg
                    m = current_manifest
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, lambda m=m: self._foundry.build(m, mission_id, deploy=deploy)
                    )
                    console.print(f"[green][Mission {mission_id[:8]}] Build PASSED[/green]")
                    return result

                except (AuditFailedError, DeploymentError) as e:
                    error_log = str(e) if isinstance(e, DeploymentError) else e.output
                    console.print(
                        f"[yellow][Mission {mission_id[:8]}] Build failed (attempt {attempt}): "
                        f"{error_log[:200]}...[/yellow]"
                    )

                    if attempt < MAX_RETRIES:
                        await self._update_status(
                            mission_id, "HEALING", f"Build failed. Self-repair attempt {attempt}."
                        )
                        try:
                            # Capture variables by value
                            m, err = current_manifest, error_log
                            healed = await asyncio.get_event_loop().run_in_executor(
                                None, lambda m=m, err=err: architect.heal_blueprint(m, err)
                            )
                            # Only update if healing succeeded and produced different code
                            if healed and healed != current_manifest:
                                console.print(
                                    f"[green][Mission {mission_id[:8]}] Healing produced new manifest[/green]"
                                )
                                current_manifest = healed
                            else:
                                console.print(
                                    f"[yellow][Mission {mission_id[:8]}] Healing returned same code, "
                                    f"will retry with different approach[/yellow]"
                                )
                        except ArchitectError as heal_err:
                            console.print(
                                f"[red][Mission {mission_id[:8]}] Healing failed: {heal_err}[/red]"
                            )
                            # Don't silently pass - log that healing failed
                            # The next attempt will still try with current_manifest
                            # but at least we know healing isn't working

                except BuildTimeoutError:
                    raise

        await self._update_status(mission_id, "FAILED", f"Failed after {MAX_RETRIES} attempts.")
        return None

    async def _phase_publish(
        self,
        mission_id: str,
        manifest: GantryManifest,
        publish: bool,
        deploy_url: str | None,
    ) -> str | None:
        """Publish to GitHub via PR."""
        if SKIP_PUBLISH or not publish or not self._publisher.is_configured():
            return None

        await self._update_status(mission_id, "PUBLISHING", "Opening Pull Request.")

        async with AsyncProgressTracker(mission_id, "PUBLISHING", self._ws_manager):
            try:
                evidence_path = MISSIONS_DIR / mission_id
                pr_url = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._publisher.publish_mission(
                        manifest, str(evidence_path), mission_id=mission_id
                    ),
                )
                console.print(f"[green][Mission {mission_id[:8]}] PR opened: {pr_url}[/green]")
                return pr_url
            except (SecurityBlock, PublishError) as e:
                console.print(f"[red][Mission {mission_id[:8]}] Publish failed: {e}[/red]")
                return None

    async def _finalize_mission(
        self, mission_id: str, deploy_url: str | None, pr_url: str | None
    ) -> None:
        """Set final mission status."""
        if deploy_url and pr_url:
            await self._update_status(mission_id, "DEPLOYED", f"Live at {deploy_url}. PR opened.")
        elif deploy_url:
            await self._update_status(mission_id, "DEPLOYED", f"Live at {deploy_url}")
        elif pr_url:
            await self._update_status(mission_id, "PR_OPENED", "PR opened for review.")
        else:
            await self._update_status(mission_id, "SUCCESS", "Build verified.")
