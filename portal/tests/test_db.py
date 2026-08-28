import db

def test_upsert_and_get_part(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", row_num=12, level_depth=1, level_marker="●",
                    fields={"vehicle": "NE2_NV1", "part_name": "FILTER", "qty": "2"})
    part = db.get_part(conn, "P001", 12)
    assert part["part_no"] == "P001"
    assert part["row_num"] == 12
    assert part["part_name"] == "FILTER"
    assert part["qty"] == "2"

def test_same_part_no_different_row_num_are_distinct(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER-A"})
    db.upsert_part(conn, "P001", 45, 2, "●", {"part_name": "FILTER-B"})
    assert db.get_part(conn, "P001", 12)["part_name"] == "FILTER-A"
    assert db.get_part(conn, "P001", 45)["part_name"] == "FILTER-B"
    assert len(db.list_parts(conn)) == 2

def test_existing_user_input_is_kept_in_assignment_scope(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    bom_id = db.get_active_bom_version(conn)["id"]
    db.create_user(conn, "worker", "hash", role="user")
    user_id = db.get_user_by_username(conn, "worker")["id"]
    db.upsert_part(conn, "P001", 12, 1, "L1", {"part_name": "FILTER"}, bom_id)
    db.upsert_user_purchase(conn, "P001", 12, "한국", user_id, {"unit_price_material": "100"}, bom_id=bom_id)
    assert ("P001", 12) in db.assigned_part_keys(conn, bom_id, user_id)
    assert len(db.list_assigned_parts(conn, bom_id, user_id)) == 1

def test_upsert_keeps_other_fields_on_partial_update(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER", "qty": "2"})
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER-V2", "qty": "2"})
    part = db.get_part(conn, "P001", 12)
    assert part["part_name"] == "FILTER-V2"
    assert len(db.list_parts(conn)) == 1

def test_upsert_and_get_purchase(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER"})
    db.upsert_purchase(conn, "P001", 12, "한국", {"currency": "KRW", "unit_price_material": "1000"})
    purchase = db.get_purchase(conn, "P001", 12, "한국")
    assert purchase["currency"] == "KRW"
    assert purchase["unit_price_material"] == "1000"

def test_upsert_purchase_records_audit_trail(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER"})
    db.upsert_purchase(conn, "P001", 12, "한국", {"unit_price_material": "1000"}, updated_by="admin")
    purchase = db.get_purchase(conn, "P001", 12, "한국")
    assert purchase["updated_by"] == "admin"
    assert purchase["updated_at"]

def test_purchase_upsert_updates_not_duplicates(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER"})
    db.upsert_purchase(conn, "P001", 12, "한국", {"unit_price_material": "1000"})
    db.upsert_purchase(conn, "P001", 12, "한국", {"unit_price_material": "2000"})
    rows = db.list_purchase_for_part(conn, "P001", 12)
    assert len(rows) == 1
    assert rows[0]["unit_price_material"] == "2000"

def test_purchase_distinct_per_row_num_for_same_part_no(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER-A"})
    db.upsert_part(conn, "P001", 45, 2, "●", {"part_name": "FILTER-B"})
    db.upsert_purchase(conn, "P001", 12, "한국", {"unit_price_material": "1000"})
    db.upsert_purchase(conn, "P001", 45, "한국", {"unit_price_material": "9999"})
    assert db.get_purchase(conn, "P001", 12, "한국")["unit_price_material"] == "1000"
    assert db.get_purchase(conn, "P001", 45, "한국")["unit_price_material"] == "9999"

def test_create_and_get_user(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.create_user(conn, "admin", "hashed-pw", "admin")
    user = db.get_user_by_username(conn, "admin")
    assert user["username"] == "admin"
    assert user["password_hash"] == "hashed-pw"
    assert user["role"] == "admin"
    assert db.get_user_by_id(conn, user["id"])["username"] == "admin"

def test_get_user_by_username_missing_returns_none(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    assert db.get_user_by_username(conn, "nobody") is None

def test_grouped_children_are_not_required_for_submission(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    bom_id = db.get_active_bom_version(conn)["id"]
    db.create_user(conn, "worker2", "hash", "user")
    user_id = db.get_user_by_username(conn, "worker2")["id"]
    db.upsert_part(conn, "A", 11, 0, "●", {"part_name": "ASSY"}, bom_id)
    db.upsert_part(conn, "B", 12, 1, "●", {"part_name": "CHILD"}, bom_id)
    db.set_part_assignment(conn, bom_id, user_id, "A", 11, True)
    db.set_part_assignment(conn, bom_id, user_id, "B", 12, True)
    db.set_part_group(conn, bom_id, "A", 11, user_id, True)
    db.upsert_user_purchase(conn, "A", 11, "한국", user_id, {"unit_price_material": "10"}, bom_id=bom_id)
    assert db.submission_progress(conn, bom_id, user_id)["total"] == 3

def test_revision_migrates_user_input_by_name_and_detail_not_part_number(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db")); db.init_db(conn)
    source = db.get_active_bom_version(conn)["id"]
    db.create_user(conn, "migrator", "hash", "user"); user_id = db.get_user_by_username(conn, "migrator")["id"]
    db.upsert_part(conn, "OLD", 11, 0, "●", {"part_name": "FILTER", "spec": "A", "qty": "2"}, source)
    db.upsert_user_purchase(conn, "OLD", 11, "한국", user_id, {"unit_price_material": "99"}, bom_id=source)
    target = db.create_draft_from_active(conn, "v2", "NE2", "admin")["id"]
    db.replace_bom_draft_data(conn, target)
    db.upsert_part(conn, "NEW", 22, 0, "●", {"part_name": "FILTER", "spec": "A", "qty": "2"}, target)
    assert db.migrate_matching_user_work(conn, source, target) == 1
    assert db.get_user_purchase(conn, "NEW", 22, "한국", user_id, target)["unit_price_material"] == "99"

def _seed_summary_data(conn):
    db.upsert_part(conn, "P001", 11, 0, "●", {"vehicle": "NE2_NV1", "category": "HVAC", "part_name": "FILTER", "qty": "2"})
    db.upsert_part(conn, "P002", 12, 0, "●", {"vehicle": "NE2_NV1", "category": "TTMM", "part_name": "BRACKET", "qty": "1"})
    db.upsert_purchase(conn, "P001", 11, "한국", {"material_cost": "100", "logistics_cost": "10", "tariff_cost": "5", "total_cost": "115"})
    db.upsert_purchase(conn, "P002", 12, "한국", {"material_cost": "200", "logistics_cost": "20", "tariff_cost": "10", "total_cost": "230"})
    db.upsert_purchase(conn, "P001", 11, "미국", {"material_cost": "50", "logistics_cost": "5", "tariff_cost": "2", "total_cost": "57"})

def test_vehicle_country_summary(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    _seed_summary_data(conn)
    result = db.vehicle_country_summary(conn)
    by_key = {(r["vehicle"], r["country"]): r for r in result}
    assert by_key[("NE2_NV1", "한국")]["material_sum"] == 300.0
    assert by_key[("NE2_NV1", "한국")]["total_sum"] == 345.0
    assert by_key[("NE2_NV1", "미국")]["material_sum"] == 50.0

def test_category_summary_filters_by_country(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    _seed_summary_data(conn)
    result = db.category_summary(conn, "한국")
    by_category = {r["category"]: r for r in result}
    assert by_category["HVAC"]["material_sum"] == 100.0
    assert by_category["TTMM"]["material_sum"] == 200.0
    assert set(by_category.keys()) == {"HVAC", "TTMM"}

def test_search_suggestions_returns_distinct_parts(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    _seed_summary_data(conn)
    result = db.search_suggestions(conn)
    part_nos = {r["part_no"] for r in result}
    assert part_nos == {"P001", "P002"}
    categories = {r["category"] for r in result}
    assert categories == {"HVAC", "TTMM"}
