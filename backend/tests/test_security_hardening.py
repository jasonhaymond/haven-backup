import asyncio

from fastapi import HTTPException

from app import config
from app.rate_limit import rate_limit as make_rate_limit


def test_login_rate_limited_after_configured_max_attempts(client):
    """End-to-end, against the route as actually wired -- proves the dependency
    is genuinely attached, not just that the limiter function works in isolation."""
    client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    client.post("/api/auth/logout")

    statuses = []
    for _ in range(config.LOGIN_RATE_LIMIT_ATTEMPTS + 2):
        response = client.post("/api/auth/login", json={"username": "jason", "password": "wrong"})
        statuses.append(response.status_code)

    assert statuses[: config.LOGIN_RATE_LIMIT_ATTEMPTS] == [401] * config.LOGIN_RATE_LIMIT_ATTEMPTS
    assert statuses[config.LOGIN_RATE_LIMIT_ATTEMPTS :] == [429, 429]


def test_rate_limit_dependency_resets_after_window(monkeypatch):
    """Direct test of the limiter's windowing logic, independent of the route wiring."""
    limiter = make_rate_limit(2, 60)
    dependency_fn = limiter.dependency

    class FakeRequest:
        class client:
            host = "1.2.3.4"

        class url:
            path = "/test/path"

    fake_time = [1000.0]
    monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: fake_time[0])

    asyncio.run(dependency_fn(FakeRequest()))
    asyncio.run(dependency_fn(FakeRequest()))
    try:
        asyncio.run(dependency_fn(FakeRequest()))
        assert False, "expected the third call within the window to be rate-limited"
    except HTTPException as e:
        assert e.status_code == 429

    fake_time[0] += 61  # past the 60s window
    asyncio.run(dependency_fn(FakeRequest()))  # should succeed now that the window rolled over


def test_session_cookie_secure_flag_follows_config(client, monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    response = client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    set_cookie = response.headers.get("set-cookie", "")
    assert "Secure" in set_cookie
    assert "HttpOnly" in set_cookie


def test_session_cookie_not_secure_when_disabled(client, monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    response = client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    set_cookie = response.headers.get("set-cookie", "")
    assert "Secure" not in set_cookie


def test_health_check_reports_version_and_db_status(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert "version" in body
