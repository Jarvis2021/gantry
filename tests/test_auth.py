# =============================================================================
# GANTRY AUTH MODULE TESTS
# =============================================================================
# Tests for authentication, rate limiting, and content guardrails.
# =============================================================================

import pytest
from unittest.mock import MagicMock, patch
from src.core.auth import (
    hash_password,
    verify_password,
    check_guardrails,
    GuardrailResult,
    RateLimiter,
)


class TestPasswordAuth:
    """Test password authentication functions."""

    def test_hash_password_produces_sha256(self):
        """Hash should be 64 character hex string (SHA256)."""
        result = hash_password("test")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hash_password_is_deterministic(self):
        """Same password should produce same hash."""
        hash1 = hash_password("mypassword")
        hash2 = hash_password("mypassword")
        assert hash1 == hash2

    def test_hash_password_different_inputs(self):
        """Different passwords should produce different hashes."""
        hash1 = hash_password("password1")
        hash2 = hash_password("password2")
        assert hash1 != hash2

    def test_verify_password_with_default(self):
        """Default password 'password' should verify."""
        # Default hash is for "password"
        with patch("src.core.auth.DEFAULT_PASSWORD_HASH", hash_password("password")):
            assert verify_password("password") is True

    def test_verify_password_wrong_password(self):
        """Wrong password should not verify."""
        with patch("src.core.auth.DEFAULT_PASSWORD_HASH", hash_password("correct")):
            assert verify_password("wrong") is False


class TestGuardrails:
    """Test content guardrails."""

    def test_valid_build_request_passes(self):
        """Valid build request should pass guardrails."""
        result = check_guardrails("Build me a todo app with user authentication")
        assert result.passed is True

    def test_too_short_message_fails(self):
        """Messages under 10 chars should fail."""
        result = check_guardrails("hi")
        assert result.passed is False
        assert "too short" in result.reason.lower()

    def test_too_few_words_fails(self):
        """Messages with fewer than 3 words should fail."""
        result = check_guardrails("build app")
        assert result.passed is False

    def test_no_build_intent_fails(self):
        """Messages without build keywords should fail."""
        result = check_guardrails("hello how are you doing today")
        assert result.passed is False
        assert "intent" in result.reason.lower()

    def test_profanity_blocked(self):
        """Profanity should be blocked."""
        result = check_guardrails("build me a damn good website please")
        assert result.passed is False

    def test_keyboard_mashing_blocked(self):
        """Keyboard mashing should be blocked."""
        result = check_guardrails("asdfasdf build app qwerty")
        assert result.passed is False

    def test_valid_complex_request_passes(self):
        """Complex valid request should pass."""
        result = check_guardrails(
            "Create a dashboard with charts showing sales data, "
            "user management, and export functionality"
        )
        assert result.passed is True

    def test_guardrail_result_has_suggestion(self):
        """Failed guardrail should include suggestion."""
        result = check_guardrails("x")
        assert result.passed is False
        assert len(result.suggestion) > 0


class TestRateLimiter:
    """Test rate limiting functionality."""

    def test_allows_initial_requests(self):
        """Should allow requests under the limit."""
        limiter = RateLimiter(window=60, max_requests=10)
        allowed, remaining = limiter.is_allowed("client1")
        assert allowed is True
        assert remaining == 9

    def test_tracks_remaining_correctly(self):
        """Should track remaining requests correctly."""
        limiter = RateLimiter(window=60, max_requests=5)
        for i in range(4):
            allowed, remaining = limiter.is_allowed("client1")
            assert allowed is True
            assert remaining == 5 - i - 1

    def test_blocks_after_limit(self):
        """Should block after limit is reached."""
        limiter = RateLimiter(window=60, max_requests=3)
        for _ in range(3):
            limiter.is_allowed("client1")

        allowed, remaining = limiter.is_allowed("client1")
        assert allowed is False
        assert remaining == 0

    def test_different_clients_independent(self):
        """Different clients should have independent limits."""
        limiter = RateLimiter(window=60, max_requests=2)
        limiter.is_allowed("client1")
        limiter.is_allowed("client1")

        # client1 is at limit
        allowed1, _ = limiter.is_allowed("client1")
        assert allowed1 is False

        # client2 should still be allowed
        allowed2, remaining2 = limiter.is_allowed("client2")
        assert allowed2 is True
        assert remaining2 == 1
