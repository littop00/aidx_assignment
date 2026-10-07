from collections import Counter

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import db
from columns import DESIGN_FIELD_LABELS

bid_bom_bp = Blueprint("bid_bom", __name__, url_prefix="/bid-bom")

PAGE_SIZE = 20
PAGE_SIZE_OPTIONS = [10, 20, 30, 50]

DETAIL_FIELDS = [
    "spec", "sub_category", "qty", "material", "surface", "weight_total",
    "config_1", "config_2", "config_3", "config_4", "spec2",
    "width", "depth_len", "height", "thickness", "length",
    "material_price", "weight_al", "weight_cu", "weight_steel",
    "weight_unit", "shape", "diy_drawing", "diy_approval", "remark",
]

DETAIL_FIELD_LABELS = {**DESIGN_FIELD_LABELS, "qty": "수량", "weight_total": "중량", "sub_category": "소분류"}

BID_COST_FIELDS = ["unit_price", "material_cost", "total_cost"]
BID_VARIANCE_FIELDS = [
    "spec_add", "spec_delete", "spec_change",
    "material_change", "tariff_change", "fx_change",
    "cost_reduction", "cost_increase", "localization",
    "bridge_total", "bridge_note",
]
BID_PURCHASE_EDITABLE_FIELDS = BID_COST_FIELDS + BID_VARIANCE_FIELDS


def _parse_float(value):
    value = (value or "").strip()
    if value == "":
        return None
    return float(value)


def _can_edit_bid_info(part, user, allowed_categories):
    if user.role == "admin":
        return True
    return part.get("category") in allowed_categories


def _build_bid_row(part, purchase, info, can_edit_bid_info):
    purchase = purchase or {}
    info = info or {}
    diff = None
    if purchase.get("total_cost") is not None and part.get("ref_material_cost") is not None:
        diff = purchase["total_cost"] - part["ref_material_cost"]
    return {
        "part": part,
        "purchase": purchase,
        "info": info,
        "diff": diff,
        "can_edit_bid_info": can_edit_bid_info,
        "status_done": purchase.get("total_cost") is not None,
        "detail": {name: part.get(name) or "" for name in DETAIL_FIELDS},
    }


def _filtered_bid_rows(conn, bid_id, user, status, search, categories, sub_categories, assigned_only):
    parts = db.list_bid_parts(conn, bid_id)
    keyword = (search or "").strip().lower()
    category_set = set(categories) if categories else None
    sub_category_set = set(sub_categories) if sub_categories else None
    allowed = db.get_user_bid_categories(conn, bid_id, user.id) if user.role != "admin" else set()

    rows = []
    for part in parts:
        if category_set and part.get("category") not in category_set:
            continue
        if sub_category_set and part.get("sub_category") not in sub_category_set:
            continue
        if keyword and not any(
            keyword in (part.get(field) or "").lower() for field in ("part_no", "part_name", "category")
        ):
            continue
        can_edit = _can_edit_bid_info(part, user, allowed)
        if assigned_only and not can_edit:
            continue
        purchase = db.get_bid_purchase(conn, bid_id, part["part_no"], part["row_num"])
        info = db.get_bid_info(conn, bid_id, part["part_no"], part["row_num"])
        row = _build_bid_row(part, purchase, info, can_edit)
        if status == "done" and not row["status_done"]:
            continue
        if status == "missing" and row["status_done"]:
            continue
        rows.append(row)
    return rows


@bid_bom_bp.route("/")
@login_required
def index():
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bid_bom_version(conn)
    if not active:
        conn.close()
        return render_template("bid_bom_placeholder.html")
    parts = db.list_bid_parts(conn, active["id"])
    category_counts = Counter(part["category"] for part in parts if part.get("category"))
    sub_category_counts = Counter(part["sub_category"] for part in parts if part.get("sub_category"))
    conn.close()
    return render_template(
        "bid_bom.html",
        active=active,
        categories=sorted(category_counts),
        category_counts=category_counts,
        sub_categories=sorted(sub_category_counts),
        sub_category_counts=sub_category_counts,
        assigned_only=request.args.get("assigned_only") == "1",
    )


@bid_bom_bp.route("/grid")
@login_required
def grid():
    status = request.args.get("status", "all")
    search = request.args.get("search", "")
    categories = request.args.getlist("category")
    sub_categories = request.args.getlist("sub_category")
    assigned_only = request.args.get("assigned_only") == "1"
    try:
        page = int(request.args.get("page", 1))
    except ValueError:
        page = 1
    try:
        page_size = int(request.args.get("page_size", PAGE_SIZE))
    except ValueError:
        page_size = PAGE_SIZE
    if page_size not in PAGE_SIZE_OPTIONS:
        page_size = PAGE_SIZE

    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bid_bom_version(conn)
    all_rows = _filtered_bid_rows(conn, active["id"], current_user, status, search, categories, sub_categories, assigned_only) if active else []
    conn.close()

    total = len(all_rows)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    page_rows = all_rows[start:start + page_size]

    window_size = 5
    window_start = max(1, page - window_size // 2)
    window_end = min(total_pages, window_start + window_size - 1)
    window_start = max(1, window_end - window_size + 1)

    return render_template(
        "partials/_bid_grid.html",
        rows=page_rows,
        total=total,
        page=page,
        total_pages=total_pages,
        page_size=page_size,
        page_size_options=PAGE_SIZE_OPTIONS,
        window_start=window_start,
        window_end=window_end,
        design_field_labels=DETAIL_FIELD_LABELS,
        detail_fields=DETAIL_FIELDS,
        assigned_only=assigned_only,
        status=status,
        search=search,
        categories=categories,
        sub_categories=sub_categories,
    )


@bid_bom_bp.route("/save", methods=["POST"])
@login_required
def save():
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bid_bom_version(conn)
    if not active:
        conn.close()
        flash("배포된 입찰 BOM이 없습니다.")
        return redirect(url_for("bid_bom.index"))

    allowed = db.get_user_bid_categories(conn, active["id"], current_user.id) if current_user.role != "admin" else set()
    parts = db.list_bid_parts(conn, active["id"])
    for part in parts:
        part_no, row_num = part["part_no"], part["row_num"]
        suffix = f"{part_no}__{row_num}"

        if f"total_cost__{suffix}" in request.form or f"unit_price__{suffix}" in request.form:
            existing = db.get_bid_purchase(conn, active["id"], part_no, row_num) or {}
            fields = {name: existing.get(name) for name in db.BID_PURCHASE_FIELD_NAMES}
            for name in BID_PURCHASE_EDITABLE_FIELDS:
                raw = request.form.get(f"{name}__{suffix}", "")
                fields[name] = raw.strip() if name == "bridge_note" else _parse_float(raw)
            db.upsert_bid_purchase(conn, active["id"], part_no, row_num, fields, updated_by=current_user.username)

        if _can_edit_bid_info(part, current_user, allowed) and (
            f"decided_price__{suffix}" in request.form or f"bid_plan__{suffix}" in request.form
        ):
            fields = {}
            for name in db.BID_INFO_FIELD_NAMES:
                raw = request.form.get(f"{name}__{suffix}", "")
                fields[name] = raw.strip() if name in ("bid_plan", "selected_vendor", "review_comment") else _parse_float(raw)
            db.upsert_bid_info(conn, active["id"], part_no, row_num, fields, updated_by=current_user.username)

    conn.close()
    flash("입찰 BOM을 저장했습니다.")
    return redirect(url_for("bid_bom.index"))
