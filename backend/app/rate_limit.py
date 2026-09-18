"""Minimal in-memory rate limiter for auth endpoints.

No Redis or other external store: this portal runs as a single process for a
single household/small team, so a per-process in-memory fixed window is
enough to blunt brute-force/credential-stuffing attempts against login and
setup without adding an infra dependency. Resets on restart -- acceptable
for this threat model.
"""

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status

_attempts: dict[str, deque] = defaultdict(deque)


def reset():
    """Test-only: clear all tracked attempts (state is otherwise a module-level global)."""
    _attempts.clear()


def rate_limit(max_attempts: int, window_seconds: int):
    async def dependency(request: Request):
        client_host = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{client_host}"
        now = time.monotonic()
        bucket = _attempts[key]

        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()

        if len(bucket) >= max_attempts:
            retry_after = max(1, int(window_seconds - (now - bucket[0])) + 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        bucket.append(now)

    return Depends(dependency)
