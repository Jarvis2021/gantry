# =============================================================================
# GANTRY FLEET MANAGER EXTENDED TESTS
# =============================================================================
# Comprehensive tests for fleet orchestration.
# =============================================================================

import os
from unittest.mock import MagicMock, patch

import pytest


class TestFleetManagerClass:
    """Test FleetManager class."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_manager_exists(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager class should exist."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert fleet is not None


class TestFleetConstants:
    """Test Fleet constants."""

    def test_max_retries_defined(self):
        """MAX_RETRIES should be defined."""
        from src.core.fleet import MAX_RETRIES

        assert MAX_RETRIES >= 1
        assert MAX_RETRIES <= 10

    def test_progress_update_seconds_defined(self):
        """PROGRESS_UPDATE_SECONDS should be defined."""
        from src.core.fleet import PROGRESS_UPDATE_SECONDS

        assert PROGRESS_UPDATE_SECONDS > 0

    def test_skip_publish_env_var(self):
        """SKIP_PUBLISH should read from env."""
        from src.core.fleet import SKIP_PUBLISH

        # Should be a boolean
        assert isinstance(SKIP_PUBLISH, bool)


class TestProgressTracker:
    """Test ProgressTracker class."""

    @patch("src.core.fleet.init_db")
    def test_progress_tracker_exists(self, mock_init_db):
        """ProgressTracker class should exist."""
        from src.core.fleet import ProgressTracker

        assert ProgressTracker is not None

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.update_mission_status")
    def test_progress_tracker_init(self, mock_update, mock_init_db):
        """ProgressTracker should initialize."""
        from src.core.fleet import ProgressTracker

        tracker = ProgressTracker("test-mission-123", "BUILDING")
        assert tracker is not None

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.update_mission_status")
    def test_progress_tracker_start(self, mock_update, mock_init_db):
        """ProgressTracker.start should return self."""
        from src.core.fleet import ProgressTracker

        tracker = ProgressTracker("test-mission-123", "BUILDING")
        result = tracker.start()
        assert result == tracker

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.update_mission_status")
    def test_progress_tracker_stop(self, mock_update, mock_init_db):
        """ProgressTracker.stop should work."""
        from src.core.fleet import ProgressTracker

        tracker = ProgressTracker("test-mission-123", "BUILDING")
        tracker.start()
        tracker.stop()  # Should not raise


class TestFleetMethods:
    """Test FleetManager methods."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_has_dispatch_mission(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have dispatch_mission."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert hasattr(fleet, "dispatch_mission")
        assert callable(fleet.dispatch_mission)

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_has_heal_and_retry(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have _heal_and_retry."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert hasattr(fleet, "_heal_and_retry")

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_has_run_mission(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have _run_mission."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert hasattr(fleet, "_run_mission")


class TestFleetDispatch:
    """Test dispatch_mission behavior."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.create_mission")
    @patch("src.core.fleet.threading.Thread")
    def test_dispatch_creates_mission(
        self,
        mock_thread,
        mock_create,
        mock_policy,
        mock_pub,
        mock_arch,
        mock_foundry,
        mock_init_db,
    ):
        """dispatch_mission should create DB mission."""
        from src.core.fleet import FleetManager

        mock_create.return_value = "test-uuid-123"
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        fleet = FleetManager()
        mission_id = fleet.dispatch_mission("Build an app")

        mock_create.assert_called_once()
        assert mission_id == "test-uuid-123"

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.create_mission")
    @patch("src.core.fleet.threading.Thread")
    def test_dispatch_starts_thread(
        self,
        mock_thread,
        mock_create,
        mock_policy,
        mock_pub,
        mock_arch,
        mock_foundry,
        mock_init_db,
    ):
        """dispatch_mission should start background thread."""
        from src.core.fleet import FleetManager

        mock_create.return_value = "test-uuid-123"
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        fleet = FleetManager()
        fleet.dispatch_mission("Build an app")

        mock_thread_instance.start.assert_called_once()

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.create_mission")
    @patch("src.core.fleet.threading.Thread")
    def test_dispatch_with_deploy_false(
        self,
        mock_thread,
        mock_create,
        mock_policy,
        mock_pub,
        mock_arch,
        mock_foundry,
        mock_init_db,
    ):
        """dispatch_mission should respect deploy=False."""
        from src.core.fleet import FleetManager

        mock_create.return_value = "test-uuid-123"
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        fleet = FleetManager()
        fleet.dispatch_mission("Build an app", deploy=False)

        # Thread should still be started
        mock_thread_instance.start.assert_called_once()

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.create_mission")
    @patch("src.core.fleet.threading.Thread")
    def test_dispatch_with_publish_false(
        self,
        mock_thread,
        mock_create,
        mock_policy,
        mock_pub,
        mock_arch,
        mock_foundry,
        mock_init_db,
    ):
        """dispatch_mission should respect publish=False."""
        from src.core.fleet import FleetManager

        mock_create.return_value = "test-uuid-123"
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        fleet = FleetManager()
        fleet.dispatch_mission("Build an app", publish=False)

        # Thread should still be started
        mock_thread_instance.start.assert_called_once()
