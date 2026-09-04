DESIGN_FIELDS = [
    ("vehicle", 2), ("category", 3), ("sub_category", 4), ("part_name", 12), ("part_no", 13),
    ("spec", 14), ("config_1", 15), ("config_2", 16), ("config_3", 17),
    ("config_4", 18), ("qty", 19), ("material", 20), ("surface", 21),
    ("spec2", 22), ("width", 23), ("depth_len", 24), ("height", 25),
    ("thickness", 26), ("length", 27), ("material_price", 28),
    ("weight_al", 29), ("weight_cu", 30), ("weight_steel", 31),
    ("weight_unit", 32), ("weight_total", 33), ("shape", 34),
    ("diy_drawing", 35), ("diy_approval", 36), ("remark", 37),
]

DESIGN_FIELD_LABELS = {
    "vehicle": "차종", "category": "구분", "sub_category": "세부구분",
    "spec": "사양", "config_1": "구성1", "config_2": "구성2",
    "config_3": "구성3", "config_4": "구성4", "qty": "수량",
    "material": "재질", "surface": "표면처리", "spec2": "규격",
    "width": "가로", "depth_len": "세로", "height": "높이",
    "thickness": "두께", "length": "길이", "material_price": "소재가격",
    "weight_al": "알루미늄", "weight_cu": "구리", "weight_steel": "철강",
    "weight_unit": "단중", "weight_total": "중량합계", "shape": "제품형상",
    "diy_drawing": "자작도", "diy_approval": "승인도", "remark": "비고",
}

LEVEL_COLUMNS = list(range(5, 12))  # E~K, depth 0~6

COUNTRIES = ["한국", "미국", "유럽"]
COUNTRY_BASE_COL = {"한국": 39, "미국": 52, "유럽": 65}

PURCHASE_FIELDS = [
    ("sourcing_part", 0), ("sourcing_assembly", 1), ("currency", 2),
    ("unit_price_material", 3), ("material_cost", 4),
    ("unit_price_logistics", 5), ("logistics_cost", 6),
    ("tariff_rate", 7), ("unit_price_tariff", 8), ("tariff_cost", 9),
    ("total_cost", 10), ("mold_cost", 11),
]

CALCULATED_PURCHASE_FIELDS = {"material_cost", "logistics_cost", "tariff_cost", "total_cost"}

# BOM data begins at row 12; rows 1~11 are headers/formatting only.
FIRST_DATA_ROW = 12

def purchase_column(country, field_name):
    base = COUNTRY_BASE_COL[country]
    for name, offset in PURCHASE_FIELDS:
        if name == field_name:
            return base + offset
    raise KeyError(field_name)
