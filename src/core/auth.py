# -----------------------------------------------------------------------------
# GANTRY FLEET - AUTHENTICATION & RATE LIMITING
# -----------------------------------------------------------------------------
# Responsibility: Protect the API with password auth, rate limiting, and
# content guardrails to prevent abuse and junk requests.
# -----------------------------------------------------------------------------

import hashlib
import os
import re
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps

from flask import jsonify, request, session
from rich.console import Console

console = Console()

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
# Password can be set via:
# - GANTRY_PASSWORD (plain text - will be hashed internally)
# - GANTRY_PASSWORD_HASH (pre-hashed SHA256)
# Plain text is automatically detected and hashed for convenience.


def _get_password_hash() -> str:
    """
    Get the password hash from environment.
    Supports both plain text and pre-hashed passwords.
    """
    # First check for pre-hashed password
    password_hash = os.getenv("GANTRY_PASSWORD_HASH", "")

    # If it looks like a valid SHA256 hash (64 hex chars), use it directly
    if password_hash and len(password_hash) == 64:
        try:
            int(password_hash, 16)  # Verify it's hex
            return password_hash
        except ValueError:
            pass

    # Check for plain text password
    plain_password = os.getenv("GANTRY_PASSWORD", "")
    if plain_password:
        # Hash the plain text password
        hashed = hashlib.sha256(plain_password.encode()).hexdigest()
        console.print("[cyan][AUTH] Password loaded from GANTRY_PASSWORD[/cyan]")
        return hashed

    # If GANTRY_PASSWORD_HASH was set but not valid hex, treat as plain text
    if password_hash:
        hashed = hashlib.sha256(password_hash.encode()).hexdigest()
        console.print("[cyan][AUTH] Password loaded (converted to hash)[/cyan]")
        return hashed

    # Default password (for development only)
    console.print("[yellow][AUTH] Using default password - set GANTRY_PASSWORD in production[/yellow]")
    return hashlib.sha256(b"password").hexdigest()


DEFAULT_PASSWORD_HASH = _get_password_hash()

# Rate limit settings
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("GANTRY_RATE_LIMIT", "30"))  # per minute

# Session timeout
SESSION_TIMEOUT = 3600  # 1 hour


# -----------------------------------------------------------------------------
# RATE LIMITER
# -----------------------------------------------------------------------------
@dataclass
class RateLimitEntry:
    """Track rate limit for a single client."""

    requests: list = field(default_factory=list)
    blocked_until: float = 0


class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window.
    Tracks requests per IP and blocks if exceeded.
    """

    def __init__(
        self, window: int = RATE_LIMIT_WINDOW, max_requests: int = RATE_LIMIT_MAX_REQUESTS
    ):
        self.window = window
        self.max_requests = max_requests
        self._clients: dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)

    def is_allowed(self, client_id: str) -> tuple[bool, int]:
        """
        Check if request is allowed.
        Returns (allowed, remaining_requests).
        """
        now = time.time()
        entry = self._clients[client_id]

        # Check if blocked
        if entry.blocked_until > now:
            return False, 0

        # Clean old requests outside window
        entry.requests = [t for t in entry.requests if t > now - self.window]

        # Check limit
        if len(entry.requests) >= self.max_requests:
            # Block for the window period
            entry.blocked_until = now + self.window
            console.print(f"[yellow][RATE_LIMIT] Client {client_id} blocked[/yellow]")
            return False, 0

        # Allow and record
        entry.requests.append(now)
        remaining = self.max_requests - len(entry.requests)
        return True, remaining

    def get_client_id(self) -> str:
        """Extract client ID from request (IP-based)."""
        # Check X-Forwarded-For for proxied requests
        if request.headers.get("X-Forwarded-For"):
            return request.headers["X-Forwarded-For"].split(",")[0].strip()
        return request.remote_addr or "unknown"


# Global rate limiter
rate_limiter = RateLimiter()


def require_rate_limit(f: Callable) -> Callable:
    """Decorator to enforce rate limiting on routes."""

    @wraps(f)
    def decorated(*args, **kwargs):
        client_id = rate_limiter.get_client_id()
        allowed, _remaining = rate_limiter.is_allowed(client_id)

        if not allowed:
            return (
                jsonify(
                    {
                        "error": "Rate limit exceeded. Please wait before retrying.",
                        "speech": "Too many requests. Please slow down.",
                        "retry_after": RATE_LIMIT_WINDOW,
                    }
                ),
                429,
            )

        # Execute the wrapped function
        return f(*args, **kwargs)

    return decorated


# -----------------------------------------------------------------------------
# PASSWORD AUTHENTICATION
# -----------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Hash password with SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str) -> bool:
    """Verify password against stored hash."""
    return hash_password(password) == DEFAULT_PASSWORD_HASH


def is_authenticated() -> bool:
    """Check if current session is authenticated."""
    if "authenticated" not in session:
        return False
    if "auth_time" not in session:
        return False

    # Check timeout
    if time.time() - session["auth_time"] > SESSION_TIMEOUT:
        session.clear()
        return False

    return session["authenticated"] is True


def authenticate_session(password: str) -> bool:
    """Attempt to authenticate with password."""
    if verify_password(password):
        session["authenticated"] = True
        session["auth_time"] = time.time()
        console.print("[green][AUTH] Session authenticated[/green]")
        return True
    console.print("[red][AUTH] Authentication failed[/red]")
    return False


def require_auth(f: Callable) -> Callable:
    """Decorator to require authentication on routes."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return (
                jsonify(
                    {
                        "error": "Authentication required",
                        "speech": "Please enter your password to continue.",
                        "needs_auth": True,
                    }
                ),
                401,
            )
        return f(*args, **kwargs)

    return decorated


# -----------------------------------------------------------------------------
# CONTENT GUARDRAILS
# -----------------------------------------------------------------------------
# Patterns that indicate abuse or junk requests
BLOCKED_PATTERNS = [
    r"\b(fuck|shit|damn|ass|bitch|crap)\b",  # Profanity
    r"\btest\s*\d+\b",  # "test1", "test 123"
    r"^(hi|hello|hey|yo|sup)$",  # Just greetings
    r"^.{1,5}$",  # Too short (less than 6 chars)
    r"^[a-z]{20,}$",  # Just random letters
    r"(asdf|qwerty|zxcv)",  # Keyboard mashing
]

# Minimum context required
MIN_MESSAGE_LENGTH = 10
MIN_WORD_COUNT = 3


@dataclass
class GuardrailResult:
    """Result of guardrail check."""

    passed: bool
    reason: str = ""
    suggestion: str = ""


def check_guardrails(message: str) -> GuardrailResult:
    """
    Check if message passes content guardrails.
    Returns result with suggestion if blocked.
    """
    # Normalize
    clean = message.strip().lower()

    # Check length
    if len(clean) < MIN_MESSAGE_LENGTH:
        return GuardrailResult(
            passed=False,
            reason="Message too short",
            suggestion="Please provide more details about what you want to build. "
            "For example: 'Build a todo app with user login and dark mode'",
        )

    # Check word count
    words = clean.split()
    if len(words) < MIN_WORD_COUNT:
        return GuardrailResult(
            passed=False,
            reason="Not enough context",
            suggestion="Please describe your app idea in more detail. "
            "What features should it have? Who is it for?",
        )

    # Check blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, clean, re.IGNORECASE):
            return GuardrailResult(
                passed=False,
                reason="Invalid request",
                suggestion="Please provide a clear, professional description of the app you want to build.",
            )

    # Check for meaningful content (has nouns/verbs)
    app_keywords = [
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
    has_intent = any(kw in clean for kw in app_keywords)

    if not has_intent:
        return GuardrailResult(
            passed=False,
            reason="No clear build intent",
            suggestion="Please describe what you want to build. "
            "Start with 'Build me...' or 'Create a...' followed by your app idea.",
        )

    return GuardrailResult(passed=True)


def require_guardrails(f: Callable) -> Callable:
    """Decorator to enforce content guardrails."""

    @wraps(f)
    def decorated(*args, **kwargs):
        data = request.json or {}
        messages = data.get("messages", [])

        # Check the last user message
        user_messages = [m for m in messages if m.get("role") == "user"]
        if user_messages:
            last_message = user_messages[-1].get("content", "")
            result = check_guardrails(last_message)

            if not result.passed:
                return (
                    jsonify(
                        {
                            "response": result.suggestion,
                            "ready_to_build": False,
                            "blocked_reason": result.reason,
                        }
                    ),
                    200,  # Return 200 so UI can show the suggestion
                )

        return f(*args, **kwargs)

    return decorated
