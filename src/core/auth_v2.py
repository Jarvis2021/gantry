# -----------------------------------------------------------------------------
# GANTRY FLEET - AUTHENTICATION v2 (Argon2 + Per-User Rate Limiting)
# -----------------------------------------------------------------------------
# Modern authentication with:
# - Argon2 password hashing (replaces SHA256)
# - Token-based sessions
# - Per-user rate limiting (not just per-IP)
# - Content guardrails
# -----------------------------------------------------------------------------

import os
import re
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from rich.console import Console

console = Console()

# Password hasher with secure defaults
ph = PasswordHasher()

# Session storage (in production, use Redis)
_sessions: dict[str, dict] = {}

# Session timeout
SESSION_TIMEOUT = 3600  # 1 hour


# =============================================================================
# PASSWORD HASHING (Argon2)
# =============================================================================


def _get_password_hash() -> str:
    """
    Get or create the password hash.

    Supports:
    - GANTRY_PASSWORD (plain text - will be hashed)
    - GANTRY_PASSWORD_HASH (pre-hashed argon2)
    """
    # Check for pre-hashed password
    password_hash = os.getenv("GANTRY_PASSWORD_HASH", "")
    if password_hash and password_hash.startswith("$argon2"):
        return password_hash

    # Check for plain text password
    plain_password = os.getenv("GANTRY_PASSWORD", "")
    if plain_password:
        hashed = ph.hash(plain_password)
        console.print("[cyan][AUTH] Password loaded and hashed with Argon2[/cyan]")
        return hashed

    # Default password (for development only)
    console.print(
        "[yellow][AUTH] Using default password - set GANTRY_PASSWORD in production[/yellow]"
    )
    return ph.hash("password")


DEFAULT_PASSWORD_HASH = _get_password_hash()


def verify_password(password: str) -> bool:
    """Verify password against stored Argon2 hash."""
    try:
        ph.verify(DEFAULT_PASSWORD_HASH, password)
        return True
    except VerifyMismatchError:
        return False


# =============================================================================
# TOKEN-BASED SESSIONS
# =============================================================================


@dataclass
class AuthResult:
    """Result of authentication attempt."""

    success: bool
    token: str | None = None
    error: str | None = None


async def authenticate_user(password: str) -> AuthResult:
    """
    Authenticate user and create session token.

    Returns:
        AuthResult with token if successful
    """
    if verify_password(password):
        token = secrets.token_urlsafe(32)
        _sessions[token] = {
            "created_at": time.time(),
            "last_access": time.time(),
        }
        console.print("[green][AUTH] Session created[/green]")
        return AuthResult(success=True, token=token)

    console.print("[red][AUTH] Authentication failed[/red]")
    return AuthResult(success=False, error="Invalid password")


async def verify_session(token: str) -> bool:
    """Verify if a session token is valid."""
    if not token or token not in _sessions:
        return False

    session = _sessions[token]

    # Check timeout
    if time.time() - session["created_at"] > SESSION_TIMEOUT:
        del _sessions[token]
        return False

    # Update last access
    session["last_access"] = time.time()
    return True


async def get_current_user(token: str = "") -> str:
    """Get current user ID from token (for dependency injection)."""
    # In a real system, this would decode the token to get user ID
    # For now, use token as user ID
    if await verify_session(token):
        return token[:16]  # Use first 16 chars as user ID
    return "anonymous"


def invalidate_session(token: str) -> None:
    """Invalidate a session token."""
    _sessions.pop(token, None)


# =============================================================================
# RATE LIMITING
# =============================================================================


@dataclass
class RateLimitEntry:
    """Track rate limit for a single client."""

    requests: list = field(default_factory=list)
    blocked_until: float = 0


class RateLimiter:
    """
    Sliding window rate limiter.
    Tracks requests per client and blocks if exceeded.
    """

    def __init__(self, window: int = 60, max_requests: int = 30):
        self.window = window
        self.max_requests = max_requests
        self._clients: dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)

    def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed."""
        now = time.time()
        entry = self._clients[client_id]

        # Check if blocked
        if entry.blocked_until > now:
            return False

        # Clean old requests outside window
        entry.requests = [t for t in entry.requests if t > now - self.window]

        # Check limit
        if len(entry.requests) >= self.max_requests:
            entry.blocked_until = now + self.window
            console.print(f"[yellow][RATE] Client {client_id[:8]} blocked[/yellow]")
            return False

        # Allow and record
        entry.requests.append(now)
        return True


class TokenBucket:
    """
    Token bucket rate limiter for per-user limiting.
    More flexible than sliding window - allows bursts.
    """

    def __init__(self, rate: float = 10.0, capacity: int = 30):
        """
        Args:
            rate: Tokens per second to add
            capacity: Maximum tokens in bucket
        """
        self.rate = rate
        self.capacity = capacity
        self._buckets: dict[str, dict] = {}

    def consume(self, user_id: str, tokens: int = 1) -> bool:
        """
        Try to consume tokens from user's bucket.

        Returns:
            True if tokens were available, False if rate limited
        """
        now = time.time()

        if user_id not in self._buckets:
            self._buckets[user_id] = {
                "tokens": self.capacity,
                "last_update": now,
            }

        bucket = self._buckets[user_id]

        # Add tokens based on time elapsed
        elapsed = now - bucket["last_update"]
        bucket["tokens"] = min(
            self.capacity,
            bucket["tokens"] + elapsed * self.rate,
        )
        bucket["last_update"] = now

        # Try to consume
        if bucket["tokens"] >= tokens:
            bucket["tokens"] -= tokens
            return True

        return False


# =============================================================================
# CONTENT GUARDRAILS
# =============================================================================

BLOCKED_PATTERNS = [
    r"\b(fuck|shit|damn|ass|bitch|crap)\b",  # Profanity
    r"\btest\s*\d+\b",  # "test1", "test 123"
    r"^(hi|hello|hey|yo|sup)$",  # Just greetings
    r"^.{1,5}$",  # Too short (less than 6 chars)
    r"^[a-z]{20,}$",  # Just random letters
    r"(asdf|qwerty|zxcv)",  # Keyboard mashing
]

MIN_MESSAGE_LENGTH = 10
MIN_WORD_COUNT = 3

APP_KEYWORDS = [
    "build",
    "create",
    "make",
    "app",
    "website",
    "api",
    "service",
    "dashboard",
    "page",
    "tool",
    "system",
    "platform",
]


@dataclass
class GuardrailResult:
    """Result of guardrail check."""

    passed: bool
    reason: str = ""
    suggestion: str = ""


def check_guardrails(message: str) -> GuardrailResult:
    """Check if message passes content guardrails."""
    clean = message.strip().lower()

    # Check length
    if len(clean) < MIN_MESSAGE_LENGTH:
        return GuardrailResult(
            passed=False,
            reason="Message too short",
            suggestion="Please provide more details about what you want to build.",
        )

    # Check word count
    words = clean.split()
    if len(words) < MIN_WORD_COUNT:
        return GuardrailResult(
            passed=False,
            reason="Not enough context",
            suggestion="Please describe your app idea in more detail.",
        )

    # Check blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, clean, re.IGNORECASE):
            return GuardrailResult(
                passed=False,
                reason="Invalid request",
                suggestion="Please provide a clear description of what you want to build.",
            )

    # Check for meaningful content
    has_intent = any(kw in clean for kw in APP_KEYWORDS)
    if not has_intent:
        return GuardrailResult(
            passed=False,
            reason="No clear build intent",
            suggestion="Start with 'Build me...' or 'Create a...' followed by your app idea.",
        )

    return GuardrailResult(passed=True)
