# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current Task

**C-2.21.1b — Market Intelligence Adapter Foundation Repair**

| 필드 | 값 |
|------|----|
| **Status** | `DONE` |
| **Priority** | 높음 |
| **Type** | Feature (어댑터 패턴 기반 인터페이스) |

---

## Goal

C-2.21.1에서 누락된 어댑터 패턴 기반(IntelligenceSource / IntelligenceEvent / IntelligenceAdapter)을  
추가해 Market Intelligence 수집 레이어의 공통 인터페이스를 완성한다.  
기존 DART finance 구현은 보존하며 변경하지 않는다.

---

## Background

- C-2.21.1은 DART XBRL 재무제표 수집만 구현하고 원래 ROADMAP 범위를 누락했다.
- C-2.21.1b는 그 드리프트를 보정한다 (D-10 결정 참조).
- DART finance 구현(financial_statements 등)은 첫 번째 구체 소스로 유지된다.
- C-2.22부터 추가하는 모든 수집기는 IntelligenceAdapter를 상속해야 한다.

---

## Scope

구현 항목:
1. `IntelligenceSource` / `IntelligenceEvent` DB 모델 + Alembic 마이그레이션
2. `IntelligenceAdapter` 추상 base 클래스 (`app/market_intelligence/adapters/base.py`)
3. `IntelligenceRawItem` / `IntelligenceEventCandidate` DTO
4. `build_dedup_hash()` 헬퍼
5. `DartFinanceAdapter` 스켈레톤 (fetch 미구현, normalize 시그니처만)
6. Repository: `IntelligenceSourceRepository`, `IntelligenceEventRepository`
7. 테스트 19개 (MockTransport 불필요 — DB 통합 + 순수 단위 테스트)
8. docs: DECISIONS.md D-10, ROADMAP.md C-2.21.1b 추가, NEXT-TASK.md 업데이트

---

## Definition of Done

- [x] `intelligence_sources` + `intelligence_events` 테이블 + 마이그레이션 (`e3f4a5b6c7d8`)
- [x] `IntelligenceAdapter` 추상 클래스 + DTO + `build_dedup_hash()`
- [x] `DartFinanceAdapter` 스켈레톤 (C-2.22+ 연결 대기)
- [x] repository 2개 (get_by_key, list_enabled, list_by_source, existing_hashes)
- [x] 19개 테스트 전체 통과
- [x] 기존 DART finance 수집 동작 변경 없음
- [x] DECISIONS.md D-10 추가
- [x] ROADMAP.md C-2.21.1 → PARTIAL, C-2.21.1b 추가

---

## Safety Constraints

- `KIS_REAL_TRADING_ENABLED=false` 유지
- 실주문 API 호출 없음
- 기존 `DartProvider`, `DartIngestService`, `DartFinanceProvider`, `DartFinanceIngestService` 변경 없음
- 실제 RSS/EDGAR/신규 수집기 구현 금지

---

## Next Task After Completion

**C-2.22 — Intelligence Ingestion Pipeline**

뉴스 RSS 피드 수집기, 테마/섹터 데이터 수집기 구현.  
모든 수집기는 `IntelligenceAdapter`를 상속하고 `IntelligenceSource`에 등록한다.

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
