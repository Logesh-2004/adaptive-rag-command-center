"""Guards for running the API as a public demo.

All of them are off when their setting is empty, so local development needs no extra setup.

- PROXY_SECRET: only requests forwarded by the dashboard's proxy (which adds the secret) are served.
- QUERY_RATE_LIMIT_PER_MINUTE / DAILY_QUERY_LIMIT: cap how many answers each visitor, and the
  whole site, can request, because every answer spends the Groq quota.
- ADMIN_TOKEN: rebuilding the index needs this token.
"""

import hmac
import time
from collections import defaultdict, deque
from datetime import date

from fastapi import Depends, HTTPException, Request

from app.core.config import Settings, get_settings


class RateLimiter:
    """In-memory sliding-window limiter. Enough for a single-instance demo server."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._day = date.today()
        self._day_count = 0

    def reset(self) -> None:
        self._hits.clear()
        self._day = date.today()
        self._day_count = 0

    def check(self, key: str, per_minute: int, daily_limit: int) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if per_minute and len(hits) >= per_minute:
            raise HTTPException(
                status_code=429,
                detail={"status": "error", "message": "Too many questions in a minute. Wait a moment and try again.", "error_code": "rate_limited"},
            )
        today = date.today()
        if today != self._day:
            self._day, self._day_count = today, 0
        if daily_limit and self._day_count >= daily_limit:
            raise HTTPException(
                status_code=429,
                detail={"status": "error", "message": "The demo has reached its daily question limit. Try again tomorrow.", "error_code": "daily_limit"},
            )
        hits.append(now)
        self._day_count += 1


limiter = RateLimiter()


def _matches(supplied: str | None, expected: str) -> bool:
    return hmac.compare_digest((supplied or "").encode(), expected.encode())


def require_proxy(request: Request, settings: Settings = Depends(get_settings)) -> None:
    secret = settings.proxy_secret_value
    if secret and not _matches(request.headers.get("x-proxy-secret"), secret):
        raise HTTPException(status_code=403, detail={"status": "error", "message": "Requests must come through the dashboard.", "error_code": "forbidden"})


def client_key(request: Request, settings: Settings) -> str:
    # Behind the dashboard proxy every request comes from the proxy's own address, so it passes the
    # visitor's IP along. Trust that header only when the proxy secret proves where it came from.
    secret = settings.proxy_secret_value
    if secret and _matches(request.headers.get("x-proxy-secret"), secret):
        return request.headers.get("x-client-ip") or "proxy"
    return request.client.host if request.client else "unknown"


def rate_limited(request: Request, settings: Settings = Depends(get_settings)) -> None:
    limiter.check(client_key(request, settings), settings.query_rate_limit_per_minute, settings.daily_query_limit)


def require_admin(request: Request, settings: Settings = Depends(get_settings)) -> None:
    token = settings.admin_token_value
    if token and not _matches(request.headers.get("x-admin-token"), token):
        raise HTTPException(
            status_code=401,
            detail={"status": "error", "message": "Rebuilding the index needs the admin token.", "error_code": "admin_required"},
        )
