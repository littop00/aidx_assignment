import datetime
from flask import Blueprint, render_template, current_app, send_file
from flask_login import login_required
from io import BytesIO
import db
import fx
import exporter

fx_bp = Blueprint("fx", __name__, url_prefix="/fx")

def _rates(conn):
    return {c: fx.get_latest_rate(conn, c) for c in ["KRW", "USD", "EUR"]}

@fx_bp.route("/widget")
@login_required
def widget():
    conn = db.get_connection(current_app.config["DB_PATH"])
    rates = _rates(conn)
    conn.close()
    return render_template("partials/_fx_widget.html", rates=rates)

@fx_bp.route("/refresh", methods=["POST"])
@login_required
def refresh():
    conn = db.get_connection(current_app.config["DB_PATH"])
    result = fx.refresh_rates(conn, today=datetime.date.today().isoformat())
    rates = _rates(conn)
    conn.close()
    return render_template("partials/_fx_widget.html", rates=rates, message=result["reason"])

@fx_bp.route("/download")
@login_required
def download():
    conn = db.get_connection(current_app.config["DB_PATH"])
    data = exporter.export_to_template(conn, current_app.config["TEMPLATE_PATH"])
    conn.close()
    filename = f"BOM_{datetime.date.today().isoformat()}.xlsx"
    return send_file(
        BytesIO(data), as_attachment=True, download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
