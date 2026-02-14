"""Authentication and rate-limiting dependencies for API gateway."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import time

from fastapi import Request

from .config import get_settings
from .errors import ApiError


@dataclass(frozen=True)
class AuthContext:
    """Authenticated caller context."""

    subject: str
    token: str
    roles: frozenset[str]


class InMemoryRateLimiter:
    """Simple fixed-window rate limiter with per-key counters."""

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self._lock = Lock()
        self._limit = limit
        self._window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def set_limits(self, *, limit: int, window_seconds: int) -> None:
        with self._lock:
            self._limit = limit
            self._window_seconds = window_seconds
            self._hits.clear()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def allow(self, key: str) -> bool:
        now = time()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - self._window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                return False
            bucket.append(now)
            return True


_settings = get_settings()
_rate_limiter = InMemoryRateLimiter(
    limit=max(_settings.rate_limit_requests, 1),
    window_seconds=max(_settings.rate_limit_window_seconds, 1),
)


def get_rate_limiter() -> InMemoryRateLimiter:
    """Expose limiter singleton for tests and route dependencies."""

    return _rate_limiter


def get_auth_context(request: Request) -> AuthContext:
    """Validate bearer token and return caller context."""

    settings = get_settings()
    if not settings.auth_enabled:
        return AuthContext(subject="anonymous", token="", roles=frozenset({"anonymous"}))

    raw = request.headers.get("authorization", "")
    scheme, _, token = raw.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(
            status_code=401,
            code="UNAUTHORIZED",
            message="Missing or invalid authentication token.",
            trace_id=request.headers.get("x-trace-id"),
        )

    if token not in settings.auth_tokens:
        raise ApiError(
            status_code=401,
            code="UNAUTHORIZED",
            message="Missing or invalid authentication token.",
            trace_id=request.headers.get("x-trace-id"),
        )

    roles = settings.token_roles.get(token, frozenset({"operator"}))
    return AuthContext(subject="gateway-client", token=token, roles=frozenset(roles))


def require_roles(request: Request, auth: AuthContext, *allowed_roles: str) -> None:
    """Validate caller roles for sensitive routes."""

    normalized = {role.strip().lower() for role in allowed_roles if role.strip()}
    if not normalized:
        return

    if auth.roles.intersection(normalized):
        return

    raise ApiError(
        status_code=403,
        code="FORBIDDEN",
        message="Caller lacks required role for this action.",
        trace_id=request.headers.get("x-trace-id"),
    )


def enforce_rate_limit(request: Request, auth: AuthContext | None = None) -> None:
    """Enforce per-caller request rate limit."""

    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    key = "anon"
    if auth is not None and auth.token:
        key = f"token:{auth.token}"
    elif request.client and request.client.host:
        key = f"ip:{request.client.host}"

    allowed = _rate_limiter.allow(key)
    if not allowed:
        raise ApiError(
            status_code=429,
            code="RATE_LIMITED",
            message="Too many requests.",
            trace_id=request.headers.get("x-trace-id"),
        )
