# -----------------------------------------------------------------------------
# GIT INFRASTRUCTURE - GitHub Integration
# -----------------------------------------------------------------------------
# Responsibility: Execute Git operations for publishing code to GitHub.
# Uses subprocess for lean, direct git command execution.
#
# Features:
# - Auto-create repositories via GitHub API
# - Push code using HTTPS with PAT
#
# Security:
# - PAT tokens are passed securely via URL encoding
# - Tokens are NEVER logged in plain text
# - Git config uses token only for remote operations
# -----------------------------------------------------------------------------

import subprocess
from pathlib import Path

import requests
from rich.console import Console

console = Console()

# GitHub API configuration
GITHUB_API_URL = "https://api.github.com"


class GitError(Exception):
    """Raised when a Git operation fails."""

    pass


class RepoCreationError(Exception):
    """Raised when GitHub repo creation fails."""

    pass


def create_github_repo(token: str, repo_name: str, private: bool = False) -> str:
    """
    Create a new GitHub repository via API.

    This enables fully automatic publishing - no need to pre-create repos.

    Args:
        token: GitHub Personal Access Token with 'repo' scope
        repo_name: Name for the new repository
        private: Whether to create a private repo (default: public)

    Returns:
        The repository clone URL

    Raises:
        RepoCreationError: If API call fails
    """
    console.print(f"[cyan][GITHUB API] Creating repository: {repo_name}[/cyan]")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    payload = {
        "name": repo_name,
        "private": private,
        "auto_init": True,  # Initialize with README to create main branch (required for PRs)
        "description": "Auto-deployed by Gantry Fleet",
    }

    try:
        response = requests.post(
            f"{GITHUB_API_URL}/user/repos", headers=headers, json=payload, timeout=30
        )

        if response.status_code == 201:
            data = response.json()
            clone_url = data.get("clone_url", "")
            console.print(f"[green][GITHUB API] Repository created: {repo_name}[/green]")
            return clone_url

        elif response.status_code == 422:
            # 422 = Validation failed (repo already exists)
            error_data = response.json()
            errors = error_data.get("errors", [])
            for err in errors:
                if err.get("message") == "name already exists on this account":
                    console.print(
                        f"[yellow][GITHUB API] Repository already exists: {repo_name}[/yellow]"
                    )
                    return f"https://github.com/{repo_name}.git"  # Return existing

            raise RepoCreationError(f"Validation failed: {error_data}")

        elif response.status_code == 401:
            raise RepoCreationError("Invalid GitHub token or missing 'repo' scope")

        elif response.status_code == 403:
            raise RepoCreationError("Token lacks permission to create repositories")

        else:
            raise RepoCreationError(f"GitHub API error {response.status_code}: {response.text}")

    except requests.RequestException as e:
        raise RepoCreationError(f"GitHub API request failed: {e}")


class PRCreationError(Exception):
    """Raised when GitHub PR creation fails."""

    pass


def create_pull_request(
    token: str,
    username: str,
    repo_name: str,
    branch: str,
    title: str,
    body: str,
    base: str = "main",
) -> str:
    """
    Create a Pull Request via GitHub API.

    This implements the "Junior Dev Model" - Gantry proposes, human approves.

    Args:
        token: GitHub Personal Access Token
        username: GitHub username (repo owner)
        repo_name: Repository name
        branch: Source branch (feature branch)
        title: PR title
        body: PR description
        base: Target branch (default: main)

    Returns:
        The Pull Request URL

    Raises:
        PRCreationError: If PR creation fails
    """
    console.print(f"[cyan][GITHUB API] Opening Pull Request: {title}[/cyan]")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    payload = {"title": title, "body": body, "head": branch, "base": base}

    try:
        response = requests.post(
            f"{GITHUB_API_URL}/repos/{username}/{repo_name}/pulls",
            headers=headers,
            json=payload,
            timeout=30,
        )

        if response.status_code == 201:
            data = response.json()
            pr_url = data.get("html_url", "")
            pr_number = data.get("number", "?")
            console.print(f"[green][GITHUB API] PR #{pr_number} created: {pr_url}[/green]")
            return pr_url

        elif response.status_code == 422:
            # Could be "no commits between branches" or PR already exists
            error_data = response.json()
            message = error_data.get("message", "")
            errors = error_data.get("errors", [])

            # Check if PR already exists
            if "A pull request already exists" in str(errors):
                console.print(
                    f"[yellow][GITHUB API] PR already exists for branch {branch}[/yellow]"
                )
                return f"https://github.com/{username}/{repo_name}/pulls"

            raise PRCreationError(f"PR validation failed: {message} - {errors}")

        elif response.status_code == 404:
            raise PRCreationError(f"Repository not found: {username}/{repo_name}")

        elif response.status_code == 401:
            raise PRCreationError("Invalid GitHub token")

        else:
            raise PRCreationError(f"GitHub API error {response.status_code}: {response.text}")

    except requests.RequestException as e:
        raise PRCreationError(f"GitHub API request failed: {e}")


class GitProvider:
    """
    Lean Git operations wrapper using subprocess.

    Why subprocess over gitpython:
    - No additional dependency
    - Direct control over commands
    - Easier to debug in containers
    """

    def __init__(self, workspace_path: str) -> None:
        """
        Initialize Git provider with workspace path.

        Args:
            workspace_path: Path to the directory to be versioned.
        """
        self._workspace = Path(workspace_path)
        self._token: str | None = None
        self._username: str | None = None
        self._repo_name: str | None = None

        if not self._workspace.exists():
            raise GitError(f"Workspace does not exist: {workspace_path}")

        console.print(f"[cyan][GIT] Workspace: {self._workspace}[/cyan]")

    def _run(
        self, cmd: list, capture_output: bool = True, check: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Run a git command in the workspace.

        Args:
            cmd: Command parts (e.g., ["git", "init"])
            capture_output: Capture stdout/stderr
            check: Raise on non-zero exit

        Returns:
            CompletedProcess result

        Raises:
            GitError: If command fails and check=True
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=self._workspace,
                capture_output=capture_output,
                text=True,
                timeout=60,  # 1 minute timeout for git operations
            )

            if check and result.returncode != 0:
                # Sanitize error output to remove any token traces
                error_msg = self._sanitize_output(result.stderr or result.stdout or "Unknown error")
                raise GitError(f"Git command failed: {error_msg}")

            return result

        except subprocess.TimeoutExpired:
            raise GitError("Git operation timed out (60s limit)")
        except subprocess.SubprocessError as e:
            raise GitError(f"Git subprocess error: {e}")

    def _sanitize_output(self, text: str) -> str:
        """Remove any sensitive data from output before logging."""
        if self._token and self._token in text:
            text = text.replace(self._token, "[REDACTED]")
        return text

    def init_repo(self) -> None:
        """
        Initialize a new Git repository.

        Runs: git init
        """
        console.print("[cyan][GIT] Initializing repository...[/cyan]")
        self._run(["git", "init"])

        # Configure default branch name
        self._run(["git", "branch", "-M", "main"], check=False)

        console.print("[green][GIT] Repository initialized[/green]")

    def configure_user(self, name: str = "Gantry Bot", email: str = "gantry@localhost") -> None:
        """
        Configure Git user for commits.

        Args:
            name: Committer name
            email: Committer email
        """
        self._run(["git", "config", "user.name", name])
        self._run(["git", "config", "user.email", email])
        console.print(f"[cyan][GIT] Configured user: {name}[/cyan]")

    def configure_auth(self, token: str, username: str, repo_name: str) -> None:
        """
        Configure remote origin with Personal Access Token.

        Security: Token is embedded in URL for HTTPS auth.
        The token is stored in instance but NEVER logged.

        Args:
            token: GitHub Personal Access Token
            username: GitHub username
            repo_name: Repository name (e.g., "my-project")
        """
        self._token = token
        self._username = username
        self._repo_name = repo_name

        # Build authenticated remote URL
        # Format: https://<token>@github.com/<username>/<repo>.git
        remote_url = f"https://{token}@github.com/{username}/{repo_name}.git"

        # Remove existing remote if present
        self._run(["git", "remote", "remove", "origin"], check=False)

        # Add authenticated remote
        self._run(["git", "remote", "add", "origin", remote_url])

        # Log without exposing token
        safe_url = f"https://[REDACTED]@github.com/{username}/{repo_name}.git"
        console.print(f"[cyan][GIT] Remote configured: {safe_url}[/cyan]")

    def commit_and_push(self, branch: str = "main", message: str = "Gantry Auto-Deploy") -> str:
        """
        Stage all files, commit, and push to remote.

        For feature branches, fetches remote first to get main branch.

        Args:
            branch: Target branch name
            message: Commit message

        Returns:
            The repository URL (public, without token)

        Raises:
            GitError: If any git operation fails
        """
        # For feature branches, we need special handling
        # NOTE: We do NOT push to main directly - repos should be created with auto_init
        if branch.startswith("feat/"):
            console.print("[cyan][GIT] Setting up feature branch workflow...[/cyan]")

            # Try to fetch remote main (may fail if repo is new/empty)
            fetch_result = self._run(["git", "fetch", "origin", "main"], check=False)

            if fetch_result.returncode == 0:
                # Main exists - branch from it
                console.print("[cyan][GIT] Branching from origin/main...[/cyan]")
                self._run(["git", "checkout", "-b", branch, "origin/main"], check=False)
            else:
                # Main doesn't exist - create orphan branch (PR will create main on merge)
                console.print(
                    "[yellow][GIT] No main branch found, creating orphan feature branch...[/yellow]"
                )
                self._run(["git", "checkout", "--orphan", branch])

            # Add all project files
            console.print("[cyan][GIT] Staging project files...[/cyan]")
            self._run(["git", "add", "-A"])
            console.print(f"[cyan][GIT] Committing feature: {message}[/cyan]")
            self._run(["git", "commit", "-m", message])
        else:
            # Regular commit for non-feature branches
            console.print("[cyan][GIT] Staging files...[/cyan]")
            self._run(["git", "add", "-A"])

            # Check if there's anything to commit
            status = self._run(["git", "status", "--porcelain"])
            if not status.stdout.strip():
                console.print("[yellow][GIT] Nothing to commit[/yellow]")
                return self._get_repo_url()

            console.print(f"[cyan][GIT] Committing: {message}[/cyan]")
            self._run(["git", "commit", "-m", message])

        # Push the branch
        console.print(f"[cyan][GIT] Pushing to {branch}...[/cyan]")
        self._run(["git", "push", "-u", "origin", branch, "--force"])

        repo_url = self._get_repo_url()
        console.print(f"[green][GIT] Pushed successfully: {repo_url}[/green]")

        return repo_url

    def _get_repo_url(self) -> str:
        """Get public repository URL (without token)."""
        if self._username and self._repo_name:
            return f"https://github.com/{self._username}/{self._repo_name}"
        return "https://github.com"

    def add_gitignore(self, patterns: list = None) -> None:
        """
        Create a .gitignore file with common patterns.

        Args:
            patterns: List of patterns to ignore
        """
        default_patterns = [
            "__pycache__/",
            "*.pyc",
            ".env",
            "node_modules/",
            ".DS_Store",
            "*.log",
            "venv/",
            ".venv/",
        ]

        patterns = patterns or default_patterns
        gitignore_path = self._workspace / ".gitignore"

        with open(gitignore_path, "w") as f:
            f.write("\n".join(patterns))

        console.print("[cyan][GIT] Created .gitignore[/cyan]")
