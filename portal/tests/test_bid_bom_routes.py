import db


def _login(client, admin_user):
    client.post("/login", data=admin_user)


def _confirmed_source_bom(app):
    conn = db.get_connection(app.config["DB_PATH"])
    bom_id = db.get_active_bom_version(conn)["id"]
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER"}, bom_id)
    db.publish_bom_version(conn, bom_id)
    db.confirm_bom_version(conn, bom_id)
    conn.close()
    return bom_id


def test_bid_bom_index_requires_login(client):
    resp = client.get("/bid-bom/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_bid_bom_index_shows_placeholder(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/bid-bom/")
    assert resp.status_code == 200
    assert "준비중".encode() in resp.data


def test_admin_bid_bom_versions_requires_login(client):
    resp = client.get("/admin/bid-boms")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_bid_bom_versions_lists_confirmed_sources(client, admin_user, app):
    _login(client, admin_user)
    bom_id = _confirmed_source_bom(app)
    resp = client.get("/admin/bid-boms")
    assert resp.status_code == 200
    assert f'value="{bom_id}"'.encode() in resp.data


def test_create_bid_bom_rejects_unconfirmed_source(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    bom_id = db.get_active_bom_version(conn)["id"]
    db.publish_bom_version(conn, bom_id)
    conn.close()
    resp = client.post("/admin/bid-boms/create", data={"name": "입찰 v1", "source_bom_id": str(bom_id)})
    assert resp.status_code == 302
    conn = db.get_connection(app.config["DB_PATH"])
    assert db.list_bid_bom_versions(conn) == []


def test_create_bid_bom_from_confirmed_source(client, admin_user, app):
    _login(client, admin_user)
    bom_id = _confirmed_source_bom(app)
    resp = client.post("/admin/bid-boms/create", data={"name": "입찰 v1", "vehicle": "NE2_NV1", "source_bom_id": str(bom_id)})
    assert resp.status_code == 302
    conn = db.get_connection(app.config["DB_PATH"])
    versions = db.list_bid_bom_versions(conn)
    assert len(versions) == 1
    assert versions[0]["name"] == "입찰 v1"
    assert versions[0]["source_bom_version_id"] == bom_id


def test_publish_and_withdraw_bid_bom(client, admin_user, app):
    _login(client, admin_user)
    bom_id = _confirmed_source_bom(app)
    conn = db.get_connection(app.config["DB_PATH"])
    bid_id = db.create_bid_bom_from_source(conn, bom_id, "입찰 v1", "NE2_NV1", "admin")["id"]
    conn.close()
    resp = client.post(f"/admin/bid-boms/{bid_id}/publish")
    assert resp.status_code == 302
    conn = db.get_connection(app.config["DB_PATH"])
    assert db.get_bid_bom_version(conn, bid_id)["status"] == "published"
    conn.close()
    resp = client.post(f"/admin/bid-boms/{bid_id}/withdraw", data={"reason": "오류"})
    assert resp.status_code == 302
    conn = db.get_connection(app.config["DB_PATH"])
    assert db.get_bid_bom_version(conn, bid_id)["is_withdrawn"] == 1


def test_delete_bid_bom_draft(client, admin_user, app):
    _login(client, admin_user)
    bom_id = _confirmed_source_bom(app)
    conn = db.get_connection(app.config["DB_PATH"])
    bid_id = db.create_bid_bom_from_source(conn, bom_id, "입찰 v1", "NE2_NV1", "admin")["id"]
    conn.close()
    resp = client.post(f"/admin/bid-boms/{bid_id}/delete")
    assert resp.status_code == 302
    conn = db.get_connection(app.config["DB_PATH"])
    assert db.get_bid_bom_version(conn, bid_id) is None
