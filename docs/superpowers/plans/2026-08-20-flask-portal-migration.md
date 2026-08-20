# BOM 재료비 포탈 Flask 마이그레이션 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `proto(rev.0)` (Streamlit) 프로토타입을 `portal/`(Flask+HTMX+Bootstrap5)로 마이그레이션 — 복합키 DB 스키마, 로그인, 카드형 라이트테마 UI까지 갖춘 로컬 실행 가능한 정식판 1차 버전을 만든다.

**Architecture:** Flask 애플리케이션 팩토리 + Jinja2 서버렌더링 + HTMX 부분 갱신. 기존 순수 파이썬 로직 모듈(`columns.py`, `fx.py`, `parser.py`, `calc.py`, `exporter.py`)은 그대로 재사용하고, `db.py`만 복합키 스키마로 재작성한다. `proto(rev.0)/`는 수정하지 않고 그대로 둔다 (참고/롤백용).

**Tech Stack:** Flask, Flask-Login, Jinja2, HTMX, Bootstrap 5, SQLite, waitress(WSGI), openpyxl, pytest, werkzeug.security

## Global Constraints

- 작업 위치는 새 폴더 `portal/` (프로젝트 루트: `D:\재료비 관리 포탈 PJT\portal\`). `proto(rev.0)/`는 절대 수정하지 않는다.
- DB 스키마: `parts`, `purchase_data` 모두 PK를 `(part_no, row_num)` 기반 복합키로 전환한다. 동일 품번이 서로 다른 조립위치(행)에 재사용되는 케이스(실제 BOM 74건)를 보존해야 한다. `purchase_data`는 국가별 입력이 존재하므로 PK는 `(part_no, row_num, country)`.
- 신규 `users` 테이블: `id, username, password_hash, role, created_at`. `role` 컬럼은 값 `admin` 하나만 쓰되 컬럼은 미리 확보 (로직 미구현).
- 로그인: Flask-Login. 초기 관리자 계정은 `flask create-admin <username> <password>` CLI로만 생성 (하드코딩 기본 계정 금지 — 보안).
- UI 톤: 밝은 회색 배경(#F5F7FA), 흰 카드+옅은 그림자+좌측 포인트컬러 보더, 좌측 고정 사이드바 내비게이션.
- SPA 프레임워크(React 등) 도입 안 함 — HTMX로 부분 갱신.
- `bom.db`는 재생성 대상 (기존 322건은 테스트 데이터라 폐기 동의됨). `portal/`은 빈 DB로 시작.
- 로컬 실행: `run.py`에서 waitress로 서빙 + 브라우저 자동 오픈.
- 이번 범위 아님(구현 금지): SUMMARY 집계, 다중사용자 동시입력 로직, 관리자/설계자 권한 분리 로직, 로드맵 신규필드(소싱/물류/차종 상세), PHASE2~5, 서버/클라우드 배포.

---

## File Structure

```
portal/
├── run.py                     # 진입점: waitress 서빙 + 브라우저 오픈
├── config.py                  # DB_PATH, TEMPLATE_PATH, SECRET_KEY
├── columns.py                 # proto에서 그대로 복사 (수정 없음)
├── fx.py                      # proto에서 그대로 복사 (수정 없음)
├── parser.py                  # proto에서 그대로 복사 (수정 없음)
├── calc.py                    # 수정: recalculate_purchase_row에 row_num 인자 추가
├── exporter.py                # 수정: composite key 조회로 변경
├── db.py                      # 재작성: 복합키 스키마 + users 테이블
├── auth.py                    # Flask-Login User 클래스 + user_loader
├── app.py                     # Flask 애플리케이션 팩토리, CLI 커맨드, 블루프린트 등록
├── routes/
│   ├── __init__.py
│   ├── auth_routes.py         # /login, /logout
│   ├── home_routes.py         # /  (대시보드 + 업로드)
│   ├── bom_routes.py          # /bom (조회/필터/인라인편집, HTMX)
│   └── fx_routes.py           # /fx/refresh (환율 수동갱신, HTMX)
├── templates/
│   ├── base.html              # 사이드바+상단바 레이아웃
│   ├── login.html
│   ├── home.html
│   ├── bom.html
│   ├── partials/
│   │   ├── _grid.html         # HTMX 부분갱신 대상 (필터/페이지네이션 결과)
│   │   ├── _row.html          # 인라인편집 저장 후 갱신되는 단일 행
│   │   └── _fx_widget.html    # 환율 위젯 (사이드바 하단, HTMX 갱신)
├── static/
│   └── style.css              # 라이트 ERP 테마 커스텀 CSS
├── tests/
│   ├── __init__.py
│   ├── fixtures.py            # proto에서 복사 (수정 없음)
│   ├── conftest.py            # Flask test client + tmp db fixture
│   ├── test_db.py             # 재작성 (복합키)
│   ├── test_calc.py           # 재작성 (row_num 인자)
│   ├── test_exporter.py       # 재작성 (복합키 조회)
│   ├── test_parser.py         # proto에서 복사 (수정 없음 — parser 인터페이스 불변)
│   ├── test_auth.py           # 신규
│   └── test_bom_routes.py     # 신규
└── requirements.txt
```

**Interfaces 요약 (모듈 간 계약):**
- `db.get_connection(db_path) -> sqlite3.Connection`
- `db.init_db(conn) -> None`
- `db.upsert_part(conn, part_no, row_num, level_depth, level_marker, fields: dict) -> None`
- `db.get_part(conn, part_no, row_num) -> dict | None`
- `db.list_parts(conn) -> list[dict]`
- `db.upsert_purchase(conn, part_no, row_num, country, fields: dict) -> None`
- `db.get_purchase(conn, part_no, row_num, country) -> dict | None`
- `db.list_purchase_for_part(conn, part_no, row_num) -> list[dict]`
- `db.create_user(conn, username, password_hash, role="admin") -> None`
- `db.get_user_by_username(conn, username) -> dict | None`
- `db.get_user_by_id(conn, user_id) -> dict | None`
- `calc.recalculate_purchase_row(conn, part_no, row_num, country, fields: dict) -> dict`
- `exporter.export_to_template(conn, template_path) -> bytes` (시그니처 불변, 내부만 복합키 조회로 변경)
- `parser.parse_and_upsert(conn, file_like) -> dict` (시그니처 불변 — 이미 row_num을 db.upsert_part에 넘기고 있음)

---

### Task 1: `portal/` 스캐폴딩 + 순수 모듈 이식

**Files:**
- Create: `portal/config.py`
- Create: `portal/columns.py` (proto와 동일 내용)
- Create: `portal/fx.py` (proto와 동일 내용)
- Create: `portal/parser.py` (proto와 동일 내용)
- Create: `portal/requirements.txt`
- Create: `portal/tests/__init__.py`
- Create: `portal/tests/fixtures.py` (proto와 동일 내용)
- Test: `portal/tests/test_columns.py`

**Interfaces:**
- Produces: `columns.DESIGN_FIELDS`, `columns.PURCHASE_FIELDS`, `columns.COUNTRIES`, `columns.COUNTRY_BASE_COL`, `columns.purchase_column`, `columns.LEVEL_COLUMNS`, `columns.FIRST_DATA_ROW`, `columns.CALCULATED_PURCHASE_FIELDS` — 이후 모든 태스크가 이 모듈을 import.

- [ ] **Step 1: 디렉토리 생성 및 순수 모듈 복사**

`portal/columns.py`, `portal/fx.py`, `portal/parser.py`는 `proto(rev.0)/`의 동일 파일과 완전히 같은 내용으로 생성한다 (이미 위에서 Read한 내용 그대로 복사 — columns.py는 DESIGN_FIELDS/LEVEL_COLUMNS/COUNTRIES/COUNTRY_BASE_COL/PURCHASE_FIELDS/CALCULATED_PURCHASE_FIELDS/FIRST_DATA_ROW/purchase_column 전체, fx.py는 API_URL/store_rate/get_latest_rate/fetch_rates_from_api/refresh_rates 전체, parser.py는 parse_and_upsert 전체).

`portal/config.py`:
```python
import secrets

DB_PATH = "bom.db"
TEMPLATE_PATH = r"D:\재료비 관리 포탈 PJT\BOM 양식.xlsx"
SECRET_KEY = secrets.token_hex(32)
```

`portal/requirements.txt`:
```
flask>=3.0
flask-login>=0.6
waitress>=3.0
openpyxl>=3.1
requests>=2.31
pytest>=8.0
werkzeug>=3.0
```

`portal/tests/__init__.py`: 빈 파일.

`portal/tests/fixtures.py`: proto의 `tests/fixtures.py`와 완전히 같은 내용 (`make_bom_fixture`).

- [ ] **Step 2: Write the failing test**

```python
# portal/tests/test_columns.py
import columns

def test_purchase_column_korea_material_cost():
    assert columns.purchase_column("한국", "material_cost") == 43

def test_design_fields_contains_part_no():
    names = [n for n, _ in columns.DESIGN_FIELDS]
    assert "part_no" in names
```

- [ ] **Step 3: Run test to verify it fails**

Run (from `portal/` with `PYTHONPATH=.`): `python -m pytest tests/test_columns.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'columns'` (파일 생성 전이면) 또는 즉시 PASS 확인용으로 먼저 columns.py 없이 실행해 실패를 확인한다.

- [ ] **Step 4: 모듈 생성 후 재실행**

Step 1의 파일들을 생성한 뒤 재실행.

Run: `python -m pytest tests/test_columns.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add portal/columns.py portal/fx.py portal/parser.py portal/config.py portal/requirements.txt portal/tests/__init__.py portal/tests/fixtures.py portal/tests/test_columns.py
git commit -m "feat(portal): scaffold portal package, port pure-python modules"
```

---

### Task 2: DB 복합키 스키마 재작성 + users 테이블

**Files:**
- Create: `portal/db.py`
- Create: `portal/tests/test_db.py`

**Interfaces:**
- Consumes: `columns.DESIGN_FIELDS`, `columns.PURCHASE_FIELDS` (Task 1)
- Produces: `db.get_connection`, `db.init_db`, `db.upsert_part(conn, part_no, row_num, level_depth, level_marker, fields)`, `db.get_part(conn, part_no, row_num)`, `db.list_parts(conn)`, `db.upsert_purchase(conn, part_no, row_num, country, fields)`, `db.get_purchase(conn, part_no, row_num, country)`, `db.list_purchase_for_part(conn, part_no, row_num)`, `db.create_user(conn, username, password_hash, role="admin")`, `db.get_user_by_username(conn, username)`, `db.get_user_by_id(conn, user_id)` — Task 3(calc/exporter), Task 4(auth), Task 5+(routes)가 이 시그니처를 사용.

- [ ] **Step 1: Write the failing tests**

```python
# portal/tests/test_db.py
import db

def test_upsert_and_get_part(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", row_num=12, level_depth=1, level_marker="●",
                    fields={"vehicle": "NE2_NV1", "part_name": "FILTER", "qty": "2"})
    part = db.get_part(conn, "P001", 12)
    assert part["part_no"] == "P001"
    assert part["row_num"] == 12
    assert part["part_name"] == "FILTER"
    assert part["qty"] == "2"

def test_same_part_no_different_row_num_are_distinct(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER-A"})
    db.upsert_part(conn, "P001", 45, 2, "●", {"part_name": "FILTER-B"})
    assert db.get_part(conn, "P001", 12)["part_name"] == "FILTER-A"
    assert db.get_part(conn, "P001", 45)["part_name"] == "FILTER-B"
    assert len(db.list_parts(conn)) == 2

def test_upsert_keeps_other_fields_on_partial_update(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER", "qty": "2"})
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER-V2", "qty": "2"})
    part = db.get_part(conn, "P001", 12)
    assert part["part_name"] == "FILTER-V2"
    assert len(db.list_parts(conn)) == 1

def test_upsert_and_get_purchase(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER"})
    db.upsert_purchase(conn, "P001", 12, "한국", {"currency": "KRW", "unit_price_material": "1000"})
    purchase = db.get_purchase(conn, "P001", 12, "한국")
    assert purchase["currency"] == "KRW"
    assert purchase["unit_price_material"] == "1000"

def test_purchase_upsert_updates_not_duplicates(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER"})
    db.upsert_purchase(conn, "P001", 12, "한국", {"unit_price_material": "1000"})
    db.upsert_purchase(conn, "P001", 12, "한국", {"unit_price_material": "2000"})
    rows = db.list_purchase_for_part(conn, "P001", 12)
    assert len(rows) == 1
    assert rows[0]["unit_price_material"] == "2000"

def test_purchase_distinct_per_row_num_for_same_part_no(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER-A"})
    db.upsert_part(conn, "P001", 45, 2, "●", {"part_name": "FILTER-B"})
    db.upsert_purchase(conn, "P001", 12, "한국", {"unit_price_material": "1000"})
    db.upsert_purchase(conn, "P001", 45, "한국", {"unit_price_material": "9999"})
    assert db.get_purchase(conn, "P001", 12, "한국")["unit_price_material"] == "1000"
    assert db.get_purchase(conn, "P001", 45, "한국")["unit_price_material"] == "9999"

def test_create_and_get_user(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.create_user(conn, "admin", "hashed-pw", "admin")
    user = db.get_user_by_username(conn, "admin")
    assert user["username"] == "admin"
    assert user["password_hash"] == "hashed-pw"
    assert user["role"] == "admin"
    assert db.get_user_by_id(conn, user["id"])["username"] == "admin"

def test_get_user_by_username_missing_returns_none(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    assert db.get_user_by_username(conn, "nobody") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Write implementation**

```python
# portal/db.py
import sqlite3
import datetime
from columns import DESIGN_FIELDS, PURCHASE_FIELDS

def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(conn):
    design_cols = ", ".join(f"{name} TEXT" for name, _ in DESIGN_FIELDS if name != "part_no")
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS parts (
            part_no TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            level_depth INTEGER,
            level_marker TEXT,
            {design_cols},
            PRIMARY KEY (part_no, row_num)
        )
    """)
    purchase_cols = ", ".join(f"{name} TEXT" for name, _ in PURCHASE_FIELDS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS purchase_data (
            part_no TEXT NOT NULL,
            row_num INTEGER NOT NULL,
            country TEXT NOT NULL,
            {purchase_cols},
            PRIMARY KEY (part_no, row_num, country),
            FOREIGN KEY (part_no, row_num) REFERENCES parts(part_no, row_num)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fx_rates (
            currency TEXT NOT NULL,
            rate_date TEXT NOT NULL,
            rate REAL NOT NULL,
            PRIMARY KEY (currency, rate_date)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()

def upsert_part(conn, part_no, row_num, level_depth, level_marker, fields):
    design_names = [n for n, _ in DESIGN_FIELDS if n != "part_no"]
    columns = ["part_no", "row_num", "level_depth", "level_marker"] + design_names
    values = [part_no, row_num, level_depth, level_marker] + [fields.get(n) for n in design_names]
    placeholders = ", ".join(["?"] * len(columns))
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("part_no", "row_num"))
    conn.execute(
        f"INSERT INTO parts ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(part_no, row_num) DO UPDATE SET {updates}",
        values,
    )
    conn.commit()

def get_part(conn, part_no, row_num):
    row = conn.execute(
        "SELECT * FROM parts WHERE part_no = ? AND row_num = ?", (part_no, row_num)
    ).fetchone()
    return dict(row) if row else None

def list_parts(conn):
    rows = conn.execute("SELECT * FROM parts ORDER BY row_num").fetchall()
    return [dict(r) for r in rows]

def upsert_purchase(conn, part_no, row_num, country, fields):
    columns = ["part_no", "row_num", "country"] + [n for n, _ in PURCHASE_FIELDS]
    values = [part_no, row_num, country] + [fields.get(n) for n, _ in PURCHASE_FIELDS]
    placeholders = ", ".join(["?"] * len(columns))
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("part_no", "row_num", "country"))
    conn.execute(
        f"INSERT INTO purchase_data ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(part_no, row_num, country) DO UPDATE SET {updates}",
        values,
    )
    conn.commit()

def get_purchase(conn, part_no, row_num, country):
    row = conn.execute(
        "SELECT * FROM purchase_data WHERE part_no = ? AND row_num = ? AND country = ?",
        (part_no, row_num, country),
    ).fetchone()
    return dict(row) if row else None

def list_purchase_for_part(conn, part_no, row_num):
    rows = conn.execute(
        "SELECT * FROM purchase_data WHERE part_no = ? AND row_num = ?", (part_no, row_num)
    ).fetchall()
    return [dict(r) for r in rows]

def create_user(conn, username, password_hash, role="admin"):
    conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
        (username, password_hash, role, datetime.datetime.now().isoformat()),
    )
    conn.commit()

def get_user_by_username(conn, username):
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None

def get_user_by_id(conn, user_id):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_db.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add portal/db.py portal/tests/test_db.py
git commit -m "feat(portal): composite-key schema (part_no,row_num) + users table"
```

---

### Task 3: `calc.py` / `exporter.py` 복합키 대응 + `parser.py` 이식 검증

**Files:**
- Create: `portal/calc.py`
- Create: `portal/exporter.py`
- Create: `portal/tests/test_calc.py`
- Create: `portal/tests/test_exporter.py`
- Create: `portal/tests/test_parser.py` (proto와 동일 내용 — parser 인터페이스는 변경 없음)

**Interfaces:**
- Consumes: `db.get_part(conn, part_no, row_num)`, `db.get_purchase`, `db.list_purchase_for_part`, `db.upsert_purchase` (Task 2), `fx.get_latest_rate` (Task 1)
- Produces: `calc.compute_material_cost` (변경 없음), `calc.compute_total_cost` (변경 없음), `calc.recalculate_purchase_row(conn, part_no, row_num, country, fields)`, `exporter.export_to_template(conn, template_path)` — Task 5+(bom routes)가 사용.

- [ ] **Step 1: Write the failing tests**

```python
# portal/tests/test_calc.py
import db
import fx
import calc

def test_compute_material_cost_basic(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    fx.store_rate(conn, "USD", "2026-08-13", 1350.0)
    result = calc.compute_material_cost(conn, unit_price="10", qty="2", currency="USD")
    assert result == 27000.0

def test_compute_material_cost_krw_rate_is_one(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    result = calc.compute_material_cost(conn, unit_price="5000", qty="3", currency="KRW")
    assert result == 15000.0

def test_compute_material_cost_missing_rate_returns_none(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    result = calc.compute_material_cost(conn, unit_price="10", qty="2", currency="EUR")
    assert result is None

def test_compute_total_cost_sums_and_treats_none_as_zero():
    assert calc.compute_total_cost(1000.0, None, 200.0) == 1200.0
    assert calc.compute_total_cost(None, None, None) == 0.0

def test_recalculate_purchase_row_fills_calculated_fields(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER", "qty": "1"})
    fields = {
        "currency": "KRW", "unit_price_material": "1000",
        "logistics_cost": "50", "tariff_cost": "10",
    }
    result = calc.recalculate_purchase_row(conn, "P001", 12, "한국", fields)
    assert result["material_cost"] == 1000.0
    assert result["total_cost"] == 1060.0

def test_recalculate_purchase_row_uses_correct_row_when_same_part_no(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER-A", "qty": "1"})
    db.upsert_part(conn, "P001", 45, 2, "●", {"part_name": "FILTER-B", "qty": "10"})
    fields = {"currency": "KRW", "unit_price_material": "100"}
    result = calc.recalculate_purchase_row(conn, "P001", 45, "한국", fields)
    assert result["material_cost"] == 1000.0  # qty=10 from row 45, not row 12
```

```python
# portal/tests/test_exporter.py
import openpyxl
from io import BytesIO
import db
import exporter

def make_template_with_merge(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM_복사본"
    ws.merge_cells("B1:D1")
    ws["B1"] = "■ NE2_NV1 BOM"
    path = tmp_path / "template.xlsx"
    wb.save(path)
    return str(path)

def test_export_writes_part_values_at_original_coordinates(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", row_num=11, level_depth=1, level_marker="●",
                    fields={"part_name": "FILTER", "qty": "2"})
    db.upsert_purchase(conn, "P001", 11, "한국", {"currency": "KRW", "unit_price_material": "1000", "material_cost": "2000"})

    template_path = make_template_with_merge(tmp_path)
    output_bytes = exporter.export_to_template(conn, template_path)

    wb = openpyxl.load_workbook(BytesIO(output_bytes))
    ws = wb["BOM_복사본"]
    assert ws.cell(row=11, column=12).value == "FILTER"
    assert ws.cell(row=11, column=42).value == "1000"
    assert ws.cell(row=11, column=43).value == "2000"

def test_export_preserves_merged_cells(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    template_path = make_template_with_merge(tmp_path)
    output_bytes = exporter.export_to_template(conn, template_path)
    wb = openpyxl.load_workbook(BytesIO(output_bytes))
    ws = wb["BOM_복사본"]
    assert "B1:D1" in [str(r) for r in ws.merged_cells.ranges]
    assert ws["B1"].value == "■ NE2_NV1 BOM"

def test_export_handles_duplicate_part_no_different_rows(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", row_num=11, level_depth=1, level_marker="●", fields={"part_name": "FILTER-A"})
    db.upsert_part(conn, "P001", row_num=13, level_depth=1, level_marker="●", fields={"part_name": "FILTER-B"})
    template_path = make_template_with_merge(tmp_path)
    output_bytes = exporter.export_to_template(conn, template_path)
    wb = openpyxl.load_workbook(BytesIO(output_bytes))
    ws = wb["BOM_복사본"]
    assert ws.cell(row=11, column=12).value == "FILTER-A"
    assert ws.cell(row=13, column=12).value == "FILTER-B"
```

`portal/tests/test_parser.py`: proto의 `tests/test_parser.py`와 완전히 동일한 내용 (parser 인터페이스 불변이므로 그대로 이식 — `db.get_part`/`db.upsert_purchase` 호출부는 없고 parser 내부만 사용).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calc.py tests/test_exporter.py tests/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'calc'` / `'exporter'`, `test_parse_...` 는 `db.get_part(conn, part_no)` 시그니처 불일치로 `TypeError` (parser.py가 내부에서 `db.get_part(conn, part_no)` 1-arg 호출 중이므로 Task 2의 2-arg 시그니처와 충돌 — Step 3에서 parser.py도 함께 고친다).

- [ ] **Step 3: Write implementation**

```python
# portal/calc.py
import db
import fx

def compute_material_cost(conn, unit_price, qty, currency):
    if unit_price is None or qty is None or currency is None:
        return None
    rate = fx.get_latest_rate(conn, currency)
    if rate is None:
        return None
    return float(unit_price) * float(qty) * rate

def compute_total_cost(material_cost, logistics_cost, tariff_cost):
    return sum(float(v) if v not in (None, "") else 0.0
               for v in (material_cost, logistics_cost, tariff_cost))

def recalculate_purchase_row(conn, part_no, row_num, country, fields):
    part = db.get_part(conn, part_no, row_num)
    qty = part["qty"] if part else None
    material_cost = compute_material_cost(
        conn, fields.get("unit_price_material"), qty, fields.get("currency")
    )
    total_cost = compute_total_cost(
        material_cost, fields.get("logistics_cost"), fields.get("tariff_cost")
    )
    result = dict(fields)
    result["material_cost"] = material_cost
    result["total_cost"] = total_cost
    return result
```

```python
# portal/exporter.py
import openpyxl
from io import BytesIO
from columns import DESIGN_FIELDS, COUNTRIES, PURCHASE_FIELDS, purchase_column
import db

def export_to_template(conn, template_path):
    wb = openpyxl.load_workbook(template_path)
    ws = wb["BOM_복사본"]

    for part in db.list_parts(conn):
        row_num = part["row_num"]
        for name, col in DESIGN_FIELDS:
            if name == "part_no":
                continue
            value = part.get(name)
            if value is not None:
                ws.cell(row=row_num, column=col, value=value)

        for country in COUNTRIES:
            purchase = db.get_purchase(conn, part["part_no"], row_num, country)
            if not purchase:
                continue
            for name, _ in PURCHASE_FIELDS:
                value = purchase.get(name)
                if value is not None:
                    col = purchase_column(country, name)
                    ws.cell(row=row_num, column=col, value=value)

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
```

`portal/parser.py`의 `db.get_part(conn, part_no)` 호출부(Task 1에서 이식한 원본 코드 중 `existed = db.get_part(conn, part_no) is not None` 라인)를 `existed = db.get_part(conn, part_no, row_num) is not None`로 수정한다. `parse_and_upsert` 함수 시그니처(`parse_and_upsert(conn, file_like)`) 자체는 변경 없음 — 내부 구현 한 줄만 수정.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calc.py tests/test_exporter.py tests/test_parser.py -v`
Expected: PASS (전체)

- [ ] **Step 5: Commit**

```bash
git add portal/calc.py portal/exporter.py portal/parser.py portal/tests/test_calc.py portal/tests/test_exporter.py portal/tests/test_parser.py
git commit -m "feat(portal): composite-key aware calc/exporter, fix parser get_part call"
```

---

### Task 4: 인증 (Flask-Login) + `create-admin` CLI

**Files:**
- Create: `portal/auth.py`
- Create: `portal/app.py`
- Create: `portal/routes/__init__.py`
- Create: `portal/routes/auth_routes.py`
- Create: `portal/templates/base.html`
- Create: `portal/templates/login.html`
- Create: `portal/static/style.css`
- Create: `portal/tests/conftest.py`
- Create: `portal/tests/test_auth.py`

**Interfaces:**
- Consumes: `db.get_connection`, `db.init_db`, `db.get_user_by_username`, `db.get_user_by_id`, `db.create_user` (Task 2)
- Produces: `auth.PortalUser` (Flask-Login `UserMixin` 구현), `app.create_app(db_path=None) -> Flask`, CLI 커맨드 `flask create-admin`, `login_required` 데코레이터로 보호되는 라우트 패턴 — Task 5, 6, 7이 `app.create_app`과 `@login_required`를 사용.

- [ ] **Step 1: Write the failing tests**

```python
# portal/tests/conftest.py
import pytest
import db
from app import create_app

@pytest.fixture
def app(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = db.get_connection(db_path)
    db.init_db(conn)
    conn.close()
    app = create_app(db_path=db_path)
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def admin_user(app):
    from werkzeug.security import generate_password_hash
    conn = db.get_connection(app.config["DB_PATH"])
    db.create_user(conn, "admin", generate_password_hash("secret123"), "admin")
    conn.close()
    return {"username": "admin", "password": "secret123"}
```

```python
# portal/tests/test_auth.py
def test_root_redirects_to_login_when_unauthenticated(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_login_with_valid_credentials_redirects_to_home(client, admin_user):
    resp = client.post("/login", data=admin_user, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] in ("/", "http://localhost/")

def test_login_with_invalid_credentials_shows_error(client, admin_user):
    resp = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 200
    assert "로그인 실패".encode() in resp.data or b"invalid" in resp.data.lower()

def test_logout_redirects_to_login(client, admin_user):
    client.post("/login", data=admin_user)
    resp = client.get("/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_authenticated_user_can_access_home(client, admin_user):
    client.post("/login", data=admin_user)
    resp = client.get("/")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Write implementation**

```python
# portal/auth.py
from flask_login import UserMixin
import db

class PortalUser(UserMixin):
    def __init__(self, row):
        self.id = str(row["id"])
        self.username = row["username"]
        self.role = row["role"]

def load_user_by_id(conn, user_id):
    row = db.get_user_by_id(conn, int(user_id))
    return PortalUser(row) if row else None
```

```python
# portal/app.py
import os
import click
from flask import Flask
from flask_login import LoginManager
from werkzeug.security import generate_password_hash
import db
import config
from auth import PortalUser
from routes.auth_routes import auth_bp
from routes.home_routes import home_bp
from routes.bom_routes import bom_bp
from routes.fx_routes import fx_bp

def create_app(db_path=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["DB_PATH"] = db_path or config.DB_PATH
    app.config["TEMPLATE_PATH"] = config.TEMPLATE_PATH

    conn = db.get_connection(app.config["DB_PATH"])
    db.init_db(conn)
    conn.close()

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def user_loader(user_id):
        conn = db.get_connection(app.config["DB_PATH"])
        row = db.get_user_by_id(conn, int(user_id))
        conn.close()
        return PortalUser(row) if row else None

    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(bom_bp)
    app.register_blueprint(fx_bp)

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("password")
    def create_admin(username, password):
        conn = db.get_connection(app.config["DB_PATH"])
        if db.get_user_by_username(conn, username):
            click.echo(f"이미 존재하는 계정: {username}")
            return
        db.create_user(conn, username, generate_password_hash(password), "admin")
        conn.close()
        click.echo(f"관리자 계정 생성됨: {username}")

    return app
```

```python
# portal/routes/__init__.py
```

```python
# portal/routes/auth_routes.py
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
```

`portal/templates/base.html`:
```html
<!doctype html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <title>{% block title %}재료비 관리 포탈{% endblock %}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
{% if current_user.is_authenticated %}
<div class="portal-shell">
    <aside class="portal-sidebar">
        <div class="portal-brand">
            <i class="bi bi-calculator"></i>
            <span>재료비 관리 포탈</span>
        </div>
        <nav class="portal-nav">
            <a href="{{ url_for('home.index') }}" class="{{ 'active' if request.endpoint == 'home.index' }}">
                <i class="bi bi-house"></i> 홈
            </a>
            <a href="{{ url_for('bom.index') }}" class="{{ 'active' if request.endpoint and request.endpoint.startswith('bom.') }}">
                <i class="bi bi-table"></i> BOM 조회·입력
            </a>
        </nav>
        <div id="fx-widget" hx-get="{{ url_for('fx.widget') }}" hx-trigger="load">
        </div>
        <div class="portal-user">
            <i class="bi bi-person-circle"></i> {{ current_user.username }}
            <a href="{{ url_for('auth.logout') }}" title="로그아웃"><i class="bi bi-box-arrow-right"></i></a>
        </div>
    </aside>
    <main class="portal-main">
        <header class="portal-topbar">
            <h1>{% block page_title %}{% endblock %}</h1>
        </header>
        <div class="portal-content">
            {% block content %}{% endblock %}
        </div>
    </main>
</div>
{% else %}
{% block guest_content %}{% endblock %}
{% endif %}
</body>
</html>
```

`portal/templates/login.html`:
```html
{% extends "base.html" %}
{% block guest_content %}
<div class="login-shell">
    <div class="login-card">
        <div class="login-brand"><i class="bi bi-calculator"></i> 재료비 관리 포탈</div>
        {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
        <form method="post">
            <div class="mb-3">
                <label class="form-label">아이디</label>
                <input type="text" name="username" class="form-control" required autofocus>
            </div>
            <div class="mb-3">
                <label class="form-label">비밀번호</label>
                <input type="password" name="password" class="form-control" required>
            </div>
            <button type="submit" class="btn btn-primary w-100">로그인</button>
        </form>
    </div>
</div>
{% endblock %}
```

`portal/static/style.css`:
```css
:root {
    --portal-bg: #F5F7FA;
    --portal-card-bg: #FFFFFF;
    --portal-accent: #4F8CFF;
    --portal-text-muted: #6B7280;
    --portal-border: #E5E9F0;
}
body { background: var(--portal-bg); color: #1F2937; }
.portal-shell { display: flex; min-height: 100vh; }
.portal-sidebar {
    width: 240px; background: var(--portal-card-bg); border-right: 1px solid var(--portal-border);
    display: flex; flex-direction: column; padding: 1.25rem 1rem;
}
.portal-brand { font-weight: 700; font-size: 1.05rem; margin-bottom: 1.5rem; display: flex; gap: .5rem; align-items: center; }
.portal-nav { display: flex; flex-direction: column; gap: .25rem; flex: 1; }
.portal-nav a {
    color: #374151; text-decoration: none; padding: .6rem .75rem; border-radius: 8px;
    display: flex; gap: .6rem; align-items: center; font-size: .92rem;
}
.portal-nav a:hover { background: #EFF3FA; }
.portal-nav a.active { background: #EAF1FF; color: var(--portal-accent); font-weight: 600; border-left: 3px solid var(--portal-accent); }
.portal-user { border-top: 1px solid var(--portal-border); padding-top: 1rem; margin-top: 1rem; font-size: .85rem; display: flex; justify-content: space-between; align-items: center; }
.portal-main { flex: 1; display: flex; flex-direction: column; }
.portal-topbar { background: var(--portal-card-bg); border-bottom: 1px solid var(--portal-border); padding: 1rem 1.5rem; }
.portal-topbar h1 { font-size: 1.15rem; margin: 0; }
.portal-content { padding: 1.5rem; flex: 1; }
.portal-card {
    background: var(--portal-card-bg); border-radius: 10px; border: 1px solid var(--portal-border);
    border-left: 3px solid var(--portal-accent); padding: 1.1rem 1.25rem; box-shadow: 0 1px 2px rgba(16,24,40,.04);
}
.kpi-card .kpi-label { color: var(--portal-text-muted); font-size: .8rem; }
.kpi-card .kpi-value { font-size: 1.6rem; font-weight: 700; }
.login-shell { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--portal-bg); }
.login-card { background: var(--portal-card-bg); border-radius: 12px; padding: 2rem; width: 360px; box-shadow: 0 4px 16px rgba(16,24,40,.08); }
.login-brand { font-weight: 700; margin-bottom: 1.25rem; display: flex; gap: .5rem; align-items: center; }
```

- [ ] **Step 4: Run test to verify it passes**

`portal/routes/home_routes.py`, `bom_routes.py`, `fx_routes.py`는 아직 없으므로 최소 stub으로 만들어 import 에러만 없앤다 (실제 구현은 Task 5~7):

```python
# portal/routes/home_routes.py (임시 stub — Task 5에서 교체)
from flask import Blueprint, render_template
from flask_login import login_required

home_bp = Blueprint("home", __name__)

@home_bp.route("/")
@login_required
def index():
    return render_template("home.html")
```
```python
# portal/routes/bom_routes.py (임시 stub — Task 6에서 교체)
from flask import Blueprint

bom_bp = Blueprint("bom", __name__, url_prefix="/bom")

@bom_bp.route("/")
def index():
    return "stub"
```
```python
# portal/routes/fx_routes.py (임시 stub — Task 7에서 교체)
from flask import Blueprint

fx_bp = Blueprint("fx", __name__, url_prefix="/fx")

@fx_bp.route("/widget")
def widget():
    return ""
```
`portal/templates/home.html` (임시): `{% extends "base.html" %}{% block content %}<p>home stub</p>{% endblock %}`

Run: `python -m pytest tests/test_auth.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add portal/auth.py portal/app.py portal/routes portal/templates portal/static portal/tests/conftest.py portal/tests/test_auth.py
git commit -m "feat(portal): Flask-Login auth, create-admin CLI, base layout"
```

---

### Task 5: 홈 대시보드 (KPI 카드 + 업로드)

**Files:**
- Modify: `portal/routes/home_routes.py` (stub 교체)
- Modify: `portal/templates/home.html` (stub 교체)
- Create: `portal/tests/test_home_routes.py`

**Interfaces:**
- Consumes: `db.list_parts`, `db.list_purchase_for_part`, `fx.get_latest_rate`, `parser.parse_and_upsert` (Task 1~3), `app.create_app` + `login_required` (Task 4)
- Produces: `GET /` (대시보드), `POST /upload` (BOM 업로드) — 이후 태스크 없음(최종 소비 지점).

- [ ] **Step 1: Write the failing tests**

```python
# portal/tests/test_home_routes.py
import io
import openpyxl

def login(client, admin_user):
    client.post("/login", data=admin_user)

def test_home_shows_zero_parts_when_empty(client, admin_user):
    login(client, admin_user)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "0".encode() in resp.data

def make_upload_file():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM_복사본"
    ws.cell(row=11, column=13, value="P001")
    ws.cell(row=11, column=12, value="FILTER")
    ws.cell(row=11, column=19, value=2)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

def test_upload_inserts_parts_and_redirects_home(client, admin_user):
    login(client, admin_user)
    resp = client.post(
        "/upload",
        data={"bom_file": (make_upload_file(), "bom.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "신규 1건".encode() in resp.data

def test_upload_requires_login(client):
    resp = client.post(
        "/upload",
        data={"bom_file": (make_upload_file(), "bom.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code == 302
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_home_routes.py -v`
Expected: FAIL (`/upload` 라우트 없음 → 404, KPI "0" 텍스트 없음)

- [ ] **Step 3: Write implementation**

```python
# portal/routes/home_routes.py
from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash
from flask_login import login_required
import db
import fx
import parser

home_bp = Blueprint("home", __name__)

@home_bp.route("/")
@login_required
def index():
    conn = db.get_connection(current_app.config["DB_PATH"])
    parts = db.list_parts(conn)
    missing = sum(
        1 for p in parts
        if not db.list_purchase_for_part(conn, p["part_no"], p["row_num"])
    )
    usd = fx.get_latest_rate(conn, "USD")
    eur = fx.get_latest_rate(conn, "EUR")
    conn.close()
    return render_template(
        "home.html",
        total_parts=len(parts), missing=missing, usd=usd, eur=eur,
    )

@home_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    conn = db.get_connection(current_app.config["DB_PATH"])
    file = request.files["bom_file"]
    result = parser.parse_and_upsert(conn, file)
    conn.close()
    msg = f"신규 {result['inserted']}건 / 갱신 {result['updated']}건 반영됨"
    if result["skipped"]:
        msg += f" (품번 없음으로 {len(result['skipped'])}행 건너뜀)"
    flash(msg)
    return redirect(url_for("home.index"))
```

```html
{# portal/templates/home.html #}
{% extends "base.html" %}
{% block page_title %}홈{% endblock %}
{% block content %}
{% with messages = get_flashed_messages() %}
  {% if messages %}
    <div class="alert alert-success">{{ messages[0] }}</div>
  {% endif %}
{% endwith %}
<div class="row g-3 mb-3">
    <div class="col-3">
        <div class="portal-card kpi-card">
            <div class="kpi-label">총 부품수</div>
            <div class="kpi-value">{{ "{:,}".format(total_parts) }}</div>
        </div>
    </div>
    <div class="col-3">
        <div class="portal-card kpi-card">
            <div class="kpi-label">구매정보 미입력</div>
            <div class="kpi-value">{{ "{:,}".format(missing) }}</div>
        </div>
    </div>
    <div class="col-3">
        <div class="portal-card kpi-card">
            <div class="kpi-label">USD 환율</div>
            <div class="kpi-value">{{ "%.1f"|format(usd) if usd else "미확보" }}</div>
        </div>
    </div>
    <div class="col-3">
        <div class="portal-card kpi-card">
            <div class="kpi-label">EUR 환율</div>
            <div class="kpi-value">{{ "%.1f"|format(eur) if eur else "미확보" }}</div>
        </div>
    </div>
</div>
<div class="portal-card">
    <h5><i class="bi bi-upload"></i> BOM 업로드</h5>
    <p class="text-muted">설계 BOM 엑셀을 업로드하면 품번 기준으로 시스템에 반영됩니다 (재업로드 시 구매입력값은 유지됨).</p>
    <form method="post" action="{{ url_for('home.upload') }}" enctype="multipart/form-data" class="d-flex gap-2">
        <input type="file" name="bom_file" accept=".xlsx" class="form-control" required>
        <button type="submit" class="btn btn-primary text-nowrap">업로드</button>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_home_routes.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add portal/routes/home_routes.py portal/templates/home.html portal/tests/test_home_routes.py
git commit -m "feat(portal): home dashboard with KPI cards and BOM upload"
```

---

### Task 6: BOM 조회·입력 그리드 (필터 + 페이지네이션 + HTMX 인라인 편집)

**Files:**
- Modify: `portal/routes/bom_routes.py` (stub 교체)
- Create: `portal/templates/bom.html`
- Create: `portal/templates/partials/_grid.html`
- Create: `portal/templates/partials/_row.html`
- Create: `portal/tests/test_bom_routes.py`

**Interfaces:**
- Consumes: `db.list_parts`, `db.get_purchase`, `db.upsert_purchase` (Task 2), `calc.recalculate_purchase_row(conn, part_no, row_num, country, fields)` (Task 3), `columns.COUNTRIES` (Task 1)
- Produces: `GET /bom` (전체 페이지), `GET /bom/grid` (HTMX 부분: 필터+페이지네이션), `POST /bom/row/<part_no>/<int:row_num>/<country>` (인라인 편집 저장, HTMX 부분: 단일 행) — 최종 소비 지점.

- [ ] **Step 1: Write the failing tests**

```python
# portal/tests/test_bom_routes.py
import db

def login(client, admin_user):
    client.post("/login", data=admin_user)

def seed_parts(app, n=25):
    conn = db.get_connection(app.config["DB_PATH"])
    for i in range(n):
        conn2_part_no = f"P{i:03d}"
        db.upsert_part(conn, conn2_part_no, 11 + i, 1, "●", {"part_name": f"PART-{i}", "qty": "1"})
    conn.close()

def test_bom_index_requires_login(client):
    resp = client.get("/bom/", follow_redirects=False)
    assert resp.status_code == 302

def test_bom_grid_shows_first_page(client, admin_user, app):
    login(client, admin_user)
    seed_parts(app, n=25)
    resp = client.get("/bom/grid?country=한국&page=1")
    assert resp.status_code == 200
    assert b"P000" in resp.data
    assert b"P024" not in resp.data  # page size 20 -> 2nd page item not shown

def test_bom_grid_search_filters_by_part_name(client, admin_user, app):
    login(client, admin_user)
    seed_parts(app, n=5)
    resp = client.get("/bom/grid?country=한국&search=PART-2")
    assert b"PART-2" in resp.data
    assert b"PART-1<" not in resp.data

def test_save_row_recalculates_and_persists(client, admin_user, app):
    login(client, admin_user)
    conn = db.get_connection(app.config["DB_PATH"])
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER", "qty": "2"})
    conn.close()
    resp = client.post(
        "/bom/row/P001/12/한국",
        data={"currency": "KRW", "unit_price_material": "500", "logistics_cost": "0", "tariff_cost": "0", "tariff_rate": "0", "mold_cost": "0", "unit_price_logistics": "0"},
    )
    assert resp.status_code == 200
    conn = db.get_connection(app.config["DB_PATH"])
    purchase = db.get_purchase(conn, "P001", 12, "한국")
    conn.close()
    assert purchase["material_cost"] == "1000.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bom_routes.py -v`
Expected: FAIL (`/bom/` stub returns "stub" not redirect; `/bom/grid`, `/bom/row/...` 404)

- [ ] **Step 3: Write implementation**

```python
# portal/routes/bom_routes.py
from flask import Blueprint, render_template, request, current_app
from flask_login import login_required
import db
import calc
from columns import COUNTRIES

bom_bp = Blueprint("bom", __name__, url_prefix="/bom")

PAGE_SIZE = 20

def _to_float(value):
    try:
        return float(value) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0

def _build_row_view(part, purchase):
    purchase = purchase or {}
    has_price = bool(purchase.get("unit_price_material"))
    return {
        "part_no": part["part_no"],
        "row_num": part["row_num"],
        "part_name": part.get("part_name") or "",
        "qty": _to_float(part.get("qty")),
        "status_done": has_price,
        "currency": purchase.get("currency") or "KRW",
        "unit_price_material": purchase.get("unit_price_material") or "",
        "material_cost": _to_float(purchase.get("material_cost")),
        "unit_price_logistics": purchase.get("unit_price_logistics") or "",
        "logistics_cost": purchase.get("logistics_cost") or "",
        "tariff_rate": purchase.get("tariff_rate") or "",
        "tariff_cost": purchase.get("tariff_cost") or "",
        "total_cost": _to_float(purchase.get("total_cost")),
        "mold_cost": purchase.get("mold_cost") or "",
    }

def _filtered_rows(conn, country, status, search):
    parts = db.list_parts(conn)
    keyword = (search or "").strip().lower()
    rows = []
    for p in parts:
        if keyword and keyword not in (p["part_no"] or "").lower() and keyword not in (p.get("part_name") or "").lower():
            continue
        purchase = db.get_purchase(conn, p["part_no"], p["row_num"], country)
        row = _build_row_view(p, purchase)
        if status == "done" and not row["status_done"]:
            continue
        if status == "missing" and row["status_done"]:
            continue
        rows.append(row)
    return rows

@bom_bp.route("/")
@login_required
def index():
    return render_template("bom.html", countries=COUNTRIES)

@bom_bp.route("/grid")
@login_required
def grid():
    country = request.args.get("country", COUNTRIES[0])
    status = request.args.get("status", "all")
    search = request.args.get("search", "")
    page = int(request.args.get("page", 1))

    conn = db.get_connection(current_app.config["DB_PATH"])
    all_rows = _filtered_rows(conn, country, status, search)
    conn.close()

    total = len(all_rows)
    start = (page - 1) * PAGE_SIZE
    page_rows = all_rows[start:start + PAGE_SIZE]
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    material_sum = sum(r["material_cost"] for r in all_rows)
    total_sum = sum(r["total_cost"] for r in all_rows)

    return render_template(
        "partials/_grid.html",
        rows=page_rows, country=country, status=status, search=search,
        page=page, total_pages=total_pages, total=total,
        material_sum=material_sum, total_sum=total_sum,
    )

@bom_bp.route("/row/<part_no>/<int:row_num>/<country>", methods=["POST"])
@login_required
def save_row(part_no, row_num, country):
    fields = {
        "currency": request.form.get("currency"),
        "unit_price_material": request.form.get("unit_price_material"),
        "unit_price_logistics": request.form.get("unit_price_logistics"),
        "logistics_cost": request.form.get("logistics_cost"),
        "tariff_rate": request.form.get("tariff_rate"),
        "tariff_cost": request.form.get("tariff_cost"),
        "mold_cost": request.form.get("mold_cost"),
    }
    conn = db.get_connection(current_app.config["DB_PATH"])
    calculated = calc.recalculate_purchase_row(conn, part_no, row_num, country, fields)
    db.upsert_purchase(conn, part_no, row_num, country, calculated)
    part = db.get_part(conn, part_no, row_num)
    purchase = db.get_purchase(conn, part_no, row_num, country)
    conn.close()
    row = _build_row_view(part, purchase)
    return render_template("partials/_row.html", row=row, country=country)
```

```html
{# portal/templates/bom.html #}
{% extends "base.html" %}
{% block page_title %}BOM 조회·입력{% endblock %}
{% block content %}
<div class="portal-card mb-3">
    <form id="filter-form" class="row g-2 align-items-end"
          hx-get="{{ url_for('bom.grid') }}" hx-target="#grid-container" hx-trigger="change, submit, keyup changed delay:400ms from:[name=search]">
        <div class="col-2">
            <label class="form-label">국가</label>
            <select name="country" class="form-select">
                {% for c in countries %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
            </select>
        </div>
        <div class="col-2">
            <label class="form-label">상태</label>
            <select name="status" class="form-select">
                <option value="all">전체</option>
                <option value="done">완료</option>
                <option value="missing">미입력</option>
            </select>
        </div>
        <div class="col-4">
            <label class="form-label">검색</label>
            <input type="text" name="search" class="form-control" placeholder="품번 또는 품명">
        </div>
        <input type="hidden" name="page" value="1">
    </form>
</div>
<div id="grid-container" hx-get="{{ url_for('bom.grid') }}" hx-trigger="load" hx-vals='{"country": "{{ countries[0] }}"}'>
    로딩 중...
</div>
{% endblock %}
```

```html
{# portal/templates/partials/_grid.html #}
<table class="table table-hover bg-white">
    <thead>
    <tr>
        <th>상태</th><th>품번</th><th>품명</th><th>수량</th><th>통화</th>
        <th>재료비단가</th><th>재료비(자동)</th><th>물류비단가</th><th>물류비</th>
        <th>관세율(%)</th><th>관세금액</th><th>총합계(자동)</th><th>금형비</th><th></th>
    </tr>
    </thead>
    <tbody id="grid-body">
    {% for row in rows %}
        {% include "partials/_row.html" %}
    {% endfor %}
    </tbody>
</table>
<div class="d-flex justify-content-between align-items-center portal-card">
    <span>표시 {{ rows|length }} / {{ total }}건 · 재료비 합계 {{ "{:,.0f}".format(material_sum) }} · 총합계 합계 {{ "{:,.0f}".format(total_sum) }}</span>
    <div>
        {% if page > 1 %}
        <button class="btn btn-sm btn-outline-secondary"
                hx-get="{{ url_for('bom.grid', country=country, status=status, search=search, page=page-1) }}"
                hx-target="#grid-container">이전</button>
        {% endif %}
        <span>{{ page }} / {{ total_pages }}</span>
        {% if page < total_pages %}
        <button class="btn btn-sm btn-outline-secondary"
                hx-get="{{ url_for('bom.grid', country=country, status=status, search=search, page=page+1) }}"
                hx-target="#grid-container">다음</button>
        {% endif %}
    </div>
</div>
```

```html
{# portal/templates/partials/_row.html #}
<tr id="row-{{ row.part_no }}-{{ row.row_num }}"
    hx-post="{{ url_for('bom.save_row', part_no=row.part_no, row_num=row.row_num, country=country) }}"
    hx-trigger="change" hx-target="this" hx-swap="outerHTML">
    <td>{{ "✅ 완료" if row.status_done else "⏳ 미입력" }}</td>
    <td>{{ row.part_no }}</td>
    <td>{{ row.part_name }}</td>
    <td>{{ "{:,.0f}".format(row.qty) }}</td>
    <td>
        <select name="currency" class="form-select form-select-sm">
            {% for c in ["KRW", "USD", "EUR"] %}
            <option value="{{ c }}" {{ "selected" if row.currency == c }}>{{ c }}</option>
            {% endfor %}
        </select>
    </td>
    <td><input type="text" name="unit_price_material" class="form-control form-control-sm" value="{{ row.unit_price_material }}"></td>
    <td>{{ "{:,.0f}".format(row.material_cost) }}</td>
    <td><input type="text" name="unit_price_logistics" class="form-control form-control-sm" value="{{ row.unit_price_logistics }}"></td>
    <td><input type="text" name="logistics_cost" class="form-control form-control-sm" value="{{ row.logistics_cost }}"></td>
    <td><input type="text" name="tariff_rate" class="form-control form-control-sm" value="{{ row.tariff_rate }}"></td>
    <td><input type="text" name="tariff_cost" class="form-control form-control-sm" value="{{ row.tariff_cost }}"></td>
    <td>{{ "{:,.0f}".format(row.total_cost) }}</td>
    <td><input type="text" name="mold_cost" class="form-control form-control-sm" value="{{ row.mold_cost }}"></td>
</tr>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bom_routes.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add portal/routes/bom_routes.py portal/templates/bom.html portal/templates/partials portal/tests/test_bom_routes.py
git commit -m "feat(portal): BOM grid with filter/pagination and HTMX inline edit"
```

---

### Task 7: 환율 위젯 (사이드바) + 다운로드

**Files:**
- Modify: `portal/routes/fx_routes.py` (stub 교체)
- Create: `portal/templates/partials/_fx_widget.html`
- Create: `portal/tests/test_fx_routes.py`

**Interfaces:**
- Consumes: `fx.get_latest_rate`, `fx.refresh_rates` (Task 1), `exporter.export_to_template` (Task 3)
- Produces: `GET /fx/widget` (HTMX 사이드바 위젯), `POST /fx/refresh` (수동 갱신), `GET /fx/download` (엑셀 다운로드) — 최종 소비 지점.

- [ ] **Step 1: Write the failing tests**

```python
# portal/tests/test_fx_routes.py
import fx

def login(client, admin_user):
    client.post("/login", data=admin_user)

def test_fx_widget_shows_not_secured_when_no_rates(client, admin_user):
    login(client, admin_user)
    resp = client.get("/fx/widget")
    assert resp.status_code == 200
    assert "미확보".encode() in resp.data

def test_fx_refresh_updates_rate_and_widget_reflects_it(client, admin_user, app, monkeypatch):
    login(client, admin_user)
    monkeypatch.setattr("fx.fetch_rates_from_api", lambda: {"USD": 1350.0, "EUR": 1450.0})
    resp = client.post("/fx/refresh")
    assert resp.status_code == 200
    assert b"1,350" in resp.data or b"1350" in resp.data

def test_download_requires_login(client):
    resp = client.get("/fx/download", follow_redirects=False)
    assert resp.status_code == 302

def test_download_returns_xlsx(client, admin_user, app):
    login(client, admin_user)
    resp = client.get("/fx/download")
    assert resp.status_code == 200
    assert resp.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fx_routes.py -v`
Expected: FAIL (`/fx/widget` returns empty string stub, `/fx/refresh` 404, `/fx/download` 404)

- [ ] **Step 3: Write implementation**

```python
# portal/routes/fx_routes.py
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
```

```html
{# portal/templates/partials/_fx_widget.html #}
<div class="portal-card fx-widget" style="margin: 0.75rem 0;">
    <div class="fw-semibold mb-1"><i class="bi bi-currency-exchange"></i> 환율</div>
    {% for currency, rate in rates.items() %}
    <div class="d-flex justify-content-between small">
        <span>{{ currency }}</span>
        <span>{{ "{:,.2f}".format(rate) if rate else "미확보" }}</span>
    </div>
    {% endfor %}
    <button class="btn btn-sm btn-outline-primary w-100 mt-2"
            hx-post="{{ url_for('fx.refresh') }}" hx-target="#fx-widget" hx-swap="innerHTML">
        수동 갱신
    </button>
    {% if message %}<div class="small text-muted mt-1">{{ message }}</div>{% endif %}
    <a class="btn btn-sm btn-primary w-100 mt-2" href="{{ url_for('fx.download') }}">
        <i class="bi bi-download"></i> 엑셀 다운로드
    </a>
</div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_fx_routes.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add portal/routes/fx_routes.py portal/templates/partials/_fx_widget.html portal/tests/test_fx_routes.py
git commit -m "feat(portal): fx rate widget with manual refresh and xlsx download"
```

---

### Task 8: `run.py` 로컬 실행 진입점 + 전체 테스트 스위트 확인

**Files:**
- Create: `portal/run.py`
- Test: 전체 스위트 재확인

**Interfaces:**
- Consumes: `app.create_app` (Task 4)
- Produces: 없음 (최종 실행 진입점)

- [ ] **Step 1: Write the failing test**

```python
# portal/tests/test_run.py
import runpy
import sys
from unittest.mock import patch

def test_run_module_calls_serve_and_opens_browser():
    with patch("waitress.serve") as mock_serve, patch("webbrowser.open") as mock_open:
        mock_serve.side_effect = KeyboardInterrupt  # stop the "serve forever" loop for the test
        try:
            runpy.run_module("run", run_name="__main__")
        except KeyboardInterrupt:
            pass
        assert mock_open.called
        assert mock_serve.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run'`

- [ ] **Step 3: Write implementation**

```python
# portal/run.py
import threading
import webbrowser
import waitress
from app import create_app

HOST = "127.0.0.1"
PORT = 5050

def _open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}/")

if __name__ == "__main__":
    app = create_app()
    threading.Timer(1.0, _open_browser).start()
    waitress.serve(app, host=HOST, port=PORT)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run.py -v`
Expected: PASS

Then run the full suite:

Run: `python -m pytest -v`
Expected: 전체 PASS (Task 1~8 누적 테스트 전부)

- [ ] **Step 5: Commit**

```bash
git add portal/run.py portal/tests/test_run.py
git commit -m "feat(portal): local run entrypoint with waitress + auto browser open"
```

---

### Task 9: 실제 BOM 파일 수동 브라우저 검증 (자동화 테스트 아님)

**Files:** 없음 (수동 검증)

- [ ] **Step 1**: `cd portal && python -m flask --app app:create_app create-admin admin <비밀번호>` 로 관리자 계정 생성
- [ ] **Step 2**: `python run.py` 실행 → 브라우저 자동 오픈 확인
- [ ] **Step 3**: 로그인 → 홈에서 `BOM 양식.xlsx`(`D:\재료비 관리 포탈 PJT\BOM 양식.xlsx`) 업로드 → KPI 카드 수치 갱신 확인
- [ ] **Step 4**: BOM 조회·입력 화면에서 국가/상태/검색 필터 동작 확인, 실제 중복 품번(74건 패턴) 행이 모두 별도로 보이는지 확인
- [ ] **Step 5**: 인라인 편집(재료비단가 입력) → 자동계산 반영 확인 → 페이지 새로고침 후 값 유지 확인
- [ ] **Step 6**: 환율 수동 갱신 버튼 → 위젯 값 갱신 확인
- [ ] **Step 7**: 엑셀 다운로드 → 원본 좌표에 값 채워졌는지 확인
- [ ] **Step 8**: 로그아웃 → 보호된 라우트 접근 시 로그인 페이지로 리다이렉트되는지 확인

이 태스크는 커밋 없음 — 문제 발견 시 이슈로 기록 후 별도 수정 태스크 진행.

---

## Self-Review Notes

- **Spec coverage**: 설계문서 2~6장 항목(아키텍처, 데이터모델 PK전환/users, UI 5개 화면, 에러처리 3종, 테스트계획) 모두 Task 1~9에 매핑됨. 7장 Out-of-Scope 항목(SUMMARY, 다중사용자, 권한분리 로직, 신규필드, PHASE2~5, 서버배포)은 의도적으로 미구현.
- **Placeholder scan**: 전 태스크 코드 블록 실제 동작 코드로 작성, "TODO"/"similar to" 없음.
- **Type consistency**: `db.get_part/get_purchase/list_purchase_for_part/upsert_purchase`에 `row_num` 인자 일관 적용, `calc.recalculate_purchase_row`도 동일 시그니처로 Task 3, 6에서 일치.
