# =============================================================================
# GANTRY AUTH MODULE TESTS
# =============================================================================
# Tests for Argon2 authentication, rate limiting, and content guardrails.
# =============================================================================

from src.core.auth import (
    RateLimiter,
    TokenBucket,
    check_guardrails,
    verify_password,
)


class TestPasswordAuth:
    """Test Argon2 password authentication functions."""

    def test_verify_password_returns_bool(self):
        """verify_password should return boolean."""
        result = verify_password("anypassword")
        assert isinstance(result, bool)

    def test_verify_password_wrong_password(self):
        """Wrong password should not verify (with default)."""
        # Default password is "password"
        result = verify_password("definitely_wrong_password_12345")
        assert result is False


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
        allowed = limiter.is_allowed("client1")
        assert allowed is True

    def test_tracks_requests(self):
        """Should track requests correctly."""
        limiter = RateLimiter(window=60, max_requests=5)
        for i in range(4):
            allowed = limiter.is_allowed("client1")
            assert allowed is True

    def test_blocks_after_limit(self):
        """Should block after limit is reached."""
        limiter = RateLimiter(window=60, max_requests=3)
        for _ in range(3):
            limiter.is_allowed("client1")

        allowed = limiter.is_allowed("client1")
        assert allowed is False

    def test_different_clients_independent(self):
        """Different clients should have independent limits."""
        limiter = RateLimiter(window=60, max_requests=2)
        limiter.is_allowed("client1")
        limiter.is_allowed("client1")

        # client1 is at limit
        allowed1 = limiter.is_allowed("client1")
        assert allowed1 is False

        # client2 should still be allowed
        allowed2 = limiter.is_allowed("client2")
        assert allowed2 is True


class TestTokenBucket:
    """Test TokenBucket rate limiting."""

    def test_token_bucket_initial_tokens(self):
        """TokenBucket should start with max tokens."""
        bucket = TokenBucket(rate=1.0, capacity=10)
        # Should allow multiple requests initially (with user_id)
        for _ in range(10):
            assert bucket.consume("user1") is True

    def test_token_bucket_blocks_when_empty(self):
        """TokenBucket should block when empty."""
        bucket = TokenBucket(rate=0.1, capacity=2)
        bucket.consume("user1")
        bucket.consume("user1")
        # Third should fail (no time for refill)
        assert bucket.consume("user1") is False

    def test_token_bucket_per_user(self):
        """TokenBucket should track per user."""
        bucket = TokenBucket(rate=0.1, capacity=2)
        bucket.consume("user1")
        bucket.consume("user1")
        # user1 is empty, but user2 should have tokens
        assert bucket.consume("user1") is False
        assert bucket.consume("user2") is True
