# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current State

**활성 구현 작업 없음 (No active implementation task).**

| 필드 | 값 |
|------|----|
| **마지막 완료 작업** | C-2.30.1 — Bulk Approval Safety Guard (`DONE`) |
| **현재 상태** | 진행 중인 구현 작업 없음 |
| **다음에 필요한 것** | 다음 로드맵 방향을 사람이 선택해야 함 (아래 후보 참조) |

> ⚠️ 신규 Phase 로드맵(ROADMAP.md "다음 작업 로드맵")이 C-2.30까지 모두 완료되어,
> 명확히 정의된 다음 작업이 없다. **사용자가 방향을 선택하기 전에는 새 기능을 시작하지 않는다.**

---

## Candidate Next Directions (사용자 선택 필요)

**A. Approval Notification Integration**
- 백엔드 + 프론트엔드 (full-stack)
- Telegram 또는 알림 provider opt-in
- 알림 설정/시크릿(토큰)을 다루므로 **사용자의 명시적 승인 필요**
- 실전 주문/매매 코드 변경 없음
- 참고: 백엔드 `app/services/notifications/`(telegram 등)와 config 키는 이미 존재하나,
  알림 API 라우터·승인 이벤트 연결·프론트 알림 UI는 없음. `notification_provider="none"` 기본값.

**B. Research/Operations Stabilization**
- 알려진 10개 pre-existing 실패 테스트 정리
- scheduler/test 환경 오염 정리
- 기능 추가 전 신뢰성 개선

**C. Intelligence Pipeline Productionization**
- 어떤 자율 스케줄러 잡을 켤 수 있는지 결정
- 더 안전한 잡 기본값, 실행 로그, 수동 실행 UX 추가
- 여전히 실전 매매 없음

**D. Product/UI Polish**
- 모바일 대시보드 사용성 개선
- 매매 동작 변경 없음

**⛔ 위 방향 중 하나를 사용자가 선택하기 전에는 다음 기능을 착수하지 않는다.**

---

## Completed: C-2.30.1

구현 완료 파일 (frontend-only):
- `frontend/src/components/research/BulkApproveConfirm.tsx` (신규)
- `frontend/src/components/research/ProposalsSection.tsx` — 일괄 승인 확인 게이트 통합
- `frontend/src/components/research/ScannerProposalsSection.tsx` — 동일 + 일괄 거절 confirm
- `frontend/src/index.css` — 확인 게이트 강조 스타일

## Completed: C-2.30

구현 완료 파일 (frontend-only):
- `frontend/src/components/research/StrategyProposalReportCard.tsx` (신규)
- `frontend/src/components/research/ScannerProposalReportCard.tsx` (신규)
- `frontend/src/components/research/LivePromotionReviewCard.tsx` (신규)
- `frontend/src/components/research/TransitionPlanView.tsx` (신규)
- `frontend/src/components/research/approvalBlocks.tsx` (신규)
- `frontend/src/components/research/safetyCopy.ts` (신규, 정적 안전 문구)
- `frontend/src/api/research.ts` — transition-plan / live-readiness / live-promote 바인딩
- `frontend/src/types/research.ts` — TransitionPlan / LiveReadinessReport / LivePromotion* 타입
- 제안 섹션 통합 + stale "DRAFT" → "TESTING" 정정 + 모바일 반응형 CSS
- **보류**: Telegram/모바일 푸시 알림 통합 (별도 작업, 사용자 승인 필요)

## Completed: C-2.29.1

구현 완료 파일:
- `app/services/status_transition_planner.py` (신규)
- `app/domain/repositories/experiment.py` — list_running_for_strategy_version 추가
- `app/services/proposal_service.py` — DRAFT → TESTING
- `app/services/scanner_proposal_service.py` — DRAFT → TESTING
- `app/api/v1/strategy_proposals.py` — transition-plan 엔드포인트 추가
- `app/api/v1/scanner_proposals.py` — transition-plan 엔드포인트 추가
- `tests/test_c2_29_1_status_transition_planner.py` (22 tests, all pass)
- `tests/test_c2_27_ai_proposals.py` — DRAFT → TESTING 업데이트
- `tests/test_c2_39_scanner_proposals.py` — DRAFT → TESTING 업데이트
- `tests/test_c2_25_intelligence_scanner_proposal.py` — DRAFT → TESTING 업데이트

## Completed: C-2.29

구현 완료 파일:
- `app/domain/models/promotion.py` — LivePromotionRecord 모델 추가
- `alembic/versions/j1k2l3m4n5o6_add_live_promotion_records.py` (신규)
- `app/domain/repositories/promotion.py` — LivePromotionRecordRepository 추가
- `app/services/live_promotion_gate_service.py` (신규)
- `app/api/v1/live_promotion.py` (신규)
- `app/main.py` — live_promotion_api 라우터 등록
- `app/domain/models/__init__.py` — LivePromotionRecord 등록
- `tests/test_c2_29_live_promotion_gate.py` (26 tests, all pass)

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
