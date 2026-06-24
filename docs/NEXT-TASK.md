# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current Task

**C-2.24 — Candidate Discovery System**

| 필드 | 값 |
|------|----|
| **Status** | `DONE` |
| **Priority** | 높음 |
| **Type** | Feature (IntelligenceEvent 기반 관심 후보 자동 발굴) |

---

## Goal

수집된 IntelligenceEvent에서 symbol_code가 있는 이벤트를 후보로 발굴하고 저장한다.
LLM 미호출, 휴리스틱 점수 계산, deterministic why_text.

---

## Definition of Done

- [x] `IntelligenceCandidateStatus` enum (PENDING/REVIEWED/PROMOTED/IGNORED) 추가
- [x] `IntelligenceCandidate` 모델 (기존 CandidateEvent와 완전 분리, scanner FK 없음)
- [x] Alembic 마이그레이션 `f1a2b3c4d5e6_add_intelligence_candidates.py`
- [x] `IntelligenceCandidateRepository` — create/list_recent/existing_hashes/update_status
- [x] `IntelligenceCandidateDiscoveryService` — discover(), _calc_score(), _build_why_text()
- [x] `POST /intelligence/discover`, `GET /intelligence/candidates`, `GET /intelligence/candidates/{id}` API
- [x] `intelligence_discovery_scheduler_enabled=False` 기본 비활성 스케줄러 잡
- [x] 22개 테스트 전체 통과
- [x] 기존 CandidateEvent.scanner_rule_version_id NOT NULL 유지
- [x] LLM 호출 없음
- [x] 주문·실거래 코드 변경 없음

---

## Safety Constraints

- `KIS_REAL_TRADING_ENABLED=false` 유지
- 실주문 API 호출 없음
- 기존 CandidateEvent 미수정
- C-2.25 이후 작업 시작 금지

---

## Next Task After Completion

**C-2.25 — Scanner Rule Auto-Generation**

AI가 시장 맥락과 후보 패턴을 분석해 스캐너 룰을 자동 생성/제안.
범위: LLM 기반 스캐너 룰 생성, 제안→사람 승인→DRAFT 버전 생성 흐름.
선행 조건: C-2.24 완료.

---

## Completed: C-2.24

구현 완료 파일:
- `app/domain/models/enums.py` — IntelligenceCandidateStatus 추가
- `app/domain/models/intelligence_candidate.py` (신규)
- `app/domain/models/__init__.py` — IntelligenceCandidate 등록
- `alembic/versions/f1a2b3c4d5e6_add_intelligence_candidates.py` (신규)
- `app/domain/repositories/intelligence_candidate.py` (신규)
- `app/services/intelligence_candidate_discovery_service.py` (신규)
- `app/api/v1/intelligence.py` — discover/candidates 엔드포인트 추가
- `app/core/config.py` — intelligence_discovery_scheduler_* 설정 추가
- `app/scheduler/jobs.py` — INTELLIGENCE_DISCOVERY_JOB_ID, run_intelligence_discovery_job 추가
- `app/scheduler/registry.py` — ControllableJob 등록
- `tests/test_c2_24_intelligence_candidate_discovery.py` (22 tests, all pass)

---

## Completed: C-2.23

구현 완료 파일:
- `app/domain/repositories/intelligence.py` — list_recent(), list_recent_for_bundle() 추가
- `app/services/theme_activity_service.py` — ThemeActivityService, compute_theme_synergy_bonus
- `app/services/analysis_bundle_service.py` — themes, recent_intelligence 키 추가
- `tests/test_c2_23_market_theme_context.py` (12 tests, all pass)

---

## Completed: C-2.22

구현 완료 파일:
- `app/market_intelligence/adapters/generic_rss_adapter.py`
- `app/market_intelligence/adapters/dart_disclosure_adapter.py`
- `app/market_intelligence/adapters/__init__.py`
- `app/services/intelligence_ingest_service.py`
- `app/api/v1/intelligence.py`
- `app/core/config.py` — intelligence_ingest_scheduler_* 추가
- `app/scheduler/jobs.py` — INTELLIGENCE_INGEST_JOB_ID 추가
- `app/scheduler/registry.py` — ControllableJob 등록
- `app/main.py` — intelligence_api router 등록
- `tests/test_c2_22_intelligence_ingestion.py` (19 tests, all pass)

---

## Completed: C-2.21.1b

구현 완료 파일:
- `alembic/versions/e3f4a5b6c7d8_add_intelligence_tables.py`
- `app/domain/models/intelligence.py`
- `app/domain/models/enums.py` — IntelligenceSourceType/Provider/MarketScope/EventStatus 추가
- `app/domain/repositories/intelligence.py`
- `app/market_intelligence/adapters/base.py`
- `tests/test_c2_21_1b_intelligence_foundation.py` (19 tests, all pass)
