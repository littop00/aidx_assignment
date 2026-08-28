from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash
from flask_login import login_required, current_user
import db
import fx
import parser

home_bp = Blueprint("home", __name__)

@home_bp.route("/")
@login_required
def index():
    conn = db.get_connection(current_app.config["DB_PATH"])
    parts = db.list_parts(conn)
    vehicles = db.list_vehicles(conn)
    selected_vehicle = request.args.get("vehicle", "NE2_NV1")
    if selected_vehicle not in vehicles:
        selected_vehicle = vehicles[0] if vehicles else ""
    missing = sum(
        1 for p in parts
        if not db.list_purchase_for_part(conn, p["part_no"], p["row_num"])
    )
    usd = fx.get_latest_rate(conn, "USD")
    eur = fx.get_latest_rate(conn, "EUR")
    active_version = db.get_active_bom_version(conn)
    active_bom_id = active_version["id"] if active_version else None
    vehicle_summary = db.vehicle_country_summary(conn, active_bom_id)
    case_countries, case_matrix = db.dashboard_case_matrix(conn, active_bom_id)
    dashboard_cases = []
    for country in case_countries:
        categories = db.bom_tree(conn, country, selected_vehicle, active_bom_id)
        dashboard_cases.append({
            "country": country,
            "title": "국내" if country == "한국" else country,
            "subtitle": "재료비 기준" if country == "한국" else "해외 비용 기준",
            "categories": categories,
            "material_total": sum(category["material_sum"] for category in categories),
            "logistics_total": sum(category["logistics_sum"] for category in categories),
            "total": sum(category["total_sum"] for category in categories),
        })
    latest_bom_upload = db.get_latest_bom_upload(conn)
    conn.close()
    domestic_rows = [row for row in vehicle_summary if row["country"] == "한국"]
    overseas_rows = [row for row in vehicle_summary if row["country"] != "한국"]
    domestic_case_total = sum(float(row["material_sum"] or 0) for row in domestic_rows)
    overseas_case_total = sum(float(row["total_sum"] or 0) for row in overseas_rows)
    case_summary = [
        {"case_name": "Case 1", "case_type": "국내", "country": "한국", "vehicle": row["vehicle"], "material": row["material_sum"] or 0, "logistics": 0, "total": row["material_sum"] or 0}
        for row in domestic_rows
    ] + [
        {"case_name": "Case 2", "case_type": "해외", "country": row["country"], "vehicle": row["vehicle"], "material": row["material_sum"] or 0, "logistics": (row["total_sum"] or 0) - (row["material_sum"] or 0), "total": row["total_sum"] or 0}
        for row in overseas_rows
    ]
    return render_template(
        "home.html",
        total_parts=len(parts), missing=missing, usd=usd, eur=eur,
        vehicle_summary=vehicle_summary,
        domestic_case_total=domestic_case_total,
        overseas_case_total=overseas_case_total,
        latest_bom_upload=latest_bom_upload,
        case_summary=case_summary,
        case_countries=case_countries,
        case_matrix=case_matrix,
        dashboard_cases=dashboard_cases,
        vehicles=vehicles,
        selected_vehicle=selected_vehicle,
        active_version=active_version,
    )

@home_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    flash("BOM 업로드는 관리자 화면에서 새 초안을 만든 뒤 진행해 주세요.")
    return redirect(url_for("admin.bom_versions") if current_user.role == "admin" else url_for("bom.index"))
