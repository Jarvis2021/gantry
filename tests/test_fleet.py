# =============================================================================
# GANTRY FLEET MANAGER TESTS
# =============================================================================
# Tests for the fleet orchestration module.
# =============================================================================

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestFleetManager:
    """Test FleetManager class."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_init_creates_fleet(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should initialize successfully."""
        from src.core.fleet import FleetManager
        fleet = FleetManager()
        assert fleet is not None

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_has_dispatch_method(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have dispatch_mission method."""
        from src.core.fleet import FleetManager
        fleet = FleetManager()
        assert hasattr(fleet, "dispatch_mission")
        assert callable(fleet.dispatch_mission)


class TestMissionFlow:
    """Test mission execution flow."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.update_mission_status")
    @patch("src.core.fleet.create_mission")
    def test_dispatch_starts_thread(
        self, mock_create, mock_update, mock_policy, mock_pub, 
        mock_arch, mock_foundry, mock_init_db
    ):
        """dispatch_mission should start a background thread."""
        from src.core.fleet import FleetManager
        fleet = FleetManager()
        
        with patch("src.core.fleet.threading.Thread") as mock_thread:
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance
            
            fleet.dispatch_mission("Build an app")
            
            # Thread should be started
            mock_thread_instance.start.assert_called_once()
