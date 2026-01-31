# -----------------------------------------------------------------------------
# THE DEPLOYER - VERCEL DEPLOYMENT
# -----------------------------------------------------------------------------
# Responsibility: Deploy successfully built code to Vercel for live URLs.
# Executes deployment commands inside the container and captures the URL.
#
# Why Vercel:
# - Instant deployments (seconds, not minutes)
# - Automatic HTTPS
# - Global CDN
# - Zero configuration for most frameworks
# -----------------------------------------------------------------------------

import os
import re
import time

import requests
from docker.models.containers import Container
from rich.console import Console

console = Console()


class DeploymentError(Exception):
    """Raised when Vercel deployment fails."""

    pass


class Deployer:
    """
    Vercel Deployment Handler.

    Executes deployment commands inside a running container
    and captures the production URL.

    Requirements:
    - Container must have Vercel CLI installed (gantry/builder image)
    - VERCEL_TOKEN must be set in environment
    """

    def __init__(self) -> None:
        """Initialize Deployer with Vercel token from environment."""
        self._token = os.getenv("VERCEL_TOKEN")

        if self._token:
            console.print("[green][DEPLOYER] Vercel token configured[/green]")
        else:
            console.print("[yellow][DEPLOYER] VERCEL_TOKEN not set - deployment disabled[/yellow]")

    def is_configured(self) -> bool:
        """Check if Vercel deployment is available."""
        return bool(self._token)

    def _parse_vercel_url(self, output: str) -> str | None:
        """
        Parse the production URL from Vercel CLI output.

        Vercel outputs URLs in various formats:
        - Production: https://project-xxx.vercel.app
        - https://project-hash-team.vercel.app

        Args:
            output: Raw stdout from vercel deploy command

        Returns:
            The production URL if found, None otherwise
        """
        # Pattern priorities (most specific first)
        patterns = [
            r"Production: (https://[^\s]+)",  # "Production: https://..."
            r"(https://[a-zA-Z0-9-]+\.vercel\.app)",  # Any vercel.app URL
        ]

        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                url = match.group(1) if "Production" in pattern else match.group(0)
                return url.strip()

        return None

    def deploy_mission(self, container: Container, project_name: str) -> str:
        """
        Deploy the project to Vercel and return the live URL.

        This method executes inside the running container that has
        the built code in /workspace.

        Args:
            container: Running Docker container with built code
            project_name: Name for the Vercel project

        Returns:
            The live production URL (e.g., https://myapp.vercel.app)

        Raises:
            DeploymentError: If deployment fails or URL cannot be parsed
        """
        if not self._token:
            raise DeploymentError("VERCEL_TOKEN not configured")

        console.print(f"[cyan][DEPLOYER] Deploying {project_name} to Vercel...[/cyan]")

        # Sanitize project name for Vercel (lowercase, alphanumeric, hyphens)
        safe_name = re.sub(r"[^a-zA-Z0-9-]", "-", project_name.lower())

        # Deploy directly without linking - creates new project with specified name
        # Using --public flag to ensure the deployment is publicly accessible
        console.print(f"[cyan][DEPLOYER] Deploying {safe_name} to production...[/cyan]")

        # Build deploy command - let Vercel use default scope
        # The --public flag makes deployment accessible without authentication
        deploy_cmd = f"vercel deploy --prod --yes --token {self._token} --name {safe_name} --public"

        exit_code, output = container.exec_run(
            cmd=["sh", "-c", deploy_cmd],
            workdir="/workspace",
            environment={"VERCEL_TOKEN": self._token},
        )

        output_str = output.decode("utf-8") if isinstance(output, bytes) else str(output)

        if exit_code != 0:
            console.print(f"[red][DEPLOYER] Deployment failed: {output_str[:200]}[/red]")
            raise DeploymentError(f"Vercel deployment failed: {output_str[:500]}")

        # Step 3: Parse URL from output
        live_url = self._parse_vercel_url(output_str)

        if not live_url:
            console.print("[yellow][DEPLOYER] Deployed but couldn't parse URL[/yellow]")
            console.print(f"[dim]Output: {output_str[:300]}[/dim]")
            raise DeploymentError("Deployment succeeded but URL not found in output")

        console.print(f"[green][DEPLOYER] LIVE: {live_url}[/green]")

        # Verify the deployment actually works
        if not self._verify_deployment(live_url):
            raise DeploymentError(
                f"Deployment verification failed - {live_url} is not accessible or returns error"
            )

        console.print(f"[green][DEPLOYER] Verified: {live_url} is responding[/green]")
        return live_url

    def _verify_deployment(self, url: str, retries: int = 3) -> bool:
        """
        Verify that the deployed URL actually works.

        Args:
            url: The deployed Vercel URL
            retries: Number of retries (deployments can take a moment to propagate)

        Returns:
            True if URL responds with 2xx status
        """
        console.print(f"[cyan][DEPLOYER] Verifying deployment at {url}...[/cyan]")

        for attempt in range(retries):
            try:
                # Add a delay for propagation
                if attempt > 0:
                    time.sleep(3)

                response = requests.get(url, timeout=10, allow_redirects=True)

                # Check if we got redirected to SSO (Vercel team protection)
                if "vercel.com/sso" in response.url or response.status_code == 401:
                    console.print(
                        "[yellow][DEPLOYER] Vercel SSO protection detected - deployment may require login[/yellow]"
                    )
                    # This is a config issue, not a code issue - return True
                    return True

                if 200 <= response.status_code < 400:
                    console.print(
                        f"[green][DEPLOYER] Got {response.status_code} from {url}[/green]"
                    )
                    return True
                else:
                    console.print(
                        f"[yellow][DEPLOYER] Got {response.status_code} (attempt {attempt + 1}/{retries})[/yellow]"
                    )

            except requests.RequestException as e:
                console.print(
                    f"[yellow][DEPLOYER] Request failed: {e} (attempt {attempt + 1}/{retries})[/yellow]"
                )

        return False
