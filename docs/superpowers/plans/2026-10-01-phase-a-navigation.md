# Phase A — Navigation/Tab Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the portal's sidebar navigation to the target tree from `portal/PHASE2_PLAN.md` (Phase A section) by exposing the orphaned "재료비 Summary" route, adding placeholder pages for the not-yet-built "차종별 협력사 현황" dashboard and "입찰 BOM" tab, and reorganizing the sidebar accordion structure to match.

**Architecture:** Flask blueprints (`home`, `bom`, new `bid_bom`), server-rendered Jinja2 templates extending `base_new.html`, Alpine.js for accordion open/close state (existing pattern, reused as-is), htmx for the "재료비 Summary" page body (reuses the existing `bom.summary` fragment endpoint unmodified). No database schema changes. No changes to existing route business logic — this phase is purely additive routes + one template restructure.

**Judgment call (per "알아서 하셈"):** The target tree nests "BOM 조회" and "수주 재료비 입력" as children under a "수주 BOM" parent. Implementing that as a true 3-level accordion (수주 BOM → BOM 조회 → 현재 BOM/BOM 이력) adds UI complexity not justified here. Instead "수주 BOM" becomes a `menu-title` section header (same pattern as today's "MANAGEMENT"/"ADMINISTRATION" headers) containing two sibling 2-level accordions: "BOM 조회" (현재 BOM / BOM 이력) and "수주 재료비 입력" (담당 품목 관리 / BOM 입력, non-admin only — unchanged visibility rule from current "내 BOM 관리"). This preserves every existing link and active-state rule while matching the requested grouping visually.

## Global Constraints

- No changes to `portal/db.py` schema or any existing route's query/business logic — this phase only adds new thin routes and reorganizes nav markup.
- Follow existing code style exactly: Tailwind utility classes, Alpine `x-data`/`x-show`/`x-cloak` accordion pattern, Bootstrap Icons (`bi bi-*`), Korean UI copy.
- All new routes require `@login_required` (every existing nav-linked route does).
- Run tests from `portal/` with `pytest` (uses the existing `tests/conftest.py` fixtures: `app`, `client`, `admin_user`).
- Do not `git push` — commit locally only.

---

### Task 1: "차종별 협력사 현황" placeholder dashboard page

**Files:**
- Modify: `portal/routes/home_routes.py` (add route after `index()`, which ends at line 48)
- Create: `portal/templates/dashboard_vendor_placeholder.html`
- Test: `portal/tests/test_home_routes.py` (append)

**Interfaces:**
- Produces: endpoint `home.vendor_dashboard`, path `/dashboard/vendors`, GET, `@login_required`, renders `dashboard_vendor_placeholder.html` with no context variables. Task 4 links to this endpoint by name.

- [ ] **Step 1: Write the failing tests**

Append to `portal/tests/test_home_routes.py`:

```python
def test_vendor_dashboard_requires_login(client):
    resp = client.get("/dashboard/vendors")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_vendor_dashboard_shows_placeholder(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/dashboard/vendors")
    assert resp.status_code == 200
    assert "준비중".encode() in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd portal && python -m pytest tests/test_home_routes.py -k vendor_dashboard -v`
Expected: FAIL with `werkzeug.routing.exceptions.BuildError` or 404 (route doesn't exist yet).

- [ ] **Step 3: Create the placeholder template**

Create `portal/templates/dashboard_vendor_placeholder.html`:

```html
{% extends "base_new.html" %}
{% block title %}차종별 협력사 현황 - TMS Portal{% endblock %}
{% block page_title %}차종별 협력사 현황{% endblock %}
{% block content %}
<div class="bg-white rounded-2xl p-10 shadow-sm border-none flex flex-col items-center justify-center text-center gap-3">
    <i class="bi bi-hourglass-split text-4xl text-[#A3AED0]"></i>
    <h3 class="text-lg font-bold text-[#1B2559]">준비중입니다</h3>
    <p class="text-sm text-[#A3AED0]">입찰 BOM의 선정 협력사 정보가 쌓이면 차종별 협력사 현황을 제공할 예정입니다.</p>
</div>
{% endblock %}
```

- [ ] **Step 4: Add the route**

In `portal/routes/home_routes.py`, insert immediately after the `index()` function (after line 48, before the `/export/dashboard.xlsx` route):

```python
@home_bp.route("/dashboard/vendors")
@login_required
def vendor_dashboard():
    return render_template("dashboard_vendor_placeholder.html")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd portal && python -m pytest tests/test_home_routes.py -k vendor_dashboard -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add portal/routes/home_routes.py portal/templates/dashboard_vendor_placeholder.html portal/tests/test_home_routes.py
git commit -m "feat: add 차종별 협력사 현황 placeholder page"
```

---

### Task 2: "재료비 Summary" full page (expose orphaned `bom.summary` fragment)

**Files:**
- Modify: `portal/routes/bom_routes.py` (add route after `summary()`, which ends at line 316)
- Create: `portal/templates/summary.html`
- Test: `portal/tests/test_bom_routes.py` (append)

**Interfaces:**
- Consumes: existing endpoint `bom.summary` (`portal/routes/bom_routes.py:302-316`), which renders `partials/_summary.html` and expects no required query params (`country` defaults to `COUNTRIES[0]`).
- Produces: endpoint `bom.summary_page`, path `/bom/summary-page`, GET, `@login_required`, renders `summary.html`. Task 4 links to this endpoint by name.

- [ ] **Step 1: Write the failing tests**

Append to `portal/tests/test_bom_routes.py`:

```python
def test_summary_page_requires_login(client):
    resp = client.get("/bom/summary-page")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_summary_page_embeds_summary_fragment(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/bom/summary-page")
    assert resp.status_code == 200
    assert b'hx-get="/bom/summary"' in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd portal && python -m pytest tests/test_bom_routes.py -k summary_page -v`
Expected: FAIL (route doesn't exist yet, 404/BuildError).

- [ ] **Step 3: Create the host page template**

Create `portal/templates/summary.html`:

```html
{% extends "base_new.html" %}
{% block title %}재료비 Summary - TMS Portal{% endblock %}
{% block page_title %}재료비 Summary{% endblock %}
{% block content %}
<div id="summary-container" hx-get="{{ url_for('bom.summary') }}" hx-trigger="load"></div>
{% endblock %}
```

- [ ] **Step 4: Add the route**

In `portal/routes/bom_routes.py`, insert immediately after the `summary()` function (after line 316, before the `/row/<part_no>/<int:row_num>/<country>` route):

```python
@bom_bp.route("/summary-page")
@login_required
def summary_page():
    return render_template("summary.html")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd portal && python -m pytest tests/test_bom_routes.py -k summary_page -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add portal/routes/bom_routes.py portal/templates/summary.html portal/tests/test_bom_routes.py
git commit -m "feat: expose 재료비 Summary as a standalone page"
```

---

### Task 3: "입찰 BOM" placeholder blueprint

**Files:**
- Create: `portal/routes/bid_bom_routes.py`
- Create: `portal/templates/bid_bom_placeholder.html`
- Modify: `portal/app.py` (register blueprint, lines 11-15 and 28-32)
- Test: `portal/tests/test_bid_bom_routes.py` (new file)

**Interfaces:**
- Produces: blueprint `bid_bom_bp` (name `bid_bom`, url_prefix `/bid-bom`), endpoint `bid_bom.index`, path `/bid-bom/`, GET, `@login_required`, renders `bid_bom_placeholder.html`. Task 4 links to this endpoint by name. Phase C (future, separate plan) extends this blueprint with real routes — do not add more than the one placeholder route now.

- [ ] **Step 1: Write the failing tests**

Create `portal/tests/test_bid_bom_routes.py`:

```python
def _login(client, admin_user):
    client.post("/login", data=admin_user)


def test_bid_bom_index_requires_login(client):
    resp = client.get("/bid-bom/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_bid_bom_index_shows_placeholder(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/bid-bom/")
    assert resp.status_code == 200
    assert "준비중".encode() in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd portal && python -m pytest tests/test_bid_bom_routes.py -v`
Expected: FAIL (module/blueprint doesn't exist, both tests error).

- [ ] **Step 3: Create the placeholder template**

Create `portal/templates/bid_bom_placeholder.html`:

```html
{% extends "base_new.html" %}
{% block title %}입찰 BOM - TMS Portal{% endblock %}
{% block page_title %}입찰 BOM{% endblock %}
{% block content %}
<div class="bg-white rounded-2xl p-10 shadow-sm border-none flex flex-col items-center justify-center text-center gap-3">
    <i class="bi bi-hourglass-split text-4xl text-[#A3AED0]"></i>
    <h3 class="text-lg font-bold text-[#1B2559]">준비중입니다</h3>
    <p class="text-sm text-[#A3AED0]">입찰 BOM 기능은 다음 단계에서 추가될 예정입니다.</p>
</div>
{% endblock %}
```

- [ ] **Step 4: Create the blueprint**

Create `portal/routes/bid_bom_routes.py`:

```python
from flask import Blueprint, render_template
from flask_login import login_required

bid_bom_bp = Blueprint("bid_bom", __name__, url_prefix="/bid-bom")


@bid_bom_bp.route("/")
@login_required
def index():
    return render_template("bid_bom_placeholder.html")
```

- [ ] **Step 5: Register the blueprint**

In `portal/app.py`, add the import alongside the other route imports (after line 15):

```python
from routes.bid_bom_routes import bid_bom_bp
```

And register it alongside the other blueprints (after line 32):

```python
    app.register_blueprint(bid_bom_bp)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd portal && python -m pytest tests/test_bid_bom_routes.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add portal/routes/bid_bom_routes.py portal/templates/bid_bom_placeholder.html portal/app.py portal/tests/test_bid_bom_routes.py
git commit -m "feat: add 입찰 BOM placeholder tab"
```

---

### Task 4: Restructure sidebar navigation

**Files:**
- Modify: `portal/templates/base_new.html:31-98` (entire `<nav>` block)
- Test: `portal/tests/test_home_routes.py` (append)

**Interfaces:**
- Consumes: `home.index`, `home.vendor_dashboard` (Task 1), `bom.summary_page` (Task 2), `bom.index`, `bom.grid`, `bom.history`, `bom.my_assignments`, `bom.assignment_grid`, `bom.my_bom`, `bom.submissions`, `bid_bom.index` (Task 3), `admin.bom_versions`, `admin.reviews` — all existing or produced by Tasks 1-3. No new interfaces produced; this is a leaf UI task.

- [ ] **Step 1: Write the failing test**

Append to `portal/tests/test_home_routes.py`:

```python
def test_dashboard_nav_includes_restructured_sections(client, admin_user):
    _login(client, admin_user)
    resp = client.get("/")
    assert b'href="/dashboard/vendors"' in resp.data
    assert b'href="/bom/summary-page"' in resp.data
    assert b'href="/bid-bom/"' in resp.data
    assert "차종별 재료비 현황".encode() in resp.data
    assert "수주 BOM".encode() in resp.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd portal && python -m pytest tests/test_home_routes.py -k restructured -v`
Expected: FAIL (current nav has none of these hrefs/labels).

- [ ] **Step 3: Replace the nav block**

In `portal/templates/base_new.html`, replace lines 31-98 (from `    <nav class="p-4">` through the closing `    </nav>`) with:

```html
    <nav class="p-4">
      <ul class="menu menu-md w-full gap-1 p-0">
        <li class="menu-title text-[#A3AED0] font-bold text-xs tracking-wider mb-2 px-2">DASHBOARD</li>
        <li x-data="{ open: {{ 'true' if request.endpoint in ('home.index', 'home.vendor_dashboard') else 'false' }} }">
          <a href="#" @click.prevent="open = !open" class="flex items-center justify-between gap-3 px-4 py-3 rounded-xl font-medium cursor-pointer {% if request.endpoint in ('home.index', 'home.vendor_dashboard') %}text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
            <span class="flex items-center gap-3"><i class="bi bi-speedometer2 text-lg"></i> 대시보드</span>
            <i class="bi text-xs" :class="open ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
          </a>
          <ul x-show="open" x-cloak class="pl-8 mt-1 flex flex-col gap-1">
            <li>
              <a href="{{ url_for('home.index') }}" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium {% if request.endpoint == 'home.index' %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
                차종별 재료비 현황
              </a>
            </li>
            <li>
              <a href="{{ url_for('home.vendor_dashboard') }}" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium {% if request.endpoint == 'home.vendor_dashboard' %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
                차종별 협력사 현황
              </a>
            </li>
          </ul>
        </li>
        <li>
          <a href="{{ url_for('bom.summary_page') }}" class="flex items-center gap-3 px-4 py-3 rounded-xl font-medium {% if request.endpoint == 'bom.summary_page' %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
            <i class="bi bi-pie-chart text-lg"></i> 재료비 Summary
          </a>
        </li>

        <li class="menu-title text-[#A3AED0] font-bold text-xs tracking-wider mt-4 mb-2 px-2">수주 BOM</li>
        <li x-data="{ open: {{ 'true' if request.endpoint in ('bom.index', 'bom.grid', 'bom.history') else 'false' }} }">
          <a href="#" @click.prevent="open = !open" class="flex items-center justify-between gap-3 px-4 py-3 rounded-xl font-medium cursor-pointer {% if request.endpoint in ('bom.index', 'bom.grid', 'bom.history') %}text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
            <span class="flex items-center gap-3"><i class="bi bi-table text-lg"></i> BOM 조회</span>
            <i class="bi text-xs" :class="open ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
          </a>
          <ul x-show="open" x-cloak class="pl-8 mt-1 flex flex-col gap-1">
            <li>
              <a href="{{ url_for('bom.index') }}" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium {% if request.endpoint in ('bom.index', 'bom.grid') and not request.args.get('version_id') %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
                현재 BOM
              </a>
            </li>
            <li>
              <a href="{{ url_for('bom.history') }}" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium {% if request.endpoint == 'bom.history' or (request.endpoint in ('bom.index', 'bom.grid') and request.args.get('version_id')) %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
                BOM 이력
              </a>
            </li>
          </ul>
        </li>

        {% if current_user.role != 'admin' %}
        <li x-data="{ open: {{ 'true' if request.endpoint in ('bom.my_assignments', 'bom.assignment_grid', 'bom.my_bom') else 'false' }} }">
          <a href="#" @click.prevent="open = !open" class="flex items-center justify-between gap-3 px-4 py-3 rounded-xl font-medium cursor-pointer {% if request.endpoint in ('bom.my_assignments', 'bom.assignment_grid', 'bom.my_bom') %}text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
            <span class="flex items-center gap-3"><i class="bi bi-pencil-square text-lg"></i> 수주 재료비 입력</span>
            <i class="bi text-xs" :class="open ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
          </a>
          <ul x-show="open" x-cloak class="pl-8 mt-1 flex flex-col gap-1">
            <li>
              <a href="{{ url_for('bom.my_assignments') }}" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium {% if request.endpoint in ('bom.my_assignments', 'bom.assignment_grid') %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
                담당 품목 관리
              </a>
            </li>
            <li>
              <a href="{{ url_for('bom.my_bom') }}" class="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium {% if request.endpoint == 'bom.my_bom' %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
                BOM 입력
              </a>
            </li>
          </ul>
        </li>
        <li>
          <a href="{{ url_for('bom.submissions') }}" class="flex items-center gap-3 px-4 py-3 rounded-xl font-medium {% if request.endpoint and request.endpoint.startswith('bom.submission') %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
            <i class="bi bi-send-check text-lg"></i> 내 제출 현황
          </a>
        </li>
        {% endif %}

        <li>
          <a href="{{ url_for('bid_bom.index') }}" class="flex items-center gap-3 px-4 py-3 rounded-xl font-medium {% if request.endpoint and request.endpoint.startswith('bid_bom.') %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
            <i class="bi bi-clipboard2-data text-lg"></i> 입찰 BOM
          </a>
        </li>

        {% if current_user.role == 'admin' %}
        <li class="menu-title text-[#A3AED0] font-bold text-xs tracking-wider mt-4 mb-2 px-2">ADMINISTRATION</li>
        <li>
          <a href="{{ url_for('admin.bom_versions') }}" class="flex items-center gap-3 px-4 py-3 rounded-xl font-medium {% if request.endpoint == 'admin.bom_versions' %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
            <i class="bi bi-clipboard2-check text-lg"></i> BOM 관리자
          </a>
        </li>
        <li>
          <a href="{{ url_for('admin.reviews') }}" class="flex items-center gap-3 px-4 py-3 rounded-xl font-medium {% if request.endpoint and request.endpoint.startswith('admin.review') %}bg-blue-50 text-blue-600 font-bold{% else %}text-[#A3AED0] hover:bg-gray-50 hover:text-[#1B2559]{% endif %}">
            <i class="bi bi-clipboard-check text-lg"></i> 제출 검토
          </a>
        </li>
        {% endif %}
      </ul>
    </nav>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd portal && python -m pytest tests/test_home_routes.py -k restructured -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite to catch nav-dependent regressions**

Run: `cd portal && python -m pytest -v`
Expected: all tests PASS. Pay attention to any test asserting old nav labels/hrefs (e.g. "내 BOM 관리", "BOM 조회/관리") — none exist in the current test files per the Task 1-3 exploration, but re-check output for unexpected failures before committing.

- [ ] **Step 6: Commit**

```bash
git add portal/templates/base_new.html portal/tests/test_home_routes.py
git commit -m "refactor: restructure sidebar nav into Phase A target tree"
```

---

## Self-Review Notes

- **Spec coverage:** All four Phase A bullets from `portal/PHASE2_PLAN.md` (nav tree, 재료비 Summary exposure, 차종별 협력사 현황 placeholder, 입찰 BOM placeholder) map 1:1 to Tasks 1-4.
- **Placeholder scan:** No TBD/TODO. The one open design choice (3-level vs. 2-level accordion nesting) is resolved explicitly in the Architecture section, not left vague.
- **Type/interface consistency:** Endpoint names (`home.vendor_dashboard`, `bom.summary_page`, `bid_bom.index`) are identical between the task that defines them and the nav task that consumes them.
- **Scope:** Pure additive routes/templates + one template edit. No DB, no business logic, no other phase's work included.
