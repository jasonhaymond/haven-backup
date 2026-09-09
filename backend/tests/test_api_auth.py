def test_setup_required_true_when_no_users(client):
    response = client.get("/api/auth/setup-required")
    assert response.json() == {"setup_required": True}


def test_setup_creates_admin_and_logs_in(client):
    response = client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    assert response.status_code == 200
    assert response.json()["username"] == "jason"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "jason"


def test_setup_rejected_once_a_user_exists(client):
    client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    second = client.post("/api/auth/setup", json={"username": "someone-else", "password": "correct-horse-battery"})
    assert second.status_code == 409


def test_login_wrong_password_rejected(client):
    client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    client.post("/api/auth/logout")

    response = client.post("/api/auth/login", json={"username": "jason", "password": "wrong-password"})
    assert response.status_code == 401


def test_login_success(client):
    client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    client.post("/api/auth/logout")

    response = client.post("/api/auth/login", json={"username": "jason", "password": "correct-horse-battery"})
    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_protected_route_requires_auth(client):
    response = client.get("/api/hosts")
    assert response.status_code == 401


def test_logout_clears_session(client):
    client.post("/api/auth/setup", json={"username": "jason", "password": "correct-horse-battery"})
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
