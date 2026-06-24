# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current Task

**C-2.26 — Strategy Assignment Automation**

| 필드 | 값 |
|------|----|
| **Status** | `DONE` |
| **Priority** | 높음 |
| **Type** | Feature (IntelligenceCandidate 기반 heuristic 전략 배정 제안) |

---

## Goal

PENDING IntelligenceCandidate에 적합한 strategy_type과 파라미터를 heuristic으로 제안.
제안은 항상 pending. 사람 승인 시 candidate → PROMOTED. StrategyVersion 미생성.

---

## Definition of Done

- [x] `IntelligenceStrategyProposalStatus` enum 추가
- [x] `IntelligenceStrategyProposal` 모델 신규 구현
- [x] Alembic 마이그레이션 (`g1h2i3j4k5l6`)
- [x] `IntelligenceStrategyProposalRepository` (create/get/list/approve/reject)
- [x] `IntelligenceStrategyAssignmentGenerator` (heuristic, LLM 미사용)
- [x] 8개 heuristic 매칭 규칙 + fallback
- [x] 중복 방지 (`existing_for_candidate` + `dedup_hash`)
- [x] `POST /intelligence/strategy-proposals/generate` API
- [x] `GET /intelligence/strategy-proposals` API
- [x] `GET /intelligence/strategy-proposals/{id}` API
- [x] `POST /intelligence/strategy-proposals/{id}/approve` API
- [x] `POST /intelligence/strategy-proposals/{id}/reject` API
- [x] 30개 테스트 전체 통과
- [x] StrategyVersion 자동 생성 없음
- [x] StrategyAssignmentLog 자동 생성 없음
- [x] auto_trade_enabled True 없음
- [x] LLM/AnalysisProvider 호출 없음
- [x] 기존 StrategyAssignmentLog FK 미수정
- [x] 기존 AssignmentService.assign() 미변경
- [x] 주문·실거래 코드 변경 없음

---

## Safety Constraints

- `KIS_REAL_TRADING_ENABLED=false` 유지
- 실주문 API 호출 없음
- StrategyVersion 자동 생성 없음
- AI 제안 자동 적용 금지 (pending → approved 자동 전환 없음)
- C-2.27 이후 작업 시작 금지

---

## Next Task After Completion

**C-2.27 — Paper Experiment Autopilot**

배정된 전략을 paper에서 자동 실험하고 성과를 자동 측정.
범위: 실험 자동 시작/종료 조건, 성과 지표 자동 계산, 실험 비교 자동화.
선행 조건: C-2.26 완료.

---

## Completed: C-2.26

구현 완료 파일:
- `app/domain/models/enums.py` — IntelligenceStrategyProposalStatus 추가
- `app/domain/models/intelligence_strategy_proposal.py` (신규)
- `app/domain/models/__init__.py` — IntelligenceStrategyProposal 등록
- `alembic/versions/g1h2i3j4k5l6_add_intelligence_strategy_proposals.py` (신규)
- `app/domain/repositories/intelligence_strategy_proposal.py` (신규)
- `app/services/intelligence_strategy_assignment_generator.py` (신규)
- `app/api/v1/intelligence.py` — strategy-proposals 5개 엔드포인트 추가
- `tests/test_c2_26_intelligence_strategy_assignment.py` (30 tests, all pass)

---

## Completed: C-2.25

구현 완료 파일:
- `app/services/intelligence_scanner_proposal_generator.py` (신규)
- `app/api/v1/intelligence.py` — scanner-proposals/generate 엔드포인트 추가
- `app/core/config.py` — intelligence_scanner_proposal_scheduler_* 설정 추가
- `app/scheduler/jobs.py` — INTELLIGENCE_SCANNER_PROPOSAL_JOB_ID, run_intelligence_scanner_proposal_job 추가
- `app/scheduler/registry.py` — ControllableJob 등록
- `tests/test_c2_25_intelligence_scanner_proposal.py` (18 tests, all pass)

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
