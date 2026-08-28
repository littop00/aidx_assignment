import columns

def test_purchase_column_korea_material_cost():
    assert columns.purchase_column("한국", "material_cost") == 43

def test_design_fields_contains_part_no():
    names = [n for n, _ in columns.DESIGN_FIELDS]
    assert "part_no" in names
