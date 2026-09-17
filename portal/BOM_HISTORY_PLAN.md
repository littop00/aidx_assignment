# BOM 조회/관리 서브메뉴 + 확정 BOM 이력 조회 기능

## Context

관리자가 BOM 초안을 "확정"(`admin.publish_draft`)하면 `bom_versions.status`가
`draft → published`로 바뀌고, 기존 `published` 버전은 `archived`로 보관 처리된다
(`db.py:496-499 publish_bom_version`). 이 로직 자체는 정상 동작하고 있고,
버전별 원가 데이터도 `bom_parts`/`bom_purchase_data`에 `bom_id`로 완전히
분리 저장되어 유실되지 않는다.

문제는 **화면에서 과거 확정본을 볼 방법이 전혀 없다는 것**이다. `bom.index`/
`bom.grid`는 항상 `db.get_active_bom_version()` (가장 최근 published)만 조회하고,
`admin_boms.html`(BOM 관리자 페이지)도 draft 관리 폼만 있을 뿐 지난 확정본을
열람하는 링크가 없다. 그래서 사용자 입장에서는 "확정하고 나면 이전 BOM이
사라진 것처럼" 보여 "확정 기능이 제대로 작동 안 한다"는 오해가 생긴다.

이번 작업은 새 계산 로직 없이, 이미 존재하는 버전별 데이터를 **읽기 전용으로
열람**할 수 있는 화면을 추가하는 것이 핵심이다. 동시에 좌측 네비게이션의
"BOM 조회" 항목을 "BOM 조회/관리"로 바꾸고, 그 아래에 "현재 BOM" / "확정 BOM
이력" 서브 트리를 만든다 (admin, 일반 user 계정 모두 동일하게 노출).

## 변경 대상 및 접근 방식

### 1. 네비게이션 서브트리 — `templates/base_new.html` (약 39-43번째 줄)

기존 단일 `<li><a href="{{ url_for('bom.index') }}">BOM 조회</a></li>` 항목을
Alpine `x-data="{open: ...}"` 기반 접이식 부모 메뉴로 교체. 사이드바에 이런
패턴이 아직 없으므로 새로 도입하되, 기존 프로필 드롭다운(76번째 줄 부근)의
`x-data`/`@click`/`@click.outside` 스타일을 그대로 재사용:

```html
<li x-data="{open: request.endpoint in ('bom.index','bom.grid','bom.history')}">
  <a href="#" @click.prevent="open = !open"
     class="flex items-center justify-between gap-3 px-4 py-3 rounded-xl font-medium ...">
    <span class="flex items-center gap-3"><i class="bi bi-table text-lg"></i> BOM 조회/관리</span>
    <i class="bi text-xs" :class="open ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
  </a>
  <ul x-show="open" x-cloak class="pl-8 mt-1 flex flex-col gap-1">
    <li><a href="{{ url_for('bom.index') }}" class="... {% if request.endpoint=='bom.index' %}active{% endif %}">현재 BOM</a></li>
    <li><a href="{{ url_for('bom.history') }}" class="... {% if request.endpoint=='bom.history' %}active{% endif %}">확정 BOM 이력</a></li>
  </ul>
</li>
```

(정확한 Tailwind 클래스는 기존 nav 항목 스타일과 동일하게 맞춘다.) `bom.grid`
활성화 판정은 부모 `open` 초기값에만 관여하고, 하이라이트는 `bom.index`/
`bom.history` 두 자식 링크에서 처리한다.

### 2. 확정 이력 목록 라우트 — `routes/bom_routes.py`

새 라우트 추가 (admin 전용 아님, 로그인만 필요):

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

`db.list_bom_versions`(이미 존재, `db.py:386`)는 전체 버전을 최신순으로 반환하므로
그대로 재사용. 새 템플릿 `templates/bom_history.html` (`bom.html`의 상단 카드
스타일을 참고해 최소 구성): 표 형태로 버전명 / 차종 / Rev / 확정일
(`published_at`) / 상태(현재 사용중 = `active` id와 일치 / 과거 확정본) /
"조회" 링크 `{{ url_for('bom.index', version_id=v.id) }}`.

### 3. `bom.index` 에 `version_id` 지원 — `routes/bom_routes.py:112-132`

```python
@bom_bp.route("/")
@login_required
def index():
    conn = db.get_connection(current_app.config["DB_PATH"])
    version_id = request.args.get("version_id", type=int)
    active_version = db.get_active_bom_version(conn)
    if version_id:
        target = db.get_bom_version(conn, version_id)
        if not target or target["status"] not in ("published", "archived"):
            conn.close()
            abort(404)
        view_version = target
        viewing_history = target["id"] != (active_version["id"] if active_version else None)
    else:
        view_version = active_version
        viewing_history = False
    ...
    can_edit = (not viewing_history) and current_user.role != "admin" and (submission and submission["status"] in ("draft", "returned"))
```

`submission`/`progress`/`overseas_countries`는 기존처럼 `view_version["id"]`
기준으로 계산 (active_version 대신 view_version 사용). 템플릿에는
`viewing_history=viewing_history`, `view_version=view_version`을 추가로 전달.

### 4. `bom.grid` 에 동일하게 `version_id` 지원 — `routes/bom_routes.py:156-218`

- `version_id = request.args.get("version_id", type=int)` 파싱.
- `version_id`가 있으면 `db.get_bom_version`으로 검증(없거나 draft면 400/404),
  이후 `active_version`을 이 조회 대상으로 취급 (`target_version`).
- `_filtered_rows(conn, display_countries, status, search, categories, input_user_id, assigned_only, bom_id=target_version["id"])`
  — `_filtered_rows` 시그니처에 `bom_id=None` 파라미터 추가 (아래 5번).
- 과거 이력 열람 시 강제로 읽기 전용/툴바 숨김:
  ```python
  viewing_history = version_id and (not active_version or version_id != active_version["id"])
  can_edit = False if viewing_history else (True if current_user.role == "admin" else ...)
  assignment_enabled = False if viewing_history else (...)
  show_group_button = False if viewing_history else (...)
  show_confirm_button = False if viewing_history else (...)
  ```
  `_grid.html`의 툴바 버튼/행 편집 가능 여부는 전부 이 네 플래그로만
  분기하므로 (`templates/partials/_grid.html:3`, `templates/partials/_row.html:3`
  의 `row_editable`), 이 플래그들만 끄면 별도 저장 라우트(`save_row`,
  `set_assignment` 등) 수정 없이 안전하게 읽기 전용이 된다.

### 5. `_filtered_rows` 에 `bom_id` 스레딩 — `routes/bom_routes.py:61-110`

```python
def _filtered_rows(conn, countries, status, search, categories=None, user_id=None, assigned_only=False, bom_id=None):
    ...
    parts = db.list_parts(conn, bom_id)
    active = db.get_bom_version(conn, bom_id) if bom_id else db.get_active_bom_version(conn)
    ...
    purchase = db.get_user_purchase(conn, p["part_no"], p["row_num"], primary_country, effective_user_id, bom_id) if effective_user_id else db.get_purchase(conn, p["part_no"], p["row_num"], primary_country, bom_id)
    ...
    row["country_data"] = {
        country: _build_row_view(p, db.get_user_purchase(conn, p["part_no"], p["row_num"], country, effective_user_id, bom_id) if effective_user_id else db.get_purchase(conn, p["part_no"], p["row_num"], country, bom_id))
        for country in countries
    }
```
(`db.get_purchase`/`get_user_purchase`/`list_parts`/`category_owner`/
`group_for_part`/`group_members`/`assigned_part_keys`는 이미 전부 `bom_id`
파라미터를 받으므로 새 DB 함수는 필요 없음.)

### 6. `bom.html` — 이력 열람 배너 + `version_id` 유지

- 상단에 `{% if viewing_history %}` 배너 추가: "과거 확정 BOM 이력 조회 중:
  {{ view_version.name }} (Rev.{{ view_version.version_no }}) · 확정일
  {{ view_version.published_at }} · 읽기 전용" + "현재 BOM으로 돌아가기"
  링크(`bom.index`, 파라미터 없이).
- `#filter-form`에 `version_id`가 있으면 hidden input으로 추가해서
  `hx-get`으로 페이지네이션/필터 변경 시에도 계속 같은 과거 버전을 조회하게
  유지 (기존 `input-country` hidden input과 같은 패턴).
- `viewing_history`일 때는 "관리자 제출"/BOM 행 추가 등 편집성 버튼도 숨김
  (이미 `can_edit`/`active_version` 조건에 걸려 있는 것들은 자동으로 숨겨짐,
  버튼이 `active_version` 존재 여부로만 조건화된 경우만 추가로
  `not viewing_history` 조건 보강).

## 하지 않는 것

- `admin_boms.html`(BOM 관리자 페이지)은 건드리지 않음 — draft 관리 전용으로
  유지, 이력 열람은 새 `bom.history` 화면에서만 제공.
- `save_row`/`set_assignment`/`set_selected_group` 등 쓰기 라우트는 수정하지
  않음 — 읽기 전용 강제는 프론트엔드 플래그(4번)만으로 충분.
- `is_confirmed`/`try_confirm_bom_version` (전원 승인시 자동 확정 플래그)은
  이번 요청과 무관한 별개 개념이므로 손대지 않음.

## 검증

1. `python -c "import ast; ast.parse(open('routes/bom_routes.py',encoding='utf-8').read())"` 로 문법 확인.
2. 서버 재시작 후 admin/user 계정으로 로그인 → 좌측 "BOM 조회/관리" 클릭 시
   서브메뉴 펼쳐지는지, "현재 BOM"/"확정 BOM 이력" 링크 동작 확인.
3. 관리자 계정에서 BOM 하나 확정(publish) → 다시 새 초안 업로드 후 재확정 →
   "확정 BOM 이력"에 두 개 버전(현재 사용중 / 과거 확정본)이 모두 나오는지 확인.
4. 과거 확정본 "조회" 클릭 → 그리드가 뜨되 모든 입력 필드 `disabled`, 툴바
   버튼(일괄적용/그룹지정/담당품목저장/전체확정)이 전부 숨겨지는지 확인.
5. "현재 BOM으로 돌아가기" 클릭 시 정상적으로 활성 BOM 편집 화면으로 복귀하는지 확인.
