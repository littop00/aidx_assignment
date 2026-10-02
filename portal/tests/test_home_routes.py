import db
from tests.fixtures import make_bom_fixture


def _login(client, admin_user):
    client.post("/login", data=admin_user)


def test_home_shows_placeholder(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "준비중".encode() in resp.data


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


def test_vendor_dashboard_requires_login(client):
    resp = client.get("/dashboard/vendors")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_vendor_dashboard_shows_placeholder(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/dashboard/vendors")
    assert resp.status_code == 200
    assert "준비중".encode() in resp.data


def test_dashboard_nav_includes_restructured_sections(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/")
    assert b'href="/dashboard/vendors"' not in resp.data
    assert b'href="/bom/summary-page"' in resp.data
    assert b'href="/bom/stage-summary"' in resp.data
    assert b'href="/bid-bom/"' in resp.data
    assert "차종별 SUMMARY".encode() in resp.data
    assert "단계별 SUMMARY".encode() in resp.data
    assert "수주 BOM".encode() in resp.data


def test_upload_requires_login(client):
    fixture = make_bom_fixture([{"part_no": "P001", "part_name": "FILTER", "qty": 2}])
    resp = client.post(
        "/upload",
        data={"bom_file": (fixture, "bom.xlsx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
