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
