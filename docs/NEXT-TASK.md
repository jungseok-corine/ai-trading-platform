# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current Task

**C-2.23 — Market/Theme Context Foundation**

| 필드 | 값 |
|------|----|
| **Status** | `DONE` |
| **Priority** | 높음 |
| **Type** | Feature (테마·맥락 기반 AI 분석 번들 확장) |

---

## Goal

테마·섹터 맥락을 AI 분석 번들에 통합, ThemeActivityService로 활성 테마 탐지,
ThemeSynergyScorer로 시너지 bonus 계산.

---

## Definition of Done

- [x] `IntelligenceEventRepository.list_recent()` — 최근 N시간 이벤트 조회
- [x] `IntelligenceEventRepository.list_recent_for_bundle()` — source_key JOIN 포함, dict 반환
- [x] `ThemeActivityService.get_active_themes()` — 이벤트 title/summary에서 Theme.code/name 매칭
- [x] `compute_theme_synergy_bonus()` — pure function, CandidateEvent.score 비수정
- [x] `AnalysisBundleService.build_full()` — `themes` + `recent_intelligence` 키 추가
- [x] 12개 테스트 전체 통과
- [x] Alembic 마이그레이션 없음 (기존 data JSONB 사용)
- [x] CandidateEvent.score 수정 없음
- [x] 주문·실거래 코드 변경 없음

---

## Safety Constraints

- `KIS_REAL_TRADING_ENABLED=false` 유지
- 실주문 API 호출 없음
- CandidateEvent.score 자동 수정 금지
- C-2.24 이후 작업 시작 금지

---

## Next Task After Completion

**C-2.24 — Candidate Discovery System**

AI가 수집된 인텔리전스 데이터에서 자동으로 유망 후보 종목을 발굴.
범위: AI 기반 후보 점수 산정, 맥락(why) 자동 생성·보존, 후보 이벤트와 연결.
선행 조건: C-2.23 완료.

---

## Completed: C-2.23

구현 완료 파일:
- `app/domain/repositories/intelligence.py` — `list_recent()`, `list_recent_for_bundle()` 추가
- `app/services/theme_activity_service.py` — `ThemeActivityService`, `compute_theme_synergy_bonus`
- `app/services/analysis_bundle_service.py` — `themes`, `recent_intelligence` 키 추가, `_build_themes()` 헬퍼
- `tests/test_c2_23_market_theme_context.py` (12 tests, all pass)

---

## Completed: C-2.22

구현 완료 파일:
- `app/market_intelligence/adapters/generic_rss_adapter.py`
- `app/market_intelligence/adapters/dart_disclosure_adapter.py`
- `app/market_intelligence/adapters/__init__.py` (DartDisclosureAdapter, GenericRssAdapter export)
- `app/services/intelligence_ingest_service.py`
- `app/api/v1/intelligence.py`
- `app/core/config.py` — intelligence_ingest_scheduler_enabled/hour/minute 추가
- `app/scheduler/jobs.py` — INTELLIGENCE_INGEST_JOB_ID, run_intelligence_ingest_job 추가
- `app/scheduler/registry.py` — ControllableJob 등록
- `app/main.py` — intelligence_api router 등록
- `tests/test_c2_22_intelligence_ingestion.py` (19 tests, all pass)

---

## Completed: C-2.21.1b

구현 완료 파일:
- `alembic/versions/e3f4a5b6c7d8_add_intelligence_tables.py`
- `app/domain/models/intelligence.py` (IntelligenceSource, IntelligenceEvent)
- `app/domain/models/enums.py` — IntelligenceSourceType / IntelligenceProvider / IntelligenceMarketScope / IntelligenceEventStatus 추가
- `app/domain/repositories/intelligence.py`
- `app/market_intelligence/__init__.py`
- `app/market_intelligence/adapters/__init__.py`
- `app/market_intelligence/adapters/base.py` (IntelligenceAdapter, DTO, build_dedup_hash)
- `app/market_intelligence/adapters/dart_finance_adapter.py` (스켈레톤)
- `tests/test_c2_21_1b_intelligence_foundation.py` (19 tests, all pass)
- 수정: `app/domain/models/__init__.py`, `docs/DECISIONS.md`, `docs/ROADMAP.md`

---

## Completed: C-2.21.1 (PARTIAL → 어댑터 기반은 C-2.21.1b에서 완성)

구현 완료 파일 (커밋 30cb3d8):
- `alembic/versions/d2e3f4a5b6c7_add_financial_statements.py`
- `app/domain/models/financial_statement.py`
- `app/domain/repositories/financial_statement.py`
- `app/services/dart_finance_provider.py`
- `app/services/dart_finance_ingest_service.py`
- `app/api/v1/dart_finance.py`
- `tests/test_c2_21_1_dart_finance.py` (14 tests, all pass)
- 수정: `app/domain/models/__init__.py`, `app/core/config.py`, `app/scheduler/jobs.py`, `app/scheduler/registry.py`, `app/main.py`, `app/services/analysis_bundle_service.py`
