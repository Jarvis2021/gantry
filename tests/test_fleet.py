# =============================================================================
# GANTRY FLEET MANAGER TESTS
# =============================================================================
# Tests for the fleet orchestration module.
# =============================================================================

import pytest
from unittest.mock import MagicMock, patch


class TestFleetManager:
    """Test FleetManager class."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_init_creates_fleet(self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db):
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

    def test_fleet_constants(self):
        """Fleet should have required constants."""
        from src.core.fleet import MAX_RETRIES, PROGRESS_UPDATE_SECONDS

        assert MAX_RETRIES >= 1
        assert PROGRESS_UPDATE_SECONDS > 0

    def test_progress_tracker_exists(self):
        """ProgressTracker class should exist."""
        from src.core.fleet import ProgressTracker

        assert ProgressTracker is not None


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
        self, mock_create, mock_update, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
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

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.create_mission")
    def test_dispatch_accepts_flags(
        self, mock_create, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """dispatch_mission should accept deploy and publish flags."""
        from src.core.fleet import FleetManager

        # create_mission returns a string (UUID)
        mock_create.return_value = "test-uuid-12345678-abcd"

        fleet = FleetManager()

        with patch("src.core.fleet.threading.Thread") as mock_thread:
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance

            # dispatch_mission signature: (prompt, deploy=True, publish=True)
            result = fleet.dispatch_mission("Build app", deploy=False, publish=False)

            # Should have called thread
            mock_thread.assert_called_once()
            # Result should be the mission_id string
            assert result == "test-uuid-12345678-abcd"


class TestProgressTracker:
    """Test ProgressTracker class."""

    @patch("src.core.fleet.init_db")
    def test_progress_tracker_init(self, mock_init_db):
        """ProgressTracker should initialize."""
        from src.core.fleet import ProgressTracker

        tracker = ProgressTracker("test-mission", "BUILDING")
        assert tracker is not None

    @patch("src.core.fleet.init_db")
    def test_progress_tracker_start_stop(self, mock_init_db):
        """ProgressTracker should start and stop."""
        from src.core.fleet import ProgressTracker

        tracker = ProgressTracker("test-mission", "BUILDING")

        # Start returns self
        result = tracker.start()
        assert result == tracker

        # Stop should work without error
        tracker.stop()


class TestFleetIntegration:
    """Integration tests for Fleet module."""

    def test_imports_work(self):
        """All required imports should work."""
        from src.core.fleet import FleetManager, ProgressTracker, MAX_RETRIES

        assert FleetManager is not None
        assert ProgressTracker is not None
        assert MAX_RETRIES is not None

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_has_heal_method(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have _heal_and_retry method."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert hasattr(fleet, "_heal_and_retry")
        assert callable(fleet._heal_and_retry)
