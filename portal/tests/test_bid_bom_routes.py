def _login(client, admin_user):
    client.post("/login", data=admin_user)


def test_bid_bom_index_requires_login(client):
    resp = client.get("/bid-bom/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_bid_bom_index_shows_placeholder(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/bid-bom/")
    assert resp.status_code == 200
    assert "준비중".encode() in resp.data
