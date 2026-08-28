def test_root_redirects_when_unauthenticated(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_success_redirects_home(client, admin_user):
    resp = client.post("/login", data=admin_user)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_login_failure_shows_error(client, admin_user):
    resp = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 200
    assert "로그인 실패".encode() in resp.data


def test_logout_redirects_to_login(client, admin_user):
    client.post("/login", data=admin_user)
    resp = client.get("/logout")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_authenticated_user_can_access_home(client, admin_user):
    client.post("/login", data=admin_user)
    resp = client.get("/")
    assert resp.status_code == 200
