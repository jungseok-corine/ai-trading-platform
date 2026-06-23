# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current Task

**C-2.21.1 — Market Intelligence Core Foundation**

| 필드 | 값 |
|------|----|
| **Status** | `DONE` |
| **Priority** | 높음 |
| **Type** | Feature (DB 모델 + Provider + 서비스 + 번들 통합) |

---

## Goal

DART 재무제표(손익계산서·재무상태표)를 수집·저장하고, AI 분석 bundle에 재무 요약을 주입한다.  
C-2.21.0 Spike 결론에 따라 DartLab 없이 DART API 직접 호출 방식으로 구현한다.

---

## Background

- C-2.21.0 Spike 결론: DartLab 비권장, DART API 직접 구현 권장
- 우리에게 없는 유일한 핵심 데이터: DART XBRL 재무제표
- AI 분석 bundle에 현재 재무 컨텍스트가 없어 LLM 분석의 깊이가 제한됨
- 기존 패턴: `DartProvider` + `DartIngestService` 동형으로 구현

---

## Scope

구현 항목:
1. `FinancialStatement` DB 모델 + Alembic 마이그레이션
2. `DartFinanceProvider` — DART company.json + fnlttSinglAcnt.json async 클라이언트
3. `DartFinanceIngestService` — watchlist 종목별 재무제표 수집·저장
4. API 엔드포인트 — `POST /dart/finance/ingest`, `GET /dart/finance/{stock_code}`
5. `AnalysisBundleService` 확장 — `financials` 키 추가
6. 스케줄러 잡 `dart_finance_scheduler` (기본 비활성)
7. 테스트 (MockTransport)

---

## Safety Constraints

- `KIS_REAL_TRADING_ENABLED=false` 유지
- 실주문 API 호출 없음
- 기존 `DartProvider`, `DartIngestService` 코드 변경 없음
- 새 스케줄러 잡 기본 비활성 (`dart_finance_scheduler_enabled=False`)
- `.env`, API 키, 시크릿 값 출력 없음

---

## Definition of Done

- [x] `financial_statements` 테이블 생성 + alembic 마이그레이션 (`d2e3f4a5b6c7`)
- [x] `DartFinanceProvider`: company.json + fnlttSinglAcnt.json 호출, MockTransport 테스트
- [x] `DartFinanceIngestService`: watchlist 종목별 수집, 중복 upsert
- [x] API 엔드포인트 등록 (`POST /dart/finance/ingest`, `GET /dart/finance/{stock_code}`)
- [x] `AnalysisBundleService.build_full()` 에 `financials` 키 추가
- [x] 스케줄러 잡 기본 비활성으로 추가 (`DART_FINANCE_JOB_ID`, 매일 02:00)
- [x] 전체 테스트 통과 (기존 9개 사전 실패 제외 — 7개 알려진 + 2개 test_c3_8 사전 실패 확인)
- [x] 프론트 빌드 통과 (API만 추가, 프론트 변경 없음)

---

## Next Task After Completion

**C-2.22 — Intelligence Ingestion Pipeline**

뉴스 RSS 피드 수집기, 테마/섹터 데이터 수집기 구현.

---

## Completed: C-2.21.1

구현 완료 파일:
- `alembic/versions/d2e3f4a5b6c7_add_financial_statements.py`
- `app/domain/models/financial_statement.py`
- `app/domain/repositories/financial_statement.py`
- `app/services/dart_finance_provider.py`
- `app/services/dart_finance_ingest_service.py`
- `app/api/v1/dart_finance.py`
- `tests/test_c2_21_1_dart_finance.py` (14 tests, all pass)
- 수정: `app/domain/models/__init__.py`, `app/core/config.py`, `app/scheduler/jobs.py`, `app/scheduler/registry.py`, `app/main.py`, `app/services/analysis_bundle_service.py`
