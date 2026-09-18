import httpx

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


def _login(client):
    client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})


def test_update_available_when_a_newer_tag_exists(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(config, "UPDATE_CHECK_ENABLED", True)
    monkeypatch.setattr(version_router, "__version__", "0.2.0")  # independent of whatever the real app version is
    monkeypatch.setattr(
        version_router.httpx, "get",
        lambda *a, **k: _FakeResponse([{"name": "v0.2.0"}, {"name": "v0.3.0"}, {"name": "v0.1.0"}]),
    )

    response = client.get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert body["latest"] == "v0.3.0"
    assert body["update_available"] is True


def test_no_update_available_when_current_is_latest(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(config, "UPDATE_CHECK_ENABLED", True)
    monkeypatch.setattr(version_router, "__version__", "0.3.0")
    monkeypatch.setattr(
        version_router.httpx, "get",
        lambda *a, **k: _FakeResponse([{"name": "v0.2.0"}, {"name": "v0.3.0"}]),
    )

    response = client.get("/api/version")
    body = response.json()
    assert body["current"] == "0.3.0"
    assert body["update_available"] is False


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


def test_network_failure_degrades_gracefully(client, monkeypatch):
    _login(client)
    monkeypatch.setattr(config, "UPDATE_CHECK_ENABLED", True)

    def _boom(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(version_router.httpx, "get", _boom)

    response = client.get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert body["update_available"] is False


def test_version_endpoint_requires_auth(client):
    response = client.get("/api/version")
    assert response.status_code == 401
