# =============================================================================
# GANTRY DATABASE MODULE TESTS
# =============================================================================
# Tests for database configuration.
# =============================================================================

from src.core.db import DB_CONFIG


class TestDBConfig:
    """Test database configuration."""

    def test_config_has_required_keys(self):
        """DB config should have all required keys."""
        required_keys = ["host", "port", "user", "password", "database"]
        for key in required_keys:
            assert key in DB_CONFIG

    def test_port_is_integer(self):
        """Port should be an integer."""
        assert isinstance(DB_CONFIG["port"], int)

    def test_database_name_configured(self):
        """Database name should be configured."""
        assert len(DB_CONFIG["database"]) > 0
        assert isinstance(DB_CONFIG["database"], str)
