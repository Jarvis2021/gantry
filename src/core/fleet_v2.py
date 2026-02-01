# -----------------------------------------------------------------------------
# THE FLEET MANAGER v2 - REFACTORED ORCHESTRATOR
# -----------------------------------------------------------------------------
# Orchestrates the complete mission pipeline with self-repair.
# Refactored: _run_mission split into smaller, focused functions.
#
# Functions (each under 50 lines):
# - dispatch_mission: Queue mission and spawn task
# - _run_mission: Main orchestration loop
# - _phase_architect: Draft blueprint
# - _phase_validate: Policy check
# - _phase_build: Build with self-healing
# - _phase_publish: GitHub PR
# - _update_status: Status updates with WebSocket broadcast
# -----------------------------------------------------------------------------

import asyncio
import os
import traceback
from typing import TYPE_CHECKING

from rich.console import Console

from src.core.architect import Architect, ArchitectError
from src.core.db import create_mission, update_mission_status
from src.core.deployer import DeploymentError
from src.core.foundry import MISSIONS_DIR, AuditFailedError, BuildTimeoutError, Foundry
from src.core.policy import PolicyGate, SecurityViolation
from src.core.publisher import Publisher, PublishError, SecurityBlock
from src.domain.models import GantryManifest

if TYPE_CHECKING:
    from src.main_fastapi import ConnectionManager

console = Console()

# Configuration
MAX_RETRIES = 3
SKIP_PUBLISH = os.getenv("GANTRY_SKIP_PUBLISH", "").lower() == "true"


class FleetManager:
    """
    The Fleet Orchestrator v2.

    Pipeline: Voice Memo -> DB -> Architect -> Policy -> Foundry -> DB
    All operations run as async tasks for non-blocking execution.
    """

    def __init__(self, ws_manager: "ConnectionManager | None" = None) -> None:
        """Initialize the Fleet Manager."""
        from src.core.db import init_db

        init_db()

        self._foundry = Foundry()
        self._policy = PolicyGate()
        self._publisher = Publisher()
        self._architect: Architect | None = None
        self._ws_manager = ws_manager

        console.print("[green][FLEET] Fleet Manager v2 online[/green]")

    def _get_architect(self) -> Architect:
        """Lazy init Architect."""
        if self._architect is None:
            self._architect = Architect()
        return self._architect

    async def _broadcast(self, mission_id: str, status: str, message: str) -> None:
        """Broadcast status update via WebSocket."""
        if self._ws_manager:
            await self._ws_manager.broadcast(mission_id, {
                "type": "status",
                "mission_id": mission_id,
                "status": status,
                "message": message,
            })

    async def _update_status(
        self, mission_id: str, status: str, speech: str
    ) -> None:
        """Update mission status in DB and broadcast via WebSocket."""
        update_mission_status(mission_id, status, speech)
        await self._broadcast(mission_id, status, speech)

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def dispatch_mission(
        self, prompt: str, deploy: bool = True, publish: bool = True
    ) -> str:
        """
        Dispatch a new mission.

        Creates DB entry (PENDING) and spawns async task.
        Returns immediately with mission ID.
        """
        mission_id = create_mission(prompt)
        console.print(
            f"[cyan][FLEET] Mission queued: {mission_id[:8]} "
            f"(deploy={deploy}, publish={publish})[/cyan]"
        )

        # Spawn async task (stored to prevent garbage collection)
        task = asyncio.create_task(
            self._run_mission(mission_id, prompt, deploy, publish)
        )
        # Store reference to prevent GC
        task.add_done_callback(lambda _: None)

        return mission_id

    # =========================================================================
    # MISSION PIPELINE
    # =========================================================================

    async def _run_mission(
        self, mission_id: str, prompt: str, deploy: bool, publish: bool
    ) -> None:
        """
        Execute the complete mission pipeline.

        Flow: Draft → Validate → Build (with healing) → Deploy → Publish
        """
        try:
            # Phase 1: Architecture
            manifest = await self._phase_architect(mission_id, prompt)
            if not manifest:
                return

            # Phase 2: Validation
            if not await self._phase_validate(mission_id, manifest):
                return

            # Phase 3: Build (with self-healing)
            result = await self._phase_build(mission_id, manifest, deploy)
            if not result:
                return

            deploy_url = result.deploy_url

            # Phase 4: Publishing
            pr_url = await self._phase_publish(
                mission_id, manifest, publish, deploy_url
            )

            # Final status
            await self._finalize_mission(mission_id, deploy_url, pr_url)

        except Exception as e:
            console.print(f"[red][Mission {mission_id[:8]}] Critical error: {e}[/red]")
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            await self._update_status(
                mission_id, "CRITICAL_FAILURE",
                f"Mission aborted. Error: {str(e)[:100]}"
            )

    # =========================================================================
    # PHASE 1: ARCHITECTURE
    # =========================================================================

    async def _phase_architect(
        self, mission_id: str, prompt: str
    ) -> GantryManifest | None:
        """Draft the blueprint from the prompt."""
        console.print(f"[cyan][Mission {mission_id[:8]}] Drafting blueprint...[/cyan]")
        await self._update_status(mission_id, "ARCHITECTING", "Drafting blueprint.")

        try:
            architect = self._get_architect()
            manifest = architect.draft_blueprint(prompt)
            console.print(
                f"[green][Mission {mission_id[:8]}] Blueprint ready: "
                f"{manifest.project_name}[/green]"
            )
            return manifest

        except ArchitectError as e:
            console.print(f"[red][Mission {mission_id[:8]}] Architect failed: {e}[/red]")
            await self._update_status(
                mission_id, "FAILED", "Blueprint generation failed."
            )
            return None

    # =========================================================================
    # PHASE 2: VALIDATION
    # =========================================================================

    async def _phase_validate(
        self, mission_id: str, manifest: GantryManifest
    ) -> bool:
        """Validate manifest against policy."""
        console.print(f"[cyan][Mission {mission_id[:8]}] Policy check...[/cyan]")
        await self._update_status(mission_id, "VALIDATING", "Running security check.")

        try:
            self._policy.validate(manifest)
            return True

        except SecurityViolation as e:
            console.print(f"[red][Mission {mission_id[:8]}] Policy violation: {e}[/red]")
            await self._update_status(
                mission_id, "BLOCKED", "Request denied. Policy violation."
            )
            return False

    # =========================================================================
    # PHASE 3: BUILD (WITH SELF-HEALING)
    # =========================================================================

    async def _phase_build(
        self, mission_id: str, manifest: GantryManifest, deploy: bool
    ):
        """Build with self-healing loop."""
        architect = self._get_architect()
        current_manifest = manifest

        for attempt in range(1, MAX_RETRIES + 1):
            console.print(
                f"[cyan][Mission {mission_id[:8]}] Building "
                f"(attempt {attempt}/{MAX_RETRIES})...[/cyan]"
            )
            await self._update_status(
                mission_id, "BUILDING",
                f"Building {current_manifest.project_name}. Attempt {attempt}."
            )

            try:
                result = self._foundry.build(current_manifest, mission_id, deploy=deploy)
                console.print(
                    f"[green][Mission {mission_id[:8]}] Build PASSED[/green]"
                )
                return result

            except (AuditFailedError, DeploymentError) as e:
                error_log = str(e) if isinstance(e, DeploymentError) else e.output
                console.print(
                    f"[yellow][Mission {mission_id[:8]}] Build failed: {type(e).__name__}[/yellow]"
                )

                if attempt < MAX_RETRIES:
                    current_manifest = await self._heal_manifest(
                        mission_id, architect, current_manifest, error_log, attempt
                    )
                    if not current_manifest:
                        break

            except BuildTimeoutError:
                console.print(f"[red][Mission {mission_id[:8]}] Timeout[/red]")
                await self._update_status(
                    mission_id, "TIMEOUT", "Dead man's switch triggered."
                )
                return None

        # Exhausted retries
        await self._update_status(
            mission_id, "FAILED",
            f"Build failed after {MAX_RETRIES} attempts."
        )
        return None

    async def _heal_manifest(
        self,
        mission_id: str,
        architect: Architect,
        manifest: GantryManifest,
        error_log: str,
        attempt: int,
    ) -> GantryManifest | None:
        """Attempt to heal a failed manifest."""
        console.print(
            f"[yellow][Mission {mission_id[:8]}] Self-healing attempt {attempt}...[/yellow]"
        )
        await self._update_status(
            mission_id, "HEALING",
            f"Build failed. Self-repair attempt {attempt} of {MAX_RETRIES}."
        )

        try:
            healed = architect.heal_blueprint(manifest, error_log)
            console.print(
                f"[cyan][Mission {mission_id[:8]}] Healed manifest received[/cyan]"
            )
            return healed
        except ArchitectError as e:
            console.print(
                f"[red][Mission {mission_id[:8]}] Healing failed: {e}[/red]"
            )
            return None

    # =========================================================================
    # PHASE 4: PUBLISHING
    # =========================================================================

    async def _phase_publish(
        self,
        mission_id: str,
        manifest: GantryManifest,
        publish: bool,
        deploy_url: str | None,
    ) -> str | None:
        """Publish to GitHub via PR."""
        should_skip = SKIP_PUBLISH or not publish

        if should_skip:
            skip_reason = "GANTRY_SKIP_PUBLISH=true" if SKIP_PUBLISH else "publish=false"
            console.print(
                f"[yellow][Mission {mission_id[:8]}] Publishing skipped ({skip_reason})[/yellow]"
            )
            return None

        if not self._publisher.is_configured():
            return None

        console.print(f"[cyan][Mission {mission_id[:8]}] Opening Pull Request...[/cyan]")
        await self._update_status(mission_id, "PUBLISHING", "Opening Pull Request.")

        try:
            evidence_path = MISSIONS_DIR / mission_id
            pr_url = self._publisher.publish_mission(
                manifest, str(evidence_path), mission_id=mission_id
            )
            console.print(f"[green][Mission {mission_id[:8]}] PR opened: {pr_url}[/green]")
            return pr_url

        except (SecurityBlock, PublishError) as e:
            console.print(
                f"[red][Mission {mission_id[:8]}] Publish failed: {e}[/red]"
            )
            return None

    # =========================================================================
    # FINALIZATION
    # =========================================================================

    async def _finalize_mission(
        self, mission_id: str, deploy_url: str | None, pr_url: str | None
    ) -> None:
        """Set final mission status based on outcomes."""
        if deploy_url and pr_url:
            console.print(f"[green][Mission {mission_id[:8]}] LIVE + PR[/green]")
            await self._update_status(
                mission_id, "DEPLOYED",
                f"Gantry successful. Live at {deploy_url}. PR opened."
            )
        elif deploy_url:
            console.print(f"[green][Mission {mission_id[:8]}] LIVE: {deploy_url}[/green]")
            await self._update_status(
                mission_id, "DEPLOYED",
                f"Gantry successful. Live at {deploy_url}"
            )
        elif pr_url:
            console.print(f"[green][Mission {mission_id[:8]}] PR OPENED[/green]")
            await self._update_status(
                mission_id, "PR_OPENED",
                "Gantry successful. Pull Request opened."
            )
        else:
            console.print(f"[green][Mission {mission_id[:8]}] COMPLETE[/green]")
            await self._update_status(
                mission_id, "SUCCESS",
                "Gantry successful. Build verified."
            )
