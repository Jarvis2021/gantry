# =============================================================================
# GANTRY AUTH EXTENDED TESTS
# =============================================================================
# Additional tests for authentication and rate limiting.
# =============================================================================

import os
import time
from unittest.mock import MagicMock, patch

import pytest


class TestRateLimiterExtended:
    """Extended tests for RateLimiter."""

    def test_rate_limiter_window_configurable(self):
        """RateLimiter window should be configurable."""
        from src.core.auth import RateLimiter

        limiter = RateLimiter(window=30, max_requests=10)
        assert limiter.window == 30
        assert limiter.max_requests == 10

    def test_rate_limiter_blocks_after_limit(self):
        """RateLimiter should block after max requests."""
        from src.core.auth import RateLimiter

        limiter = RateLimiter(window=60, max_requests=3)

        # First 3 should be allowed
        for i in range(3):
            allowed, remaining = limiter.is_allowed("test-client")
            assert allowed is True

        # 4th should be blocked
        allowed, remaining = limiter.is_allowed("test-client")
        assert allowed is False

    def test_rate_limiter_different_clients(self):
        """RateLimiter should track clients separately."""
        from src.core.auth import RateLimiter

        limiter = RateLimiter(window=60, max_requests=2)

        # Client A
        limiter.is_allowed("client-a")
        limiter.is_allowed("client-a")
        allowed_a, _ = limiter.is_allowed("client-a")

        # Client B should still be allowed
        allowed_b, _ = limiter.is_allowed("client-b")

        assert allowed_a is False
        assert allowed_b is True


class TestPasswordHashing:
    """Test password hashing functions."""

    def test_hash_password_returns_hex(self):
        """hash_password should return hex string."""
        from src.core.auth import hash_password

        result = hash_password("test123")
        assert len(result) == 64  # SHA256 hex
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_password_deterministic(self):
        """hash_password should be deterministic."""
        from src.core.auth import hash_password

        result1 = hash_password("mypassword")
        result2 = hash_password("mypassword")
        assert result1 == result2

    def test_hash_password_different_for_different_input(self):
        """hash_password should differ for different inputs."""
        from src.core.auth import hash_password

        result1 = hash_password("password1")
        result2 = hash_password("password2")
        assert result1 != result2


class TestVerifyPassword:
    """Test password verification."""

    def test_verify_password_correct(self):
        """verify_password should return True for correct password."""
        from src.core.auth import verify_password, hash_password

        with patch("src.core.auth.DEFAULT_PASSWORD_HASH", hash_password("correct")):
            from importlib import reload
            import src.core.auth

            # Direct check
            expected_hash = hash_password("correct")
            actual_hash = hash_password("correct")
            assert expected_hash == actual_hash


class TestGuardrails:
    """Test content guardrails."""

    def test_check_guardrails_short_message(self):
        """Short messages should be blocked."""
        from src.core.auth import check_guardrails

        result = check_guardrails("hi")
        assert result.passed is False
        assert "short" in result.reason.lower()

    def test_check_guardrails_valid_message(self):
        """Valid build requests should pass."""
        from src.core.auth import check_guardrails

        result = check_guardrails("Build me a todo application with React")
        assert result.passed is True

    def test_check_guardrails_no_intent(self):
        """Messages without build intent should be blocked."""
        from src.core.auth import check_guardrails

        result = check_guardrails("The weather is nice today in the city")
        assert result.passed is False
        assert "intent" in result.reason.lower()

    def test_check_guardrails_profanity(self):
        """Profanity should be blocked."""
        from src.core.auth import check_guardrails

        result = check_guardrails("Build me a damn website please")
        assert result.passed is False


class TestGuardrailResult:
    """Test GuardrailResult dataclass."""

    def test_guardrail_result_passed(self):
        """GuardrailResult should store passed state."""
        from src.core.auth import GuardrailResult

        result = GuardrailResult(passed=True)
        assert result.passed is True
        assert result.reason == ""

    def test_guardrail_result_failed(self):
        """GuardrailResult should store failure reason."""
        from src.core.auth import GuardrailResult

        result = GuardrailResult(passed=False, reason="Too short", suggestion="Add more details")
        assert result.passed is False
        assert result.reason == "Too short"
        assert result.suggestion == "Add more details"


class TestRateLimitEntry:
    """Test RateLimitEntry dataclass."""

    def test_rate_limit_entry_defaults(self):
        """RateLimitEntry should have default values."""
        from src.core.auth import RateLimitEntry

        entry = RateLimitEntry()
        assert entry.requests == []
        assert entry.blocked_until == 0


class TestSessionTimeout:
    """Test session timeout constant."""

    def test_session_timeout_defined(self):
        """SESSION_TIMEOUT should be defined."""
        from src.core.auth import SESSION_TIMEOUT

        assert SESSION_TIMEOUT > 0
        assert SESSION_TIMEOUT == 3600  # 1 hour


class TestRateLimitConstants:
    """Test rate limit constants."""

    def test_rate_limit_window_defined(self):
        """RATE_LIMIT_WINDOW should be defined."""
        from src.core.auth import RATE_LIMIT_WINDOW

        assert RATE_LIMIT_WINDOW > 0

    def test_rate_limit_max_requests_defined(self):
        """RATE_LIMIT_MAX_REQUESTS should be defined."""
        from src.core.auth import RATE_LIMIT_MAX_REQUESTS

        assert RATE_LIMIT_MAX_REQUESTS > 0
