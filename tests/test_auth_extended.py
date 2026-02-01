# =============================================================================
# GANTRY AUTH EXTENDED TESTS
# =============================================================================
# Additional tests for Argon2 authentication and rate limiting.
# =============================================================================

import time


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
            allowed = limiter.is_allowed("test-client")
            assert allowed is True

        # 4th should be blocked
        allowed = limiter.is_allowed("test-client")
        assert allowed is False

    def test_rate_limiter_different_clients(self):
        """RateLimiter should track clients separately."""
        from src.core.auth import RateLimiter

        limiter = RateLimiter(window=60, max_requests=2)

        # Client A
        limiter.is_allowed("client-a")
        limiter.is_allowed("client-a")
        allowed_a = limiter.is_allowed("client-a")

        # Client B should still be allowed
        allowed_b = limiter.is_allowed("client-b")

        assert allowed_a is False
        assert allowed_b is True


class TestArgon2Password:
    """Test Argon2 password functions."""

    def test_verify_password_returns_bool(self):
        """verify_password should return boolean."""
        from src.core.auth import verify_password

        result = verify_password("anypassword")
        assert isinstance(result, bool)


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


class TestTokenBucket:
    """Test TokenBucket rate limiting."""

    def test_token_bucket_allows_burst(self):
        """TokenBucket should allow burst up to capacity."""
        from src.core.auth import TokenBucket

        bucket = TokenBucket(rate=1.0, capacity=5)
        # Should allow 5 requests in a burst
        for _ in range(5):
            assert bucket.consume("user1") is True

    def test_token_bucket_refills(self):
        """TokenBucket should refill over time."""
        from src.core.auth import TokenBucket

        bucket = TokenBucket(rate=10.0, capacity=5)  # 10 tokens per second
        # Consume all
        for _ in range(5):
            bucket.consume("user1")
        
        # Wait for refill
        time.sleep(0.2)  # Should get ~2 tokens
        assert bucket.consume("user1") is True


class TestAuthResult:
    """Test AuthResult dataclass."""

    def test_auth_result_success(self):
        """AuthResult should store success state."""
        from src.core.auth import AuthResult

        result = AuthResult(success=True, token="test-token")
        assert result.success is True
        assert result.token == "test-token"

    def test_auth_result_failure(self):
        """AuthResult should store failure error."""
        from src.core.auth import AuthResult

        result = AuthResult(success=False, error="Invalid password")
        assert result.success is False
        assert result.error == "Invalid password"
