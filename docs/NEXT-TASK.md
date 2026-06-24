# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current Task

**C-2.27 — Paper Experiment Autopilot**

| 필드 | 값 |
|------|----|
| **Status** | `DONE` |
| **Priority** | 높음 |
| **Type** | Feature (Intelligence proposal → paper 실험 materialize + 자동 conclude) |

---

## Goal

APPROVED IntelligenceStrategyProposal을 paper 실험으로 materialize하고, 실험 성과 비교를 자동화한다.

---

## Definition of Done

- [x] `IntelligenceStrategyProposal.experiment_id` nullable FK 추가
- [x] `IntelligenceStrategyProposal.materialized_at` nullable 추가
- [x] Alembic 마이그레이션 (`h1i2j3k4l5m6`)
- [x] `IntelligenceExperimentService.materialize()` — Strategy(DRAFT) + Experiment(RUNNING) 생성
- [x] `IntelligenceExperimentService.conclude()` — COMPLETED + ExperimentResult 저장
- [x] `IntelligenceExperimentService.check_stop_conditions()` — max_days / min_trades
- [x] `IntelligenceExperimentService.autopilot_check()` — RUNNING 실험 자동 점검
- [x] `POST /intelligence/strategy-proposals/{id}/materialize` API
- [x] `POST /intelligence/experiments/{id}/conclude` API
- [x] `intelligence_experiment_autopilot_scheduler_enabled=False` 기본 비활성 스케줄러 잡
- [x] ControllableJob 레지스트리 등록
- [x] 29개 테스트 전체 통과
- [x] StrategyVersion.status = DRAFT (ACTIVE 미생성)
- [x] auto_trade_enabled True 강제 False override
- [x] 중복 materialize 방지 (already_existed 반환)
- [x] ExperimentResult는 materialize 시 미생성 (conclude 시 생성)
- [x] 실전 주문 코드 변경 없음
- [x] 기존 ResearchPipelineService/AssignmentService 미변경

---

## Safety Constraints

- `KIS_REAL_TRADING_ENABLED=false` 유지
- 실주문 API 호출 없음
- StrategyVersion ACTIVE 자동 생성 없음
- auto_trade_enabled True 없음
- C-2.28 이후 작업 시작 금지

---

## Next Task After Completion

**C-2.28 — AI Evolution Loop**

실험 결과를 AI가 자동 분석하고, 개선 제안을 생성하며, 회고 결과가 다음 제안에 반영되는 루프 완성.
범위: 실험 결과 → AI 분석 자동 트리거, 개선 제안 자동 생성, 회고 → 제안 품질 개선 피드백.
선행 조건: C-2.27 완료.

---

## Completed: C-2.27

구현 완료 파일:
- `app/domain/models/intelligence_strategy_proposal.py` — experiment_id, materialized_at 필드 추가
- `alembic/versions/h1i2j3k4l5m6_add_experiment_link_to_intelligence_proposal.py` (신규)
- `app/services/intelligence_experiment_service.py` (신규)
- `app/api/v1/intelligence.py` — materialize/conclude 엔드포인트 추가
- `app/core/config.py` — intelligence_experiment_autopilot_* 설정 추가
- `app/scheduler/jobs.py` — INTELLIGENCE_EXPERIMENT_AUTOPILOT_JOB_ID 추가
- `app/scheduler/registry.py` — ControllableJob 등록
- `tests/test_c2_27_intelligence_paper_experiment.py` (29 tests, all pass)

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
