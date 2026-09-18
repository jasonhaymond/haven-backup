import httpx
import pytest

from app import config
from app.routers import version as version_router


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


@pytest.fixture(autouse=True)
def _fresh_cache():
    # Explicit, not just relying on conftest's autouse reset -- these tests are
    # specifically about the cache's own logic, so they own their starting state.
    version_router.reset_cache()
    yield
    version_router.reset_cache()


def _login(client):
    client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})


# -----------------------------
# Core caching/comparison logic -- called directly, not through the HTTP layer.
# FastAPI runs sync route handlers in a worker thread pool; testing the plain
# functions directly avoids any dependency on that scheduling for what is really
# just "does this pure function compare versions correctly."
# -----------------------------
def test_fetch_latest_tag_picks_highest_semver(monkeypatch):
    monkeypatch.setattr(
        version_router.httpx, "get",
        lambda *a, **k: _FakeResponse([{"name": "v0.2.0"}, {"name": "v0.3.0"}, {"name": "v0.1.0"}]),
    )
    assert version_router._fetch_latest_tag() == "v0.3.0"


def test_fetch_latest_tag_degrades_to_cached_value_on_network_failure():
    version_router._cache["latest"] = "v0.2.0"
    version_router._cache["checked_at"] = 0.0  # force a re-check, which will fail

    def _boom(*a, **k):
        raise httpx.ConnectError("no network")

    import app.routers.version as v
    v.httpx.get = _boom
    try:
        assert version_router._fetch_latest_tag() == "v0.2.0"  # last-known-good, not None
    finally:
        v.httpx.get = httpx.get


def test_fetch_latest_tag_uses_cache_within_ttl(monkeypatch):
    calls = []
    monkeypatch.setattr(version_router.httpx, "get", lambda *a, **k: calls.append(1) or _FakeResponse([{"name": "v1.0.0"}]))

    first = version_router._fetch_latest_tag()
    second = version_router._fetch_latest_tag()

    assert first == second == "v1.0.0"
    assert len(calls) == 1  # second call was a cache hit, no second network call


def test_get_version_reports_update_available(monkeypatch):
    monkeypatch.setattr(version_router, "__version__", "0.2.0")
    monkeypatch.setattr(config, "UPDATE_CHECK_ENABLED", True)
    monkeypatch.setattr(version_router, "_fetch_latest_tag", lambda: "v0.3.0")

    info = version_router.get_version()
    assert info.latest == "v0.3.0"
    assert info.update_available is True


def test_get_version_no_update_when_current_is_latest(monkeypatch):
    monkeypatch.setattr(version_router, "__version__", "0.3.0")
    monkeypatch.setattr(config, "UPDATE_CHECK_ENABLED", True)
    monkeypatch.setattr(version_router, "_fetch_latest_tag", lambda: "v0.3.0")

    info = version_router.get_version()
    assert info.update_available is False


# -----------------------------
# Endpoint-level wiring: auth requirement and the disabled short-circuit.
# -----------------------------
def test_check_disabled_reports_no_outbound_call(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(config, "UPDATE_CHECK_ENABLED", False)

    def _boom(*a, **k):
        raise AssertionError("should not call GitHub when the check is disabled")

    monkeypatch.setattr(version_router.httpx, "get", _boom)

    response = client.get("/api/version")
    body = response.json()
    assert body["check_enabled"] is False
    assert body["update_available"] is False
    assert body["latest"] is None


def test_version_endpoint_requires_auth(client):
    response = client.get("/api/version")
    assert response.status_code == 401
