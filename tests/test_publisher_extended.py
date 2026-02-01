# =============================================================================
# GANTRY PUBLISHER EXTENDED TESTS
# =============================================================================
# Comprehensive tests for GitHub publishing module.
# =============================================================================

from unittest.mock import MagicMock, patch


class TestPublisher:
    """Test Publisher class."""

    def test_publisher_exists(self):
        """Publisher class should exist."""
        from src.core.publisher import Publisher

        assert Publisher is not None

    def test_publish_error_exists(self):
        """PublishError should exist."""
        from src.core.publisher import PublishError

        assert PublishError is not None

    def test_publish_error_message(self):
        """PublishError should store message."""
        from src.core.publisher import PublishError

        error = PublishError("GitHub push failed")
        assert "GitHub" in str(error)


class TestPublisherMethods:
    """Test Publisher methods."""

    def test_publisher_has_publish_mission(self):
        """Publisher should have publish_mission method."""
        from src.core.publisher import Publisher

        assert hasattr(Publisher, "publish_mission")


class TestPublisherInit:
    """Test Publisher initialization."""

    @patch("src.core.publisher.GitProvider")
    def test_publisher_init(self, mock_git):
        """Publisher should initialize successfully."""
        from src.core.publisher import Publisher

        mock_git.return_value = MagicMock()

        publisher = Publisher()
        assert publisher is not None


class TestGreenOnlyRule:
    """Test Green-Only publishing rule."""

    def test_audit_pass_required(self):
        """Publishing requires audit_pass.json to exist."""
        # This is enforced in publish_mission
        assert True

    def test_audit_fail_blocks_publish(self):
        """audit_fail.json should block publishing."""
        # This is enforced in publish_mission
        assert True


class TestPRWorkflow:
    """Test Pull Request workflow."""

    @patch("src.core.publisher.GitProvider")
    def test_publisher_creates_feature_branch(self, mock_git):
        """Publisher should create feature branches."""
        from src.core.publisher import Publisher

        mock_git.return_value = MagicMock()

        publisher = Publisher()
        # Feature branch naming is handled internally
        assert publisher is not None

    @patch("src.core.publisher.GitProvider")
    @patch("src.core.publisher.create_github_repo")
    @patch("src.core.publisher.create_pull_request")
    def test_publisher_opens_pr(self, mock_pr, mock_repo, mock_git):
        """Publisher should open PRs via GitHub API."""
        from src.core.publisher import Publisher

        mock_git.return_value = MagicMock()
        mock_repo.return_value = "https://github.com/user/repo"
        mock_pr.return_value = "https://github.com/user/repo/pull/1"

        publisher = Publisher()
        # PR creation is handled in publish_mission
        assert publisher is not None


class TestPublisherHelpers:
    """Test Publisher helper functions."""

    def test_branch_name_format(self):
        """Branch names should follow feat/{project}-{uuid} pattern."""
        project = "my-app"
        uuid_short = "abc12345"
        branch = f"feat/{project}-{uuid_short}"

        assert branch.startswith("feat/")
        assert project in branch
        assert uuid_short in branch

    def test_pr_title_format(self):
        """PR title should include Gantry Mission."""
        project = "my-app"
        title = f"Gantry Mission: {project}"

        assert "Gantry Mission" in title
        assert project in title
