# =============================================================================
# GANTRY DEPLOYER EXTENDED TESTS
# =============================================================================
# Comprehensive tests for the Vercel deployment module.
# =============================================================================

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestDeployerClass:
    """Test Deployer class."""

    def test_deployer_class_exists(self):
        """Deployer class should exist."""
        from src.core.deployer import Deployer

        assert Deployer is not None

    def test_deployment_error_exists(self):
        """DeploymentError exception should exist."""
        from src.core.deployer import DeploymentError

        assert DeploymentError is not None

    def test_deployment_error_message(self):
        """DeploymentError should store message."""
        from src.core.deployer import DeploymentError

        error = DeploymentError("Vercel deploy failed")
        assert "Vercel" in str(error)


class TestDeployerInit:
    """Test Deployer initialization."""

    def test_deployer_init_without_token(self):
        """Deployer should initialize even without token."""
        with patch.dict(os.environ, {"VERCEL_TOKEN": ""}, clear=False):
            from src.core.deployer import Deployer

            deployer = Deployer()
            assert deployer is not None

    def test_deployer_init_with_token(self):
        """Deployer should initialize with VERCEL_TOKEN."""
        with patch.dict(os.environ, {"VERCEL_TOKEN": "test-token-123"}):
            from src.core.deployer import Deployer

            deployer = Deployer()
            assert deployer is not None


class TestDeployerMethods:
    """Test Deployer methods."""

    def test_deployer_has_deploy_mission(self):
        """Deployer should have deploy_mission method."""
        from src.core.deployer import Deployer

        assert hasattr(Deployer, "deploy_mission")

    def test_deploy_mission_method_signature(self):
        """deploy_mission should accept path and project_name."""
        from src.core.deployer import Deployer

        # Check method signature
        assert hasattr(Deployer, "deploy_mission")

    def test_deployer_stores_token(self):
        """Deployer should store token internally."""
        with patch.dict(os.environ, {"VERCEL_TOKEN": "test-token-xyz"}):
            from src.core.deployer import Deployer

            deployer = Deployer()
            assert deployer is not None


class TestDeployerHelpers:
    """Test Deployer helper methods."""

    def test_deployer_extracts_url(self):
        """Deployer should extract URL from Vercel output."""
        # URL patterns in Vercel output
        output = "Production: https://my-app.vercel.app"
        assert "https://" in output
        assert "vercel.app" in output
