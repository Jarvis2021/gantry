# -----------------------------------------------------------------------------
# THE FOUNDRY - BUILDER & EVIDENCE
# -----------------------------------------------------------------------------
# Responsibility: Executes Fabrication Instructions in an isolated Project Pod.
# Creates Evidence (Black Box) for every mission, pass or fail.
#
# Safety Features:
# - Dead Man's Switch: 180 second hard timeout
# - Resource Limits: 512MB memory cap
# - Black Box: Every step is logged to flight_recorder.json
#
# This is the "Body" of the Fleet Protocol. It has NO knowledge of AI/LLMs.
# -----------------------------------------------------------------------------

import io
import json
import os
import tarfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import docker
from docker.errors import APIError, ImageNotFound
from docker.models.containers import Container
from rich.console import Console

from src.core.deployer import Deployer, DeploymentError
from src.domain.models import GantryManifest, StackType

console = Console()

# Configuration
BUILD_TIMEOUT_SECONDS = 180  # Dead Man's Switch - 3 minutes
MEMORY_LIMIT = "512m"  # Prevent memory leaks
MISSIONS_DIR = Path(__file__).parent.parent.parent / "missions"

# Universal builder image (has Python, Node, Git, Vercel)
BUILDER_IMAGE = "gantry/builder:latest"

# Fallback images if builder not available
STACK_IMAGES = {
    StackType.PYTHON: "python:3.11-slim",
    StackType.NODE: "node:20-alpine",
    StackType.RUST: "rust:1.75-slim",
}


class BuildTimeoutError(Exception):
    """Raised when build exceeds Dead Man's Switch timeout."""

    pass


class AuditFailedError(Exception):
    """Raised when audit_command fails (exit code != 0)."""

    def __init__(self, message: str, exit_code: int, output: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.output = output


@dataclass
class FlightLogEntry:
    """A single entry in the flight recorder."""

    timestamp: str
    event: str
    details: str | None = None


@dataclass
class BuildResult:
    """Result of a successful build."""

    container_id: str
    project_name: str
    audit_passed: bool
    duration_seconds: float
    deploy_url: str | None = None  # Live URL from Vercel


class BlackBox:
    """
    Evidence Pack - The Flight Recorder.

    Every mission creates a dedicated folder with:
    - manifest.json: The fabrication instructions
    - audit_pass.json OR audit_fail.json: The verdict
    - flight_recorder.json: Complete session log

    Why: "Black Box" Evidence requirement. Even failed missions leave a trail.
    """

    def __init__(self, mission_id: str) -> None:
        self.mission_id = mission_id
        self.folder = MISSIONS_DIR / mission_id
        self.folder.mkdir(parents=True, exist_ok=True)
        self._log: list[FlightLogEntry] = []

        console.print(f"[cyan][BLACKBOX] Evidence folder: {self.folder}[/cyan]")

    def log(self, event: str, details: str | None = None) -> None:
        """Record an event in the flight recorder."""
        entry = FlightLogEntry(
            timestamp=datetime.utcnow().isoformat(), event=event, details=details
        )
        self._log.append(entry)

    def save_manifest(self, manifest: GantryManifest) -> None:
        """Save manifest.json to evidence folder."""
        path = self.folder / "manifest.json"
        with open(path, "w") as f:
            json.dump(manifest.model_dump(), f, indent=2)
        self.log("MANIFEST_SAVED", str(path))

    def save_audit_pass(self, output: str) -> None:
        """Save audit_pass.json - The Critic approved."""
        report = {"timestamp": datetime.utcnow().isoformat(), "verdict": "PASS", "output": output}
        path = self.folder / "audit_pass.json"
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        self.log("AUDIT_PASSED")

    def save_audit_fail(self, exit_code: int, output: str) -> None:
        """Save audit_fail.json - The Critic rejected."""
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "verdict": "FAIL",
            "exit_code": exit_code,
            "output": output,
        }
        path = self.folder / "audit_fail.json"
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        self.log("AUDIT_FAILED", f"Exit code: {exit_code}")

    def finalize(self) -> None:
        """Save flight_recorder.json - Complete session log."""
        path = self.folder / "flight_recorder.json"
        with open(path, "w") as f:
            json.dump(
                [
                    {"timestamp": e.timestamp, "event": e.event, "details": e.details}
                    for e in self._log
                ],
                f,
                indent=2,
            )
        console.print(f"[green][BLACKBOX] Flight recorder saved: {path}[/green]")


class Foundry:
    """
    The Docker Body that executes Fabrication Instructions.

    Connects to DOCKER_HOST (Proxy) for isolation.
    Enforces Dead Man's Switch and resource limits.
    Deploys to Vercel for live URLs.
    """

    def __init__(self) -> None:
        """Initialize connection to Docker (via Proxy)."""
        docker_host = os.getenv("DOCKER_HOST")
        self._use_builder_image = True  # Use universal builder by default
        self._deployer = Deployer()  # Vercel deployment handler

        if docker_host:
            self._client = docker.DockerClient(base_url=docker_host)
            console.print(f"[green][FOUNDRY] Connected via proxy: {docker_host}[/green]")
        else:
            self._client = docker.from_env()
            console.print("[green][FOUNDRY] Connected to local Docker[/green]")

        # Check if builder image exists
        try:
            self._client.images.get(BUILDER_IMAGE)
            console.print(f"[green][FOUNDRY] Builder image ready: {BUILDER_IMAGE}[/green]")
        except ImageNotFound:
            console.print(
                "[yellow][FOUNDRY] Builder image not found, will use stack-specific images[/yellow]"
            )
            self._use_builder_image = False

    def _get_image(self, stack: StackType) -> str:
        """Get the appropriate Docker image for the build."""
        if self._use_builder_image:
            return BUILDER_IMAGE
        return STACK_IMAGES.get(stack, STACK_IMAGES[StackType.PYTHON])

    def _verify_serverless_structure(self, container: Container, manifest: GantryManifest) -> bool:
        """
        Verify the project has correct Vercel serverless structure.

        Checks:
        1. api/index.js or api/index.py exists
        2. vercel.json exists with rewrites
        3. Handler exports correctly

        Args:
            container: Running Docker container with the app
            manifest: The manifest

        Returns:
            True if structure is valid, False otherwise
        """
        console.print("[cyan][FOUNDRY] Verifying Vercel serverless structure...[/cyan]")

        # Check required files exist
        if manifest.stack == StackType.NODE:
            check_cmd = """
            if [ -f api/index.js ] && [ -f vercel.json ]; then
                # Check that api/index.js exports a function
                if grep -q "module.exports" api/index.js; then
                    echo "STRUCTURE_VALID"
                    exit 0
                else
                    echo "MISSING_EXPORT: api/index.js must have module.exports"
                    exit 1
                fi
            else
                echo "MISSING_FILES: Need api/index.js and vercel.json"
                exit 1
            fi
            """
        elif manifest.stack == StackType.PYTHON:
            check_cmd = """
            if [ -f api/index.py ] && [ -f vercel.json ]; then
                # Check that api/index.py has handler class
                if grep -q "class handler" api/index.py; then
                    echo "STRUCTURE_VALID"
                    exit 0
                else
                    echo "MISSING_HANDLER: api/index.py must have 'class handler'"
                    exit 1
                fi
            else
                echo "MISSING_FILES: Need api/index.py and vercel.json"
                exit 1
            fi
            """
        else:
            return True

        exit_code, output = container.exec_run(cmd=["sh", "-c", check_cmd], workdir="/workspace")

        output_str = output.decode("utf-8") if isinstance(output, bytes) else str(output)
        console.print(f"[dim][FOUNDRY] Structure check: {output_str.strip()}[/dim]")

        return exit_code == 0 and "STRUCTURE_VALID" in output_str

    def _create_tar(self, manifest: GantryManifest) -> bytes:
        """Create in-memory tar archive of all files."""
        tar_buffer = io.BytesIO()

        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            for file_spec in manifest.files:
                content = file_spec.content.encode("utf-8")
                info = tarfile.TarInfo(name=file_spec.path)
                info.size = len(content)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(content))

        tar_buffer.seek(0)
        return tar_buffer.read()

    def _find_design_reference(self, mission_folder: Path) -> str | None:
        """Find design-reference image in mission folder (design-reference.png, .jpg, etc.)."""
        if not mission_folder.exists():
            return None
        for ext in ("png", "jpg", "jpeg", "gif", "webp"):
            name = f"design-reference.{ext}"
            if (mission_folder / name).exists():
                return name
        return None

    def _create_design_image_tar(self, mission_folder: Path, design_ref: str) -> bytes | None:
        """Create tar containing design-reference image as public/design-reference.{ext}."""
        src = mission_folder / design_ref
        if not src.exists() or not src.is_file():
            return None
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            info = tar.gettarinfo(str(src), arcname=f"public/{design_ref}")
            with open(src, "rb") as f:
                tar.addfile(info, f)
        tar_buffer.seek(0)
        return tar_buffer.read()

    def _ensure_image(self, image: str) -> None:
        """Pull image if not present."""
        try:
            self._client.images.get(image)
            console.print(f"[cyan][FOUNDRY] Image ready: {image}[/cyan]")
        except ImageNotFound:
            console.print(f"[yellow][FOUNDRY] Pulling: {image}...[/yellow]")
            self._client.images.pull(image)
            console.print(f"[green][FOUNDRY] Pulled: {image}[/green]")

    def build(self, manifest: GantryManifest, mission_id: str, deploy: bool = True) -> BuildResult:
        """
        Execute Fabrication Instructions in a Project Pod.

        Args:
            manifest: The GantryManifest (Fabrication Instructions).
            mission_id: Mission ID for evidence tracking.
            deploy: Whether to deploy to Vercel (default True, set False for tests).

        Returns:
            BuildResult with audit outcome.

        Raises:
            BuildTimeoutError: Dead Man's Switch triggered.
            AuditFailedError: audit_command failed.
        """
        start_time = datetime.utcnow()
        project_name = manifest.project_name

        # Initialize Black Box
        blackbox = BlackBox(mission_id)
        blackbox.log("BUILD_STARTED", project_name)
        blackbox.save_manifest(manifest)

        container: Container | None = None
        timeout_triggered = threading.Event()

        def _dead_mans_switch():
            """Kill container after timeout."""
            timeout_triggered.set()
            if container:
                try:
                    console.print("[red][FOUNDRY] TIMEOUT! Killing Pod...[/red]")
                    container.kill()
                    container.remove(force=True)
                except Exception:
                    pass

        # Start Dead Man's Switch
        timer = threading.Timer(BUILD_TIMEOUT_SECONDS, _dead_mans_switch)
        timer.daemon = True
        timer.start()

        try:
            console.print(
                f"[cyan][FOUNDRY] Building: {project_name} (TTL: {BUILD_TIMEOUT_SECONDS}s)[/cyan]"
            )
            blackbox.log("POD_INIT")

            # Get image (prefer universal builder)
            image = self._get_image(manifest.stack)
            self._ensure_image(image)
            blackbox.log("IMAGE_READY", image)

            # Spawn Pod with resource limits
            console.print(f"[cyan][FOUNDRY] Spawning Pod (mem: {MEMORY_LIMIT})...[/cyan]")

            try:
                container = self._client.containers.run(
                    image,
                    command="tail -f /dev/null",
                    name=f"gantry_{mission_id[:8]}",
                    detach=True,
                    auto_remove=False,
                    working_dir="/workspace",
                    mem_limit=MEMORY_LIMIT,
                )
            except APIError as e:
                if "Conflict" in str(e):
                    console.print("[yellow][FOUNDRY] Removing stale Pod...[/yellow]")
                    try:
                        old = self._client.containers.get(f"gantry_{mission_id[:8]}")
                        old.remove(force=True)
                    except Exception:
                        pass
                    container = self._client.containers.run(
                        image,
                        command="tail -f /dev/null",
                        name=f"gantry_{mission_id[:8]}",
                        detach=True,
                        auto_remove=False,
                        working_dir="/workspace",
                        mem_limit=MEMORY_LIMIT,
                    )
                else:
                    raise

            blackbox.log("POD_SPAWNED", container.short_id)
            console.print(f"[green][FOUNDRY] Pod active: {container.short_id}[/green]")

            if timeout_triggered.is_set():
                raise BuildTimeoutError("Dead Man's Switch triggered")

            # Inject files
            console.print(f"[cyan][FOUNDRY] Injecting {len(manifest.files)} files...[/cyan]")
            tar_data = self._create_tar(manifest)
            container.put_archive("/workspace", tar_data)
            blackbox.log("FILES_INJECTED", str(len(manifest.files)))

            # Inject uploaded design-reference image into repo (public/ so it is served)
            mission_folder = MISSIONS_DIR / mission_id
            design_ref = self._find_design_reference(mission_folder)
            if design_ref:
                design_tar = self._create_design_image_tar(mission_folder, design_ref)
                if design_tar:
                    container.put_archive("/workspace", design_tar)
                    blackbox.log("DESIGN_IMAGE_INJECTED", design_ref)
                    console.print(f"[cyan][FOUNDRY] Design image added: public/{design_ref}[/cyan]")

            if timeout_triggered.is_set():
                raise BuildTimeoutError("Dead Man's Switch triggered")

            # Install dependencies if requirements.txt exists (Python)
            has_requirements = any(f.path == "requirements.txt" for f in manifest.files)
            if has_requirements and manifest.stack == StackType.PYTHON:
                console.print("[cyan][FOUNDRY] Installing Python dependencies...[/cyan]")
                blackbox.log("DEPS_INSTALL_STARTED", "requirements.txt")

                dep_exit, dep_output = container.exec_run(
                    cmd=["sh", "-c", "pip install -r requirements.txt --quiet"],
                    workdir="/workspace",
                )

                if dep_exit != 0:
                    dep_output_str = (
                        dep_output.decode("utf-8")
                        if isinstance(dep_output, bytes)
                        else str(dep_output)
                    )
                    console.print(
                        f"[yellow][FOUNDRY] Dependency install warning: {dep_output_str[:100]}[/yellow]"
                    )
                    blackbox.log("DEPS_INSTALL_WARNING", dep_output_str[:200])
                else:
                    blackbox.log("DEPS_INSTALLED")
                    console.print("[green][FOUNDRY] Dependencies installed[/green]")

            # Install dependencies if package.json exists (Node)
            has_package_json = any(f.path == "package.json" for f in manifest.files)
            if has_package_json and manifest.stack == StackType.NODE:
                console.print("[cyan][FOUNDRY] Installing Node dependencies...[/cyan]")
                blackbox.log("DEPS_INSTALL_STARTED", "package.json")

                dep_exit, dep_output = container.exec_run(
                    cmd=["sh", "-c", "npm install --silent"],
                    workdir="/workspace",
                )

                if dep_exit == 0:
                    blackbox.log("DEPS_INSTALLED")
                    console.print("[green][FOUNDRY] Dependencies installed[/green]")

            if timeout_triggered.is_set():
                raise BuildTimeoutError("Dead Man's Switch triggered")

            # Run Critic (audit_command)
            console.print(f"[cyan][FOUNDRY] Running audit: {manifest.audit_command}[/cyan]")
            blackbox.log("AUDIT_STARTED", manifest.audit_command)

            exit_code, output = container.exec_run(
                cmd=["sh", "-c", manifest.audit_command],
                workdir="/workspace",
            )

            output_str = output.decode("utf-8") if isinstance(output, bytes) else str(output)
            duration = (datetime.utcnow() - start_time).total_seconds()

            # Critic's Verdict
            if exit_code != 0:
                console.print(f"[red][FOUNDRY] Audit FAILED (exit: {exit_code})[/red]")
                blackbox.save_audit_fail(exit_code, output_str)
                blackbox.log("BUILD_FAILED")
                blackbox.finalize()

                container.remove(force=True)
                raise AuditFailedError(
                    f"Audit failed with exit code {exit_code}",
                    exit_code=exit_code,
                    output=output_str,
                )

            console.print(f"[green][FOUNDRY] Audit PASSED ({duration:.1f}s)[/green]")
            blackbox.save_audit_pass(output_str)
            blackbox.log("BUILD_COMPLETE", f"Duration: {duration:.1f}s")

            # STRUCTURE CHECK: Verify Vercel serverless format before deploying
            if manifest.stack in (StackType.NODE, StackType.PYTHON):
                blackbox.log("STRUCTURE_CHECK_STARTED", "Verifying Vercel format")

                structure_valid = self._verify_serverless_structure(container, manifest)
                if not structure_valid:
                    blackbox.save_audit_fail(-1, "Invalid Vercel serverless structure")
                    blackbox.log("STRUCTURE_CHECK_FAILED")
                    blackbox.finalize()
                    container.remove(force=True)
                    raise AuditFailedError(
                        "Vercel structure check failed",
                        exit_code=-1,
                        output="Project must have api/index.js (or .py) with proper exports, and vercel.json with rewrites. See Vercel serverless function format.",
                    )

                blackbox.log("STRUCTURE_CHECK_PASSED")
                console.print("[green][FOUNDRY] Vercel structure check PASSED[/green]")

            # Deploy to Vercel (if configured, using builder image, and deploy=True)
            deploy_url = None
            if not deploy:
                console.print("[yellow][FOUNDRY] Vercel deployment skipped (deploy=false)[/yellow]")
                blackbox.log("DEPLOY_SKIPPED", "deploy=false")
            elif self._deployer.is_configured() and self._use_builder_image:
                blackbox.log("DEPLOY_STARTED", "Vercel")
                try:
                    deploy_url = self._deployer.deploy_mission(container, project_name)
                    blackbox.log("DEPLOY_COMPLETE", deploy_url)
                except DeploymentError as e:
                    console.print(f"[yellow][FOUNDRY] Deployment warning: {e}[/yellow]")
                    blackbox.log("DEPLOY_FAILED", str(e))

            blackbox.finalize()

            # Cleanup Pod
            container.remove(force=True)

            return BuildResult(
                container_id=container.short_id,
                project_name=project_name,
                audit_passed=True,
                duration_seconds=duration,
                deploy_url=deploy_url,
            )

        except BuildTimeoutError:
            blackbox.log("TIMEOUT_TRIGGERED", f"Limit: {BUILD_TIMEOUT_SECONDS}s")
            blackbox.save_audit_fail(-1, "Dead Man's Switch triggered - build timeout")
            blackbox.finalize()
            raise

        except AuditFailedError:
            raise

        except Exception as e:
            blackbox.log("BUILD_ERROR", str(e))
            blackbox.save_audit_fail(-1, str(e))
            blackbox.finalize()

            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            raise

        finally:
            timer.cancel()
