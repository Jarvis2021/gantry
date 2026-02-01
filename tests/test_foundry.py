# =============================================================================
# GANTRY FOUNDRY TESTS
# =============================================================================
# Tests for the Docker container build module.
# =============================================================================

from unittest.mock import MagicMock, patch


class TestFoundry:
    """Test Foundry class."""

    def test_foundry_class_exists(self):
        """Foundry class should exist."""
        from src.core.foundry import Foundry

        assert Foundry is not None

    def test_foundry_has_build_method(self):
        """Foundry should have build method defined."""
        from src.core.foundry import Foundry

        assert hasattr(Foundry, "build")

    def test_builder_image_constant(self):
        """Foundry should use gantry/builder:latest image."""
        from src.core.foundry import BUILDER_IMAGE

        assert "gantry/builder" in BUILDER_IMAGE

    def test_build_timeout_constant(self):
        """Build timeout should be defined."""
        from src.core.foundry import BUILD_TIMEOUT_SECONDS

        assert BUILD_TIMEOUT_SECONDS > 0
        assert BUILD_TIMEOUT_SECONDS <= 300  # Max 5 minutes

    def test_memory_limit_constant(self):
        """Memory limit should be defined."""
        from src.core.foundry import MEMORY_LIMIT

        assert MEMORY_LIMIT is not None
        assert "m" in MEMORY_LIMIT or "g" in MEMORY_LIMIT  # Megabytes or Gigabytes


class TestAuditFailedError:
    """Test AuditFailedError exception."""

    def test_audit_failed_error_message(self):
        """AuditFailedError should store output."""
        from src.core.foundry import AuditFailedError

        error = AuditFailedError("Tests failed", exit_code=1, output="2 errors")
        assert "Tests failed" in str(error)
        assert error.output == "2 errors"
        assert error.exit_code == 1

    def test_audit_failed_error_exit_code(self):
        """AuditFailedError should preserve exit code."""
        from src.core.foundry import AuditFailedError

        error = AuditFailedError("Lint failed", exit_code=127, output="cmd not found")
        assert error.exit_code == 127


class TestBuildResult:
    """Test BuildResult model."""

    def test_build_result_fields(self):
        """BuildResult should have required fields."""
        from src.core.foundry import BuildResult

        result = BuildResult(
            container_id="abc123",
            project_name="TestApp",
            audit_passed=True,
            duration_seconds=10.5,
        )
        assert result.container_id == "abc123"
        assert result.project_name == "TestApp"
        assert result.audit_passed is True
        assert result.duration_seconds == 10.5

    def test_build_result_optional_deploy_url(self):
        """BuildResult should handle optional deploy_url."""
        from src.core.foundry import BuildResult

        result = BuildResult(
            container_id="def456",
            project_name="FailedApp",
            audit_passed=False,
            duration_seconds=5.0,
        )
        assert result.audit_passed is False
        assert result.deploy_url is None

    def test_build_result_with_deploy_url(self):
        """BuildResult should store deploy_url when provided."""
        from src.core.foundry import BuildResult

        result = BuildResult(
            container_id="ghi789",
            project_name="DeployedApp",
            audit_passed=True,
            duration_seconds=15.0,
            deploy_url="https://my-app.vercel.app",
        )
        assert result.deploy_url == "https://my-app.vercel.app"


class TestBlackBox:
    """Test BlackBox logging class."""

    def test_blackbox_class_exists(self):
        """BlackBox class should exist."""
        from src.core.foundry import BlackBox

        assert BlackBox is not None

    def test_blackbox_init(self):
        """BlackBox should initialize with mission_id."""
        from src.core.foundry import BlackBox

        with patch("src.core.foundry.Path.mkdir"):
            box = BlackBox("test-mission-123")
            assert box is not None

    def test_blackbox_has_log_method(self):
        """BlackBox should have log method."""
        from src.core.foundry import BlackBox

        assert hasattr(BlackBox, "log")


class TestFoundryMethods:
    """Test Foundry methods with mocking."""

    @patch("src.core.foundry.Deployer")
    @patch("src.core.foundry.docker")
    def test_foundry_init(self, mock_docker, mock_deployer):
        """Foundry should initialize successfully."""
        from src.core.foundry import Foundry

        mock_docker.DockerClient.return_value = MagicMock()

        foundry = Foundry()
        assert foundry is not None

    def test_foundry_has_attributes(self):
        """Foundry should have required attributes."""
        from src.core.foundry import Foundry

        # Check class has the build method
        assert hasattr(Foundry, "build")
        assert callable(Foundry.build)
