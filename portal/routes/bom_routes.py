from collections import Counter

from flask import Blueprint, render_template, request, current_app, jsonify, redirect, url_for
from flask_login import login_required, current_user
import db
import calc
from columns import COUNTRIES, DESIGN_FIELDS

bom_bp = Blueprint("bom", __name__, url_prefix="/bom")

PAGE_SIZE = 20
PAGE_SIZE_OPTIONS = [10, 20, 30, 50]

def _to_float(value):
    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return float(value) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0

def _build_row_view(part, purchase):
    purchase = purchase or {}
    has_price = bool(purchase.get("unit_price_material"))
    row = {
        "part_no": part["part_no"],
        "row_num": part["row_num"],
        "part_name": part.get("part_name") or "",
        "vehicle": part.get("vehicle") or "",
        "level_depth": part.get("level_depth") or 0,
        "level_marker": part.get("level_marker") or "",
        "category": part.get("category") or "",
        "qty": _to_float(part.get("qty")),
        "status_done": has_price,
        "currency": purchase.get("currency") or "KRW",
        "unit_price_material": purchase.get("unit_price_material") or "",
        "material_cost": _to_float(purchase.get("material_cost")),
        "unit_price_logistics": purchase.get("unit_price_logistics") or "",
        "logistics_cost": _to_float(purchase.get("logistics_cost")),
        "tariff_rate": purchase.get("tariff_rate") or "",
        "tariff_cost": _to_float(purchase.get("tariff_cost")),
        "total_cost": _to_float(purchase.get("total_cost")),
        "mold_cost": purchase.get("mold_cost") or "",
        "updated_at": purchase.get("updated_at") or "",
        "updated_by": purchase.get("updated_by") or "",
    }
    # Render the E~K LEVEL columns one-for-one with their headers.  The
    # source value itself is not meaningful in the portal; a dot preserves
    # hierarchy without showing the old numeric "1" marker.
    row["level_slots"] = ["●" if index == row["level_depth"] else "" for index in range(7)]
    row["detail"] = {name: part.get(name) or "" for name, _ in DESIGN_FIELDS if name not in ("part_no", "part_name")}
    row["sourcing_part"] = purchase.get("sourcing_part") or ""
    row["sourcing_assembly"] = purchase.get("sourcing_assembly") or ""
    row["sourcing_part_location"] = purchase.get("sourcing_part_location") or ""
    row["sourcing_assembly_location"] = purchase.get("sourcing_assembly_location") or ""
    row["special_fx_rate"] = purchase.get("special_fx_rate") or ""
    row["special_fx_reason"] = purchase.get("special_fx_reason") or ""
    return row

def _filtered_rows(conn, countries, status, search, categories=None, user_id=None, assigned_only=False):
    primary_country = countries[0]
    parts = db.list_parts(conn)
    keyword = (search or "").strip().lower()
    categories = set(categories) if categories else None
    active = db.get_active_bom_version(conn)
    assigned_keys = db.assigned_part_keys(conn, active["id"], user_id) if active and user_id is not None else set()
    rows = []
    for p in parts:
        is_assigned = (p["part_no"], p["row_num"]) in assigned_keys
        if assigned_only and not is_assigned:
            continue
        if categories and p.get("category") not in categories:
            continue
        if keyword and not any(
            keyword in (p.get(field) or "").lower()
            for field in ("part_no", "part_name", "category")
        ):
            continue
        purchase = db.get_user_purchase(conn, p["part_no"], p["row_num"], primary_country, user_id) if user_id else db.get_purchase(conn, p["part_no"], p["row_num"], primary_country)
        row = _build_row_view(p, purchase)
        group = db.group_for_part(conn, active["id"], p["part_no"], p["row_num"]) if active else None
        row["group"] = group
        row["is_group_parent"] = bool(group and group["parent_part_no"] == p["part_no"] and group["parent_row_num"] == p["row_num"])
        row["group_child"] = bool(group and not row["is_group_parent"])
        row["mip"] = any((row["country_data"].get(c, {}).get("sourcing_part") or "") == "MIP" for c in countries) if "country_data" in row else False
        row["assigned"] = is_assigned
        row["country_data"] = {
            country: _build_row_view(p, db.get_user_purchase(conn, p["part_no"], p["row_num"], country, user_id) if user_id else db.get_purchase(conn, p["part_no"], p["row_num"], country))
            for country in countries
        }
        row["mip"] = any((row["country_data"][c].get("sourcing_part") or "").upper().startswith("MIP") for c in countries)
        row["status_done"] = all(
            row["country_data"][country]["unit_price_material"] not in (None, "")
            for country in countries
        )
        if status == "done" and not row["status_done"]:
            continue
        if status == "missing" and row["status_done"]:
            continue
        rows.append(row)
    return rows

@bom_bp.route("/")
@login_required
def index():
    conn = db.get_connection(current_app.config["DB_PATH"])
    active_version = db.get_active_bom_version(conn)
    submission = db.get_or_create_submission(conn, active_version["id"], int(current_user.id)) if active_version else None
    suggestions = db.search_suggestions(conn)
    parts = db.list_parts(conn)
    latest_bom_upload = db.get_latest_bom_upload(conn)
    progress = db.submission_progress(conn, active_version["id"], int(current_user.id)) if active_version else {"done": 0, "total": 0, "percent": 0}
    conn.close()
    category_counts = Counter(p["category"] for p in parts if p.get("category"))
    categories = sorted(category_counts)
    return render_template(
        "bom.html", countries=COUNTRIES, suggestions=suggestions,
        categories=categories, category_counts=category_counts,
        latest_bom_upload=latest_bom_upload, active_version=active_version, submission=submission,
        can_edit=current_user.role == "admin" or (submission and submission["status"] in ("draft", "returned")),
        progress=progress,
    )

@bom_bp.route("/grid")
@login_required
def grid():
    selected_countries = [country for country in request.args.getlist("country") if country]
    country = selected_countries[0] if selected_countries else "미국"
    status = request.args.get("status", "all")
    search = request.args.get("search", "")
    categories = request.args.getlist("category")
    assigned_only = request.args.get("assigned") == "1"
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", PAGE_SIZE))
    if page_size not in PAGE_SIZE_OPTIONS:
        page_size = PAGE_SIZE

    conn = db.get_connection(current_app.config["DB_PATH"])
    active_version = db.get_active_bom_version(conn)
    submission = db.get_or_create_submission(conn, active_version["id"], int(current_user.id)) if active_version else None
    configured_countries = [country for country in db.list_bom_countries(conn, active_version["id"] if active_version else None) if country != "한국"]
    if current_user.role != "admin" or not selected_countries:
        selected_countries = configured_countries
    display_countries = ["한국"] + selected_countries
    input_user_id = None if current_user.role == "admin" else int(current_user.id)
    all_rows = _filtered_rows(conn, display_countries, status, search, categories, input_user_id, assigned_only)
    overseas_countries = db.list_overseas_countries(conn)
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

    material_sum = sum(sum(r["country_data"][c]["material_cost"] for c in display_countries) for r in all_rows)
    logistics_sum = sum(sum(r["country_data"][c]["logistics_cost"] for c in selected_countries) for r in all_rows)
    total_sum = sum(sum(r["country_data"][c]["total_cost"] for c in display_countries) for r in all_rows)

    return render_template(
        "partials/_grid.html",
        rows=page_rows, country=country, status=status, search=search,
        page=page, total_pages=total_pages, total=total,
        page_size=page_size, page_size_options=PAGE_SIZE_OPTIONS,
        window_start=window_start, window_end=window_end,
        material_sum=material_sum, logistics_sum=logistics_sum, total_sum=total_sum,
        # Reuse this list for both case-column management and sourcing choices.
        countries=overseas_countries,
        sourcing_countries=["KD", "LP", "MIP"] + overseas_countries,
        selected_countries=selected_countries,
        can_manage_countries=current_user.role == "admin",
        is_admin=current_user.role == "admin",
        can_edit=current_user.role == "admin" or (submission and submission["status"] in ("draft", "returned")),
        assignment_enabled=current_user.role != "admin",
        assigned_only=assigned_only,
    )

@bom_bp.route("/rows", methods=["POST"])
@login_required
def add_row():
    if current_user.role != "admin":
        return jsonify({"ok": False, "message": "관리자만 BOM 행을 추가할 수 있습니다."}), 403
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bom_version(conn)
    anchor = db.get_part_by_row_num(conn, request.form.get("anchor_row_num", type=int), active["id"]) if active else None
    if not anchor:
        conn.close()
        return jsonify({"ok": False, "message": "기준 행을 찾을 수 없습니다."}), 404
    try:
        part = db.add_manual_part(conn, active["id"], anchor["part_no"], anchor["row_num"], request.form.get("position", "after"), {
            "part_name": (request.form.get("part_name") or "").strip(),
            "part_no": (request.form.get("part_no") or "").strip(),
            "qty": request.form.get("qty"),
            "spec": request.form.get("spec"),
        })
        result = {"ok": True, "row_num": part["row_num"]}
    except ValueError as exc:
        result = {"ok": False, "message": str(exc)}
    conn.close()
    return jsonify(result), (200 if result["ok"] else 422)

@bom_bp.route("/summary")
@login_required
def summary():
    country = request.args.get("country", COUNTRIES[0])
    conn = db.get_connection(current_app.config["DB_PATH"])
    categories = db.bom_tree(conn, country)
    conn.close()
    grand_material = sum(c["material_sum"] for c in categories)
    grand_logistics = sum(c["logistics_sum"] for c in categories)
    grand_tariff = sum(c["tariff_sum"] for c in categories)
    grand_total = sum(c["total_sum"] for c in categories)
    return render_template(
        "partials/_summary.html",
        categories=categories, country=country, countries=COUNTRIES,
        grand_material=grand_material, grand_logistics=grand_logistics,
        grand_tariff=grand_tariff, grand_total=grand_total,
    )

@bom_bp.route("/row/<part_no>/<int:row_num>/<country>", methods=["POST"])
@bom_bp.route("/row/by-number/<int:row_num>/<country>", methods=["POST"])
@login_required
def save_row(row_num, country, part_no=None):
    conn = db.get_connection(current_app.config["DB_PATH"])
    active_version = db.get_active_bom_version(conn)
    part = db.get_part(conn, part_no, row_num, active_version["id"]) if active_version and part_no is not None else (db.get_part_by_row_num(conn, row_num, active_version["id"]) if active_version else None)
    if not active_version or not part:
        conn.close()
        return jsonify({"error": "BOM 행을 찾을 수 없습니다."}), 404
    part_no = part["part_no"]
    submission = db.get_or_create_submission(conn, active_version["id"], int(current_user.id)) if active_version else None
    if current_user.role != "admin" and submission["status"] not in ("draft", "returned"):
        conn.close()
        return jsonify({"error": "제출된 BOM은 관리자 검토 전까지 수정할 수 없습니다."}), 403
    if current_user.role != "admin" and (part_no, row_num) not in db.assigned_part_keys(conn, active_version["id"], int(current_user.id)):
        conn.close()
        return jsonify({"error": "먼저 이 품목을 내 담당 품목으로 선택해 주세요."}), 403
    group = db.group_for_part(conn, active_version["id"], part_no, row_num)
    if group and (group["parent_part_no"], group["parent_row_num"]) != (part_no, row_num):
        conn.close()
        return jsonify({"error": "그룹 하위 품목입니다. 상위 그룹 품목에서 재료비를 입력하세요."}), 422
    if group and current_user.role != "admin" and group["owner_user_id"] != int(current_user.id):
        conn.close()
        return jsonify({"error": "그룹 담당자만 상위 품목의 재료비를 입력할 수 있습니다."}), 403
    editable_fields = ("currency", "unit_price_material", "unit_price_logistics", "tariff_rate", "mold_cost", "sourcing_part", "sourcing_assembly", "sourcing_part_location", "sourcing_assembly_location", "special_fx_rate", "special_fx_reason")
    target_countries = request.form.getlist("target_country")
    if not target_countries:
        target_countries = [name.split("__", 1)[0] for name in request.form if "__" in name]
    target_countries = target_countries or [country]
    target_countries = list(dict.fromkeys(target_countries))
    field_errors = []
    country_results = {}
    for target_country in target_countries:
        fields = {
            field: request.form.get(f"{target_country}__{field}", request.form.get(field))
            for field in editable_fields
        }
        calculated = calc.recalculate_purchase_row(conn, part_no, row_num, target_country, fields)
        field_errors.extend(calculated.pop("field_errors", []))
        if current_user.role == "admin":
            db.upsert_purchase(conn, part_no, row_num, target_country, calculated, updated_by=current_user.username)
        else:
            db.upsert_user_purchase(conn, part_no, row_num, target_country, int(current_user.id), calculated, updated_by=current_user.username)
        country_results[target_country] = calculated
    part = db.get_part(conn, part_no, row_num)
    purchase = db.get_purchase(conn, part_no, row_num, country) if current_user.role == "admin" else db.get_user_purchase(conn, part_no, row_num, country, int(current_user.id))
    completion_countries = db.list_bom_countries(conn, active_version["id"])
    completion_values = [
        db.get_purchase(conn, part_no, row_num, configured_country) if current_user.role == "admin"
        else db.get_user_purchase(conn, part_no, row_num, configured_country, int(current_user.id))
        for configured_country in completion_countries
    ]
    conn.close()
    row = _build_row_view(part, purchase)
    row["status_done"] = bool(completion_countries) and all(
        value and value.get("unit_price_material") not in (None, "")
        for value in completion_values
    )
    row["country_data"] = {country: row}
    if field_errors:
        toast = {"type": "error", "message": ", ".join(field_errors) + " 값이 숫자가 아니에요. 해당 항목은 저장되지 않았어요."}
    else:
        toast = {"type": "success", "message": "저장되었습니다."}
    if request.accept_mimetypes.best == "application/json":
        return jsonify({
            "material_cost": row["material_cost"],
            "logistics_cost": row["logistics_cost"],
            "total_cost": row["total_cost"],
            "updated_at": row["updated_at"],
            "updated_by": row["updated_by"],
            "status_done": row["status_done"],
            "countries": country_results,
            "error": ", ".join(dict.fromkeys(field_errors)) if field_errors else None,
        })
    return render_template("partials/_row.html", row=row, country=country, selected_countries=[country], toast=toast)

@bom_bp.route("/submit", methods=["POST"])
@login_required
def submit():
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bom_version(conn)
    if active:
        progress = db.submission_progress(conn, active["id"], int(current_user.id))
        if not progress["total"]:
            conn.close()
            return jsonify({"ok": False, "message": "먼저 본인이 입력할 담당 품목을 선택해 주세요."}), 422
        if progress["done"] < progress["total"]:
            conn.close()
            return jsonify({"ok": False, "message": f"필수 재료단가 입력이 {progress['total'] - progress['done']}건 남아 있습니다. 미입력 필터로 확인해 주세요."}), 422
        db.get_or_create_submission(conn, active["id"], int(current_user.id))
        db.save_submission_snapshot(conn, active["id"], int(current_user.id))
        db.update_submission_status(conn, active["id"], int(current_user.id), "submitted")
    conn.close()
    return jsonify({"ok": True, "message": "검토 요청으로 제출했습니다."})

@bom_bp.route("/assignments/<part_no>/<int:row_num>", methods=["POST"])
@bom_bp.route("/assignments/row/<int:row_num>", methods=["POST"])
@login_required
def set_assignment(row_num, part_no=None):
    if current_user.role == "admin":
        return jsonify({"ok": False, "message": "관리자는 담당 품목을 선택하지 않습니다."}), 403
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bom_version(conn)
    part = db.get_part(conn, part_no, row_num, active["id"]) if active and part_no is not None else (db.get_part_by_row_num(conn, row_num, active["id"]) if active else None)
    if not active or not part:
        conn.close()
        return jsonify({"ok": False, "message": "품목을 찾을 수 없습니다."}), 404
    part_no = part["part_no"]
    submission = db.get_or_create_submission(conn, active["id"], int(current_user.id))
    if submission["status"] not in ("draft", "returned"):
        conn.close()
        return jsonify({"ok": False, "message": "제출된 BOM은 담당 품목을 변경할 수 없습니다."}), 403
    assigned = request.form.get("assigned") in ("1", "true", "on")
    db.set_part_assignment(conn, active["id"], int(current_user.id), part_no, row_num, assigned)
    count = len(db.assigned_part_keys(conn, active["id"], int(current_user.id)))
    conn.close()
    return jsonify({"ok": True, "assigned": assigned, "count": count})

@bom_bp.route("/reset-work", methods=["POST"])
@login_required
def reset_work():
    if current_user.role == "admin":
        return jsonify({"ok": False, "message": "관리자 입력값은 이 기능으로 초기화할 수 없습니다."}), 403
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bom_version(conn)
    submission = db.get_or_create_submission(conn, active["id"], int(current_user.id)) if active else None
    if not active or submission["status"] not in ("draft", "returned"):
        conn.close()
        return jsonify({"ok": False, "message": "제출 후에는 초기화할 수 없습니다."}), 403
    db.reset_user_bom_work(conn, active["id"], int(current_user.id))
    conn.close()
    return jsonify({"ok": True, "message": "담당 품목과 저장된 입력값을 모두 초기화했습니다."})

@bom_bp.route("/groups/<part_no>/<int:row_num>", methods=["POST"])
@login_required
def set_group(part_no, row_num):
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bom_version(conn)
    if not active:
        conn.close()
        return jsonify({"ok": False, "message": "배포된 BOM이 없습니다."}), 404
    enabled = request.form.get("enabled") in ("1", "true", "on")
    current = db.group_for_part(conn, active["id"], part_no, row_num)
    submission = db.get_or_create_submission(conn, active["id"], int(current_user.id))
    allowed = current_user.role == "admin" or (not current and submission["status"] in ("draft", "returned")) or (current and current["owner_user_id"] == int(current_user.id) and submission["status"] in ("draft", "returned"))
    if not allowed:
        conn.close()
        return jsonify({"ok": False, "message": "그룹은 제출 전 생성자 또는 관리자만 변경할 수 있습니다."}), 403
    try:
        db.set_part_group(conn, active["id"], part_no, row_num, int(current_user.id), enabled)
    except ValueError as exc:
        conn.close()
        return jsonify({"ok": False, "message": str(exc)}), 422
    conn.close()
    return jsonify({"ok": True, "enabled": enabled})

@bom_bp.route("/groups/selected", methods=["POST"])
@login_required
def set_selected_group():
    row_nums = sorted({int(value) for value in request.form.getlist("row_num")})
    if len(row_nums) < 2:
        return jsonify({"ok": False, "message": "그룹으로 지정할 행을 두 개 이상 선택하세요."}), 422
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bom_version(conn)
    parts = [db.get_part_by_row_num(conn, row_num, active["id"]) for row_num in row_nums] if active else []
    if not active or any(part is None for part in parts):
        conn.close()
        return jsonify({"ok": False, "message": "선택한 BOM 행을 찾을 수 없습니다."}), 404
    parent = parts[0]
    existing = db.group_for_part(conn, active["id"], parent["part_no"], parent["row_num"])
    if existing and existing["parent_part_no"] == parent["part_no"] and existing["parent_row_num"] == parent["row_num"]:
        db.set_part_group(conn, active["id"], parent["part_no"], parent["row_num"], int(current_user.id), False)
        conn.close()
        return jsonify({"ok": True, "removed": True})
    try:
        db.set_part_group(conn, active["id"], parent["part_no"], parent["row_num"], int(current_user.id), True)
    except ValueError as exc:
        conn.close()
        return jsonify({"ok": False, "message": str(exc)}), 422
    conn.close()
    return jsonify({"ok": True})

@bom_bp.route("/row/by-number/<int:row_num>/<country>/preview", methods=["POST"])
@login_required
def preview_row(row_num, country):
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bom_version(conn)
    part = db.get_part_by_row_num(conn, row_num, active["id"]) if active else None
    if not part:
        conn.close()
        return jsonify({"error": "BOM 행을 찾을 수 없습니다."}), 404
    fields = {field: request.form.get(f"{country}__{field}", request.form.get(field)) for field in ("currency", "unit_price_material", "unit_price_logistics", "tariff_rate", "mold_cost", "special_fx_rate")}
    result = calc.recalculate_purchase_row(conn, part["part_no"], row_num, country, fields)
    conn.close()
    return jsonify({key: result.get(key) or 0 for key in ("material_cost", "logistics_cost", "total_cost")})

@bom_bp.route("/notifications/read", methods=["POST"])
@login_required
def read_notifications():
    conn = db.get_connection(current_app.config["DB_PATH"])
    db.mark_notifications_read(conn, int(current_user.id))
    conn.close()
    return redirect(request.referrer or url_for("home.index"))

@bom_bp.route("/submissions")
@login_required
def submissions():
    conn = db.get_connection(current_app.config["DB_PATH"])
    items = db.list_user_submissions(conn, int(current_user.id))
    conn.close()
    return render_template("my_submissions.html", submissions=items)

@bom_bp.route("/submissions/<int:submission_id>")
@login_required
def submission_detail(submission_id):
    conn = db.get_connection(current_app.config["DB_PATH"])
    submission = db.get_submission(conn, submission_id)
    if submission and not db.submission_snapshot(submission).get("rows"):
        db.save_submission_snapshot(conn, submission["bom_version_id"], submission["user_id"])
        submission = db.get_submission(conn, submission_id)
    conn.close()
    if not submission or (current_user.role != "admin" and submission["user_id"] != int(current_user.id)):
        from flask import abort
        abort(404)
    history_conn = db.get_connection(current_app.config["DB_PATH"])
    revision_history = db.list_submission_revisions(history_conn, submission_id)
    history_conn.close()
    return render_template("submission_detail.html", submission=submission, snapshot=db.submission_snapshot(submission), revision_history=revision_history, review_mode=False)

@bom_bp.route("/row/<part_no>/<int:row_num>/<country>/history")
@login_required
def row_history(part_no, row_num, country):
    conn = db.get_connection(current_app.config["DB_PATH"])
    history = db.list_purchase_history(conn, part_no, row_num, country)
    conn.close()
    return jsonify(history)
