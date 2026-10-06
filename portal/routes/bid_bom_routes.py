from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import db

bid_bom_bp = Blueprint("bid_bom", __name__, url_prefix="/bid-bom")

BID_PURCHASE_READONLY_FIELDS = ["material", "size", "surface", "weight_unit", "weight_total", "dev_type", "remark"]
BID_PURCHASE_EDITABLE_FIELDS = [
    "unit_price", "material_cost", "total_cost",
    "spec_add", "spec_delete", "spec_change",
    "material_change", "tariff_change", "fx_change",
    "cost_reduction", "cost_increase", "localization",
    "bridge_total", "bridge_note",
]


@bid_bom_bp.route("/")
@login_required
def index():
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bid_bom_version(conn)
    if not active:
        conn.close()
        return render_template("bid_bom_placeholder.html")
    parts = db.list_bid_parts(conn, active["id"])
    rows = []
    for part in parts:
        purchase = db.get_bid_purchase(conn, active["id"], part["part_no"], part["row_num"]) or {}
        diff = None
        if purchase.get("total_cost") is not None and part.get("ref_material_cost") is not None:
            diff = purchase["total_cost"] - part["ref_material_cost"]
        rows.append({"part": part, "purchase": purchase, "diff": diff})
    conn.close()
    return render_template("bid_bom.html", active=active, rows=rows)


def _parse_float(value):
    value = (value or "").strip()
    if value == "":
        return None
    return float(value)


@bid_bom_bp.route("/save", methods=["POST"])
@login_required
def save():
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bid_bom_version(conn)
    if not active:
        conn.close()
        flash("배포된 입찰 BOM이 없습니다.")
        return redirect(url_for("bid_bom.index"))
    parts = db.list_bid_parts(conn, active["id"])
    for part in parts:
        part_no, row_num = part["part_no"], part["row_num"]
        suffix = f"{part_no}__{row_num}"
        if f"total_cost__{suffix}" not in request.form and f"unit_price__{suffix}" not in request.form:
            continue
        existing = db.get_bid_purchase(conn, active["id"], part_no, row_num) or {}
        fields = {name: existing.get(name) for name in BID_PURCHASE_READONLY_FIELDS + BID_PURCHASE_EDITABLE_FIELDS}
        for name in BID_PURCHASE_EDITABLE_FIELDS:
            raw = request.form.get(f"{name}__{suffix}", "")
            fields[name] = raw.strip() if name == "bridge_note" else _parse_float(raw)
        db.upsert_bid_purchase(conn, active["id"], part_no, row_num, fields, updated_by=current_user.username)
    conn.close()
    flash("입찰 재료비 변동내역을 저장했습니다.")
    return redirect(url_for("bid_bom.index"))
