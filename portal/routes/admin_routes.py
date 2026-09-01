from functools import wraps

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for, abort
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

import db
import parser
from columns import DESIGN_FIELDS, PURCHASE_FIELDS

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

@admin_bp.route("/boms")
@admin_required
def bom_versions():
    conn = db.get_connection(current_app.config["DB_PATH"])
    versions = db.list_bom_versions(conn)
    active = db.get_active_bom_version(conn)
    countries = db.list_overseas_countries(conn)
    version_countries = {version["id"]: db.list_bom_countries(conn, version["id"]) for version in versions}
    differences = {version["id"]: db.bom_version_difference(conn, active["id"] if active else None, version["id"]) for version in versions if version["status"] == "draft"}
    submissions = db.list_submissions(conn, active["id"]) if active else []
    users = db.list_users(conn)
    draft_parts = {version["id"]: db.list_parts(conn, version["id"]) for version in versions if version["status"] == "draft"}
    conn.close()
    return render_template("admin_boms.html", versions=versions, active=active, countries=countries, version_countries=version_countries, differences=differences, submissions=submissions, users=users, draft_parts=draft_parts, design_fields=DESIGN_FIELDS)

@admin_bp.route("/boms/draft", methods=["POST"])
@admin_required
def create_draft():
    name = (request.form.get("name") or "새 BOM").strip()
    vehicle = (request.form.get("vehicle") or "").strip()
    copy_costs = request.form.get("copy_costs") == "on"
    conn = db.get_connection(current_app.config["DB_PATH"])
    draft = db.create_draft_from_active(conn, name, vehicle, current_user.username, copy_costs)
    conn.close()
    flash(f"{draft['name']} 초안을 만들었습니다.")
    return redirect(url_for("admin.bom_versions"))

@admin_bp.route("/boms/<int:bom_id>/upload", methods=["POST"])
@admin_required
def upload_draft(bom_id):
    file = request.files.get("bom_file")
    conn = db.get_connection(current_app.config["DB_PATH"])
    version = db.get_bom_version(conn, bom_id)
    if not version or version["status"] != "draft":
        conn.close()
        abort(400)
    if not file or not file.filename:
        conn.close()
        flash("업로드할 BOM 파일을 선택해 주세요.")
        return redirect(url_for("admin.bom_versions"))
    previous = db.get_active_bom_version(conn)
    result = parser.parse_and_upsert(conn, file, bom_id=bom_id, replace_existing=True)
    carried = db.migrate_matching_user_work(conn, previous["id"], bom_id) if previous and previous["id"] != bom_id else 0
    conn.execute("UPDATE bom_versions SET file_name = ? WHERE id = ?", (file.filename, bom_id))
    conn.commit()
    conn.close()
    flash(f"초안 BOM을 교체했습니다: 신규 {result['inserted']}건 / 갱신 {result['updated']}건 / 이전 입력 이관 {carried}건")
    return redirect(url_for("admin.bom_versions"))

@admin_bp.route("/boms/<int:bom_id>/publish", methods=["POST"])
@admin_required
def publish_draft(bom_id):
    conn = db.get_connection(current_app.config["DB_PATH"])
    version = db.get_bom_version(conn, bom_id)
    if not version or version["status"] != "draft":
        conn.close()
        abort(400)
    if not db.list_parts(conn, bom_id):
        conn.close()
        flash("BOM 행이 없는 초안은 확정할 수 없습니다.")
        return redirect(url_for("admin.bom_versions"))
    db.publish_bom_version(conn, bom_id)
    conn.close()
    flash(f"{version['name']}을 확정했습니다. 이제 사용자에게 이 BOM이 표시됩니다.")
    return redirect(url_for("admin.bom_versions"))

@admin_bp.route("/boms/<int:bom_id>/withdraw", methods=["POST"])
@admin_required
def withdraw_bom(bom_id):
    reason = (request.form.get("reason") or "").strip()
    conn = db.get_connection(current_app.config["DB_PATH"])
    if not db.withdraw_bom_version(conn, bom_id, reason, current_user.username):
        conn.close()
        abort(400)
    conn.close()
    flash("배포를 취소하고 모든 사용자에게 안내했습니다.")
    return redirect(url_for("admin.bom_versions"))

@admin_bp.route("/boms/<int:bom_id>/delete", methods=["POST"])
@admin_required
def delete_draft(bom_id):
    conn = db.get_connection(current_app.config["DB_PATH"])
    version = db.get_bom_version(conn, bom_id)
    if not version or version["status"] != "draft":
        conn.close()
        abort(400)
    db.delete_bom_draft(conn, bom_id)
    conn.close()
    flash(f"{version['name']} 초안을 삭제했습니다.")
    return redirect(url_for("admin.bom_versions"))

@admin_bp.route("/boms/<int:bom_id>/countries", methods=["POST"])
@admin_required
def set_countries(bom_id):
    conn = db.get_connection(current_app.config["DB_PATH"])
    version = db.get_bom_version(conn, bom_id)
    if not version or version["status"] != "draft":
        conn.close()
        abort(400)
    db.set_bom_countries(conn, bom_id, request.form.getlist("country"))
    conn.close()
    flash("초안 국가 설정을 저장했습니다.")
    return redirect(url_for("admin.bom_versions"))

@admin_bp.route("/boms/<int:bom_id>/rows", methods=["POST"])
@admin_required
def add_bom_row(bom_id):
    conn = db.get_connection(current_app.config["DB_PATH"])
    version = db.get_bom_version(conn, bom_id)
    if not version or version["status"] != "draft":
        conn.close()
        abort(400)
    fields = {key: value for key, value in request.form.items() if key not in ("anchor_part_no", "anchor_row_num", "position")}
    try:
        db.add_manual_part(conn, bom_id, request.form.get("anchor_part_no", ""), int(request.form.get("anchor_row_num", 0)), request.form.get("position", "after"), fields)
        flash("BOM 행을 추가했습니다. 다운로드 파일에도 같은 위치로 삽입됩니다.")
    except ValueError as exc:
        flash(str(exc))
    finally:
        conn.close()
    return redirect(url_for("admin.bom_versions"))

@admin_bp.route("/boms/<int:bom_id>/rows/<part_no>/<int:row_num>", methods=["POST"])
@admin_required
def edit_bom_row(bom_id, part_no, row_num):
    conn = db.get_connection(current_app.config["DB_PATH"])
    version = db.get_bom_version(conn, bom_id)
    part = db.get_part(conn, part_no, row_num, bom_id)
    if not version or version["status"] != "draft" or not part:
        conn.close()
        abort(400)
    fields = {name: request.form.get(name, part.get(name)) for name, _ in DESIGN_FIELDS}
    fields["part_name"] = (fields.get("part_name") or "").strip()
    if not fields["part_name"]:
        conn.close()
        flash("품명은 비워 둘 수 없습니다.")
        return redirect(url_for("admin.bom_versions"))
    db.upsert_part(conn, part_no, row_num, part.get("level_depth"), part.get("level_marker"), fields, bom_id)
    conn.close()
    flash("상세 BOM 정보를 저장했습니다.")
    return redirect(url_for("admin.bom_versions"))

@admin_bp.route("/users", methods=["POST"])
@admin_required
def create_user():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    role = request.form.get("role") if request.form.get("role") in ("admin", "user") else "user"
    if not username or not password:
        flash("사용자명과 비밀번호를 입력해 주세요.")
        return redirect(url_for("admin.bom_versions"))
    conn = db.get_connection(current_app.config["DB_PATH"])
    try:
        db.create_user(conn, username, generate_password_hash(password), role)
        flash(f"{username} 사용자를 만들었습니다.")
    except Exception:
        flash("이미 존재하는 사용자명입니다.")
    finally:
        conn.close()
    return redirect(url_for("admin.bom_versions"))

@admin_bp.route("/reviews")
@admin_required
def reviews():
    conn = db.get_connection(current_app.config["DB_PATH"])
    active = db.get_active_bom_version(conn)
    submissions = db.list_submissions(conn, active["id"]) if active else []
    conn.close()
    return render_template("admin_reviews.html", submissions=submissions, active=active)

@admin_bp.route("/reviews/<int:submission_id>")
@admin_required
def review_detail(submission_id):
    conn = db.get_connection(current_app.config["DB_PATH"])
    submission = db.get_submission(conn, submission_id)
    # Legacy submissions created before snapshots are backfilled once so the
    # reviewer is never presented with an empty approval screen.
    if submission and not db.submission_snapshot(submission).get("rows"):
        db.save_submission_snapshot(conn, submission["bom_version_id"], submission["user_id"])
        submission = db.get_submission(conn, submission_id)
    revision_history = db.list_submission_revisions(conn, submission_id) if submission else []
    conn.close()
    if not submission:
        abort(404)
    return render_template("submission_detail.html", submission=submission, snapshot=db.submission_snapshot(submission), revision_history=revision_history, review_mode=True)

@admin_bp.route("/reviews/<int:submission_id>/<status>", methods=["POST"])
@admin_required
def review_submission(submission_id, status):
    if status not in ("approved", "returned"):
        abort(400)
    conn = db.get_connection(current_app.config["DB_PATH"])
    submission = db.get_submission(conn, submission_id)
    if not submission:
        conn.close()
        abort(404)
    if status == "approved":
        rows = conn.execute("SELECT * FROM bom_user_purchase_data WHERE bom_id=? AND user_id=?", (submission["bom_version_id"], submission["user_id"])).fetchall()
        extra = ("sourcing_part_location", "sourcing_assembly_location", "special_fx_rate", "special_fx_reason")
        for row in rows:
            values = dict(row)
            fields = {name: values.get(name) for name, _ in PURCHASE_FIELDS}
            fields.update({name: values.get(name) for name in extra})
            db.upsert_purchase(conn, values["part_no"], values["row_num"], values["country"], fields, updated_by=current_user.username, bom_id=submission["bom_version_id"])
    db.update_submission_status(conn, submission["bom_version_id"], submission["user_id"], status, current_user.username, request.form.get("review_comment"))
    conn.close()
    flash("검토 상태를 저장했습니다.")
    return redirect(url_for("admin.reviews"))
