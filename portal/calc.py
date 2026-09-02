import db
import fx

NUMERIC_FIELD_LABELS = {
    "unit_price_material": "재료단가",
    "unit_price_logistics": "운송비용",
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

def _box_pieces(box_dim, part_dim):
    box_dim = _to_float(box_dim)
    part_dim = _to_float(part_dim)
    if not box_dim or not part_dim:
        return None
    pieces = int(box_dim // part_dim)
    return pieces if pieces > 0 else None

def compute_effective_boxes(settings, part):
    """Box-fit + weight-limit auto-correction. Returns None if settings/part
    dimensions are incomplete. Otherwise a dict with pieces_per_box,
    boxes_per_container (admin input), effective_boxes (after correction),
    and auto_corrected (bool)."""
    if not settings or not part:
        return None
    pieces_w = _box_pieces(settings.get("box_width"), part.get("width"))
    pieces_d = _box_pieces(settings.get("box_depth"), part.get("depth_len"))
    pieces_h = _box_pieces(settings.get("box_height"), part.get("height"))
    if not pieces_w or not pieces_d or not pieces_h:
        return None
    pieces_per_box = pieces_w * pieces_d * pieces_h
    weight_total = _to_float(part.get("weight_total"))
    boxes_per_container = _to_float(settings.get("boxes_per_container"))
    if not weight_total or not boxes_per_container:
        return None
    box_weight = pieces_per_box * weight_total
    weight_limit = _to_float(settings.get("container_weight_limit_kg"))
    effective_boxes = boxes_per_container
    auto_corrected = False
    if weight_limit and box_weight * boxes_per_container > weight_limit:
        effective_boxes = max(1, int(weight_limit // box_weight))
        auto_corrected = True
    return {
        "pieces_per_box": pieces_per_box,
        "boxes_per_container": boxes_per_container,
        "effective_boxes": effective_boxes,
        "auto_corrected": auto_corrected,
    }

def compute_export_logistics(conn, part, country):
    """Auto-calculated per-piece export logistics unit price for overseas
    countries, derived from box-fit + container freight rate. Returns None
    if the BOM's logistics master settings or the country's freight rate
    aren't set up yet (caller should fall back to manual input in that case)."""
    if not part:
        return None
    bom_id = part.get("bom_id")
    settings = db.get_logistics_settings(conn, bom_id)
    boxes = compute_effective_boxes(settings, part)
    if not boxes:
        return None
    freight = db.get_container_freight(conn, bom_id, country)
    if freight is None:
        return None
    total_pieces = boxes["pieces_per_box"] * boxes["effective_boxes"]
    freight_per_piece = _to_float(freight) / total_pieces
    packaging_cost = _to_float(settings.get("export_packaging_cost")) or 0
    packaging_per_piece = packaging_cost / boxes["pieces_per_box"]
    return {
        "unit_price_logistics": freight_per_piece + packaging_per_piece,
        "auto_corrected": boxes["auto_corrected"],
        "boxes_per_container": boxes["boxes_per_container"],
        "effective_boxes": boxes["effective_boxes"],
    }

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
    special_fx_rate = fields.get("special_fx_rate") if country != "한국" else None
    fields = dict(fields)
    if country != "한국":
        export = compute_export_logistics(conn, part, country)
        if export:
            fields["unit_price_logistics"] = export["unit_price_logistics"]
    material_cost = compute_material_cost(
        conn, fields.get("unit_price_material"), qty, fields.get("currency"), special_fx_rate
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
