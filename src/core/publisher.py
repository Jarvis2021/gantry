# -----------------------------------------------------------------------------
# THE PUBLISHER - GREEN-ONLY PUSH
# -----------------------------------------------------------------------------
# Responsibility: Push successfully audited code to GitHub.
# Enforces the "Green Light Deploy" rule - only passing builds get published.
#
# The Gate:
# - Reads audit_report.json from evidence path
# - BLOCKS any push if audit status != "PASS"
# - This is the final security checkpoint before code goes public
# -----------------------------------------------------------------------------

import json
import os
import shutil
from pathlib import Path
from typing import Optional

from rich.console import Console

from src.domain.models import GantryManifest
from src.infra.git_client import GitProvider, GitError

console = Console()


class SecurityBlock(Exception):
    """Raised when attempting to publish a failed mission."""
    pass


class PublishError(Exception):
    """Raised when publishing fails for non-security reasons."""
    pass


class Publisher:
    """
    The Green-Only Publisher.
    
    Enforces the core Gantry Guarantee:
    "Code is only pushed if the Critic Agent passes audits."
    
    Flow:
    1. Check audit_report.json for PASS verdict
    2. If PASS: Initialize git, commit files, push to GitHub
    3. If FAIL: Raise SecurityBlock (no code leaves the building)
    """

    def __init__(self) -> None:
        """Initialize Publisher with GitHub credentials from environment."""
        self._token = os.getenv("GITHUB_TOKEN")
        self._username = os.getenv("GITHUB_USERNAME")
        
        if not self._token:
            console.print("[yellow][PUBLISHER] GITHUB_TOKEN not set - publishing disabled[/yellow]")
        if not self._username:
            console.print("[yellow][PUBLISHER] GITHUB_USERNAME not set - publishing disabled[/yellow]")
        
        if self._token and self._username:
            console.print("[green][PUBLISHER] GitHub credentials loaded[/green]")

    def is_configured(self) -> bool:
        """Check if GitHub credentials are available."""
        return bool(self._token and self._username)

    def _check_audit_status(self, evidence_path: Path) -> bool:
        """
        Check the audit verdict from evidence files.
        
        Args:
            evidence_path: Path to mission evidence folder
            
        Returns:
            True if audit passed, False otherwise
            
        Raises:
            PublishError: If evidence files cannot be read
        """
        # Check for audit_pass.json (preferred)
        audit_pass_path = evidence_path / "audit_pass.json"
        if audit_pass_path.exists():
            try:
                with open(audit_pass_path) as f:
                    data = json.load(f)
                    if data.get("verdict") == "PASS":
                        console.print("[green][PUBLISHER] Audit verdict: PASS[/green]")
                        return True
            except (json.JSONDecodeError, IOError) as e:
                raise PublishError(f"Failed to read audit_pass.json: {e}")
        
        # Check for audit_fail.json
        audit_fail_path = evidence_path / "audit_fail.json"
        if audit_fail_path.exists():
            console.print("[red][PUBLISHER] Audit verdict: FAIL[/red]")
            return False
        
        # Check for audit_report.json (legacy format)
        audit_report_path = evidence_path / "audit_report.json"
        if audit_report_path.exists():
            try:
                with open(audit_report_path) as f:
                    data = json.load(f)
                    status = data.get("status", "").upper()
                    if status == "PASS":
                        console.print("[green][PUBLISHER] Audit verdict: PASS[/green]")
                        return True
                    else:
                        console.print(f"[red][PUBLISHER] Audit verdict: {status}[/red]")
                        return False
            except (json.JSONDecodeError, IOError) as e:
                raise PublishError(f"Failed to read audit_report.json: {e}")
        
        raise PublishError("No audit evidence found in mission folder")

    def _prepare_publish_folder(self, manifest: GantryManifest, evidence_path: Path) -> Path:
        """
        Create a clean folder with only the source files for publishing.
        
        Args:
            manifest: The build manifest with file specs
            evidence_path: Path to mission evidence folder
            
        Returns:
            Path to the prepared publish folder
        """
        publish_path = evidence_path / "publish"
        
        # Clean and create
        if publish_path.exists():
            shutil.rmtree(publish_path)
        publish_path.mkdir(parents=True)
        
        # Write each file from manifest
        for file_spec in manifest.files:
            file_path = publish_path / file_spec.path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w") as f:
                f.write(file_spec.content)
        
        console.print(f"[cyan][PUBLISHER] Prepared {len(manifest.files)} files for publishing[/cyan]")
        return publish_path

    def publish_mission(
        self, 
        manifest: GantryManifest, 
        evidence_path: str,
        repo_name: Optional[str] = None
    ) -> str:
        """
        Publish a successfully audited mission to GitHub.
        
        THE GATE: This method enforces the Green-Only rule.
        Failed audits are BLOCKED from publishing.
        
        Args:
            manifest: The build manifest
            evidence_path: Path to mission evidence folder (string)
            repo_name: Optional repository name (defaults to project_name)
            
        Returns:
            The GitHub repository URL
            
        Raises:
            SecurityBlock: If audit did not pass (Green-Only violation)
            PublishError: If publishing fails for other reasons
        """
        evidence_path = Path(evidence_path)
        
        console.print(f"[cyan][PUBLISHER] Publishing: {manifest.project_name}[/cyan]")
        
        # THE GATE: Check audit status
        if not self._check_audit_status(evidence_path):
            raise SecurityBlock(
                "Cannot publish failed mission. "
                "The Green-Only rule blocks deployment of unaudited code."
            )
        
        # Check credentials
        if not self.is_configured():
            raise PublishError(
                "GitHub credentials not configured. "
                "Set GITHUB_TOKEN and GITHUB_USERNAME environment variables."
            )
        
        # Prepare publish folder with source files
        publish_path = self._prepare_publish_folder(manifest, evidence_path)
        
        # Initialize Git
        try:
            git = GitProvider(str(publish_path))
            git.init_repo()
            git.configure_user(name="Gantry Bot", email="gantry@auto-deploy.local")
            
            # Add .gitignore
            git.add_gitignore()
            
            # Configure remote
            target_repo = repo_name or manifest.project_name
            git.configure_auth(
                token=self._token,
                username=self._username,
                repo_name=target_repo
            )
            
            # Commit and push
            repo_url = git.commit_and_push(
                branch="main",
                message=f"Gantry Auto-Deploy: {manifest.project_name}"
            )
            
            console.print(f"[green][PUBLISHER] Published: {repo_url}[/green]")
            return repo_url
            
        except GitError as e:
            raise PublishError(f"Git operation failed: {e}")
