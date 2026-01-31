# =============================================================================
# GANTRY MAIN API TESTS
# =============================================================================
# Tests for the Flask API endpoints.
# =============================================================================

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestHealthEndpoint:
    """Test health check endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_health_returns_ok(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """Health endpoint should return status."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main import app
            client = app.test_client()
            response = client.get("/health")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "online"


class TestAuthEndpoint:
    """Test authentication endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_auth_wrong_password(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """Auth should reject wrong password."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test", "GANTRY_PASSWORD": "correct"}):
            from src.main import app
            client = app.test_client()
            response = client.post("/gantry/auth", json={"password": "wrong"})
            assert response.status_code == 401


class TestMissionsEndpoint:
    """Test missions listing endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.main.list_missions")
    def test_missions_returns_list(
        self, mock_list, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """Missions endpoint should return response with missions."""
        mock_list.return_value = []
        
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main import app
            client = app.test_client()
            response = client.get("/gantry/missions")
            assert response.status_code == 200
            data = response.get_json()
            # Response contains missions array
            assert "missions" in data
            assert isinstance(data["missions"], list)


class TestStaticFiles:
    """Test static file serving."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_index_html_served(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """Root should serve index.html."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main import app
            client = app.test_client()
            response = client.get("/")
            assert response.status_code == 200
            assert b"Gantry" in response.data
