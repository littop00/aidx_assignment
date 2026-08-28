import db
from tests.fixtures import make_bom_fixture


def _login(client, admin_user):
    client.post("/login", data=admin_user)


def test_home_shows_empty_kpi_when_no_parts(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "0".encode() in resp.data


def test_legacy_upload_redirects_admin_to_version_management(client, admin_user):
    _login(client, admin_user)
    fixture = make_bom_fixture([
        {"part_no": "P001", "part_name": "FILTER", "qty": 2},
        {"part_no": "P002", "part_name": "BRACKET", "qty": 1},
    ])
    resp = client.post(
        "/upload",
        data={"bom_file": (fixture, "bom.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/admin/boms")


def test_home_shows_vehicle_country_summary(client, admin_user, app):
    _login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 11, 0, "●", {"vehicle": "NE2_NV1", "part_name": "FILTER", "qty": "1"})
    db.upsert_purchase(conn, "P001", 11, "한국", {"material_cost": "100", "total_cost": "115"})
    conn.close()

    resp = client.get("/")
    assert b"NE2_NV1" in resp.data


def test_upload_requires_login(client):
    fixture = make_bom_fixture([{"part_no": "P001", "part_name": "FILTER", "qty": 2}])
    resp = client.post(
        "/upload",
        data={"bom_file": (fixture, "bom.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
