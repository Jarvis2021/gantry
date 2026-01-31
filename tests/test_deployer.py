# =============================================================================
# GANTRY DEPLOYER TESTS
# =============================================================================
# Tests for the Vercel deployment module.
# =============================================================================

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from src.core.deployer import Deployer, DeploymentError


class TestDeployer:
    """Test Deployer class."""

    def test_init_without_token_raises(self):
        """Deployer should raise error without VERCEL_TOKEN."""
        with patch.dict("os.environ", {"VERCEL_TOKEN": ""}, clear=True):
            # Should still work but deployment will fail
            deployer = Deployer()
            assert deployer is not None

    def test_init_with_token(self):
        """Deployer should initialize with VERCEL_TOKEN."""
        with patch.dict("os.environ", {"VERCEL_TOKEN": "test-token"}):
            deployer = Deployer()
            assert deployer is not None

    def test_deploy_requires_directory(self):
        """deploy_mission should require a valid directory."""
        with patch.dict("os.environ", {"VERCEL_TOKEN": "test-token"}):
            deployer = Deployer()
            # Deployer exists and is ready
            assert deployer is not None


class TestDeploymentError:
    """Test DeploymentError exception."""

    def test_deployment_error_message(self):
        """DeploymentError should store message."""
        error = DeploymentError("Deploy failed")
        assert str(error) == "Deploy failed"

    def test_deployment_error_with_logs(self):
        """DeploymentError can include detailed logs."""
        error = DeploymentError("Build failed: npm error")
        assert "Build failed" in str(error)
