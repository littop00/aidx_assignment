# Phase B / Phase C TODO

> 상세 스펙은 `PHASE2_PLAN.md` 참고. 이 문서는 내일 작업 시작점 메모.
> Phase A는 완료됨 (nav 재구조, 커밋 완료, 테스트 76/76 통과).

## Phase B — 수주 BOM UI/UX 개선 (B1~B8) — 전체 완료

| # | 항목 | 관련 파일 |
|---|------|-----------|
| B1 | 대분류/소분류 계층 필터 | `routes/bom_routes.py` `_filtered_rows()`/`grid()` (61-276행), `templates/bom.html` 필터바 (category-menu, 24행), `categories.py` `major_of()`/`group_of()` |
| B2 | 엑셀식 방향키 네비게이션 | `templates/my_bom.html`, `templates/partials/_row.html` (입력 셀 구조), JS keydown 핸들러 신규 작성 필요 |
| B3 | 페이지네이션 (버튼식) | 완료. 무한스크롤 구현했었으나 로딩 렉으로 버튼 페이지네이션으로 원복. `grid()`는 항상 `partials/_grid.html` 렌더, `window_start`/`window_end` 페이지 버튼 윈도우 계산 복원, `bom.html`/`my_bom.html`에 "페이지 행 수" select 복원 |
| B4 | 국내(한국) 통화/특별환율 노출 | `templates/partials/_row.html` 한국 컬럼 하드코딩 부분. DB 컬럼 `special_fx_rate`/`special_fx_reason`/`currency` 이미 존재 — 스키마 변경 불필요, 템플릿 노출만 |
| B5 | 비고(note) 길이제한 해제 | 비고 필드 템플릿 내 `maxlength` 속성 찾아서 제거. DB 제약 없음 확인됨 |
| B6 | 그룹핑 UX (그룹만 보기 필터 + 상위행 클릭만으로 해제) | `db.py` `group_for_part`/`group_members`/관련 함수, `routes/bom_routes.py` `/groups/<part_no>/<row_num>`, `/groups/selected` |
| B7 | 관리자 인라인 행추가 — 전체 필드 | `routes/bom_routes.py` `add_row()` / `db.add_manual_part()` — 현재 4필드(part_name/part_no/qty/spec)만 지원 → `columns.py`의 `DESIGN_FIELDS` 전체로 확장 |
| B8 | 초안 생성시 "기존 입력값 이관" 소스 BOM 선택 드랍다운 | 완료. `templates/admin_boms.html` 체크박스 켜지면 `source_bom_id` 드랍다운(published/archived 버전) 노출, `routes/admin_routes.py` `create_draft()` → `db.create_draft_from_active(..., source_bom_id=...)`로 전달. 미선택시 기존처럼 active 버전 사용 |

**내일 시작 순서:**
1. `templates/partials/_grid.html` 실제 경로 확인
2. 위 매핑 기준 `writing-plans` 스킬로 `docs/superpowers/plans/2026-10-0X-phase-b-*.md` 작성 (TDD 태스크 분해)
3. self-review → 커밋 (push 안 함)
4. 사용자 "빨리 만드셈" 기조 유지 — 실행방식 재질문 없이 바로 inline TDD 구현, 태스크별 커밋

## Phase C — 입찰 BOM 신규 기능

`PHASE2_PLAN.md` Phase C 섹션 기준. 신규 blueprint `bid_bom_bp` (현재 placeholder 라우트 1개만 존재, `routes/bid_bom_routes.py`) 를 실제 기능으로 확장.

**신규 DB 스키마** (기존 `bom_versions`/`bom_parts`/`bom_purchase_data` 패턴 따라감):
- `bid_bom_versions`
- `bid_bom_parts`
- `bid_purchase_data`
- `bid_info`
- `bid_category_members`

**신규 화면 3개:**
- 입찰 BOM 관리자 화면 — 확정된 수주 BOM 버전에서 "승계"로 입찰 BOM 생성
- BOM 조회 화면 (사용자용)
- 입찰정보 입력 화면 (사용자용)

화면 설계는 `"D:\재료비 관리 포탈 PJT\수주,입찰 재료비 비교양식.xlsx"` 시트1/시트2 구조 기반 (`PHASE2_PLAN.md`에 pandas dump 분석 반영됨).

**작업 순서:** Phase B 완료 후 착수. `writing-plans` 스킬로 별도 플랜 작성 — DB 스키마 마이그레이션, `db.py` CRUD 함수, `bid_bom_routes.py` 실제 라우트, 템플릿 3개 신규 작성.
