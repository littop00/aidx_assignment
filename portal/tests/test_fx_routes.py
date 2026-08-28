import fx


def _login(client, admin_user):
    client.post("/login", data=admin_user)


def test_widget_shows_missing_when_no_rates(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/fx/widget")
    assert resp.status_code == 200
    assert "미확보".encode() in resp.data


def test_refresh_updates_rate(client, admin_user, monkeypatch):
    _login(client, admin_user)
    monkeypatch.setattr(fx, "fetch_rates_from_api", lambda: {"USD": 1300.0, "EUR": 1400.0})
    resp = client.post("/fx/refresh")
    assert resp.status_code == 200
    assert "1,300.00".encode() in resp.data


def test_download_requires_login(client):
    resp = client.get("/fx/download")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_download_returns_excel_mimetype(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/fx/download")
    assert resp.status_code == 200
    assert resp.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
