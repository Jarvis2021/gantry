# -----------------------------------------------------------------------------
# DOCKER PROVIDER
# -----------------------------------------------------------------------------
# Responsibility: A robust wrapper around the Docker SDK with connection
# validation and detailed error reporting.
#
# This is part of the Infrastructure layer - it provides low-level Docker
# access to the Foundry without exposing SDK complexity.
# -----------------------------------------------------------------------------

import platform
import subprocess
import time

import docker
from docker import DockerClient
from docker.errors import DockerException
from rich.console import Console
from rich.panel import Panel

console = Console()


class DockerProviderError(Exception):
    """Raised when Docker connection fails and cannot be recovered."""

    pass


class DockerProvider:
    """
    Robust Docker SDK wrapper with auto-wake capability.

    Why this design:
    - Encapsulates all Docker connection logic in one place
    - Provides auto-wake for Docker Desktop (macOS/Windows)
    - Fails fast with clear error messages if Docker is unavailable
    """

    def __init__(self, auto_wake: bool = True) -> None:
        """
        Initialize the Docker provider.

        Args:
            auto_wake: If True, attempt to start Docker Desktop if it's sleeping.
        """
        self._client: DockerClient | None = None
        self._auto_wake = auto_wake

        # Attempt initial connection
        self._connect()

    def _wake_docker(self) -> DockerClient | None:
        """
        Attempt to launch Docker Desktop if it's sleeping.

        Why this exists: Docker Desktop on macOS/Windows often goes to sleep.
        For a voice-activated system, we need to handle this gracefully.

        Returns:
            DockerClient if wake succeeds, None otherwise.
        """
        system = platform.system()
        console.print("[yellow][DOCKER] Engine sleeping. Attempting auto-wake...[/yellow]")

        try:
            if system == "Darwin":  # macOS
                subprocess.run(["open", "-a", "Docker"], check=False)
            elif system == "Windows":
                import os

                default_path = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
                if os.path.exists(default_path):
                    subprocess.Popen([default_path])
                else:
                    console.print(
                        "[yellow][DOCKER] Docker Desktop not found in default location[/yellow]"
                    )
                    return None
            elif system == "Linux":
                # Use user-level systemctl to avoid sudo password hang
                subprocess.run(["systemctl", "--user", "start", "docker"], check=False)

            # Wait for Docker to come online
            with console.status(
                "[yellow]Waiting for Docker Engine (up to 60s)...[/yellow]", spinner="clock"
            ):
                for _ in range(60):
                    try:
                        client = docker.from_env()
                        client.ping()
                        console.print("[green][DOCKER] Engine Online.[/green]")
                        return client
                    except DockerException:
                        time.sleep(1)

            console.print("[red][DOCKER] Wake timeout - Docker did not respond[/red]")
            return None

        except Exception as e:
            console.print(f"[red][DOCKER] Auto-wake failed: {e}[/red]")
            return None

    def _connect(self) -> None:
        """
        Establish connection to Docker daemon.

        Raises:
            DockerProviderError: If connection fails and auto-wake is disabled or fails.
        """
        try:
            self._client = docker.from_env()
            self._client.ping()
            console.print("[green][DOCKER] Connected to Docker Engine[/green]")
        except DockerException:
            if self._auto_wake:
                self._client = self._wake_docker()

            if self._client is None:
                console.print(
                    Panel(
                        "[bold red]CRITICAL: Docker Engine Unavailable[/bold red]\n\n"
                        "1. Open Docker Desktop manually\n"
                        "2. Wait for the green status light\n"
                        "3. Restart Gantry",
                        title="SYSTEM HALT",
                        border_style="red",
                    )
                )
                raise DockerProviderError("Docker Engine is not available")

    def get_client(self) -> DockerClient:
        """
        Get the Docker client, verifying connection is still active.

        Returns:
            Active DockerClient instance.

        Raises:
            DockerProviderError: If Docker connection is lost.
        """
        if self._client is None:
            raise DockerProviderError("Docker client not initialized")

        try:
            self._client.ping()
            return self._client
        except DockerException as e:
            console.print(f"[red][DOCKER] Connection lost: {e}[/red]")

            # Attempt reconnection
            if self._auto_wake:
                self._connect()
                if self._client:
                    return self._client

            raise DockerProviderError(f"Docker connection lost and recovery failed: {e}")

    def is_connected(self) -> bool:
        """
        Check if Docker is currently reachable.

        Returns:
            True if Docker is connected and responsive.
        """
        if self._client is None:
            return False
        try:
            self._client.ping()
            return True
        except DockerException:
            return False
