import db
import fx

NUMERIC_FIELD_LABELS = {
    "unit_price_material": "재료단가",
    "unit_price_logistics": "물류단가",
    "tariff_rate": "관세율",
}

def _to_float(value):
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return float(value)
    except (TypeError, ValueError):
        return None

def compute_material_cost(conn, unit_price, qty, currency, special_fx_rate=None):
    unit_price = _to_float(unit_price)
    qty = _to_float(qty)
    if unit_price is None or qty is None or currency is None:
        return None
    rate = _to_float(special_fx_rate) if special_fx_rate not in (None, "") else fx.get_latest_rate(conn, currency)
    if rate is None:
        return None
    return unit_price * qty * rate

def compute_logistics_cost(unit_price_logistics, qty):
    unit_price_logistics = _to_float(unit_price_logistics)
    qty = _to_float(qty)
    if unit_price_logistics is None or qty is None:
        return None
    return unit_price_logistics * qty

def compute_tariff_cost(material_cost, tariff_rate):
    tariff_rate = _to_float(tariff_rate)
    if material_cost is None or tariff_rate is None:
        return None
    return material_cost * tariff_rate / 100

def compute_total_cost(material_cost, logistics_cost, tariff_cost):
    return sum(float(v) if v not in (None, "") else 0.0
               for v in (material_cost, logistics_cost, tariff_cost))

def recalculate_purchase_row(conn, part_no, row_num, country, fields):
    part = db.get_part(conn, part_no, row_num)
    qty = part["qty"] if part else None
    material_cost = compute_material_cost(
        conn, fields.get("unit_price_material"), qty, fields.get("currency"), fields.get("special_fx_rate")
    )
    logistics_cost = compute_logistics_cost(fields.get("unit_price_logistics"), qty)
    tariff_cost = compute_tariff_cost(material_cost, fields.get("tariff_rate"))
    # The displayed logistics figure includes tariff; keep tariff separately
    # for audit/export while avoiding a double count in total_cost.
    total_logistics_cost = compute_total_cost(logistics_cost, tariff_cost, None)
    total_cost = compute_total_cost(material_cost, total_logistics_cost, None)
    result = dict(fields)
    result["material_cost"] = material_cost
    result["logistics_cost"] = total_logistics_cost
    result["tariff_cost"] = tariff_cost
    result["total_cost"] = total_cost
    result["field_errors"] = [
        label for name, label in NUMERIC_FIELD_LABELS.items()
        if fields.get(name) not in (None, "") and _to_float(fields.get(name)) is None
    ]
    return result
