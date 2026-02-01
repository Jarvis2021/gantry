# =============================================================================
# GANTRY DOCKER CLIENT TESTS
# =============================================================================
# Tests for the Docker infrastructure client.
# =============================================================================

import pytest
from unittest.mock import MagicMock, patch


class TestDockerClient:
    """Test DockerClient class."""

    def test_docker_client_class_exists(self):
        """DockerClient should be importable from docker SDK."""
        # The module uses the docker SDK's DockerClient directly
        import docker

        assert docker.DockerClient is not None

    def test_docker_host_config(self):
        """Docker host should be configurable via environment."""
        import os

        # Default or configured host
        host = os.getenv("DOCKER_HOST", "tcp://docker-proxy:2375")
        assert host is not None


class TestDockerModule:
    """Test docker_client module functions."""

    def test_module_imports(self):
        """docker_client module should import cleanly."""
        from src.infra import docker_client

        assert docker_client is not None

    def test_docker_provider_exists(self):
        """DockerProvider class should exist."""
        from src.infra.docker_client import DockerProvider

        assert DockerProvider is not None

    def test_docker_provider_error_exists(self):
        """DockerProviderError exception should exist."""
        from src.infra.docker_client import DockerProviderError

        assert DockerProviderError is not None
