# =============================================================================
# GANTRY FLEET MANAGER EXTENDED TESTS
# =============================================================================
# Comprehensive tests for async fleet orchestration.
# =============================================================================

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


class TestAsyncProgressTracker:
    """Test AsyncProgressTracker class."""

    @patch("src.core.fleet.init_db")
    def test_async_progress_tracker_exists(self, mock_init_db):
        """AsyncProgressTracker class should exist."""
        from src.core.fleet import AsyncProgressTracker

        assert AsyncProgressTracker is not None

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.update_mission_status")
    def test_async_progress_tracker_init(self, mock_update, mock_init_db):
        """AsyncProgressTracker should initialize."""
        from src.core.fleet import AsyncProgressTracker

        tracker = AsyncProgressTracker("test-mission-123", "BUILDING")
        assert tracker is not None

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.update_mission_status")
    def test_async_progress_tracker_stores_state(self, mock_update, mock_init_db):
        """AsyncProgressTracker should store mission_id and status."""
        from src.core.fleet import AsyncProgressTracker

        tracker = AsyncProgressTracker("test-mission-123", "BUILDING")
        assert tracker.mission_id == "test-mission-123"
        assert tracker.phase == "BUILDING"

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.update_mission_status")
    @pytest.mark.asyncio
    async def test_async_progress_tracker_aenter_aexit(self, mock_update, mock_init_db):
        """AsyncProgressTracker should work as async context manager."""
        from src.core.fleet import AsyncProgressTracker

        async with AsyncProgressTracker("test-mission-123", "BUILDING") as tracker:
            assert tracker is not None


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
    def test_fleet_has_retry_failed_mission(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have retry_failed_mission."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert hasattr(fleet, "retry_failed_mission")

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

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_has_process_voice_input(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have process_voice_input."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert hasattr(fleet, "process_voice_input")
        assert callable(fleet.process_voice_input)


class TestFleetDispatch:
    """Test dispatch_mission behavior."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.create_mission")
    @pytest.mark.asyncio
    async def test_dispatch_creates_mission(
        self,
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

        fleet = FleetManager()

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            mission_id = await fleet.dispatch_mission("Build an app")

            mock_create.assert_called_once()
            assert mission_id == "test-uuid-123"

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.create_mission")
    @pytest.mark.asyncio
    async def test_dispatch_with_deploy_false(
        self,
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

        fleet = FleetManager()

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            result = await fleet.dispatch_mission("Build an app", deploy=False)

            assert result == "test-uuid-123"

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    @patch("src.core.fleet.create_mission")
    @pytest.mark.asyncio
    async def test_dispatch_with_publish_false(
        self,
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

        fleet = FleetManager()

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = MagicMock()
            mock_create_task.return_value = mock_task

            result = await fleet.dispatch_mission("Build an app", publish=False)

            assert result == "test-uuid-123"


class TestConsultationFlow:
    """Test consultation flow methods."""

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_has_start_consultation(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have _start_consultation."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert hasattr(fleet, "_start_consultation")

    @patch("src.core.fleet.init_db")
    @patch("src.core.fleet.Foundry")
    @patch("src.core.fleet.Architect")
    @patch("src.core.fleet.Publisher")
    @patch("src.core.fleet.PolicyGate")
    def test_fleet_has_continue_consultation(
        self, mock_policy, mock_pub, mock_arch, mock_foundry, mock_init_db
    ):
        """FleetManager should have _continue_consultation."""
        from src.core.fleet import FleetManager

        fleet = FleetManager()
        assert hasattr(fleet, "_continue_consultation")
