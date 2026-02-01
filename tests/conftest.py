"""
Pytest configuration and fixtures for Gantry tests.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test environment variables
os.environ.setdefault("BEDROCK_API_KEY", "test-api-key")
os.environ.setdefault("GITHUB_TOKEN", "test-github-token")
os.environ.setdefault("GITHUB_USERNAME", "test-user")
os.environ.setdefault("VERCEL_TOKEN", "test-vercel-token")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test_db")


@pytest.fixture
def mock_docker_client():
    """Mock Docker client for testing."""
    client = MagicMock()
    client.ping.return_value = True
    client.images.get.return_value = MagicMock()

    container = MagicMock()
    container.short_id = "abc123"
    container.exec_run.return_value = (0, b"Success")
    container.stop.return_value = None

    client.containers.run.return_value = container

    return client


@pytest.fixture
def temp_mission_dir(tmp_path):
    """Create a temporary mission directory."""
    mission_dir = tmp_path / "test-mission-id"
    mission_dir.mkdir()
    return mission_dir


@pytest.fixture
def mock_github_api():
    """Mock GitHub API responses."""
    with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
        # Mock repo creation
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {
                "html_url": "https://github.com/test/repo",
                "clone_url": "https://github.com/test/repo.git",
            },
        )

        # Mock PR creation
        mock_get.return_value = MagicMock(status_code=200)

        yield {"post": mock_post, "get": mock_get}
