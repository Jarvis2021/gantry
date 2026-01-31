# =============================================================================
# GANTRY GIT CLIENT EXTENDED TESTS
# =============================================================================
# Comprehensive tests for Git infrastructure.
# =============================================================================

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGitProvider:
    """Test GitProvider class."""

    def test_git_provider_exists(self):
        """GitProvider class should exist."""
        from src.infra.git_client import GitProvider

        assert GitProvider is not None

    def test_git_error_exists(self):
        """GitError should exist."""
        from src.infra.git_client import GitError

        assert GitError is not None

    def test_repo_creation_error_exists(self):
        """RepoCreationError should exist."""
        from src.infra.git_client import RepoCreationError

        assert RepoCreationError is not None

    def test_pr_creation_error_exists(self):
        """PRCreationError should exist."""
        from src.infra.git_client import PRCreationError

        assert PRCreationError is not None


class TestGitProviderMethods:
    """Test GitProvider methods."""

    def test_git_provider_has_init_repo(self):
        """GitProvider should have init_repo method."""
        from src.infra.git_client import GitProvider

        assert hasattr(GitProvider, "init_repo")

    def test_git_provider_has_configure_user(self):
        """GitProvider should have configure_user method."""
        from src.infra.git_client import GitProvider

        assert hasattr(GitProvider, "configure_user")

    def test_git_provider_has_configure_auth(self):
        """GitProvider should have configure_auth method."""
        from src.infra.git_client import GitProvider

        assert hasattr(GitProvider, "configure_auth")

    def test_git_provider_has_commit_and_push(self):
        """GitProvider should have commit_and_push method."""
        from src.infra.git_client import GitProvider

        assert hasattr(GitProvider, "commit_and_push")

    def test_git_provider_has_add_gitignore(self):
        """GitProvider should have add_gitignore method."""
        from src.infra.git_client import GitProvider

        assert hasattr(GitProvider, "add_gitignore")


class TestGitHubFunctions:
    """Test GitHub API functions."""

    def test_create_github_repo_exists(self):
        """create_github_repo function should exist."""
        from src.infra.git_client import create_github_repo

        assert callable(create_github_repo)

    def test_create_pull_request_exists(self):
        """create_pull_request function should exist."""
        from src.infra.git_client import create_pull_request

        assert callable(create_pull_request)

    def test_create_github_repo_signature(self):
        """create_github_repo should have correct signature."""
        from src.infra.git_client import create_github_repo
        import inspect

        sig = inspect.signature(create_github_repo)
        params = list(sig.parameters.keys())
        assert "token" in params
        assert "repo_name" in params

    def test_create_pull_request_signature(self):
        """create_pull_request should have correct signature."""
        from src.infra.git_client import create_pull_request
        import inspect

        sig = inspect.signature(create_pull_request)
        params = list(sig.parameters.keys())
        assert "token" in params
        assert "username" in params
        assert "repo_name" in params


class TestGitProviderInit:
    """Test GitProvider initialization."""

    def test_git_provider_class_callable(self):
        """GitProvider should be callable."""
        from src.infra.git_client import GitProvider

        assert callable(GitProvider)

    def test_git_provider_requires_workspace(self):
        """GitProvider should require workspace_path."""
        from src.infra.git_client import GitProvider
        import inspect

        sig = inspect.signature(GitProvider.__init__)
        params = list(sig.parameters.keys())
        assert "workspace_path" in params


class TestGitOperations:
    """Test git operations."""

    def test_git_provider_has_init_repo(self):
        """GitProvider should have init_repo method."""
        from src.infra.git_client import GitProvider

        assert hasattr(GitProvider, "init_repo")

    def test_git_provider_has_configure_user(self):
        """GitProvider should have configure_user method."""
        from src.infra.git_client import GitProvider

        assert hasattr(GitProvider, "configure_user")
