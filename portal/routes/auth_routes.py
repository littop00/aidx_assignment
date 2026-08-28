from flask import Blueprint, render_template, request, redirect, url_for, current_app
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash
import db
from auth import PortalUser

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = db.get_connection(current_app.config["DB_PATH"])
        row = db.get_user_by_username(conn, request.form["username"])
        conn.close()
        if row and check_password_hash(row["password_hash"], request.form["password"]):
            login_user(PortalUser(row))
            return redirect(url_for("home.index"))
        return render_template("login.html", error="로그인 실패: 아이디 또는 비밀번호가 올바르지 않습니다.")
    return render_template("login.html", error=None)

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
