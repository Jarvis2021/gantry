# =============================================================================
# GANTRY GIT CLIENT TESTS
# =============================================================================
# Tests for the Git infrastructure client.
# =============================================================================



class TestGitProvider:
    """Test GitProvider class."""

    def test_git_provider_class_exists(self):
        """GitProvider class should exist."""
        from src.infra.git_client import GitProvider

        assert GitProvider is not None

    def test_git_provider_has_required_attributes(self):
        """GitProvider should have required methods."""
        from src.infra.git_client import GitProvider

        # Check that the class has commit_and_push method
        assert hasattr(GitProvider, "commit_and_push")
        assert hasattr(GitProvider, "init_repo")
        assert hasattr(GitProvider, "configure_user")


class TestGitError:
    """Test GitError exception."""

    def test_git_error_message(self):
        """GitError should store message."""
        from src.infra.git_client import GitError

        error = GitError("Push failed: permission denied")
        assert "Push failed" in str(error)


class TestGitHelpers:
    """Test Git helper functions."""

    def test_branch_name_generation(self):
        """Branch names should follow pattern."""
        # Branch format: feat/{project}-{uuid}
        project = "my-app"
        uuid_short = "abc123"
        branch = f"feat/{project}-{uuid_short}"
        assert branch.startswith("feat/")
        assert project in branch

    def test_create_github_repo_function_exists(self):
        """create_github_repo helper function should exist."""
        from src.infra.git_client import create_github_repo

        assert callable(create_github_repo)

    def test_create_pull_request_function_exists(self):
        """create_pull_request helper function should exist."""
        from src.infra.git_client import create_pull_request

        assert callable(create_pull_request)
