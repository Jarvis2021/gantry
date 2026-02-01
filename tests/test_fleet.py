# =============================================================================
# GANTRY FLEET MANAGER TESTS
# =============================================================================
# Tests for the async fleet orchestration module.
# =============================================================================

from unittest.mock import MagicMock, patch

import pytest


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

    def test_async_progress_tracker_exists(self):
        """AsyncProgressTracker class should exist."""
        from src.core.fleet import AsyncProgressTracker

        assert AsyncProgressTracker is not None


class TestMissionFlow:
    """Test mission execution flow."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.update_mission_status")
    @patch("src.core.fleet.create_mission")
    @pytest.mark.asyncio
    async def test_dispatch_creates_task(
        self, mock_create, mock_update, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """dispatch_mission should create an async task."""
        from src.core.fleet import FleetManager

        mock_create.return_value = "test-uuid-123"

        fleet = FleetManager()

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            result = await fleet.dispatch_mission("Build an app")

            # Should return mission ID
            assert result == "test-uuid-123"

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.create_mission")
    @pytest.mark.asyncio
    async def test_dispatch_accepts_flags(
        self, mock_create, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """dispatch_mission should accept deploy and publish flags."""
        from src.core.fleet import FleetManager

        mock_create.return_value = "test-uuid-12345678-abcd"

        fleet = FleetManager()

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            result = await fleet.dispatch_mission("Build app", deploy=False, publish=False)

            assert result == "test-uuid-12345678-abcd"


class TestAsyncProgressTracker:
    """Test AsyncProgressTracker class."""

    @patch("src.core.fleet.init_db")
    def test_async_progress_tracker_init(self, mock_init_db):
        """AsyncProgressTracker should initialize."""
        from src.core.fleet import AsyncProgressTracker

        tracker = AsyncProgressTracker("test-mission", "BUILDING")
        assert tracker is not None

    @patch("src.core.fleet.init_db")
    def test_async_progress_tracker_init_with_status(self, mock_init_db):
        """AsyncProgressTracker should store mission_id and status."""
        from src.core.fleet import AsyncProgressTracker

        tracker = AsyncProgressTracker("test-mission", "BUILDING")
        assert tracker.mission_id == "test-mission"
        assert tracker.phase == "BUILDING"

    @patch("src.core.fleet.init_db")
    @pytest.mark.asyncio
    async def test_async_progress_tracker_context_manager(self, mock_init_db):
        """AsyncProgressTracker should work as async context manager."""
        from src.core.fleet import AsyncProgressTracker

        async with AsyncProgressTracker("test-mission", "BUILDING") as tracker:
            assert tracker is not None


class TestFleetIntegration:
    """Integration tests for Fleet module."""

    def test_imports_work(self):
        """All required imports should work."""
        from src.core.fleet import MAX_RETRIES, AsyncProgressTracker, FleetManager

        assert FleetManager is not None
        assert AsyncProgressTracker is not None
        assert MAX_RETRIES is not None

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_has_run_mission_method(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have _run_mission method."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert hasattr(fleet, "_run_mission")
        assert callable(fleet._run_mission)

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_has_process_voice_input(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have process_voice_input method."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert hasattr(fleet, "process_voice_input")
        assert callable(fleet.process_voice_input)
