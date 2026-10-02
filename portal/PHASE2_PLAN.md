# UI/UX 개편 + 입찰 BOM 기능 확장 — Phase 2 기획

작성일 2026-10-01. 사용자 요청 원문의 10개 항목을 3개 독립 작업(A→B→C)으로
분할. 각 작업은 착수 시 이 문서를 기반으로 별도 구현 계획(파일별 diff 수준)을
다시 뽑아서 진행한다 — 이 문서는 설계/스펙 수준.

## 작업 순서 및 이유

1. **Phase A — 네비게이션/탭 구조 개편**: 뒤의 B/C가 들어갈 자리를 먼저 만들어야
   함. 코드 변경 범위 작고 리스크 낮음.
2. **Phase B — 수주 BOM 조회/입력 화면 UI/UX 개선** (요청 원문 1~7번)
3. **Phase C — 입찰 BOM 신규 기능** (요청 원문 8번). 범위가 가장 크고, 신규
   테이블/화면/권한 모델이 전부 새로 생기므로 마지막.

표 구조 변경 금지 등 기존 제약(`UX_PROPOSAL.md` 참고)은 계속 유효.

---

## Phase A — 네비게이션/탭 구조 개편

### 신규 메뉴 트리

```
대시보드
  ├ 차종별 재료비 현황      -> home.index 그대로 이동 (기존 차종 필터 대시보드)
  └ 차종별 협력사 현황      -> 신규. Phase C 완료 전까지 "준비중" 빈 상태만 노출
재료비 Summary             -> bom.summary 라우트를 사이드바에 정식 노출
                               (현재 고아 라우트 — base_new.html에 링크 없음)
수주 BOM
  ├ BOM 조회               -> bom.index / bom.grid / bom.history (현재 "BOM 조회/관리")
  └ 수주 재료비 입력        -> bom.my_assignments / bom.my_bom (현재 "내 BOM 관리")
입찰 BOM                   -> 신규. Phase C 완료 전까지 "준비중" 빈 상태만 노출
내 제출 현황                -> bom.submissions, 독립 탭 유지 (변경 없음)
──────────────
ADMINISTRATION (관리자 전용, 그대로 유지)
  ├ BOM 관리자             -> admin.bom_versions
  ├ 입찰 BOM 관리자         -> Phase C에서 신설
  └ 제출 검토              -> admin.reviews
```

### 결정 사항
- "차종별 협력사 현황"은 입찰 BOM의 "선정 협력사" 데이터를 근거로 하므로
  Phase C 데이터가 쌓이기 전까지는 공석(빈 화면)으로 둔다.
- "재료비 Summary"는 이번에 사이드바 노출과 함께 가벼운 폴리시(소분류
  드릴다운 등 Phase B의 분류 체계 변경사항 반영)까지 포함한다.
- Admin 전용 메뉴는 10개 항목 어디에도 언급 없었으므로 그대로 별도 섹션 유지.

### 변경 범위
- `templates/base_new.html`: 사이드바 트리 재구성.
- `routes/home_routes.py`: 대시보드를 "차종별 재료비 현황" 서브 라우트로,
  "차종별 협력사 현황" 신규 라우트(빈 상태) 추가.
- 신규 템플릿: `dashboard_vendor.html`(빈 상태), `bid_bom_placeholder.html`.
- DB/기존 라우트 로직 변경 없음 — 순수 재배치 + 이름 변경 + 신규 빈 화면.

---

## Phase B — 수주 BOM 조회/입력 UI/UX 개선

### B1. 대분류/소분류 계층 필터 (요청 1번)
현재 `bom.grid`의 "구분" 필터는 `category`(소분류: HVAC/EVAP/HTR/TTMM 등)
평면 체크박스만 지원. `재료비 Summary`(`db.summary_tree`)는 이미
`categories.py`의 `major_of`/`group_of`로 대분류(HVAC/CRFM/TTMM/SENSOR/
E-COMP) → 그룹 → 소분류 계층을 쓰고 있음 — 이 체계를 BOM 조회 필터에도
그대로 재사용.
- `routes/bom_routes.py` `index()`: `categories` 목록을 대분류로 그룹핑해서
  템플릿에 전달.
- `templates/bom.html` 필터 바: 대분류 선택 시 하위 소분류만 체크박스로
  펼쳐지는 2단 드롭다운으로 변경 (기존 평면 목록 대체).
- `_filtered_rows`의 category 필터 로직은 변경 불필요 — 최종적으로 넘어오는
  `category` 값 자체는 지금과 동일.

### B2. 엑셀 스타일 키보드 네비게이션 (요청 2번)
방향키로 셀 이동, Enter로 아래 셀 이동. 현재 그리드는 `<table>` + 셀당
`<input class="row-autosave">` 구조라 DOM 좌표만 계산하면 구현 가능.
- 각 입력 셀에 `data-row`/`data-col` 부여 (렌더링 순서 기준 인덱스).
- 전역 `keydown` 리스너: `ArrowUp/Down/Left/Right`는 해당 방향의 살아있는
  (disabled 아닌) 셀로 focus 이동, `Enter`는 Down과 동일 동작 + 필요시
  autosave 트리거.
- 무한스크롤(B3)과 결합되므로, 아래로 이동 시 다음 페이지가 아직 로드 안
  됐으면 자동 로드 트리거 필요 (경계 케이스).
- 변경 파일: `templates/partials/_row.html`(data 속성), `base_new.html`
  또는 `bom.html`에 공용 스크립트 추가.

### B3. 페이지네이션 제거 → 무한스크롤 (요청 3번)
- `partials/_grid.html`의 번호 페이지네이션(처음/이전/다음/끝) 제거.
- 마지막 행 다음에 sentinel row 추가, `hx-trigger="revealed"` +
  `hx-swap="beforeend"`로 다음 `page_size` 묶음을 테이블 끝에 이어붙임.
- `bom_routes.py` `grid()`: `page_size` 선택 UI는 삭제하되 내부 페이징 로직
  자체는 유지(한번에 전체 로드 아님 — 서버 부하 방지).
- 필터/검색 변경 시 전체 리셋 후 1페이지부터 다시 무한스크롤 시작.

### B4. 국내(한국) 통화/특별환율 노출 (요청 4번)
DB 스키마 변경 불필요 — `bom_purchase_data`/`bom_user_purchase_data`는 이미
country 무관하게 `currency`/`special_fx_rate`/`special_fx_reason` 컬럼을
가짐. 현재 `partials/_row.html`에서 한국 컬럼만 `<input type="hidden"
name="한국__currency" value="KRW">`로 하드코딩하고 특별환율/사유 입력칸
자체를 렌더링 안 함.
- `_row.html`: 한국 컬럼 블록을 해외 국가 블록과 동일한 구조(currency
  select + special_fx_rate + special_fx_reason)로 교체.
- 국내 수입품(해외 소싱이지만 국내向) 케이스 지원이 목적이므로 통화
  select 기본값은 KRW 유지하되 USD/EUR로 변경 가능하게.

### B5. 특이사항(비고) 길이 제한 해제 (요청 5번)
- 사용자 답변: 제한 없음. 현재 `note` 컬럼은 TEXT라 DB 제약 없음 — 템플릿에
  `maxlength` 속성이 걸려있는지만 확인 후 있으면 제거. (grep 결과 현재
  명시적 `maxlength` 없음 — 있다면 제거, 없으면 작업 불필요.)

### B6. 그룹핑 개선 (요청 6번, ★)
- **그룹 필터**: "미입력만 보기"와 같은 패턴으로 "그룹 지정된 품목만 보기"
  체크박스 필터 추가. `_filtered_rows`에 `group_only` 파라미터 추가,
  `row["group"]`가 있는 행만 통과.
- **상위 행만 선택해 해제**: 현재 `set_selected_group`은 그룹 해제 시
  기존 멤버와 동일한 선택 조합을 요구(`WORKFLOW.md` U-5 케이스 7). 상위
  행 1개만 선택했을 때도 "이 상위가 속한 그룹을 해체"로 동작하도록
  `db.py`의 그룹 지정/해제 판별 로직 분기 추가.
- 변경 파일: `routes/bom_routes.py`(`set_selected_group`), `db.py`(그룹
  판별 함수), `bom.html`(필터 체크박스).

### B7. 관리자 인라인 행추가 확장 (요청 7번, ★)
현재 `bom.add_row`는 admin 전용, `part_name`/`part_no`/`qty`/`spec` 4개
필드만 지원하고 별도 폼으로 입력받음. "엑셀처럼" 요구사항에 맞춰:
- 그리드 안에 빈 입력 행을 바로 추가(인라인) → 관리자가 `DESIGN_FIELDS`
  전체(재질/사이즈/표면처리/중량 등)를 그 자리에서 입력.
- `db.add_manual_part`: 현재 4개 필드만 받는 dict 파라미터를
  `DESIGN_FIELDS` 전체로 확장.
- `routes/bom_routes.py` `add_row()`: `request.form`에서 전체 설계 필드
  파싱하도록 확장. 권한은 기존대로 admin 한정 유지.
- UI: 별도 모달/폼 제거하고 그리드 내 "행 추가" 버튼 클릭 시 빈 `<tr>`을
  바로 삽입 + 저장 시 `add_row` 호출.

---

## Phase C — 입찰 BOM 신규 기능 (요청 8번)

### 개념
확정된 수주 BOM 버전 하나를 골라 **구조를 그대로 승계**해서 입찰 BOM
초안을 만든다. 승계 시점의 수주재료비는 비교 기준값으로 스냅샷 저장되고
(원본 수주 BOM이 이후에 바뀌어도 입찰 BOM 쪽 참조값은 고정), 각 부품에
입찰가/협력사 등 입찰 전용 정보를 덧붙인다. 수주 BOM과 동일하게
draft → published → archived 버전관리 + 이력 조회를 지원한다.

Excel 업로드로 입찰 BOM을 직접 만드는 방식은 이번 범위에서 제외(차후
별도 작업).

### 데이터 모델 (신규 테이블, 수주 BOM 테이블 구조를 그대로 미러링)

```sql
CREATE TABLE bid_bom_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_bom_version_id INTEGER NOT NULL,   -- 승계 출처 수주 BOM (bom_versions.id)
    version_no INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    vehicle TEXT,
    status TEXT NOT NULL CHECK(status IN ('draft','published','archived')),
    created_by TEXT, created_at TEXT NOT NULL, published_at TEXT,
    is_withdrawn INTEGER NOT NULL DEFAULT 0, withdrawn_at TEXT, withdrawal_reason TEXT,
    FOREIGN KEY (source_bom_version_id) REFERENCES bom_versions(id)
);

-- 승계 시점 스냅샷: 수주 BOM 설계정보 + 수주재료비 참조값 (읽기 전용)
CREATE TABLE bid_bom_parts (
    bid_id INTEGER NOT NULL, part_no TEXT NOT NULL, row_num INTEGER NOT NULL,
    level_depth INTEGER, level_marker TEXT,
    -- DESIGN_FIELDS 전체 (vehicle, category, sub_category, part_name, spec, material, ... )
    ref_material_cost REAL,   -- 승계 시점 수주재료비 스냅샷 (비교 기준, 고정값)
    PRIMARY KEY (bid_id, part_no, row_num),
    FOREIGN KEY (bid_id) REFERENCES bid_bom_versions(id)
);

-- 입찰 원가 (국가 구분 없음, sheet1 우측 대응) + 재료비 변동 내역(전부 수기입력)
CREATE TABLE bid_purchase_data (
    bid_id INTEGER NOT NULL, part_no TEXT NOT NULL, row_num INTEGER NOT NULL,
    material TEXT, size TEXT, surface TEXT, weight_unit REAL, weight_total REAL,
    dev_type TEXT, remark TEXT,
    unit_price REAL, material_cost REAL, total_cost REAL,
    spec_add REAL, spec_delete REAL, spec_change REAL,
    material_change REAL, tariff_change REAL, fx_change REAL,
    cost_reduction REAL, cost_increase REAL, localization REAL,
    bridge_total REAL, bridge_note TEXT,   -- bridge_total == 차액 검증용(강제 아님, UI 경고만)
    updated_at TEXT, updated_by TEXT,
    PRIMARY KEY (bid_id, part_no, row_num),
    FOREIGN KEY (bid_id, part_no, row_num) REFERENCES bid_bom_parts(bid_id, part_no, row_num)
);

-- 입찰정보 (sheet2 대응, 부품별)
CREATE TABLE bid_info (
    bid_id INTEGER NOT NULL, part_no TEXT NOT NULL, row_num INTEGER NOT NULL,
    bid_plan TEXT,              -- 입찰방안
    design_cost REAL,           -- 설계원가
    selected_vendor TEXT,       -- 선정 협력사
    decided_price REAL,         -- 결정가 ⓑ
    committed_reduction REAL,   -- 약정인하
    volume_10k REAL,            -- 수량 (만대)
    annual_purchase REAL,       -- 구매금액 (年)
    -- 재료비개선 = (ref_material_cost - decided_price) / ref_material_cost, 화면 계산값(저장 안 함)
    review_comment TEXT,        -- 검토의견
    updated_at TEXT, updated_by TEXT,
    PRIMARY KEY (bid_id, part_no, row_num),
    FOREIGN KEY (bid_id, part_no, row_num) REFERENCES bid_bom_parts(bid_id, part_no, row_num)
);

-- 담당자 지정: bom_category_members와 동일 패턴 재사용
CREATE TABLE bid_category_members (
    bid_id INTEGER NOT NULL, category TEXT NOT NULL, user_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL,
    PRIMARY KEY (bid_id, category, user_id)
);
```

**가정(미확정, 구현 착수 전 재확인 필요)**: `bid_info`/`bid_purchase_data`
입력에 수주 BOM처럼 제출→관리자 승인 플로우(`bom_submissions` 상당)가
필요한지는 이번 질의에서 다루지 않음. 일단 "담당자 지정 후 바로 저장"
방식으로 가정하고, 승인 플로우가 필요하면 Phase C 착수 시 별도 확인.

### 화면 구성
- **입찰 BOM 관리자** (admin, `ADMINISTRATION` 섹션): 확정된 수주 BOM
  버전 목록에서 하나 선택 → "입찰 BOM 승계 생성" → draft 생성. 확정/배포,
  배포 취소, 이력 조회는 수주 BOM 관리자 화면과 동일 패턴.
- **BOM 조회** (`입찰 BOM` 탭, 전 사용자): sheet1 참고 — 좌측에 수주 BOM
  참조 컬럼(읽기 전용: 레벨/사양/소분류/품번/품명/수량/소재/재질/중량/
  수주재료비), 우측에 입찰 컬럼(읽기전용 설계정보 + 입력가능 재료비
  변동내역), 맨 끝에 차액 = `bid_purchase_data.total_cost -
  bid_bom_parts.ref_material_cost` 자동계산 컬럼.
- **입찰정보 입력** (`입찰 BOM` 탭, 담당자 지정된 일반 사용자): sheet2
  참고 — 본인 담당 부품에 대해 입찰방안/설계원가/선정협력사/결정가/
  약정인하/수량/구매금액/검토의견 입력. 재료비개선율은 입력 즉시 화면에서
  계산해서 보여줌(저장값 아님, 항상 최신 ref_material_cost 기준 재계산).

### 변경/신규 파일
- `db.py`: 신규 테이블 `init_db`에 추가, `bid_*` CRUD 함수 세트(수주 BOM
  쪽 `bom_versions`/`bom_parts`/`bom_purchase_data` 관련 함수들과 1:1
  대응하도록 설계).
- `routes/bid_bom_routes.py` (신규 블루프린트): `/bid-bom/`(조회),
  `/bid-bom/input`(입찰정보 입력), `/bid-bom/history`.
- `routes/admin_routes.py`: 입찰 BOM 생성(승계)/확정/배포취소 엔드포인트.
- 신규 템플릿: `bid_bom.html`, `bid_bom_input.html`, `bid_bom_history.html`,
  `admin_bid_boms.html`.
- `app.py`: 신규 블루프린트 등록.

---

## 전체 범위 밖 (이번에 안 하는 것)
- 입�찰 BOM Excel 업로드 생성 방식 (승계만 먼저).
- 입찰 BOM 제출/승인 워크플로우 (가정 상태, 필요시 Phase C 착수 시 재확인).
- `UX_PROPOSAL.md`에 남아있던 셀 단위 dirty 시각화, 저장상태 배지, 동시편집
  충돌 감지, undo — 이번 10개 항목에 없으므로 별도 유지.

## 다음 단계
Phase A부터 착수. 각 Phase 시작 시 이 문서의 해당 섹션을 기준으로
`writing-plans` 수준의 파일별 구현 계획(BOM_HISTORY_PLAN.md 같은 수준)을
별도로 뽑아서 진행.
