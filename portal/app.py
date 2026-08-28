import os
import click
from flask import Flask
from flask_login import LoginManager
from flask_login import current_user
from werkzeug.security import generate_password_hash

import db
import config
from auth import load_user_by_id
from routes.auth_routes import auth_bp
from routes.home_routes import home_bp
from routes.bom_routes import bom_bp
from routes.fx_routes import fx_bp
from routes.admin_routes import admin_bp


def create_app(db_path=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["DB_PATH"] = db_path or config.DB_PATH
    app.config["TEMPLATE_PATH"] = config.TEMPLATE_PATH

    conn = db.get_connection(app.config["DB_PATH"])
    db.init_db(conn)
    conn.close()

    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(bom_bp)
    app.register_blueprint(fx_bp)
    app.register_blueprint(admin_bp)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @app.after_request
    def add_no_cache_headers(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def navigation_context():
        if not current_user.is_authenticated:
            return {}
        conn = db.get_connection(app.config["DB_PATH"])
        notices = db.list_notifications(conn, int(current_user.id))
        unread_count = db.unread_notification_count(conn, int(current_user.id))
        conn.close()
        return {"nav_notifications": notices, "nav_unread_count": unread_count}

    @login_manager.user_loader
    def user_loader(user_id):
        conn = db.get_connection(app.config["DB_PATH"])
        user = load_user_by_id(conn, user_id)
        conn.close()
        return user

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("password")
    def create_admin(username, password):
        conn = db.get_connection(app.config["DB_PATH"])
        password_hash = generate_password_hash(password)
        db.create_user(conn, username, password_hash, role="admin")
        conn.close()
        click.echo(f"관리자 계정 생성됨: {username}")

    return app


app = create_app()
