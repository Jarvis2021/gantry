# =============================================================================
# GANTRY MAIN API EXTENDED TESTS
# =============================================================================
# Comprehensive tests for Flask API endpoints.
# =============================================================================

import os
from unittest.mock import MagicMock, patch

import pytest


class TestAppConfiguration:
    """Test Flask app configuration."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_app_exists(self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db):
        """Flask app should exist."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main import app

            assert app is not None

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_app_has_routes(self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db):
        """App should have required routes."""
        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main import app

            # Get all registered routes
            rules = [rule.rule for rule in app.url_map.iter_rules()]

            assert "/" in rules
            assert "/health" in rules


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
            from src.main import app

            client = app.test_client()
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
            from src.main import app

            client = app.test_client()
            response = client.get("/health")
            data = response.get_json()
            assert "status" in data


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
            from src.main import app

            client = app.test_client()
            response = client.get("/")
            assert response.status_code == 200
            assert b"html" in response.data.lower() or b"Gantry" in response.data


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
            from src.main import app

            client = app.test_client()
            response = client.post("/gantry/auth", json={})
            # Should fail without password
            assert response.status_code in [400, 401]

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
            from src.main import app

            client = app.test_client()
            response = client.post("/gantry/auth", json={"password": "wrong"})
            assert response.status_code == 401


class TestMissionsEndpoint:
    """Test /gantry/missions endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.main.list_missions")
    def test_missions_returns_json(
        self, mock_list, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """Missions endpoint should return JSON."""
        mock_list.return_value = []

        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main import app

            client = app.test_client()
            response = client.get("/gantry/missions")
            assert response.status_code == 200
            assert response.content_type == "application/json"


class TestSearchEndpoint:
    """Test /gantry/search endpoint."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.db.search_missions")
    def test_search_returns_results(
        self,
        mock_search,
        mock_policy,
        mock_pub,
        mock_arch,
        mock_foundry,
        mock_init_db,
    ):
        """Search endpoint should return results."""
        mock_search.return_value = []

        with patch.dict(os.environ, {"BEDROCK_API_KEY": "test"}):
            from src.main import app

            client = app.test_client()
            response = client.get("/gantry/search?q=todo")
            assert response.status_code == 200
            data = response.get_json()
            assert "results" in data


class TestPrintBanner:
    """Test print_banner function."""

    def test_print_banner_exists(self):
        """print_banner function should exist."""
        from src.main import print_banner

        assert callable(print_banner)


class TestFleetManager:
    """Test FleetManager instance."""

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
