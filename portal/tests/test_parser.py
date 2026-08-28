import db
import parser
from tests.fixtures import make_bom_fixture

def test_parse_inserts_new_parts(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    f = make_bom_fixture([
        {"part_no": "P001", "part_name": "FILTER", "qty": 2, "level_col": 6},
        {"part_no": "P002", "part_name": "O-RING", "qty": 1, "level_col": 7},
    ])
    result = parser.parse_and_upsert(conn, f)
    assert result["inserted"] == 2
    assert result["updated"] == 0
    part = db.get_part(conn, "P001", 12)
    assert part["part_name"] == "FILTER"
    assert part["level_depth"] == 1  # column 6 -> depth 1 (5,6,7,...=depth 0,1,2..)

def test_parse_upserts_existing_part_without_touching_purchase_data(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    f1 = make_bom_fixture([{"part_no": "P001", "part_name": "FILTER", "qty": 2, "level_col": 6}])
    parser.parse_and_upsert(conn, f1)
    db.upsert_purchase(conn, "P001", 12, "한국", {"unit_price_material": "1000"})

    f2 = make_bom_fixture([{"part_no": "P001", "part_name": "FILTER-V2", "qty": 3, "level_col": 6}])
    result = parser.parse_and_upsert(conn, f2)

    assert result["inserted"] == 0
    assert result["updated"] == 1
    part = db.get_part(conn, "P001", 12)
    assert part["part_name"] == "FILTER-V2"
    purchase = db.get_purchase(conn, "P001", 12, "한국")
    assert purchase["unit_price_material"] == "1000"

def test_parse_includes_rows_with_part_name_but_no_part_no(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    f = make_bom_fixture([
        {"part_no": "", "part_name": "NO PART NO", "qty": 1, "level_col": 6},
        {"part_no": "P001", "part_name": "FILTER", "qty": 2, "level_col": 6},
    ])
    result = parser.parse_and_upsert(conn, f)
    assert result["inserted"] == 2
    assert result["skipped"] == []
    assert db.get_part(conn, "", 12)["part_name"] == "NO PART NO"

def test_parse_preserves_duplicate_part_no_across_different_rows(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    f = make_bom_fixture([
        {"part_no": "P001", "part_name": "FILTER-A", "qty": 1, "level_col": 6},
        {"part_no": "P001", "part_name": "FILTER-B", "qty": 2, "level_col": 6},
    ])
    result = parser.parse_and_upsert(conn, f)
    assert result["inserted"] == 2
    assert result["updated"] == 0
    assert db.get_part(conn, "P001", 12)["part_name"] == "FILTER-A"
    assert db.get_part(conn, "P001", 13)["part_name"] == "FILTER-B"
