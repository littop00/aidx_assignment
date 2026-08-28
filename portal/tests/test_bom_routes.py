import db
from werkzeug.security import generate_password_hash


def _login(client, admin_user):
    client.post("/login", data=admin_user)


def _seed_parts(app, n=25):
    conn = db.get_connection(app.config["DB_PATH"])
    for i in range(n):
        part_no = f"P{i:03d}"
        db.upsert_part(conn, part_no, 11 + i, 0, "●", {"part_name": f"PART{i}", "qty": "1"})
    conn.close()


def test_bom_index_requires_login(client):
    resp = client.get("/bom/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_user_submits_only_selected_assignment(client, app):
    conn = db.get_connection(app.config["DB_PATH"])
    db.create_user(conn, "worker", generate_password_hash("worker-pass"), role="user")
    db.set_bom_countries(conn, db.get_active_bom_version(conn)["id"], ["한국"])
    db.upsert_part(conn, "P001", 11, 0, "L0", {"part_name": "ASSIGNED", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 0, "L0", {"part_name": "NOT ASSIGNED", "qty": "1"})
    conn.close()
    client.post("/login", data={"username": "worker", "password": "worker-pass"})

    no_assignment = client.post("/bom/submit")
    assert no_assignment.status_code == 422
    assert "담당 품목" in no_assignment.get_json()["message"]

    selected = client.post("/bom/assignments/P001/11", data={"assigned": "1"})
    assert selected.status_code == 200
    assert selected.get_json()["count"] == 1

    saved = client.post("/bom/row/P001/11/한국", data={"currency": "KRW", "unit_price_material": "100"})
    assert saved.status_code == 200
    submitted = client.post("/bom/submit")
    assert submitted.status_code == 200


def test_user_can_reset_draft_work(client, app):
    conn = db.get_connection(app.config["DB_PATH"])
    db.create_user(conn, "reset-user", generate_password_hash("reset-pass"), role="user")
    db.upsert_part(conn, "P001", 11, 0, "L0", {"part_name": "RESET", "qty": "1"})
    conn.close()
    client.post("/login", data={"username": "reset-user", "password": "reset-pass"})
    client.post("/bom/assignments/P001/11", data={"assigned": "1"})
    client.post("/bom/row/P001/11/한국", data={"currency": "KRW", "unit_price_material": "100"})
    response = client.post("/bom/reset-work")
    assert response.status_code == 200
    conn = db.get_connection(app.config["DB_PATH"])
    active = db.get_active_bom_version(conn)
    user_id = db.get_user_by_username(conn, "reset-user")["id"]
    assert not db.assigned_part_keys(conn, active["id"], user_id)


def test_grid_paginates_results(client, admin_user, app):
    _login(client, admin_user)
    _seed_parts(app, n=25)
    resp = client.get("/bom/grid?country=한국&page=1")
    assert resp.status_code == 200
    assert resp.data.count(b"<tr id=") == 20

    resp2 = client.get("/bom/grid?country=한국&page=2")
    assert resp2.data.count(b"<tr id=") == 5


def test_grid_respects_page_size_param(client, admin_user, app):
    _login(client, admin_user)
    _seed_parts(app, n=25)
    resp = client.get("/bom/grid?country=한국&page=1&page_size=10")
    assert resp.data.count(b"<tr id=") == 10

    resp2 = client.get("/bom/grid?country=한국&page=1&page_size=999")
    assert resp2.data.count(b"<tr id=") == 20  # invalid size falls back to default


def test_grid_search_filters_by_part_no(client, admin_user, app):
    _login(client, admin_user)
    _seed_parts(app, n=5)
    resp = client.get("/bom/grid?country=한국&search=P002")
    assert b"P002" in resp.data
    assert b"P003" not in resp.data


def test_save_row_recalculates_and_persists(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER", "qty": "2"})
    conn.close()

    resp = client.post(
        "/bom/row/P001/11/한국",
        data={
            "currency": "KRW",
            "unit_price_material": "100",
            "unit_price_logistics": "",
            "logistics_cost": "",
            "tariff_rate": "",
            "tariff_cost": "",
            "mold_cost": "",
        },
    )
    assert resp.status_code == 200

    conn = db.get_connection(app.config["DB_PATH"])
    purchase = db.get_purchase(conn, "P001", 11, "한국")
    conn.close()
    assert float(purchase["material_cost"]) == 200.0
    assert float(purchase["total_cost"]) == 200.0
    assert purchase["updated_by"] == admin_user["username"]
    assert purchase["updated_at"]


def test_save_row_combines_tariff_into_total_logistics(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P002", 12, 0, "●", {"part_name": "BRACKET", "qty": "2"})
    conn.close()

    resp = client.post(
        "/bom/row/P002/12/한국",
        data={
            "currency": "KRW", "unit_price_material": "1,000",
            "unit_price_logistics": "50", "tariff_rate": "10", "mold_cost": "",
        },
    )
    assert resp.status_code == 200
    conn = db.get_connection(app.config["DB_PATH"])
    purchase = db.get_purchase(conn, "P002", 12, "한국")
    conn.close()
    assert float(purchase["material_cost"]) == 2000.0
    assert float(purchase["tariff_cost"]) == 200.0
    assert float(purchase["logistics_cost"]) == 300.0
    assert float(purchase["total_cost"]) == 2300.0
    assert b"data-save-url=" in resp.data
    assert b"row-autosave" in resp.data


def test_grid_search_filters_by_category(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER", "category": "HVAC", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 0, "●", {"part_name": "BRACKET", "category": "TTMM", "qty": "1"})
    conn.close()

    resp = client.get("/bom/grid?country=한국&search=HVAC")
    assert b"P001" in resp.data
    assert b"P002" not in resp.data


def test_grid_filters_by_multiple_selected_categories(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER", "category": "HVAC", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 0, "●", {"part_name": "BRACKET", "category": "TTMM", "qty": "1"})
    db.upsert_part(conn, "P003", 13, 0, "●", {"part_name": "SENSOR", "category": "ECOMP", "qty": "1"})
    conn.close()

    resp = client.get("/bom/grid?country=한국&category=HVAC&category=TTMM")
    assert b"P001" in resp.data
    assert b"P002" in resp.data
    assert b"P003" not in resp.data


def test_bom_index_includes_search_suggestions(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER", "category": "HVAC", "qty": "1"})
    conn.close()

    resp = client.get("/bom/")
    assert resp.status_code == 200
    assert b"part-suggestions" in resp.data
    assert b"P001" in resp.data


def test_bom_index_shows_category_counts(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER", "category": "HVAC", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 0, "●", {"part_name": "BRACKET", "category": "HVAC", "qty": "1"})
    db.upsert_part(conn, "P003", 13, 0, "●", {"part_name": "SENSOR", "category": "ECOMP", "qty": "1"})
    conn.close()

    resp = client.get("/bom/")
    html = resp.get_data(as_text=True)
    assert "HVAC" in html
    assert "ECOMP" in html
    hvac_idx = html.index("HVAC")
    assert "2" in html[hvac_idx:hvac_idx + 200]


def test_summary_groups_by_category_with_grand_total(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"category": "HVAC", "part_name": "FILTER", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 0, "●", {"category": "TTMM", "part_name": "BRACKET", "qty": "1"})
    db.upsert_purchase(conn, "P001", 11, "한국", {"material_cost": "100", "logistics_cost": "10", "tariff_cost": "5", "total_cost": "115"})
    db.upsert_purchase(conn, "P002", 12, "한국", {"material_cost": "200", "logistics_cost": "20", "tariff_cost": "10", "total_cost": "230"})
    conn.close()

    resp = client.get("/bom/summary?country=한국")
    assert resp.status_code == 200
    assert b"HVAC" in resp.data
    assert b"TTMM" in resp.data
    assert "345".encode() in resp.data
