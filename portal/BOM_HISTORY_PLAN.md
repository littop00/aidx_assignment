# BOM 조회/관리 서브메뉴 + 확정 BOM 이력 조회 기능

## Context

관리자가 BOM 초안을 "확정"(`admin.publish_draft` → `db.publish_bom_version`,
`db.py:496-508`)하면 기존 `published` 버전은 `status='archived'`로 내려가고
(499번째 줄 `UPDATE bom_versions SET status = 'archived' WHERE status = 'published'`),
대상 draft가 `published`로 승격되며 `published_at`이 찍힌다. 이 로직 자체는
정상 동작하고, 버전별 원가 데이터(`bom_parts`/`bom_purchase_data` 등)도 전부
`bom_id`로 분리 저장되어 archived가 되어도 유실되지 않는다.

문제는 **화면에서 과거 확정본(archived)을 볼 방법이 전혀 없다는 것**이다.
`bom.index`/`bom.grid`(`routes/bom_routes.py:112`, `:156`)는 항상
`db.get_active_bom_version(conn)` (= status='published' AND is_withdrawn=0
중 최신, `db.py:382-384`)만 조회하고, `admin_boms.html`도 draft 관리 폼뿐
과거 확정본 열람 링크가 없다. 그래서 확정할 때마다 이전 BOM이 사라진 것처럼
보여 "확정 기능이 제대로 작동 안 한다"는 오해가 생긴다.

이번 작업은 새 계산 로직 없이, 이미 존재하는 버전별 데이터를 **읽기 전용으로
열람**하는 화면을 추가하는 것이 핵심. 동시에 좌측 네비게이션 "BOM 조회" 항목을
"BOM 조회/관리"로 바꾸고 "현재 BOM" / "확정 BOM 이력" 서브 트리를 만든다
(admin, 일반 user 계정 모두 동일 노출 — 사용자 확정 선택).

## 변경 파일 목록

1. `templates/base_new.html` — 네비게이션 서브트리
2. `routes/bom_routes.py` — `history` 라우트 신설, `index`/`grid`/`_filtered_rows`에 `version_id`/`bom_id` 지원 추가
3. `templates/bom_history.html` — 신규 파일
4. `templates/bom.html` — 이력 열람 배너 + `version_id` 유지
5. `templates/partials/_grid.html` — 페이지네이션 링크에 `version_id` 유지 (누락 시 이력 열람 중 페이지 이동하면 현재 BOM으로 이탈함)

`my_bom.html`, `admin_boms.html`, `templates/partials/_row.html`, `db.py`는
수정하지 않음 (기존 `bom_id=None` 파라미터로 충분).

---

### 1. 네비게이션 서브트리 — `templates/base_new.html:39-43`

현재:
```html
<li>
  <a href="{{ url_for('bom.index') }}" class="flex items-center gap-3 px-4 py-3 rounded-xl font-medium {% if request.endpoint in ('bom.index', 'bom.grid', 'bom.summary') %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
    <i class="bi bi-table text-lg"></i> BOM 조회
  </a>
</li>
```

변경 후 (프로필 드롭다운의 `x-data`/`@click`/`@click.outside` 패턴 재사용,
기존 `<li>` 형제 스타일과 동일한 클래스 유지):
```html
<li x-data="{ open: {{ 'true' if request.endpoint in ('bom.index', 'bom.grid', 'bom.summary', 'bom.history') else 'false' }} }">
  <a href="#" @click.prevent="open = !open"
     class="flex items-center justify-between gap-3 px-4 py-3 rounded-xl font-medium cursor-pointer {% if request.endpoint in ('bom.index', 'bom.grid', 'bom.summary', 'bom.history') %}text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
    <span class="flex items-center gap-3"><i class="bi bi-table text-lg"></i> BOM 조회/관리</span>
    <i class="bi text-xs" :class="open ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
  </a>
  <ul x-show="open" x-cloak class="pl-8 mt-1 flex flex-col gap-1">
    <li>
      <a href="{{ url_for('bom.index') }}" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium {% if request.endpoint in ('bom.index', 'bom.grid', 'bom.summary') %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
        현재 BOM
      </a>
    </li>
    <li>
      <a href="{{ url_for('bom.history') }}" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium {% if request.endpoint == 'bom.history' %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
        확정 BOM 이력
      </a>
    </li>
  </ul>
</li>
```
비고: `open` 초기값을 Jinja 삼항으로 문자열 `'true'/'false'`를 만들어 Alpine에
넘긴다 (기존 프로필 드롭다운은 항상 `false` 시작이라 이런 패턴이 없었음 —
신규 도입). `x-cloak`은 `base_new.html:16`에 이미 `[x-cloak]{display:none!important}`
전역 스타일이 정의되어 있어 추가 CSS 불필요.

---

### 2. 확정 이력 목록 라우트 — `routes/bom_routes.py` (새 함수, `index()` 앞 또는 뒤 아무 곳)

```python
@bom_bp.route("/history")
@login_required
def history():
    conn = db.get_connection(current_app.config["DB_PATH"])
    versions = [v for v in db.list_bom_versions(conn) if v["status"] in ("published", "archived")]
    active = db.get_active_bom_version(conn)
    conn.close()
    return render_template("bom_history.html", versions=versions, active=active)
```
- `db.list_bom_versions`(`db.py:386-387`)는 전체 버전을 `version_no DESC`로
  반환 — draft는 필터링해서 제외 (사용자에게 미확정 초안을 보여줄 필요 없음).
- `active`가 `None`인 경우(현재 배포된 BOM이 전혀 없는 상태, 예: 관리자가
  withdraw만 하고 재배포 안 함) — 템플릿에서 모든 항목을 "과거 확정본"으로
  표시하면 됨 (아래 템플릿의 `v.id == active.id if active` 조건이 자연히 처리).

### 신규 템플릿 — `templates/bom_history.html`

`bom.html` 상단 카드 스타일(`bg-white rounded-2xl p-4 shadow-sm border-none`)을
그대로 재사용:
```html
{% extends "base_new.html" %}
{% block title %}확정 BOM 이력 | TMS Portal{% endblock %}
{% block page_title %}확정 BOM 이력{% endblock %}
{% block content %}
<div class="bg-white rounded-2xl p-4 shadow-sm border-none mb-4">
  <h1 class="text-xl font-bold text-[#1B2559]">확정 BOM 이력</h1>
  <p class="text-sm text-[#A3AED0] mt-1">관리자가 확정(배포)했던 BOM 버전 목록입니다. 과거 버전은 읽기 전용으로 조회할 수 있습니다.</p>
</div>
<div class="bg-white rounded-2xl shadow-sm border-none overflow-auto">
  <table class="table table-zebra align-middle text-[#1B2559]">
    <thead>
      <tr class="text-[#A3AED0] uppercase text-xs tracking-wider bg-gray-50">
        <th class="text-center">버전명</th>
        <th class="text-center">차종</th>
        <th class="text-center">Rev</th>
        <th class="text-center">확정일</th>
        <th class="text-center">상태</th>
        <th class="text-center">조회</th>
      </tr>
    </thead>
    <tbody>
      {% for v in versions %}
      <tr>
        <td class="text-center">{{ v.name }}</td>
        <td class="text-center">{{ v.vehicle or '-' }}</td>
        <td class="text-center">Rev.{{ v.version_no }}</td>
        <td class="text-center">{{ v.published_at or '-' }}</td>
        <td class="text-center">
          {% if active and v.id == active.id %}
          <span class="badge badge-lg rounded-lg font-semibold px-3 py-1 border-none bg-emerald-50 text-emerald-600">현재 사용중</span>
          {% else %}
          <span class="badge badge-lg rounded-lg font-semibold px-3 py-1 border-none bg-gray-100 text-[#A3AED0]">과거 확정본</span>
          {% endif %}
        </td>
        <td class="text-center">
          <a href="{{ url_for('bom.index', version_id=v.id) }}" class="btn btn-ghost btn-sm rounded-xl">조회</a>
        </td>
      </tr>
      {% else %}
      <tr><td colspan="6" class="text-center text-[#A3AED0] py-5">확정된 BOM 이력이 없습니다.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```
비고: 현재 사용중인 버전도 `bom.index?version_id=N`으로 조회 가능하게 두되,
`index()` 라우트에서 "target == active"면 `viewing_history=False`로 처리되어
평소 편집 화면(현재 BOM 화면과 동일)으로 보임 — 별도 분기 불필요 (3번 참고).

---

### 3. `bom.index` 에 `version_id` 지원 — `routes/bom_routes.py:112-132`

현재 코드:
```python
@bom_bp.route("/")
@login_required
def index():
    conn = db.get_connection(current_app.config["DB_PATH"])
    active_version = db.get_active_bom_version(conn)
    submission = db.get_or_create_submission(conn, active_version["id"], int(current_user.id)) if active_version else None
    suggestions = db.search_suggestions(conn)
    parts = db.list_parts(conn)
    latest_bom_upload = db.get_latest_bom_upload(conn)
    progress = db.submission_progress(conn, active_version["id"], int(current_user.id)) if active_version else {"done": 0, "total": 0, "percent": 0}
    overseas_countries = [c for c in db.list_bom_countries(conn, active_version["id"]) if c != "한국"] if active_version else []
    conn.close()
    category_counts = Counter(p["category"] for p in parts if p.get("category"))
    categories = sorted(category_counts)
    return render_template(
        "bom.html", countries=COUNTRIES, overseas_countries=overseas_countries, suggestions=suggestions,
        categories=categories, category_counts=category_counts,
        latest_bom_upload=latest_bom_upload, active_version=active_version, submission=submission,
        can_edit=current_user.role != "admin" and (submission and submission["status"] in ("draft", "returned")),
        progress=progress,
    )
```

변경 후:
```python
@bom_bp.route("/")
@login_required
def index():
    conn = db.get_connection(current_app.config["DB_PATH"])
    active_version = db.get_active_bom_version(conn)
    version_id = request.args.get("version_id", type=int)
    if version_id:
        view_version = db.get_bom_version(conn, version_id)
        if not view_version or view_version["status"] not in ("published", "archived"):
            conn.close()
            abort(404)
    else:
        view_version = active_version
    viewing_history = bool(view_version) and (not active_version or view_version["id"] != active_version["id"])

    submission = db.get_or_create_submission(conn, view_version["id"], int(current_user.id)) if view_version else None
    suggestions = db.search_suggestions(conn)
    parts = db.list_parts(conn, view_version["id"] if view_version else None)
    latest_bom_upload = db.get_latest_bom_upload(conn)
    progress = db.submission_progress(conn, view_version["id"], int(current_user.id)) if view_version else {"done": 0, "total": 0, "percent": 0}
    overseas_countries = [c for c in db.list_bom_countries(conn, view_version["id"]) if c != "한국"] if view_version else []
    conn.close()
    category_counts = Counter(p["category"] for p in parts if p.get("category"))
    categories = sorted(category_counts)
    return render_template(
        "bom.html", countries=COUNTRIES, overseas_countries=overseas_countries, suggestions=suggestions,
        categories=categories, category_counts=category_counts,
        latest_bom_upload=latest_bom_upload, active_version=view_version, submission=submission,
        can_edit=(not viewing_history) and current_user.role != "admin" and (submission and submission["status"] in ("draft", "returned")),
        progress=progress,
        viewing_history=viewing_history, view_version=view_version,
    )
```
핵심 변경점:
- `active_version` 변수는 "현재 배포본이 뭔지"를 판정하는 용도로만 남기고,
  템플릿에 실제로 넘기는 `active_version=view_version`은 지금까지처럼
  "화면에 그릴 대상 버전"의 의미를 그대로 유지 (템플릿 코드 최소 수정).
- `db.get_or_create_submission`을 **archived 버전에 대해서도 호출**하는 점에
  주의 — 이 함수가 없으면 새 submission row를 만들어버릴 수 있으므로, 과거
  버전 조회 시 부작용이 없는지 `db.py`의 `get_or_create_submission` 구현을
  구현 단계에서 반드시 재확인해야 함 (INSERT OR IGNORE 패턴이면 안전, 매번
  새로 만드는 방식이면 조회만 해도 DB에 레코드가 늘어나는 부작용 발생 가능).
- 존재하지 않는 `version_id`나 draft 버전을 가리키면 `abort(404)`.
- `active_version`이 아예 `None`이고 `version_id`도 없으면 `view_version=None`
  → 기존과 동일하게 "현재 사용할 수 있는 BOM이 없습니다" 빈 상태 노출
  (`bom.html:19`의 `{% else %}` 분기, 수정 불필요).

---

### 4. `bom.grid` 에 `version_id` 지원 — `routes/bom_routes.py:156-218`

현재 174번째 줄:
```python
configured_countries = [country for country in db.list_bom_countries(conn, active_version["id"] if active_version else None) if country != "한국"]
```
과 213-216번째 줄의 플래그 계산이 전부 `current_user.role`/`scope`만 보고
있어, 이력 열람 시에도 admin이면 `can_edit=True`, `scope=my_bom`이면 그룹/저장
버튼이 뜨는 문제가 있음 — 반드시 `viewing_history`로 강제 override해야 함.

변경 후 (핵심 부분만 발췌, 나머지 페이지네이션/합계 계산 로직은 그대로):
```python
@bom_bp.route("/grid")
@login_required
def grid():
    selected_countries = [country for country in request.args.getlist("country") if country]
    country = selected_countries[0] if selected_countries else "미국"
    status = request.args.get("status", "all")
    search = request.args.get("search", "")
    categories = request.args.getlist("category")
    assigned_only = request.args.get("assigned") == "1"
    scope = request.args.get("scope")
    version_id = request.args.get("version_id", type=int)
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", PAGE_SIZE))
    if page_size not in PAGE_SIZE_OPTIONS:
        page_size = PAGE_SIZE

    conn = db.get_connection(current_app.config["DB_PATH"])
    active_version = db.get_active_bom_version(conn)
    if version_id:
        target_version = db.get_bom_version(conn, version_id)
        if not target_version or target_version["status"] not in ("published", "archived"):
            conn.close()
            abort(404)
    else:
        target_version = active_version
    viewing_history = bool(target_version) and (not active_version or target_version["id"] != active_version["id"])

    submission = db.get_or_create_submission(conn, target_version["id"], int(current_user.id)) if target_version else None
    configured_countries = [country for country in db.list_bom_countries(conn, target_version["id"] if target_version else None) if country != "한국"]
    if current_user.role != "admin" or not selected_countries:
        selected_countries = configured_countries
    display_countries = ["한국"] + selected_countries
    input_user_id = None if current_user.role == "admin" else int(current_user.id)
    all_rows = _filtered_rows(conn, display_countries, status, search, categories, input_user_id, assigned_only, bom_id=target_version["id"] if target_version else None)
    overseas_countries = db.list_overseas_countries(conn)
    conn.close()

    total = len(all_rows)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    page_rows = all_rows[start:start + page_size]

    window_size = 5
    window_start = max(1, page - window_size // 2)
    window_end = min(total_pages, window_start + window_size - 1)
    window_start = max(1, window_end - window_size + 1)

    material_sum = sum(sum(r["country_data"][c]["material_cost"] for c in display_countries) for r in all_rows)
    logistics_sum = sum(sum(r["country_data"][c]["logistics_cost"] for c in selected_countries) for r in all_rows)
    total_sum = sum(sum(r["country_data"][c]["total_cost"] for c in display_countries) for r in all_rows)

    return render_template(
        "partials/_grid.html",
        rows=page_rows, country=country, status=status, search=search,
        page=page, total_pages=total_pages, total=total,
        page_size=page_size, page_size_options=PAGE_SIZE_OPTIONS,
        window_start=window_start, window_end=window_end,
        material_sum=material_sum, logistics_sum=logistics_sum, total_sum=total_sum,
        countries=overseas_countries,
        sourcing_countries=["KD", "LP", "MIP"],
        assembly_sourcing_options=["KD", "LP", "MIP"],
        design_field_labels=DESIGN_FIELD_LABELS,
        selected_countries=selected_countries,
        can_manage_countries=current_user.role == "admin" and not viewing_history,
        is_admin=current_user.role == "admin",
        can_edit=False if viewing_history else (True if current_user.role == "admin" else (scope == "my_bom" and submission and submission["status"] in ("draft", "returned"))),
        assignment_enabled=False if viewing_history else (current_user.role != "admin" and scope == "my_bom"),
        show_group_button=False if viewing_history else (current_user.role == "admin" or scope == "my_bom"),
        show_confirm_button=False if viewing_history else (current_user.role == "admin"),
        assigned_only=assigned_only,
        viewing_history=viewing_history,
        version_id=target_version["id"] if target_version else None,
    )
```
- `version_id=target_version["id"]`를 `_grid.html`에도 넘기는 이유: 페이지네이션
  링크(`url_for('bom.grid', page=p)`)가 `version_id`를 안 붙이면 페이지 이동
  시 현재 배포본으로 돌아가 버림 — 5번 항목에서 이 링크들에 `version_id`를
  추가해야 함.
- `can_manage_countries`도 이력 열람 중엔 꺼야 함 (원래 플랜에 누락되어 있었던
  부분 — `_grid.html`에서 이 플래그를 직접 쓰는 곳이 있는지 구현 단계에서
  재확인 필요, 현재 `_grid.html` 발췌본에는 등장하지 않지만 `bom.html`이나
  다른 partial에서 참조할 가능성 있음).

---

### 5. `_filtered_rows` 에 `bom_id` 스레딩 — `routes/bom_routes.py:61-110`

현재 시그니처/본문:
```python
def _filtered_rows(conn, countries, status, search, categories=None, user_id=None, assigned_only=False):
    primary_country = countries[0]
    parts = db.list_parts(conn)
    ...
    active = db.get_active_bom_version(conn)
    assigned_keys = db.assigned_part_keys(conn, active["id"], user_id) if active and user_id is not None else set()
    ...
        owner = db.category_owner(conn, active["id"], p.get("category")) if user_id is None and active else None
        ...
        purchase = db.get_user_purchase(conn, p["part_no"], p["row_num"], primary_country, effective_user_id) if effective_user_id else db.get_purchase(conn, p["part_no"], p["row_num"], primary_country)
        row = _build_row_view(p, purchase)
        ...
        group = db.group_for_part(conn, active["id"], p["part_no"], p["row_num"]) if active else None
        ...
        row["group_members"] = [
            m for m in (db.group_members(conn, active["id"], p["part_no"], p["row_num"]) if row["is_group_parent"] and active else [])
            ...
        ]
        ...
        row["country_data"] = {
            country: _build_row_view(p, db.get_user_purchase(conn, p["part_no"], p["row_num"], country, effective_user_id) if effective_user_id else db.get_purchase(conn, p["part_no"], p["row_num"], country))
            for country in countries
        }
```

변경 후 (모든 `active` 참조를 `bom_id` 파라미터 우선으로 교체 — `active`
지역변수 이름은 유지하되 의미를 "조회 대상 버전"으로 바꿈):
```python
def _filtered_rows(conn, countries, status, search, categories=None, user_id=None, assigned_only=False, bom_id=None):
    primary_country = countries[0]
    parts = db.list_parts(conn, bom_id)
    keyword = (search or "").strip().lower()
    categories = set(categories) if categories else None
    active = db.get_bom_version(conn, bom_id) if bom_id else db.get_active_bom_version(conn)
    assigned_keys = db.assigned_part_keys(conn, active["id"], user_id) if active and user_id is not None else set()
    rows = []
    for p in parts:
        is_assigned = (p["part_no"], p["row_num"]) in assigned_keys
        if assigned_only and not is_assigned:
            continue
        if categories and p.get("category") not in categories:
            continue
        if keyword and not any(
            keyword in (p.get(field) or "").lower()
            for field in ("part_no", "part_name", "category")
        ):
            continue
        owner = db.category_owner(conn, active["id"], p.get("category")) if user_id is None and active else None
        effective_user_id = user_id if user_id is not None else (owner["id"] if owner else None)
        purchase = db.get_user_purchase(conn, p["part_no"], p["row_num"], primary_country, effective_user_id, bom_id) if effective_user_id else db.get_purchase(conn, p["part_no"], p["row_num"], primary_country, bom_id)
        row = _build_row_view(p, purchase)
        row["target_user_id"] = owner["id"] if owner else None
        row["target_user_name"] = owner["username"] if owner else None
        group = db.group_for_part(conn, active["id"], p["part_no"], p["row_num"]) if active else None
        row["group"] = group
        row["is_group_parent"] = bool(group and group["parent_part_no"] == p["part_no"] and group["parent_row_num"] == p["row_num"])
        row["group_child"] = bool(group and not row["is_group_parent"])
        row["group_members"] = [
            m for m in (db.group_members(conn, active["id"], p["part_no"], p["row_num"]) if row["is_group_parent"] and active else [])
            if (m["part_no"], m["row_num"]) != (p["part_no"], p["row_num"])
        ]
        row["assigned"] = is_assigned
        row["country_data"] = {
            country: _build_row_view(p, db.get_user_purchase(conn, p["part_no"], p["row_num"], country, effective_user_id, bom_id) if effective_user_id else db.get_purchase(conn, p["part_no"], p["row_num"], country, bom_id))
            for country in countries
        }
        row["mip"] = any((row["country_data"][c].get("sourcing_part") or "").upper().startswith("MIP") for c in countries)
        row["status_done"] = all(
            row["country_data"][country]["unit_price_material"] not in (None, "")
            for country in countries
        )
        if status == "done" and not row["status_done"]:
            continue
        if status == "missing" and row["status_done"]:
            continue
        rows.append(row)
    return rows
```
주의: 원본 코드 94번째 줄에 있는 죽은 코드
`row["mip"] = any((row["country_data"].get(c, {}).get("sourcing_part") or "") == "MIP" for c in countries) if "country_data" in row else False`
는 바로 다음 100번째 줄에서 다시 덮어써지는 실질적 무의미 라인이다 —
이번 변경과 무관하므로 손대지 않고 그대로 둔다 (기존 동작 유지 원칙).

`db.list_parts(conn, bom_id)`, `db.get_bom_version(conn, bom_id)`,
`db.get_user_purchase(..., bom_id)`, `db.get_purchase(..., bom_id)`는 전부
기존 `db.py`에 이미 `bom_id=None` 파라미터로 구현되어 있음 — 새 DB 함수 불필요
(단, `db.category_owner`/`db.group_for_part`/`db.group_members`/
`db.assigned_part_keys`는 이미 `active["id"]`를 명시적 인자로 받고 있으므로
변경 불필요, 위 코드에서도 그대로 유지).

---

### 6. `bom.html` — 이력 열람 배너 + `version_id` 유지

파일 전체 구조(`templates/bom.html:1-131`)는 이미 확인 완료. 변경 지점:

**(a) 상단 카드 안, 4번째 줄 `<h1>` 바로 위에 배너 삽입** (5-16번째 줄 카드
블록 시작 직후):
```html
{% if viewing_history %}
<div class="alert bg-amber-50 text-amber-700 border-none rounded-2xl mb-4 flex items-center justify-between">
  <span><i class="bi bi-clock-history"></i> 과거 확정 BOM 이력 조회 중 — {{ view_version.name }} (Rev.{{ view_version.version_no }}) · 확정일 {{ view_version.published_at or '-' }} · 읽기 전용</span>
  <a href="{{ url_for('bom.index') }}" class="btn btn-sm btn-ghost rounded-xl font-semibold">현재 BOM으로 돌아가기</a>
</div>
{% endif %}
```

**(b) 17번째 줄 `{% if active_version %}` 필터 폼 안, `hx-get` 트리거 URL에
`version_id` 유지 필요.** 현재 필터 폼(`#filter-form`)은 `hx-get="{{ url_for('bom.grid') }}"`
로 고정되어 있고 각 select/input이 `hx-include`로 자기 자신의 값만 실어
보낸다. `version_id`는 사용자가 조작하는 필드가 아니므로, hidden input으로
추가해 `hx-include="#filter-form"`을 쓰는 모든 요소(검색창, 그리드 자체,
페이지네이션)가 자동으로 포함하게 한다:
```html
{% if viewing_history %}<input type="hidden" name="version_id" value="{{ view_version.id }}">{% endif %}
```
삽입 위치: `<form id="filter-form" ...>` 여는 태그 바로 다음 (기존 18번째
줄의 거대한 한 줄 HTML 안, `<div class="filter-group">...` 시작 전).

**(c) 18번째 줄 그리드 컨테이너 `hx-get`도 최초 로드시 `version_id`를 실어야
함** — 현재:
```html
<div id="grid-container" hx-get="{{ url_for('bom.grid') }}" hx-trigger="load" hx-include="#filter-form">
```
`hx-include="#filter-form"`이 이미 있으므로 (b)에서 hidden input을
`#filter-form` 안에 넣기만 하면 `hx-trigger="load"` 최초 요청에도 자동
포함됨 — 이 줄 자체는 수정 불필요. **단, hidden input을 form 태그 바깥에
두면 안 됨** (반드시 `<form id="filter-form">` 내부).

**(d) 22-23번째 줄 제출 버튼 스크립트** — `submit-bom-btn`은 이미
`my_bom.html` 쪽 화면에만 존재할 가능성이 높음(제출은 담당자 개인 작업이므로
`bom.html`에는 없을 수도 있음) — 구현 단계에서 실제로 `bom.html`에
`submit-bom-btn` 요소가 렌더링되는지 grep으로 재확인. 있다면
`{% if not viewing_history %}`로 감싸야 함.

---

### 7. `templates/partials/_grid.html` — 페이지네이션에 `version_id` 유지

`_grid.html:6`의 페이지네이션 링크 5곳(`first_url`/`prev_url`/`next_url`/
`last_url`/`window` 루프)이 전부 `url_for('bom.grid', page=N)`만 쓰고
있음 — `hx-include="#filter-form"`이 있으므로 (bom.html 6번 항목의 hidden
input 덕에) 실제 요청에는 `version_id`가 실려가지만, **`url_for`로 만든
`hx-get` 속성값 자체에는 없음** — htmx는 `hx-get` URL과 `hx-include`로 모은
폼 값을 쿼리스트링으로 병합하므로 이 자체는 문제 없음 (htmx 동작 특성상
`hx-include` 값이 GET 쿼리에 자동 추가됨). 따라서 **이 파일은 실제로는 수정
불필요** — 위 계획의 "5. 변경 파일 목록"에서 제외해도 됨. 단, 구현 단계에서
실제 htmx 버전(1.9.12) 동작으로 페이지네이션 클릭 시 `version_id`가 유지
되는지 반드시 수동 검증 (검증 절차 4-1 참고).

---

## 하지 않는 것

- `admin_boms.html`(BOM 관리자 페이지)은 건드리지 않음 — draft 관리 전용
  유지, 이력 열람은 새 `bom.history` 화면에서만 제공.
- `my_bom.html`은 건드리지 않음 — "내 BOM 관리"는 사용자 본인의 현재 담당
  작업 화면이므로 과거 버전 개념이 적용되지 않음.
- `save_row`/`set_assignment`/`set_selected_group`/`add_row`/`set_group`
  등 쓰기 라우트는 수정하지 않음 — 읽기 전용 강제는 프론트엔드 플래그
  (`can_edit`/`assignment_enabled`/`show_group_button`/`show_confirm_button`)
  만으로 충분하며, 설사 사용자가 URL을 직접 조작해 POST를 보내더라도 이
  라우트들은 전부 내부적으로 `db.get_active_bom_version(conn)`만 참조하므로
  구조적으로 archived 버전에는 쓸 수 없음 (추가 방어 코드 불필요).
- `is_confirmed`/`try_confirm_bom_version`(전원 승인시 자동 확정 플래그)은
  이번 요청과 무관한 별개 개념이므로 손대지 않음.
- `db.py`는 전혀 수정하지 않음 — 필요한 모든 함수가 이미 `bom_id=None`을
  지원.

## 리스크 / 확인 필요 사항 (구현 착수 전 재확인)

1. `db.get_or_create_submission`이 archived 버전 조회만으로 새 submission
   row를 생성하는 부작용이 있는지 (3번 항목 참고) — 있다면 이력 열람 시엔
   이 호출을 건너뛰고 `submission=None`으로 처리하는 방향으로 조정 필요.
2. `bom.html`에 `submit-bom-btn`이 실제로 존재하는지, `active_version`
   존재 여부로만 조건화된 다른 편집성 UI 요소가 더 있는지 재grep.
3. `_grid.html`에서 `can_manage_countries` 플래그를 실제로 사용하는 곳이
   있는지 (국가 추가/삭제 버튼 등) — 있다면 이력 열람 중 숨겨야 함.
4. htmx 페이지네이션이 `version_id` hidden input을 실제로 유지하며 쿼리에
   포함하는지 수동 클릭 테스트로 확인 (7번 항목 참고).

## 검증

1. `python -c "import ast; ast.parse(open('routes/bom_routes.py',encoding='utf-8').read())"` 로 문법 확인.
2. 서버 재시작 후 admin/user 계정으로 로그인 → 좌측 "BOM 조회/관리" 클릭 시
   서브메뉴 펼쳐지는지, "현재 BOM"/"확정 BOM 이력" 링크 동작 확인.
3. 관리자 계정에서 BOM 하나 확정(publish) → 다시 새 초안 업로드 후 재확정 →
   "확정 BOM 이력"에 두 개 버전(현재 사용중 / 과거 확정본)이 모두 나오는지 확인.
4. 과거 확정본 "조회" 클릭 →
   4-1. 그리드가 뜨되 모든 입력 필드 `disabled`, 툴바 버튼(일괄적용/그룹지정/
        담당품목저장/전체확정)이 전부 숨겨지는지 확인.
   4-2. 페이지 2로 이동 → 여전히 과거 버전 데이터가 보이는지 (현재 BOM으로
        안 튕기는지) 확인.
   4-3. 검색/필터 조작 후에도 과거 버전 컨텍스트 유지되는지 확인.
5. "현재 BOM으로 돌아가기" 클릭 시 정상적으로 활성 BOM 편집 화면으로 복귀
   하는지 확인.
6. 존재하지 않는 `version_id`(예: `/bom/?version_id=99999`)나 draft 상태
   버전의 id를 URL에 직접 넣었을 때 404가 뜨는지 확인.
7. 현재 배포된 BOM이 아예 없는 상태(withdraw 직후)에서 "확정 BOM 이력"
   페이지 진입 시 과거 확정본들이 전부 "과거 확정본"으로 표시되고 "현재
   사용중" 배지가 안 뜨는지 확인.
