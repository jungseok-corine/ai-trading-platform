# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current Task

**C-2.28 — AI Evolution Loop**

| 필드 | 값 |
|------|----|
| **Status** | `DONE` |
| **Priority** | 높음 |
| **Type** | Feature (실험 결과 → AI 분석 → 개선 제안 자동 생성 루프) |

---

## Goal

COMPLETED intelligence experiment를 AI가 자동 분석하고, 개선 제안(StrategyProposal)을 생성하며, 회고 결과가 다음 제안에 반영되는 루프를 완성한다.

---

## Definition of Done

- [x] `IntelligenceStrategyProposal` evolution 추적 필드 4개 추가
- [x] Alembic 마이그레이션 (`i1j2k3l4m5n6`)
- [x] `IntelligenceEvolutionService.analyze_experiment()` — LLM 분석 + pending StrategyProposal 생성
- [x] `IntelligenceEvolutionService.evolution_loop()` — 미분석 제안 일괄 처리
- [x] `IntelligenceEvolutionService.build_evolution_context()` — 순수 함수 컨텍스트 빌더
- [x] `IntelligenceStrategyProposalRepository.find_by_experiment_id()` 메서드 추가
- [x] `IntelligenceStrategyProposalRepository.list_pending_evolution()` 메서드 추가
- [x] `POST /intelligence/experiments/{id}/analyze` API
- [x] `intelligence_evolution_scheduler_enabled=False` 기본 비활성 스케줄러 잡
- [x] ControllableJob 레지스트리 등록
- [x] 29개 테스트 전체 통과
- [x] 생성된 StrategyProposal.auto_trade_enabled=False 강제
- [x] 생성된 StrategyProposal.status=PENDING (자동 승인 없음)
- [x] 생성된 StrategyProposal.source="intelligence_evolution"
- [x] trades_count < min_trades → 제안 생성 없음 (analyzed_no_proposal)
- [x] conclude() 내부 자동 호출 없음
- [x] IntelligenceStrategyProposalRead에 evolution 4개 필드 노출
- [x] 실전 주문 코드 변경 없음
- [x] DailyAnalysisService 미변경

---

## Safety Constraints

- `KIS_REAL_TRADING_ENABLED=false` 유지
- 실주문 API 호출 없음
- AI 제안 자동 승인 없음
- auto_trade_enabled True 없음
- C-2.29 이후 작업 시작 금지

---

## Next Task After Completion

**C-2.29 — Live Promotion Gate**

검증된 전략의 실전 배치를 위한 승격 게이트 UI/UX 완성.
범위: 승격 준비도 자동 평가, 실전 배치 승인 UI, 승격 후 모니터링 알림.
선행 조건: C-2.28 완료.

---

## Completed: C-2.28

구현 완료 파일:
- `app/domain/models/intelligence_strategy_proposal.py` — evolution 추적 필드 4개 추가
- `alembic/versions/i1j2k3l4m5n6_add_evolution_fields_to_intelligence_proposal.py` (신규)
- `app/domain/repositories/intelligence_strategy_proposal.py` — find_by_experiment_id, list_pending_evolution 추가
- `app/services/intelligence_evolution_service.py` (신규)
- `app/api/v1/intelligence.py` — analyze 엔드포인트 + evolution 필드 노출
- `app/core/config.py` — intelligence_evolution_* 설정 추가
- `app/scheduler/jobs.py` — INTELLIGENCE_EVOLUTION_JOB_ID 추가
- `app/scheduler/registry.py` — ControllableJob 등록
- `tests/test_c2_28_intelligence_evolution_loop.py` (29 tests, all pass)

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
