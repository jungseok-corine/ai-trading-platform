# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current Task

**C-2.22 — Intelligence Ingestion Pipeline**

| 필드 | 값 |
|------|----|
| **Status** | `DONE` |
| **Priority** | 높음 |
| **Type** | Feature (Intelligence 수집 파이프라인) |

---

## Goal

여러 데이터 소스가 IntelligenceEvent로 들어오는 ingestion pipeline 구현.

---

## Definition of Done

- [x] `GenericRssAdapter` — config JSONB의 feed_url에서 RSS 수집, xml.etree 파싱, keyword_filter 지원
- [x] `DartDisclosureAdapter` — news_events(source="dart") 브리징, 기존 DartIngestService 불변
- [x] `IntelligenceIngestionService` — 어댑터 순회, dedup, enabled 필터, 결과 summary
- [x] `POST /intelligence/ingest` — 수동 트리거, source_keys 필터 지원
- [x] 스케줄러 잡 `intelligence_ingest` — 기본 비활성(`intelligence_ingest_scheduler_enabled=False`)
- [x] 19개 테스트 전체 통과
- [x] feedparser 의존성 없음 (xml.etree.ElementTree만 사용)
- [x] 특정 언론사 URL 하드코딩 없음
- [x] 주문·실거래 코드 변경 없음

---

## Safety Constraints

- `KIS_REAL_TRADING_ENABLED=false` 유지
- 실주문 API 호출 없음
- AI 분석 연동 없음 (C-2.28에서)
- 후보 종목 생성 없음
- C-2.23 이후 작업 시작 금지

---

## Next Task After Completion

**C-2.23 — Market/Theme Context Foundation**

테마·섹터 맥락을 후보 발굴과 AI 분석에 통합.  
범위: 테마/섹터 데이터 모델, 시장 맥락 스냅샷 확장, 후보 점수에 테마 반영.  
선행 조건: C-2.22 완료.

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
