import db
import fx
import calc

def test_compute_material_cost_basic(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    fx.store_rate(conn, "USD", "2026-08-13", 1350.0)
    result = calc.compute_material_cost(conn, unit_price="10", qty="2", currency="USD")
    assert result == 27000.0

def test_compute_material_cost_krw_rate_is_one(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    result = calc.compute_material_cost(conn, unit_price="5000", qty="3", currency="KRW")
    assert result == 15000.0

def test_compute_material_cost_missing_rate_returns_none(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    result = calc.compute_material_cost(conn, unit_price="10", qty="2", currency="EUR")
    assert result is None

def test_compute_total_cost_sums_and_treats_none_as_zero():
    assert calc.compute_total_cost(1000.0, None, 200.0) == 1200.0
    assert calc.compute_total_cost(None, None, None) == 0.0

def test_compute_logistics_cost_basic():
    assert calc.compute_logistics_cost("50", "2") == 100.0
    assert calc.compute_logistics_cost("", "2") is None
    assert calc.compute_logistics_cost("50", None) is None

def test_compute_tariff_cost_basic():
    assert calc.compute_tariff_cost(1000.0, "10") == 100.0
    assert calc.compute_tariff_cost(1000.0, "") is None
    assert calc.compute_tariff_cost(None, "10") is None

def test_recalculate_purchase_row_fills_calculated_fields(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER", "qty": "2"})
    fields = {
        "currency": "KRW", "unit_price_material": "1000",
        "unit_price_logistics": "50", "tariff_rate": "10",
    }
    result = calc.recalculate_purchase_row(conn, "P001", 12, "한국", fields)
    assert result["material_cost"] == 2000.0
    assert result["logistics_cost"] == 300.0
    assert result["tariff_cost"] == 200.0
    assert result["total_cost"] == 2300.0
    assert result["field_errors"] == []

def test_recalculate_purchase_row_ignores_special_fx_for_domestic(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER", "qty": "2"})
    result = calc.recalculate_purchase_row(conn, "P001", 12, "한국", {
        "currency": "KRW", "unit_price_material": "1000", "special_fx_rate": "9999",
    })
    assert result["material_cost"] == 2000.0

def test_recalculate_purchase_row_reports_field_errors_for_non_numeric_input(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER", "qty": "2"})
    fields = {
        "currency": "KRW", "unit_price_material": "abc",
        "unit_price_logistics": "50", "tariff_rate": "10",
    }
    result = calc.recalculate_purchase_row(conn, "P001", 12, "한국", fields)
    assert result["field_errors"] == ["재료단가"]
    assert result["material_cost"] is None

def test_recalculate_purchase_row_uses_correct_row_when_same_part_no(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER-A", "qty": "1"})
    db.upsert_part(conn, "P001", 45, 2, "●", {"part_name": "FILTER-B", "qty": "10"})
    fields = {"currency": "KRW", "unit_price_material": "100"}
    result = calc.recalculate_purchase_row(conn, "P001", 45, "한국", fields)
    assert result["material_cost"] == 1000.0  # qty=10 from row 45, not row 12

def test_compute_effective_boxes_basic_fit():
    settings = {"box_width": "100", "box_depth": "100", "box_height": "100", "boxes_per_container": "10"}
    part = {"width": "50", "depth_len": "50", "height": "25", "weight_total": "1"}
    result = calc.compute_effective_boxes(settings, part)
    assert result["pieces_per_box"] == 16  # 2 * 2 * 4
    assert result["effective_boxes"] == 10
    assert result["auto_corrected"] is False

def test_compute_effective_boxes_auto_corrects_on_weight_limit():
    settings = {
        "box_width": "100", "box_depth": "100", "box_height": "100",
        "boxes_per_container": "10", "container_weight_limit_kg": "50",
    }
    part = {"width": "50", "depth_len": "50", "height": "25", "weight_total": "1"}
    # pieces_per_box=16, box_weight=16kg, 10 boxes -> 160kg > 50kg limit -> corrected to 3 boxes (48kg)
    result = calc.compute_effective_boxes(settings, part)
    assert result["auto_corrected"] is True
    assert result["effective_boxes"] == 3

def test_compute_effective_boxes_missing_dims_returns_none():
    assert calc.compute_effective_boxes({}, {"width": "50"}) is None
    assert calc.compute_effective_boxes(None, None) is None

def test_compute_export_logistics_allocates_freight_and_packaging(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    draft = db.create_draft_from_active(conn, "Export BOM", "NE2", "admin", False)
    bom_id = draft["id"]
    db.upsert_part(conn, "P001", 1, 0, "●", {
        "part_name": "FILTER", "qty": "1",
        "width": "50", "depth_len": "50", "height": "25", "weight_total": "1",
    }, bom_id)
    db.set_logistics_settings(conn, bom_id, {
        "box_width": "100", "box_depth": "100", "box_height": "100",
        "boxes_per_container": "10", "export_packaging_cost": "80",
    })
    import logistics
    logistics.store_rate(conn, "미국", "2026-01-01", {"container_freight": "8000"})
    part = db.get_part(conn, "P001", 1, bom_id)
    result = calc.compute_export_logistics(conn, part, "미국")
    # pieces_per_box=16, effective_boxes=10 -> total_pieces=160
    # freight_per_piece = 8000/160 = 50, packaging_per_piece = 80/16 = 5
    assert result["unit_price_logistics"] == 55.0
    assert result["auto_corrected"] is False

def test_compute_export_logistics_returns_none_without_rate(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    draft = db.create_draft_from_active(conn, "Export BOM", "NE2", "admin", False)
    bom_id = draft["id"]
    db.upsert_part(conn, "P001", 1, 0, "●", {
        "part_name": "FILTER", "qty": "1",
        "width": "50", "depth_len": "50", "height": "25", "weight_total": "1",
    }, bom_id)
    db.set_logistics_settings(conn, bom_id, {
        "box_width": "100", "box_depth": "100", "box_height": "100", "boxes_per_container": "10",
    })
    part = db.get_part(conn, "P001", 1, bom_id)
    assert calc.compute_export_logistics(conn, part, "미국") is None
