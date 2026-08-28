import pytest
from werkzeug.security import generate_password_hash

import db
from app import create_app


@pytest.fixture
def app(tmp_path):
    db_path = str(tmp_path / "test.db")
    flask_app = create_app(db_path=db_path)
    flask_app.config["TESTING"] = True
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_user(app):
    conn = db.get_connection(app.config["DB_PATH"])
    password_hash = generate_password_hash("secret123")
    db.create_user(conn, "admin", password_hash, role="admin")
    conn.close()
    return {"username": "admin", "password": "secret123"}
