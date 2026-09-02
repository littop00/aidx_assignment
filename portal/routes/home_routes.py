import io

from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash, send_file
from flask_login import login_required, current_user
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
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
    report = db.dashboard_report(conn, active_bom_id, selected_vehicle)
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
        report=report,
    )

@home_bp.route("/export/dashboard.xlsx")
@login_required
def export_dashboard():
    conn = db.get_connection(current_app.config["DB_PATH"])
    vehicles = db.list_vehicles(conn)
    selected_vehicle = request.args.get("vehicle", "NE2_NV1")
    if selected_vehicle not in vehicles:
        selected_vehicle = vehicles[0] if vehicles else ""
    active_version = db.get_active_bom_version(conn)
    active_bom_id = active_version["id"] if active_version else None
    report = db.dashboard_report(conn, active_bom_id, selected_vehicle)
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "재료비 Summary"
    overseas = report["overseas_countries"]
    bold_center = Alignment(horizontal="center", vertical="center")

    title = f"▶ {selected_vehicle} 재료비 (국내" + "".join(f"/{c}" for c in overseas) + ")"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6 + len(overseas) * 6)
    ws.cell(row=1, column=1, value=title).font = Font(bold=True)

    header_row, sub_row = 3, 4
    ws.merge_cells(start_row=header_row, start_column=1, end_row=sub_row, end_column=1)
    ws.cell(row=header_row, column=1, value="대분류").alignment = bold_center
    ws.merge_cells(start_row=header_row, start_column=2, end_row=sub_row, end_column=2)
    ws.cell(row=header_row, column=2, value="구분").alignment = bold_center

    col = 3
    ws.merge_cells(start_row=header_row, start_column=col, end_row=header_row, end_column=col + 3)
    ws.cell(row=header_row, column=col, value="내수").alignment = bold_center
    for label in ("재료비", "물류비", "관세", "합계"):
        ws.cell(row=sub_row, column=col, value=label).alignment = bold_center
        col += 1

    country_start_cols = {}
    for country in overseas:
        country_start_cols[country] = col
        ws.merge_cells(start_row=header_row, start_column=col, end_row=header_row, end_column=col + 5)
        ws.cell(row=header_row, column=col, value=country).alignment = bold_center
        ws.merge_cells(start_row=sub_row, start_column=col, end_row=sub_row, end_column=col + 2)
        ws.cell(row=sub_row, column=col, value="재료비(LP/KD)").alignment = bold_center
        ws.cell(row=sub_row + 1, column=col, value="LP").alignment = bold_center
        ws.cell(row=sub_row + 1, column=col + 1, value="KD").alignment = bold_center
        ws.cell(row=sub_row + 1, column=col + 2, value="합계").alignment = bold_center
        for offset, label in enumerate(("물류비", "관세", "합계"), start=3):
            ws.cell(row=sub_row, column=col + offset, value=label).alignment = bold_center
        col += 6

    row = sub_row + 2
    for major in report["majors"]:
        first_row = row
        for cat in major["categories"]:
            ws.cell(row=row, column=2, value=cat["category"])
            d = cat["domestic"]
            ws.cell(row=row, column=3, value=d["material"])
            ws.cell(row=row, column=4, value=d["logistics"])
            ws.cell(row=row, column=5, value=d["tariff"])
            ws.cell(row=row, column=6, value=d["total"])
            for country in overseas:
                o = cat["overseas"][country]
                base = country_start_cols[country]
                ws.cell(row=row, column=base, value=o["material_lp"])
                ws.cell(row=row, column=base + 1, value=o["material_kd"])
                ws.cell(row=row, column=base + 2, value=o["material_total"])
                ws.cell(row=row, column=base + 3, value=o["logistics"])
                ws.cell(row=row, column=base + 4, value=o["tariff"])
                ws.cell(row=row, column=base + 5, value=o["total"])
            row += 1
        if row - 1 > first_row:
            ws.merge_cells(start_row=first_row, start_column=1, end_row=row - 1, end_column=1)
        ws.cell(row=first_row, column=1, value=major["major"]).alignment = bold_center

    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    ws.cell(row=row, column=1, value="합 계").alignment = bold_center
    gd = report["grand_domestic"]
    ws.cell(row=row, column=3, value=gd["material"])
    ws.cell(row=row, column=4, value=gd["logistics"])
    ws.cell(row=row, column=5, value=gd["tariff"])
    ws.cell(row=row, column=6, value=gd["total"])
    for country in overseas:
        go = report["grand_overseas"][country]
        base = country_start_cols[country]
        ws.cell(row=row, column=base, value=go["material_lp"])
        ws.cell(row=row, column=base + 1, value=go["material_kd"])
        ws.cell(row=row, column=base + 2, value=go["material_total"])
        ws.cell(row=row, column=base + 3, value=go["logistics"])
        ws.cell(row=row, column=base + 4, value=go["tariff"])
        ws.cell(row=row, column=base + 5, value=go["total"])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"재료비_Summary_{selected_vehicle}.xlsx"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@home_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    flash("BOM 업로드는 관리자 화면에서 새 초안을 만든 뒤 진행해 주세요.")
    return redirect(url_for("admin.bom_versions") if current_user.role == "admin" else url_for("bom.index"))
