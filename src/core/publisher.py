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
# THE PUBLISHER - PR ENGINE (Junior Dev Model)
# -----------------------------------------------------------------------------
# Responsibility: Push code to GitHub via Pull Requests for human review.
# Enforces "Green Light Deploy" + "Junior Dev Model" rules.
#
# The Gate:
# - BLOCKS any push if audit status != "PASS"
# - NEVER pushes directly to main/master
# - ALWAYS creates feature branch and opens PR
#
# Why PR Model:
# - Gantry is your Staff Engineer, YOU remain the Lead
# - Prevents accidental secret leaks
# - Human oversight on all deployments
# -----------------------------------------------------------------------------

import json
import os
import re
import shutil
import uuid
from pathlib import Path

from rich.console import Console

from src.domain.models import GantryManifest
from src.infra.git_client import (
    GitError,
    GitProvider,
    PRCreationError,
    RepoCreationError,
    create_github_repo,
    create_pull_request,
)

console = Console()


class SecurityBlock(Exception):
    """Raised when attempting to publish a failed mission."""

    pass


class PublishError(Exception):
    """Raised when publishing fails for non-security reasons."""

    pass


class Publisher:
    """
    The PR Engine (Junior Dev Model).

    Enforces the Gantry Guarantee + Git Safety:
    - "Code is only pushed if the Critic Agent passes audits."
    - "NEVER push directly to main - ALWAYS open a PR."

    Flow:
    1. Check audit_report.json for PASS verdict
    2. If PASS:
       a. Create feature branch: feat/{project}-{short_id}
       b. Commit files to feature branch
       c. Push feature branch
       d. Open Pull Request via GitHub API
    3. If FAIL: Raise SecurityBlock (no code leaves the building)

    Why PR Model:
    - Gantry is your Staff Engineer; YOU remain the Lead
    - Human review before merge prevents accidents
    - Professional workflow for production systems
    """

    def __init__(self) -> None:
        """Initialize Publisher with GitHub credentials from environment."""
        self._token = os.getenv("GITHUB_TOKEN")
        self._username = os.getenv("GITHUB_USERNAME")

        if not self._token:
            console.print("[yellow][PUBLISHER] GITHUB_TOKEN not set - publishing disabled[/yellow]")
        if not self._username:
            console.print(
                "[yellow][PUBLISHER] GITHUB_USERNAME not set - publishing disabled[/yellow]"
            )

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
            except (OSError, json.JSONDecodeError) as e:
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
            except (OSError, json.JSONDecodeError) as e:
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

        console.print(
            f"[cyan][PUBLISHER] Prepared {len(manifest.files)} files for publishing[/cyan]"
        )
        return publish_path

    def publish_mission(
        self,
        manifest: GantryManifest,
        evidence_path: str,
        repo_name: str | None = None,
        mission_id: str | None = None,
    ) -> str:
        """
        Publish a successfully audited mission via Pull Request.

        THE GATE: This method enforces the Green-Only rule.
        Failed audits are BLOCKED from publishing.

        JUNIOR DEV MODEL: Never pushes to main. Always opens a PR.

        Args:
            manifest: The build manifest
            evidence_path: Path to mission evidence folder (string)
            repo_name: Optional repository name (defaults to project_name)
            mission_id: Optional mission ID for branch naming

        Returns:
            The Pull Request URL (not repo URL!)

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

        # Determine repository name
        target_repo = repo_name or manifest.project_name
        target_repo = self._sanitize_repo_name(target_repo)

        # Generate unique feature branch name
        short_id = (mission_id or str(uuid.uuid4()))[:8]
        feature_branch = f"feat/{self._sanitize_repo_name(manifest.project_name)}-{short_id}"

        console.print(f"[cyan][PUBLISHER] Feature branch: {feature_branch}[/cyan]")

        # AUTO-CREATE REPOSITORY via GitHub API (with main branch initialized)
        try:
            create_github_repo(token=self._token, repo_name=target_repo, private=False)
        except RepoCreationError as e:
            console.print(f"[yellow][PUBLISHER] Repo note: {e}[/yellow]")
            # Continue - repo might already exist

        # Initialize Git, commit to feature branch, and push
        try:
            git = GitProvider(str(publish_path))
            git.init_repo()
            git.configure_user(name="Gantry Bot", email="gantry@auto-deploy.local")
            git.add_gitignore()

            # Configure remote
            git.configure_auth(token=self._token, username=self._username, repo_name=target_repo)

            # Commit and push to FEATURE BRANCH (not main!)
            git.commit_and_push(
                branch=feature_branch, message=f"Gantry Mission: {manifest.project_name}"
            )

            console.print(f"[green][PUBLISHER] Branch pushed: {feature_branch}[/green]")

        except GitError as e:
            raise PublishError(f"Git operation failed: {e}")

        # OPEN PULL REQUEST via GitHub API
        try:
            pr_body = self._build_pr_body(manifest, evidence_path)

            pr_url = create_pull_request(
                token=self._token,
                username=self._username,
                repo_name=target_repo,
                branch=feature_branch,
                title=f"Gantry Mission: {manifest.project_name}",
                body=pr_body,
                base="main",
            )

            console.print(f"[green][PUBLISHER] PR opened: {pr_url}[/green]")
            return pr_url

        except PRCreationError as e:
            # Even if PR creation fails, the branch was pushed
            console.print(f"[yellow][PUBLISHER] PR creation failed: {e}[/yellow]")
            repo_url = f"https://github.com/{self._username}/{target_repo}"
            console.print(f"[yellow][PUBLISHER] Branch pushed to: {repo_url}[/yellow]")
            return repo_url

    def _build_pr_body(self, manifest: GantryManifest, evidence_path: Path) -> str:
        """
        Build the Pull Request description body.

        Args:
            manifest: The build manifest
            evidence_path: Path to mission evidence folder

        Returns:
            Formatted PR body text
        """
        return f"""## Gantry Automated Build

**Project:** {manifest.project_name}
**Stack:** {manifest.stack}
**Audit Status:** ✅ PASSED

### Files Generated
{chr(10).join(f"- `{f.path}`" for f in manifest.files)}

### Audit Command
```
{manifest.audit_command}
```

### Run Command
```
{manifest.run_command}
```

---
*This PR was automatically generated by [Gantry Fleet](https://github.com/Jarvis2021/gantry).*
*Evidence Path: `{evidence_path}`*
"""

    def _sanitize_repo_name(self, name: str) -> str:
        """
        Sanitize repository name for GitHub requirements.

        GitHub repo names can only contain:
        - Alphanumeric characters
        - Hyphens (-)
        - Underscores (_)
        - Periods (.)

        Args:
            name: Raw project name

        Returns:
            Sanitized repository name
        """
        # Replace spaces with hyphens
        sanitized = name.replace(" ", "-")
        # Remove any characters that aren't alphanumeric, hyphen, underscore, or period
        sanitized = re.sub(r"[^a-zA-Z0-9\-_.]", "", sanitized)
        # Ensure it doesn't start/end with a period
        sanitized = sanitized.strip(".")
        # Lowercase for consistency
        sanitized = sanitized.lower()

        return sanitized or "gantry-project"
