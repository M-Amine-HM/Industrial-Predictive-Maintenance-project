"""Optional API-key auth and per-client rate limiting (both off unless configured)."""
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from fastapi.security import APIKeyHeader

from . import config

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class RateLimiter:
    """Sliding one-minute window per client IP."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, client: str) -> int | None:
        """Return seconds to wait if the client is over the limit, else None."""
        now = time.monotonic()
        with self.lock:
            q = self.hits[client]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return int(60 - (now - q[0])) + 1
            q.append(now)
        return None


limiter = RateLimiter(config.RATE_LIMIT_PER_MIN)


async def protect(request: Request) -> None:
    """Dependency for prediction/drift routes."""
    if config.API_KEY:
        key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(key, config.API_KEY):
            raise HTTPException(401, "Missing or invalid API key (header X-API-Key)")
    if limiter.per_minute > 0:
        client = request.client.host if request.client else "unknown"
        wait = limiter.check(client)
        if wait is not None:
            raise HTTPException(429, f"Rate limit of {limiter.per_minute} requests/min exceeded",
                                headers={"Retry-After": str(wait)})
