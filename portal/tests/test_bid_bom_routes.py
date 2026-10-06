from werkzeug.security import generate_password_hash

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


def _published_bid_bom(app):
    conn = db.get_connection(app.config["DB_PATH"])
    bom_id = db.get_active_bom_version(conn)["id"]
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER", "part_no": "P001", "category": "엔진"}, bom_id)
    db.upsert_purchase(conn, "P001", 11, "한국", {"total_cost": 100}, bom_id=bom_id)
    db.publish_bom_version(conn, bom_id)
    db.confirm_bom_version(conn, bom_id)
    bid_id = db.create_bid_bom_from_source(conn, bom_id, "입찰 v1", "NE2_NV1", "admin")["id"]
    db.publish_bid_bom_version(conn, bid_id)
    conn.close()
    return bid_id


def test_bid_bom_grid_shows_published_version_rows(client, admin_user, app):
    _login(client, admin_user)
    _published_bid_bom(app)
    resp = client.get("/bid-bom/")
    assert resp.status_code == 200
    assert b"P001" in resp.data
    assert b"100" in resp.data


def test_bid_bom_save_updates_purchase_data(client, admin_user, app):
    _login(client, admin_user)
    bid_id = _published_bid_bom(app)
    resp = client.post("/bid-bom/save", data={
        "unit_price__P001__11": "50",
        "total_cost__P001__11": "90",
        "bridge_note__P001__11": "협력사 견적",
    })
    assert resp.status_code == 302
    conn = db.get_connection(app.config["DB_PATH"])
    purchase = db.get_bid_purchase(conn, bid_id, "P001", 11)
    assert purchase["unit_price"] == 50.0
    assert purchase["total_cost"] == 90.0
    assert purchase["bridge_note"] == "협력사 견적"


def test_bid_bom_save_skips_rows_without_submitted_fields(client, admin_user, app):
    _login(client, admin_user)
    bid_id = _published_bid_bom(app)
    resp = client.post("/bid-bom/save", data={})
    assert resp.status_code == 302
    conn = db.get_connection(app.config["DB_PATH"])
    assert db.get_bid_purchase(conn, bid_id, "P001", 11) is None


def _create_regular_user(app, username):
    conn = db.get_connection(app.config["DB_PATH"])
    password_hash = generate_password_hash("secret123")
    db.create_user(conn, username, password_hash, role="user")
    user = db.get_user_by_username(conn, username)
    conn.close()
    return {"username": username, "password": "secret123", "id": user["id"]}


def test_admin_assigns_bid_category_members(client, admin_user, app):
    _login(client, admin_user)
    bid_id = _published_bid_bom(app)
    bob = _create_regular_user(app, "bob")
    resp = client.post(f"/admin/bid-boms/{bid_id}/users/{bob['id']}/categories", data={"categories": ["엔진"]})
    assert resp.status_code == 302
    conn = db.get_connection(app.config["DB_PATH"])
    assert db.get_user_bid_categories(conn, bid_id, bob["id"]) == {"엔진"}


def test_bid_bom_input_shows_only_assigned_parts(client, app):
    bid_id = _published_bid_bom(app)
    bob = _create_regular_user(app, "bob")
    conn = db.get_connection(app.config["DB_PATH"])
    db.set_bid_category_membership(conn, bid_id, bob["id"], "엔진", True)
    conn.close()
    _login(client, bob)
    resp = client.get("/bid-bom/input")
    assert resp.status_code == 200
    assert b"P001" in resp.data


def test_bid_bom_input_hides_unassigned_parts(client, app):
    _published_bid_bom(app)
    carol = _create_regular_user(app, "carol")
    _login(client, carol)
    resp = client.get("/bid-bom/input")
    assert resp.status_code == 200
    assert b"P001" not in resp.data


def test_bid_bom_input_save_persists_bid_info(client, app):
    bid_id = _published_bid_bom(app)
    bob = _create_regular_user(app, "bob")
    conn = db.get_connection(app.config["DB_PATH"])
    db.set_bid_category_membership(conn, bid_id, bob["id"], "엔진", True)
    conn.close()
    _login(client, bob)
    resp = client.post("/bid-bom/input/save", data={
        "bid_plan__P001__11": "경쟁입찰",
        "decided_price__P001__11": "80",
    })
    assert resp.status_code == 302
    conn = db.get_connection(app.config["DB_PATH"])
    info = db.get_bid_info(conn, bid_id, "P001", 11)
    assert info["bid_plan"] == "경쟁입찰"
    assert info["decided_price"] == 80.0


def test_bid_bom_input_save_ignores_unassigned_submission(client, app):
    bid_id = _published_bid_bom(app)
    carol = _create_regular_user(app, "carol")
    _login(client, carol)
    resp = client.post("/bid-bom/input/save", data={
        "bid_plan__P001__11": "경쟁입찰",
        "decided_price__P001__11": "80",
    })
    assert resp.status_code == 302
    conn = db.get_connection(app.config["DB_PATH"])
    assert db.get_bid_info(conn, bid_id, "P001", 11) is None
