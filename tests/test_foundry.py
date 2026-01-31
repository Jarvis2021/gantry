# =============================================================================
# GANTRY FOUNDRY TESTS
# =============================================================================
# Tests for the Docker container build module.
# =============================================================================

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


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


class TestAuditFailedError:
    """Test AuditFailedError exception."""

    def test_audit_failed_error_message(self):
        """AuditFailedError should store output."""
        from src.core.foundry import AuditFailedError

        error = AuditFailedError("Tests failed", exit_code=1, output="2 errors")
        assert "Tests failed" in str(error)
        assert error.output == "2 errors"
        assert error.exit_code == 1


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
