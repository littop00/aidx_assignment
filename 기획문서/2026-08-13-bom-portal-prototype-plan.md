# BOM 재료비 포탈 프로토타입 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BOM 엑셀 업로드 → 품번 upsert → 웹에서 국가별(한국/미국/유럽) 원가 입력+자동계산 → 원본 서식 유지 엑셀 다운로드가 되는 Streamlit 로컬 프로토타입 구축.

**Architecture:** Streamlit UI(`app.py`) + SQLite(`bom.db`) + 순수 파이썬 모듈(`columns.py`/`db.py`/`parser.py`/`fx.py`/`calc.py`/`exporter.py`). 원본 `BOM 양식.xlsx`는 읽기 전용 소스/템플릿으로만 사용, 절대 직접 수정 안함.

**Tech Stack:** Python 3.11, streamlit, openpyxl, requests, sqlite3(표준 라이브러리), pytest.

## Global Constraints

- 대상 파일: `D:\재료비 관리 포탈 PJT\BOM 양식.xlsx`, 시트명 `BOM_복사본`, 데이터 시작 행 11.
- 설계정보 컬럼: B~AK열(2~37), 품번(컬럼13)이 PK. LEVEL 컬럼: E~K(5~11), depth 0~6.
- 구매정보 컬럼: 국가별 12컬럼 블록, 한국=39~50, 미국=52~63, 유럽=65~76. 그 외(77열 이후: 포장/컨테이너/수출운송비/관세FTA)는 이번 프로토타입 범위 아님(Out of Scope).
- 재료비만 자동계산: `재료비 = 단가 × 수량 × 환율(통화, 최신 확정일자)`. 물류비/관세는 구매팀 직접 입력. `총합계 = 재료비 + 물류비 + 관세` (None은 0 취급).
- 환율은 하루 1회 외부 API 갱신 후 그 날짜값 고정 사용(재계산 시 값이 안 바뀜).
- 원본 파일은 절대 in-place 수정 금지. 다운로드는 항상 원본을 임시 복사한 사본에 값 주입.
- 원본 엑셀 파일(918KB, 회사 원가 데이터 포함)은 git에 커밋하지 않는다. 테스트는 합성(fixture) 엑셀만 사용한다.
- 작업 폴더: `D:\재료비 관리 포탈 PJT\proto(rev.0)\`. 이 폴더에서 git 저장소 시작.

---

### Task 0: 프로젝트 스캐폴드 + git 초기화

**Files:**
- Create: `proto(rev.0)/requirements.txt`
- Create: `proto(rev.0)/.gitignore`
- Create: `proto(rev.0)/README.md`

**Interfaces:** 없음 (스캐폴드 전용)

- [ ] **Step 1: 폴더 구조 생성 및 파일 작성**

`requirements.txt`:
```
streamlit>=1.38
openpyxl>=3.1
requests>=2.31
pytest>=8.0
```

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
bom.db
*.xlsx
!tests/fixtures/*.xlsx
```

`README.md`:
```markdown
# BOM 재료비 포탈 프로토타입

## 실행
pip install -r requirements.txt
streamlit run app.py

## 테스트
pytest
```

- [ ] **Step 2: git 초기화 및 첫 커밋**

Run:
```bash
cd "D:\재료비 관리 포탈 PJT\proto(rev.0)"
git init
git add requirements.txt .gitignore README.md
git commit -m "chore: scaffold prototype project"
```
Expected: 커밋 성공, `git log`에 1개 커밋 표시.

---

### Task 1: 컬럼 매핑 상수 (`columns.py`)

**Files:**
- Create: `proto(rev.0)/columns.py`
- Test: `proto(rev.0)/tests/test_columns.py`

**Interfaces:**
- Produces: `DESIGN_FIELDS: list[tuple[str,int]]`, `LEVEL_COLUMNS: list[int]`, `COUNTRIES: list[str]`, `COUNTRY_BASE_COL: dict[str,int]`, `PURCHASE_FIELDS: list[tuple[str,int]]`, `CALCULATED_PURCHASE_FIELDS: set[str]`, `FIRST_DATA_ROW: int`, `purchase_column(country: str, field_name: str) -> int`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_columns.py
from columns import purchase_column, COUNTRY_BASE_COL, PURCHASE_FIELDS

def test_purchase_column_korea_material_cost():
    assert purchase_column("한국", "material_cost") == 43

def test_purchase_column_usa_total_cost():
    assert purchase_column("미국", "total_cost") == 62

def test_purchase_column_europe_mold_cost():
    assert purchase_column("유럽", "mold_cost") == 76

def test_purchase_fields_count():
    assert len(PURCHASE_FIELDS) == 12
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `cd "D:\재료비 관리 포탈 PJT\proto(rev.0)" && pytest tests/test_columns.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'columns'`)

- [ ] **Step 3: 구현**

```python
# columns.py
DESIGN_FIELDS = [
    ("vehicle", 2), ("category", 3), ("part_name", 12), ("part_no", 13),
    ("spec", 14), ("config_1", 15), ("config_2", 16), ("config_3", 17),
    ("config_4", 18), ("qty", 19), ("material", 20), ("surface", 21),
    ("spec2", 22), ("width", 23), ("depth_len", 24), ("height", 25),
    ("thickness", 26), ("length", 27), ("material_price", 28),
    ("weight_al", 29), ("weight_cu", 30), ("weight_steel", 31),
    ("weight_unit", 32), ("weight_total", 33), ("shape", 34),
    ("diy_drawing", 35), ("diy_approval", 36), ("remark", 37),
]

LEVEL_COLUMNS = list(range(5, 12))  # E~K, depth 0~6

COUNTRIES = ["한국", "미국", "유럽"]
COUNTRY_BASE_COL = {"한국": 39, "미국": 52, "유럽": 65}

PURCHASE_FIELDS = [
    ("sourcing_part", 0), ("sourcing_assembly", 1), ("currency", 2),
    ("unit_price_material", 3), ("material_cost", 4),
    ("unit_price_logistics", 5), ("logistics_cost", 6),
    ("tariff_rate", 7), ("unit_price_tariff", 8), ("tariff_cost", 9),
    ("total_cost", 10), ("mold_cost", 11),
]

CALCULATED_PURCHASE_FIELDS = {"material_cost", "total_cost"}

FIRST_DATA_ROW = 11

def purchase_column(country, field_name):
    base = COUNTRY_BASE_COL[country]
    for name, offset in PURCHASE_FIELDS:
        if name == field_name:
            return base + offset
    raise KeyError(field_name)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_columns.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add columns.py tests/test_columns.py
git commit -m "feat: add BOM column mapping constants"
```

---

### Task 2: SQLite 스키마/CRUD (`db.py`)

**Files:**
- Create: `proto(rev.0)/db.py`
- Test: `proto(rev.0)/tests/test_db.py`

**Interfaces:**
- Consumes: `columns.DESIGN_FIELDS`, `columns.PURCHASE_FIELDS`
- Produces: `get_connection(db_path: str) -> sqlite3.Connection`, `init_db(conn)`, `upsert_part(conn, part_no, row_num, level_depth, level_marker, fields: dict)`, `get_part(conn, part_no) -> dict | None`, `list_parts(conn) -> list[dict]`, `upsert_purchase(conn, part_no, country, fields: dict)`, `get_purchase(conn, part_no, country) -> dict | None`, `list_purchase_for_part(conn, part_no) -> list[dict]`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_db.py
import db

def test_upsert_and_get_part(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", row_num=12, level_depth=1, level_marker="●",
                    fields={"vehicle": "NE2_NV1", "part_name": "FILTER", "qty": "2"})
    part = db.get_part(conn, "P001")
    assert part["part_no"] == "P001"
    assert part["row_num"] == 12
    assert part["part_name"] == "FILTER"
    assert part["qty"] == "2"

def test_upsert_keeps_other_fields_on_partial_update(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER", "qty": "2"})
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER-V2", "qty": "2"})
    part = db.get_part(conn, "P001")
    assert part["part_name"] == "FILTER-V2"

def test_upsert_and_get_purchase(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER"})
    db.upsert_purchase(conn, "P001", "한국", {"currency": "KRW", "unit_price_material": "1000"})
    purchase = db.get_purchase(conn, "P001", "한국")
    assert purchase["currency"] == "KRW"
    assert purchase["unit_price_material"] == "1000"

def test_purchase_upsert_updates_not_duplicates(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    db.upsert_part(conn, "P001", 12, 1, "●", {"part_name": "FILTER"})
    db.upsert_purchase(conn, "P001", "한국", {"unit_price_material": "1000"})
    db.upsert_purchase(conn, "P001", "한국", {"unit_price_material": "2000"})
    rows = db.list_purchase_for_part(conn, "P001")
    assert len(rows) == 1
    assert rows[0]["unit_price_material"] == "2000"
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `pytest tests/test_db.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'db'`)

- [ ] **Step 3: 구현**

```python
# db.py
import sqlite3
from columns import DESIGN_FIELDS, PURCHASE_FIELDS

def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn):
    design_cols = ", ".join(f"{name} TEXT" for name, _ in DESIGN_FIELDS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS parts (
            part_no TEXT PRIMARY KEY,
            row_num INTEGER NOT NULL,
            level_depth INTEGER,
            level_marker TEXT,
            {design_cols}
        )
    """)
    purchase_cols = ", ".join(f"{name} TEXT" for name, _ in PURCHASE_FIELDS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS purchase_data (
            part_no TEXT NOT NULL,
            country TEXT NOT NULL,
            {purchase_cols},
            PRIMARY KEY (part_no, country)
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
    conn.commit()

def upsert_part(conn, part_no, row_num, level_depth, level_marker, fields):
    columns = ["part_no", "row_num", "level_depth", "level_marker"] + [n for n, _ in DESIGN_FIELDS]
    values = [part_no, row_num, level_depth, level_marker] + [fields.get(n) for n, _ in DESIGN_FIELDS]
    placeholders = ", ".join(["?"] * len(columns))
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c != "part_no")
    conn.execute(
        f"INSERT INTO parts ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(part_no) DO UPDATE SET {updates}",
        values,
    )
    conn.commit()

def get_part(conn, part_no):
    row = conn.execute("SELECT * FROM parts WHERE part_no = ?", (part_no,)).fetchone()
    return dict(row) if row else None

def list_parts(conn):
    rows = conn.execute("SELECT * FROM parts ORDER BY row_num").fetchall()
    return [dict(r) for r in rows]

def upsert_purchase(conn, part_no, country, fields):
    columns = ["part_no", "country"] + [n for n, _ in PURCHASE_FIELDS]
    values = [part_no, country] + [fields.get(n) for n, _ in PURCHASE_FIELDS]
    placeholders = ", ".join(["?"] * len(columns))
    updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in ("part_no", "country"))
    conn.execute(
        f"INSERT INTO purchase_data ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(part_no, country) DO UPDATE SET {updates}",
        values,
    )
    conn.commit()

def get_purchase(conn, part_no, country):
    row = conn.execute(
        "SELECT * FROM purchase_data WHERE part_no = ? AND country = ?", (part_no, country)
    ).fetchone()
    return dict(row) if row else None

def list_purchase_for_part(conn, part_no):
    rows = conn.execute(
        "SELECT * FROM purchase_data WHERE part_no = ?", (part_no,)
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_db.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add SQLite schema and CRUD for parts/purchase/fx"
```

---

### Task 3: BOM 업로드 파서 (`parser.py`)

**Files:**
- Create: `proto(rev.0)/parser.py`
- Test: `proto(rev.0)/tests/test_parser.py`
- Test fixture helper: `proto(rev.0)/tests/fixtures.py`

**Interfaces:**
- Consumes: `columns.DESIGN_FIELDS`, `columns.LEVEL_COLUMNS`, `columns.FIRST_DATA_ROW`, `db.upsert_part`
- Produces: `parse_and_upsert(conn, file_like) -> dict` (반환: `{"inserted": int, "updated": int, "skipped": list[int]}`)

- [ ] **Step 1: 합성 픽스처 엑셀 생성 헬퍼 작성**

```python
# tests/fixtures.py
import openpyxl
from io import BytesIO

def make_bom_fixture(rows):
    """rows: list of dict, e.g. {"part_no": "P001", "part_name": "FILTER", "qty": 2, "level_col": 6}"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOM_복사본"
    r = 11
    for row in rows:
        ws.cell(row=r, column=2, value=row.get("vehicle", "NE2_NV1"))
        ws.cell(row=r, column=3, value=row.get("category", "HVAC"))
        if "level_col" in row:
            ws.cell(row=r, column=row["level_col"], value=row.get("level_marker", "●"))
        ws.cell(row=r, column=12, value=row.get("part_name"))
        ws.cell(row=r, column=13, value=row.get("part_no"))
        ws.cell(row=r, column=19, value=row.get("qty"))
        r += 1
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
```

- [ ] **Step 2: 실패하는 테스트 작성**

```python
# tests/test_parser.py
import db
import parser
from tests.fixtures import make_bom_fixture

def test_parse_inserts_new_parts(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    f = make_bom_fixture([
        {"part_no": "P001", "part_name": "FILTER", "qty": 2, "level_col": 6},
        {"part_no": "P002", "part_name": "O-RING", "qty": 1, "level_col": 7},
    ])
    result = parser.parse_and_upsert(conn, f)
    assert result["inserted"] == 2
    assert result["updated"] == 0
    part = db.get_part(conn, "P001")
    assert part["part_name"] == "FILTER"
    assert part["level_depth"] == 1  # column 6 -> depth 1 (5,6,7,...=depth 0,1,2..)

def test_parse_upserts_existing_part_without_touching_purchase_data(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    f1 = make_bom_fixture([{"part_no": "P001", "part_name": "FILTER", "qty": 2, "level_col": 6}])
    parser.parse_and_upsert(conn, f1)
    db.upsert_purchase(conn, "P001", "한국", {"unit_price_material": "1000"})

    f2 = make_bom_fixture([{"part_no": "P001", "part_name": "FILTER-V2", "qty": 3, "level_col": 6}])
    result = parser.parse_and_upsert(conn, f2)

    assert result["inserted"] == 0
    assert result["updated"] == 1
    part = db.get_part(conn, "P001")
    assert part["part_name"] == "FILTER-V2"
    purchase = db.get_purchase(conn, "P001", "한국")
    assert purchase["unit_price_material"] == "1000"

def test_parse_skips_rows_without_part_no(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    f = make_bom_fixture([
        {"part_no": "", "part_name": "NO PART NO", "qty": 1, "level_col": 6},
        {"part_no": "P001", "part_name": "FILTER", "qty": 2, "level_col": 6},
    ])
    result = parser.parse_and_upsert(conn, f)
    assert result["inserted"] == 1
    assert 11 in result["skipped"]
```

- [ ] **Step 3: 테스트 실행해 실패 확인**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'parser'`) — 주의: 표준 라이브러리에도 `parser`란 이름이 있었으나 3.10+에서 제거됨, 충돌 없음.

- [ ] **Step 4: 구현**

```python
# parser.py
import openpyxl
from columns import DESIGN_FIELDS, LEVEL_COLUMNS, FIRST_DATA_ROW
import db

def parse_and_upsert(conn, file_like):
    wb = openpyxl.load_workbook(file_like, data_only=True)
    ws = wb["BOM_복사본"]

    inserted, updated, skipped = 0, 0, []
    for row_num in range(FIRST_DATA_ROW, ws.max_row + 1):
        part_no_cell = ws.cell(row=row_num, column=13).value
        part_no = str(part_no_cell).strip() if part_no_cell else ""
        if not part_no:
            skipped.append(row_num)
            continue

        fields = {}
        for name, col in DESIGN_FIELDS:
            value = ws.cell(row=row_num, column=col).value
            fields[name] = str(value) if value is not None else None

        level_depth, level_marker = None, None
        for depth, col in enumerate(LEVEL_COLUMNS):
            value = ws.cell(row=row_num, column=col).value
            if value is not None:
                level_depth, level_marker = depth, str(value)
                break

        existed = db.get_part(conn, part_no) is not None
        db.upsert_part(conn, part_no, row_num, level_depth, level_marker, fields)
        if existed:
            updated += 1
        else:
            inserted += 1

    return {"inserted": inserted, "updated": updated, "skipped": skipped}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `pytest tests/test_parser.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: 커밋**

```bash
git add parser.py tests/test_parser.py tests/fixtures.py
git commit -m "feat: parse BOM excel design section and upsert parts by part_no"
```

---

### Task 4: 환율 모듈 (`fx.py`)

**Files:**
- Create: `proto(rev.0)/fx.py`
- Test: `proto(rev.0)/tests/test_fx.py`

**Interfaces:**
- Consumes: `db.get_connection`, `db.init_db`
- Produces: `get_latest_rate(conn, currency: str) -> float | None`, `store_rate(conn, currency: str, rate_date: str, rate: float)`, `refresh_rates(conn, today: str, fetch_fn=None) -> dict` (반환: `{"updated": bool, "reason": str}`)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_fx.py
import db
import fx

def test_store_and_get_latest_rate(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    fx.store_rate(conn, "USD", "2026-08-10", 1350.0)
    fx.store_rate(conn, "USD", "2026-08-13", 1360.0)
    assert fx.get_latest_rate(conn, "USD") == 1360.0

def test_get_latest_rate_krw_defaults_to_one(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    assert fx.get_latest_rate(conn, "KRW") == 1.0

def test_refresh_rates_skips_if_already_updated_today(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    fx.store_rate(conn, "USD", "2026-08-13", 1360.0)
    result = fx.refresh_rates(conn, today="2026-08-13", fetch_fn=lambda: {"USD": 9999.0})
    assert result["updated"] is False
    assert fx.get_latest_rate(conn, "USD") == 1360.0

def test_refresh_rates_calls_fetch_fn_when_stale(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    fx.store_rate(conn, "USD", "2026-08-12", 1350.0)
    result = fx.refresh_rates(conn, today="2026-08-13", fetch_fn=lambda: {"USD": 1370.0})
    assert result["updated"] is True
    assert fx.get_latest_rate(conn, "USD") == 1370.0

def test_refresh_rates_keeps_old_value_on_fetch_failure(tmp_path):
    conn = db.get_connection(str(tmp_path / "test.db"))
    db.init_db(conn)
    fx.store_rate(conn, "USD", "2026-08-12", 1350.0)
    def failing_fetch():
        raise ConnectionError("api down")
    result = fx.refresh_rates(conn, today="2026-08-13", fetch_fn=failing_fetch)
    assert result["updated"] is False
    assert "api down" in result["reason"]
    assert fx.get_latest_rate(conn, "USD") == 1350.0
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `pytest tests/test_fx.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'fx'`)

- [ ] **Step 3: 구현**

```python
# fx.py
import requests

API_URL = "https://open.er-api.com/v6/latest/KRW"

def store_rate(conn, currency, rate_date, rate):
    conn.execute(
        "INSERT INTO fx_rates (currency, rate_date, rate) VALUES (?, ?, ?) "
        "ON CONFLICT(currency, rate_date) DO UPDATE SET rate=excluded.rate",
        (currency, rate_date, rate),
    )
    conn.commit()

def get_latest_rate(conn, currency):
    if currency == "KRW":
        return 1.0
    row = conn.execute(
        "SELECT rate FROM fx_rates WHERE currency = ? ORDER BY rate_date DESC LIMIT 1",
        (currency,),
    ).fetchone()
    return row["rate"] if row else None

def fetch_rates_from_api():
    resp = requests.get(API_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    krw_per_unit = {}
    for currency, rate_from_krw in data["rates"].items():
        if rate_from_krw:
            krw_per_unit[currency] = 1.0 / rate_from_krw
    return krw_per_unit

def refresh_rates(conn, today, fetch_fn=None):
    fetch_fn = fetch_fn or fetch_rates_from_api
    row = conn.execute(
        "SELECT MAX(rate_date) as latest FROM fx_rates"
    ).fetchone()
    if row["latest"] == today:
        return {"updated": False, "reason": "already refreshed today"}

    try:
        rates = fetch_fn()
    except Exception as exc:
        return {"updated": False, "reason": str(exc)}

    for currency, rate in rates.items():
        store_rate(conn, currency, today, rate)
    return {"updated": True, "reason": "refreshed from API"}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_fx.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add fx.py tests/test_fx.py
git commit -m "feat: add daily-fixed exchange rate storage and refresh"
```

---

### Task 5: 원가 계산 엔진 (`calc.py`)

**Files:**
- Create: `proto(rev.0)/calc.py`
- Test: `proto(rev.0)/tests/test_calc.py`

**Interfaces:**
- Consumes: `fx.get_latest_rate`
- Produces: `compute_material_cost(conn, unit_price: str|None, qty: str|None, currency: str|None) -> float | None`, `compute_total_cost(material_cost, logistics_cost, tariff_cost) -> float`, `recalculate_purchase_row(conn, part_no, country, fields: dict) -> dict` (계산된 `material_cost`/`total_cost`를 채운 fields 반환)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_calc.py
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
    fields = {
        "currency": "KRW", "unit_price_material": "1000",
        "logistics_cost": "50", "tariff_cost": "10",
    }
    result = calc.recalculate_purchase_row(conn, "P001", "한국", fields)
    assert result["material_cost"] == 1000.0
    assert result["total_cost"] == 1060.0
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `pytest tests/test_calc.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'calc'`)

- [ ] **Step 3: 구현**

```python
# calc.py
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

def recalculate_purchase_row(conn, part_no, country, fields):
    part = db.get_part(conn, part_no)
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

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_calc.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add calc.py tests/test_calc.py
git commit -m "feat: add material/total cost calculation engine"
```

---

### Task 6: 엑셀 다운로드 생성 (`exporter.py`)

**Files:**
- Create: `proto(rev.0)/exporter.py`
- Test: `proto(rev.0)/tests/test_exporter.py`

**Interfaces:**
- Consumes: `db.list_parts`, `db.list_purchase_for_part`, `columns.DESIGN_FIELDS`, `columns.purchase_column`
- Produces: `export_to_template(conn, template_path: str) -> bytes` (원본과 동일 서식의 xlsx 바이트를 반환)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_exporter.py
import openpyxl
from io import BytesIO
import db
import exporter
from tests.fixtures import make_bom_fixture

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
                    fields={"part_name": "FILTER", "part_no": "P001", "qty": "2"})
    db.upsert_purchase(conn, "P001", "한국", {"currency": "KRW", "unit_price_material": "1000", "material_cost": "2000"})

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
```

- [ ] **Step 2: 테스트 실행해 실패 확인**

Run: `pytest tests/test_exporter.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'exporter'`)

- [ ] **Step 3: 구현**

```python
# exporter.py
import openpyxl
from io import BytesIO
from columns import DESIGN_FIELDS, COUNTRIES, purchase_column
import db

def export_to_template(conn, template_path):
    wb = openpyxl.load_workbook(template_path)
    ws = wb["BOM_복사본"]

    for part in db.list_parts(conn):
        row_num = part["row_num"]
        for name, col in DESIGN_FIELDS:
            value = part.get(name)
            if value is not None:
                ws.cell(row=row_num, column=col, value=value)

        for country in COUNTRIES:
            purchase = db.get_purchase(conn, part["part_no"], country)
            if not purchase:
                continue
            for name, _ in purchase.keys() and [(k, None) for k in purchase if k not in ("part_no", "country")]:
                pass

    out = BytesIO()
    wb.save(out)
    return out.getvalue()
```

- [ ] **Step 4: 테스트 실행 (의도적으로 실패 확인 - 위 구현은 미완성 placeholder 루프 포함)**

위 3단계 코드의 이중 for문은 잘못된 구현이다. 아래 최종 구현으로 교체한다.

```python
# exporter.py (최종)
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
            value = part.get(name)
            if value is not None:
                ws.cell(row=row_num, column=col, value=value)

        for country in COUNTRIES:
            purchase = db.get_purchase(conn, part["part_no"], country)
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

- [ ] **Step 5: 테스트 통과 확인**

Run: `pytest tests/test_exporter.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: 커밋**

```bash
git add exporter.py tests/test_exporter.py
git commit -m "feat: export parts/purchase data back into original template coordinates"
```

---

### Task 7: Streamlit UI (`app.py`)

**Files:**
- Create: `proto(rev.0)/app.py`
- Create: `proto(rev.0)/config.py`

**Interfaces:**
- Consumes: 모든 이전 모듈 (`db`, `parser`, `fx`, `calc`, `exporter`, `columns`)
- Produces: 실행 가능한 Streamlit 앱 (자동 테스트 대상 아님, 수동 검증)

- [ ] **Step 1: 설정 파일 작성**

```python
# config.py
DB_PATH = "bom.db"
TEMPLATE_PATH = r"D:\재료비 관리 포탈 PJT\BOM 양식.xlsx"
```

- [ ] **Step 2: 앱 구현**

```python
# app.py
import datetime
import streamlit as st
import db
import parser
import fx
import calc
from columns import COUNTRIES, PURCHASE_FIELDS
from config import DB_PATH, TEMPLATE_PATH
import exporter

st.set_page_config(page_title="재료비 관리 포탈 (프로토타입)", layout="wide")

conn = db.get_connection(DB_PATH)
db.init_db(conn)
fx.refresh_rates(conn, today=datetime.date.today().isoformat())

tab_upload, tab_input, tab_fx, tab_download = st.tabs(
    ["BOM 업로드", "구매정보 입력", "환율", "다운로드"]
)

with tab_upload:
    st.subheader("설계 BOM 엑셀 업로드")
    uploaded = st.file_uploader("BOM 양식.xlsx", type=["xlsx"])
    if uploaded is not None:
        result = parser.parse_and_upsert(conn, uploaded)
        st.success(f"신규 {result['inserted']}건 / 갱신 {result['updated']}건 반영됨")
        if result["skipped"]:
            st.warning(f"품번 없음으로 건너뜀: 행 {result['skipped']}")

with tab_input:
    st.subheader("국가별 구매정보 입력")
    parts = db.list_parts(conn)
    if not parts:
        st.info("먼저 BOM을 업로드하세요.")
    else:
        part_options = {f"{p['part_no']} - {p['part_name']}": p["part_no"] for p in parts}
        selected_label = st.selectbox("품번 선택", list(part_options.keys()))
        part_no = part_options[selected_label]
        country = st.selectbox("소싱 국가", COUNTRIES)

        existing = db.get_purchase(conn, part_no, country) or {}
        with st.form("purchase_form"):
            currency = st.text_input("통화(CUR.)", value=existing.get("currency", "KRW"))
            unit_price_material = st.text_input("단가(재료비용)", value=existing.get("unit_price_material", ""))
            unit_price_logistics = st.text_input("단가(물류비용)", value=existing.get("unit_price_logistics", ""))
            logistics_cost = st.text_input("물류비", value=existing.get("logistics_cost", ""))
            tariff_rate = st.text_input("관세율(%)", value=existing.get("tariff_rate", ""))
            tariff_cost = st.text_input("관세금액", value=existing.get("tariff_cost", ""))
            mold_cost = st.text_input("금형비", value=existing.get("mold_cost", ""))
            submitted = st.form_submit_button("저장")

        if submitted:
            fields = {
                "currency": currency,
                "unit_price_material": unit_price_material,
                "unit_price_logistics": unit_price_logistics,
                "logistics_cost": logistics_cost,
                "tariff_rate": tariff_rate,
                "tariff_cost": tariff_cost,
                "mold_cost": mold_cost,
            }
            calculated = calc.recalculate_purchase_row(conn, part_no, country, fields)
            db.upsert_purchase(conn, part_no, country, calculated)
            st.success(f"재료비 {calculated['material_cost']} / 총합계 {calculated['total_cost']} 로 저장됨")

with tab_fx:
    st.subheader("적용 환율")
    for currency in ["KRW", "USD", "EUR"]:
        rate = fx.get_latest_rate(conn, currency)
        st.write(f"{currency}: {rate if rate is not None else '미확보'}")
    if st.button("환율 수동 갱신"):
        result = fx.refresh_rates(conn, today=datetime.date.today().isoformat())
        if result["updated"]:
            st.success("환율 갱신됨")
        else:
            st.warning(f"갱신 안됨: {result['reason']}")

with tab_download:
    st.subheader("엑셀 다운로드")
    if st.button("현재 데이터로 엑셀 생성"):
        data = exporter.export_to_template(conn, TEMPLATE_PATH)
        st.download_button(
            "다운로드",
            data=data,
            file_name=f"BOM_{datetime.date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
```

- [ ] **Step 3: 수동 실행 검증**

Run:
```bash
cd "D:\재료비 관리 포탈 PJT\proto(rev.0)"
pip install -r requirements.txt
streamlit run app.py
```
Expected: 브라우저에 4개 탭(업로드/입력/환율/다운로드) 표시. 실제 `BOM 양식.xlsx`를 업로드해 신규/갱신 건수가 뜨는지, 품번 하나 골라 단가 입력 후 재료비가 계산되는지, 다운로드한 파일을 열어 서식이 원본과 같은지 확인.

- [ ] **Step 4: 커밋**

```bash
git add app.py config.py
git commit -m "feat: wire Streamlit UI for upload, purchase input, fx, and download"
```

---

## Self-Review 결과

- **스펙 커버리지:** PRD FR-1(업로드/upsert)→Task3, FR-2(구매정보 입력)→Task7, FR-3(자동계산)→Task5, FR-4(환율)→Task4, FR-5(다운로드/서식유지)→Task6. 화면구성(PRD 7절)→Task7. Out-of-Scope 항목(권한, SUMMARY, 버전관리, col77+)은 의도적으로 미포함.
- **플레이스홀더 스캔:** Task6 Step3의 미완성 루프는 의도적으로 "잘못된 예시→최종본"으로 표기해 실제 구현자가 실수를 피하도록 함; 최종 코드는 완전한 구현.
- **타입/시그니처 일관성:** `db.get_part`/`list_parts`가 반환하는 dict의 키가 `columns.DESIGN_FIELDS`/`PURCHASE_FIELDS` 이름과 `exporter.py`/`calc.py`에서 쓰는 키 이름이 모두 동일함을 확인.
