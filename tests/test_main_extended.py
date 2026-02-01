# =============================================================================
# GANTRY MAIN API EXTENDED TESTS
# =============================================================================
# Comprehensive tests for FastAPI endpoints.
# =============================================================================

import os
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestAppConfiguration:
    """Test FastAPI app configuration."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_app_exists(self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db):
        """FastAPI app should exist."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main_fastapi import app

            assert app is not None

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_app_has_routes(self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db):
        """App should have required routes."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main_fastapi import app

            # Get all registered routes
            routes = [route.path for route in app.routes]

            assert "/" in routes
            assert "/health" in routes


class TestHealthEndpoint:
    """Test /health endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_health_returns_200(self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db):
        """Health endpoint should return 200."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main_fastapi import app

            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_health_returns_status(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """Health endpoint should return status field."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main_fastapi import app

            client = TestClient(app)
            response = client.get("/health")
            data = response.json()
            assert "status" in data


class TestReadyEndpoint:
    """Test /ready endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_ready_returns_200(self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db):
        """Ready endpoint should return 200."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main_fastapi import app

            client = TestClient(app)
            response = client.get("/ready")
            # May return 200 or 503 depending on DB state
            assert response.status_code in [200, 503]


class TestIndexEndpoint:
    """Test / endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_index_serves_html(self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db):
        """Index should serve HTML content."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main_fastapi import app

            client = TestClient(app)
            response = client.get("/")
            assert response.status_code == 200
            assert b"html" in response.content.lower() or b"Gantry" in response.content


class TestAuthEndpoint:
    """Test /gantry/auth endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_auth_requires_password(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """Auth should require password field."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main_fastapi import app

            client = TestClient(app)
            response = client.post("/gantry/auth", json={})
            # Should fail without password (422 validation error or 401)
            assert response.status_code in [400, 401, 422]

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_auth_rejects_wrong_password(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """Auth should reject wrong password."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test", "GANTRY_PASSWORD": "correct123"}):
            from src.main_fastapi import app

            client = TestClient(app)
            response = client.post("/gantry/auth", json={"password": "wrong"})
            assert response.status_code == 401


class TestMissionsEndpoint:
    """Test /gantry/missions endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.main_fastapi.list_missions")
    def test_missions_returns_json(
        self, mock_list, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """Missions endpoint should return JSON."""
        mock_list.return_value = []

        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main_fastapi import app

            client = TestClient(app)
            response = client.get("/gantry/missions")
            assert response.status_code == 200
            assert "application/json" in response.headers.get("content-type", "")


class TestSearchEndpoint:
    """Test /gantry/search endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.search_missions")
    @patch("src.core.db.search_missions")
    def test_search_returns_results(
        self,
        mock_db_search,
        mock_fleet_search,
        mock_policy,
        mock_pub,
        mock_arch,
        mock_foundry,
        mock_init_db,
    ):
        """Search endpoint should return results."""
        mock_db_search.return_value = []
        mock_fleet_search.return_value = []

        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main_fastapi import app

            client = TestClient(app)
            response = client.get("/gantry/search?q=todo")
            assert response.status_code == 200
            data = response.json()
            assert "results" in data


class TestFleetManager:
    """Test FleetManager class."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_class_importable(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager class should be importable."""
        from src.core.fleet import FleetManager

        assert FleetManager is not None
