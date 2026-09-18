"""Update-available visibility -- not a trigger. The actual update still runs via
scripts/update.sh on the host (see docs/DEPLOYMENT.md): this container is a built
image with no git checkout and no Docker socket access, so it cannot rebuild or
restart itself from inside the UI. That's a deliberate scope boundary, not an
oversight -- see docs/SECURITY.md for why a docker.sock passthrough wasn't added
just for this on a single-operator tool.
"""

import logging
import time

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__, config
from app.deps import get_current_user

router = APIRouter(prefix="/api/version", tags=["version"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger("haven_backup.version")

_CACHE_TTL_SECONDS = 3600
# time.monotonic()'s reference point is undefined by the stdlib -- on a freshly
# booted/started process (e.g. right after a container starts, or on a
# just-provisioned CI runner) it can legitimately read well under
# _CACHE_TTL_SECONDS. Using 0.0 as "never checked" would then read as "checked
# recently" and wrongly serve a cache hit before the first real check ever ran.
# -inf is unconditionally "expired" regardless of what the clock happens to read.
_NEVER_CHECKED = float("-inf")
_cache = {"checked_at": _NEVER_CHECKED, "latest": None}


def reset_cache():
    """Test-only: the update-check result is cached at module level."""
    _cache["checked_at"] = _NEVER_CHECKED
    _cache["latest"] = None


class VersionInfo(BaseModel):
    current: str
    latest: str | None
    update_available: bool
    check_enabled: bool


def _parse_version(tag: str):
    try:
        return tuple(int(p) for p in tag.lstrip("v").split("."))
    except ValueError:
        return None


def _fetch_latest_tag() -> str | None:
    now = time.monotonic()
    if now - _cache["checked_at"] < _CACHE_TTL_SECONDS:
        return _cache["latest"]

    try:
        response = httpx.get(
            f"https://api.github.com/repos/{config.UPDATE_CHECK_REPO}/tags",
            headers={"Accept": "application/vnd.github+json"},
            timeout=5,
        )
        response.raise_for_status()
        tags = [t["name"] for t in response.json() if _parse_version(t["name"])]
        latest = max(tags, key=_parse_version) if tags else None
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.info("Update check failed (non-fatal): %s", e)
        latest = _cache["latest"]  # keep last-known-good rather than flapping to None

    _cache["checked_at"] = now
    _cache["latest"] = latest
    return latest


@router.get("", response_model=VersionInfo)
def get_version():
    if not config.UPDATE_CHECK_ENABLED:
        return VersionInfo(current=__version__, latest=None, update_available=False, check_enabled=False)

    latest = _fetch_latest_tag()
    current_parsed = _parse_version(__version__)
    latest_parsed = _parse_version(latest) if latest else None
    update_available = bool(current_parsed and latest_parsed and latest_parsed > current_parsed)

    return VersionInfo(current=__version__, latest=latest, update_available=update_available, check_enabled=True)
