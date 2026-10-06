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


def test_summary_page_requires_login(client):
    resp = client.get("/bom/summary-page")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_summary_page_shows_empty_report_when_no_parts(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/bom/summary-page")
    assert resp.status_code == 200
    assert "데이터가 없습니다".encode() in resp.data


def test_summary_page_shows_vehicle_cost_report(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"vehicle": "NE2_NV1", "part_name": "FILTER", "qty": "1"})
    db.upsert_purchase(conn, "P001", 11, "한국", {"material_cost": "100", "total_cost": "115"})
    conn.close()

    resp = client.get("/bom/summary-page")
    assert resp.status_code == 200
    assert b"NE2_NV1" in resp.data


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


def test_grid_shows_pagination_nav_and_no_scroll_sentinel(client, admin_user, app):
    _login(client, admin_user)
    _seed_parts(app, n=25)
    resp = client.get("/bom/grid?country=한국&page=1")
    assert resp.status_code == 200
    assert b"grid-pagination" in resp.data
    assert b"scroll-sentinel" not in resp.data
    assert resp.data.count(b"<tr id=") == 20


def test_grid_next_page_still_renders_full_table_shell(client, admin_user, app):
    _login(client, admin_user)
    _seed_parts(app, n=25)
    resp = client.get("/bom/grid?country=한국&page=2")
    assert resp.status_code == 200
    assert b"<table" in resp.data
    assert resp.data.count(b"<tr id=") == 5


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


def test_bom_index_has_separate_major_and_sub_category_dropdowns(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER", "category": "HVAC", "sub_category": "DUCT", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 0, "●", {"part_name": "COIL", "category": "EVAP", "sub_category": "CORE", "qty": "1"})
    conn.close()

    resp = client.get("/bom/")
    html = resp.get_data(as_text=True)
    assert 'name="category" value="HVAC"' in html
    assert 'name="category" value="EVAP"' in html
    assert 'name="sub_category" value="DUCT"' in html
    assert 'name="sub_category" value="CORE"' in html


def test_grid_filters_by_sub_category(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER", "category": "HVAC", "sub_category": "DUCT", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 0, "●", {"part_name": "COIL", "category": "EVAP", "sub_category": "CORE", "qty": "1"})
    conn.close()

    resp = client.get("/bom/grid?country=한국&sub_category=DUCT")
    html = resp.get_data(as_text=True)
    assert "FILTER" in html
    assert "COIL" not in html


def test_grid_row_cells_are_keyboard_navigable(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER", "qty": "1"})
    conn.close()

    resp = client.get("/bom/grid?country=한국")
    html = resp.get_data(as_text=True)
    assert 'name="한국__unit_price_material"' in html
    unit_price_idx = html.index('name="한국__unit_price_material"')
    assert "nav-cell" in html[unit_price_idx:unit_price_idx + 300]


def test_grid_exposes_domestic_currency_and_special_fx_fields(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER", "qty": "1"})
    conn.close()

    resp = client.get("/bom/grid?country=한국")
    html = resp.get_data(as_text=True)
    assert 'name="한국__currency"' in html
    assert 'name="한국__special_fx_rate"' in html
    assert 'name="한국__special_fx_reason"' in html


def test_add_row_accepts_all_design_fields(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "ANCHOR", "qty": "1"})
    conn.close()

    resp = client.post("/bom/rows", data={
        "anchor_row_num": "11", "position": "after",
        "part_name": "NEW PART", "part_no": "P999", "qty": "3",
        "material": "SPCC", "width": "10", "depth_len": "20", "height": "30",
        "remark": "수동 추가",
    })
    assert resp.status_code == 200, resp.get_data(as_text=True)
    row_num = resp.get_json()["row_num"]

    conn = db.get_connection(app.config["DB_PATH"])
    part = db.get_part(conn, "P999", row_num)
    conn.close()
    assert part["material"] == "SPCC"
    assert part["width"] == "10"
    assert part["remark"] == "수동 추가"


def test_grid_has_quick_add_row_button_for_admin(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "ANCHOR", "qty": "1"})
    conn.close()

    resp = client.get("/bom/grid?country=한국")
    html = resp.get_data(as_text=True)
    assert 'id="quick-add-row-btn"' in html


def test_add_row_with_no_fields_creates_blank_manual_row(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "ANCHOR", "qty": "1"})
    conn.close()

    resp = client.post("/bom/rows", data={"anchor_row_num": "11", "position": "after"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    row_num = resp.get_json()["row_num"]

    conn = db.get_connection(app.config["DB_PATH"])
    part = db.get_part_by_row_num(conn, row_num)
    conn.close()
    assert part["manual_row"] == 1
    assert (part["part_name"] or "") == ""


def test_save_row_updates_manual_row_design_fields(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "ANCHOR", "qty": "1"})
    active = db.get_active_bom_version(conn)
    part = db.add_manual_part(conn, active["id"], "P001", 11, "after", {})
    conn.close()

    resp = client.post(
        f"/bom/row/by-number/{part['row_num']}/한국",
        data={"part_name": "새 품목", "part_no": "NEW-1", "vehicle": "NE2", "category": "HVAC", "qty": "5"},
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    conn = db.get_connection(app.config["DB_PATH"])
    saved = db.get_part_by_row_num(conn, part["row_num"])
    conn.close()
    assert saved["part_name"] == "새 품목"
    assert saved["part_no"] == "NEW-1"
    assert saved["vehicle"] == "NE2"
    assert saved["category"] == "HVAC"
    assert saved["qty"] == "5"


def test_delete_row_removes_manual_row_and_closes_gap(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "ANCHOR", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 0, "●", {"part_name": "AFTER", "qty": "1"})
    active = db.get_active_bom_version(conn)
    part = db.add_manual_part(conn, active["id"], "P001", 11, "after", {"part_name": "TEMP"})
    conn.close()
    added_row_num = part["row_num"]

    resp = client.post("/bom/row/delete", data={"row_num": str(added_row_num)})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    conn = db.get_connection(app.config["DB_PATH"])
    deleted = db.get_part_by_row_num(conn, added_row_num, active["id"])
    after = db.get_part(conn, "P002", added_row_num, active["id"])
    conn.close()
    assert deleted is None or deleted["part_no"] != "TEMP"
    assert after is not None and after["part_name"] == "AFTER"


def test_delete_row_rejects_non_manual_row(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "ANCHOR", "qty": "1"})
    conn.close()

    resp = client.post("/bom/row/delete", data={"row_num": "11"})
    assert resp.status_code == 422
    assert resp.get_json()["ok"] is False

    conn = db.get_connection(app.config["DB_PATH"])
    still_there = db.get_part(conn, "P001", 11)
    conn.close()
    assert still_there is not None


def test_delete_row_requires_admin(client, app):
    conn = db.get_connection(app.config["DB_PATH"])
    db.create_user(conn, "worker", generate_password_hash("worker-pass"), role="user")
    conn.close()
    client.post("/login", data={"username": "worker", "password": "worker-pass"})

    resp = client.post("/bom/row/delete", data={"row_num": "11"})
    assert resp.status_code == 403


def test_bom_index_has_group_only_filter_checkbox(client, admin_user, app):
    _login(client, admin_user)
    resp = client.get("/bom/")
    html = resp.get_data(as_text=True)
    assert 'name="group_only"' in html


def test_selected_group_disbands_with_single_row_selected(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "PARENT", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 1, "●", {"part_name": "CHILD", "qty": "1"})
    active = db.get_active_bom_version(conn)
    db.set_part_group(conn, active["id"], "P001", 11, 1, True, member_keys=[("P001", 11), ("P002", 12)])
    conn.close()

    resp = client.post("/bom/groups/selected", data={"row_num": ["12"]})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "removed": True}

    conn = db.get_connection(app.config["DB_PATH"])
    assert db.group_for_part(conn, active["id"], "P001", 11) is None
    conn.close()


def test_selected_group_single_ungrouped_row_returns_error(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "LONE", "qty": "1"})
    conn.close()

    resp = client.post("/bom/groups/selected", data={"row_num": ["11"]})
    assert resp.status_code == 422


def test_grid_group_child_badge_shows_parent_identity(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "PARENT", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 1, "●", {"part_name": "CHILD", "qty": "1"})
    active = db.get_active_bom_version(conn)
    db.set_part_group(conn, active["id"], "P001", 11, 1, True, member_keys=[("P001", 11), ("P002", 12)])
    conn.close()

    resp = client.get("/bom/grid?country=한국")
    html = resp.get_data(as_text=True)
    child_idx = html.index('row-P002-12')
    tail = html[child_idx:child_idx + 1500]
    assert "PARENT" in tail
    assert "P001" in tail


def test_grid_group_only_filters_to_grouped_rows(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "PARENT", "qty": "1"})
    db.upsert_part(conn, "P002", 12, 1, "●", {"part_name": "CHILD", "qty": "1"})
    db.upsert_part(conn, "P003", 13, 0, "●", {"part_name": "LONE", "qty": "1"})
    active = db.get_active_bom_version(conn)
    db.set_part_group(conn, active["id"], "P001", 11, int(admin_user["id"]) if "id" in admin_user else 1, True, member_keys=[("P001", 11), ("P002", 12)])
    conn.close()

    resp = client.get("/bom/grid?country=한국&group_only=1")
    html = resp.get_data(as_text=True)
    assert "P001" in html
    assert "P002" in html
    assert "P003" not in html


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


def test_history_requires_login(client):
    resp = client.get("/bom/history")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_history_defaults_to_purchase_type_and_lists_confirmed_version(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    bom_id = db.get_active_bom_version(conn)["id"]
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER"}, bom_id)
    db.publish_bom_version(conn, bom_id)
    db.confirm_bom_version(conn, bom_id)
    conn.close()

    resp = client.get("/bom/history")
    assert resp.status_code == 200
    assert "사용중".encode() in resp.data
    assert b"/bom/?version_id=" + str(bom_id).encode() in resp.data


def test_history_bid_type_shows_active_archived_and_withdrawn(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    bom_id = db.get_active_bom_version(conn)["id"]
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER"}, bom_id)
    db.publish_bom_version(conn, bom_id)
    db.confirm_bom_version(conn, bom_id)

    archived_id = db.create_bid_bom_from_source(conn, bom_id, "입찰 v1", "NE2_NV1", "admin")["id"]
    db.publish_bid_bom_version(conn, archived_id)

    withdrawn_id = db.create_bid_bom_from_source(conn, bom_id, "입찰 v2", "NE2_NV1", "admin")["id"]
    db.publish_bid_bom_version(conn, withdrawn_id)
    db.withdraw_bid_bom_version(conn, withdrawn_id, "오류", "admin")

    active_id = db.create_bid_bom_from_source(conn, bom_id, "입찰 v3", "NE2_NV1", "admin")["id"]
    db.publish_bid_bom_version(conn, active_id)
    conn.close()

    resp = client.get("/bom/history?type=bid")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "사용중" in html
    assert "보관" in html
    assert "배포취소" in html
    assert "/bid-bom/" in html


def test_history_bid_type_view_url_only_for_active_version(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    bom_id = db.get_active_bom_version(conn)["id"]
    db.upsert_part(conn, "P001", 11, 0, "●", {"part_name": "FILTER"}, bom_id)
    db.publish_bom_version(conn, bom_id)
    db.confirm_bom_version(conn, bom_id)

    archived_id = db.create_bid_bom_from_source(conn, bom_id, "입찰 v1", "NE2_NV1", "admin")["id"]
    db.publish_bid_bom_version(conn, archived_id)
    active_id = db.create_bid_bom_from_source(conn, bom_id, "입찰 v2", "NE2_NV1", "admin")["id"]
    db.publish_bid_bom_version(conn, active_id)
    conn.close()

    resp = client.get("/bom/history?type=bid")
    html = resp.get_data(as_text=True)
    assert html.count('href="/bid-bom/" class="btn btn-ghost btn-sm rounded-xl"') == 1
