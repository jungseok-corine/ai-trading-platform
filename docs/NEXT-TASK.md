# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current State

**C-OPS-3.3 — Run History / Manual Run Result Visibility (`DONE`, us_market 한정)**

> **OPS 트랙** = Research/Operations Stabilization 트랙. 과거 phase-log의 C-3.x ID와 혼동을
> 피하려고 `C-OPS-3.x`로 별도 번호를 쓴다.

| 필드 | 값 |
|------|----|
| **마지막 완료 작업** | (분석) Manual Scanner Run → Candidate Event 코어 플로우 점검 — **이미 완성/연결됨**. Action Inbox v1/v2(푸시 완료). |
| **현재 상태** | 진행 중인 구현 작업 없음 |
| **다음에 필요한 것** | 코어 플로우의 *구체적* 다음 deepening을 사람이 선택 (아래) |

### Manual Scanner Run → Candidate Event 플로우 점검 결과 (구현 불필요)

이 플로우는 **이미 end-to-end로 구현·연결·테스트되어 있다**. 새로 만들 필요 없음(중복 금지).

| 단계 | 존재하는 것 |
|------|------------|
| 스키마 | `scanner_rules`, `scanner_rule_versions`, `candidate_events`(+`facts`/`matched_conditions`/`score`/`triggered_at`), `scanner_rule_proposals` |
| 수동 스캔 | `POST /candidates`(symbol_facts 직접) · `POST /scanner-rules/{rule}/versions/{ver}/scan-market`(DB 시세, `_semis_symbols()`로 bounded) → `CandidateService.scan()`가 `candidate_events` 영속 |
| 후보 조회 | `GET /candidates`(+facts) · `GET /candidates/analysis`(forward 수익률) |
| 프론트 | `ScannersSection`(룰 CRUD + 시장 스캔 버튼) · `CandidatesSection`(ID/종목/점수/매칭조건/**facts**/발견시각 + 성과분석 + 다음단계 '전략 배정') |
| 테스트 | `test_c2_31_symbol_facts::test_scan_market_computes_facts_and_records_candidate`, `test_c2_24_candidate_events`, `test_c2_23_scanner_rules`, `test_c4_universe_scan` 등 |

> 추가로, 코어 루프 전체(스캐너→후보→배정→실험→AI제안→승인→실전 승격 검토)가 이미 구현되어 있음
> (C-2.2x~C-2.39). 즉 "최소 코어 스텝"으로 새로 만들 것이 없다.

**구체적 다음 deepening 후보(사람 선택 필요 — 임의 착수 금지)**:
1. 스캔 대상 유니버스 확장(현재 `_semis_symbols` 한정). ⚠️ 시세/외부 호출량↑ → 명시적 한도·승인 필요.
2. 후보 이벤트를 Action Inbox 소스로 추가(읽기전용) + CandidatesSection으로 네비게이션.
3. 후보 outcome 보드 강화(조건/시간대별 forward 수익률 시각화 — 기존 analysis 확장).
4. 후보→실험 연결 깊이(수동 배정 결과를 실험으로 묶는 UX). 단, 자동 배정/자동매매 금지.

### 오버나잇 배치 결과 (미푸시, 리뷰 대기)

| # | 작업 | 커밋 | 상태 |
|---|------|------|------|
| 1 | Operations Digest auto_trade 문구 softening (실거래 OFF 시 paper/test 안내, 심각도 유지) | `a82b6dc` | ✅ |
| 2 | Operations Digest generated_at UI + 새로고침/무효화 | `63953f7` | ✅ |
| 3 | scheduler_runs 기록 일관성(dart_ingest/data_refresh/daily_report/operations_digest) | `09e8385` | ✅ |
| 4 | 읽기전용 Action Inbox v1 (`/action-inbox` + UI 카드, 조치 버튼 없음) | `d2c4fa6` | ✅ |
| 5 | Scanner Rule / Candidate Event foundation | — | ⏭️ **건너뜀** |

**Task 5 건너뛴 이유**: 스캐너/후보 기반은 **이미 성숙하게 구현되어 있음**.
존재하는 것 — 테이블 `scanner_rules` / `scanner_rule_versions` / `candidate_events` /
`scanner_rule_proposals`(+마이그레이션), 서비스 `candidate_service` / `scanner_proposal_*` /
`intelligence_candidate_discovery_service` 등, API `/candidates` / `/scanner-rules` /
`/scanner-proposals`. 새 "foundation"을 만들면 기존 스키마와 **중복/충돌** 위험 → 안전 규칙
("깨진 스키마 부분구현 금지")에 따라 미구현. 향후 작업은 기존 시스템의 *구체적 개선점*을
사람이 지정하는 방식 권장(예: 결정론적 수동 스캔 실행 UX, 후보 outcome 보드 등).

**남은 후속 후보**: 비모니터링 수집 잡(edgar_ingest/intraday_event_monitor/dart_finance/
intelligence_*)의 scheduler_runs 기록(일관성), Action Inbox 항목 클릭 네비게이션(v2),
us_market 브라우저 콘솔 에러(사용자 텍스트 필요).

> (소규모 UI, frontend-only) `real_trading_enabled=false`일 때 auto_trade_enabled 경고를 강한 빨간
> "운영 경고" 대신 paper/test 기록 수집 안내로 표시. EngineStatusCard는 safety-status에서
> real_trading_enabled를 읽어 분기(미확인 시 보수적으로 강한 경고 유지). backend invariants_ok·
> OperationsDigest severity·auto_trade 값은 미변경. OperationsSection 다이제스트의 "안전 불변식: …"
> 문구는 backend 생성이라 그대로 유지(softening은 후속 backend 작업 필요).

> (소규모 UI, frontend-only) Engine Status 카드의 "등록된 작업"을 긴 영어/한글 혼합 문자열 →
> 한글 라벨 칩 + 개수 표시로 개선했다. `scheduler.jobLabels`에 자율 잡 라벨 추가(미지정 id는 raw id
> fallback). backend/scheduler/safety/auto_trade 변경 없음.

> C-OPS-3.3는 frontend-only. Data Freshness 페이지의 us_market row에 `us_market_refresh` 관련
> 잡 정보(마지막 실행·최근 오류)와 **수동 갱신 버튼**을 추가했다. 버튼 클릭 시에만 run-now를
> 호출하며 page load에서는 외부 API를 호출하지 않는다. backend/scheduler/기본값 미변경.
> **사용자가 방향을 선택하기 전에는 새 기능을 시작하지 않는다.**

---

## Candidate Next Directions (사용자 선택 필요)

**C-OPS-3.4. Generic Freshness → Job Mapping + Run History (권장 후속)**
- C-OPS-3.3의 us_market 패턴을 다른 source(market_data/news/dart 등)로 일반화 — 단,
  source↔job 매핑이 불명확한 것부터 정리 필요. + 진짜 run history 테이블/수동 실행 상세 결과.
- startup catch-up 정책은 별도 검토(scheduler 동작 변경이라 신중).

**A. Approval Notification Integration**
- 백엔드 + 프론트엔드 (full-stack). Telegram/알림 provider opt-in.
- 알림 설정/시크릿(토큰)을 다루므로 **사용자의 명시적 승인 필요**. 실전 주문/매매 코드 변경 없음.
- 백엔드 `app/services/notifications/`와 config 키는 이미 존재하나 API 라우터·이벤트 연결·UI 없음.

**D. Product/UI Polish**
- 모바일 대시보드 사용성 개선. 매매 동작 변경 없음.

**⛔ 위 방향 중 하나를 사용자가 선택하기 전에는 다음 기능을 착수하지 않는다.**

---

## Completed: C-OPS-3.3

구현 완료 파일 (frontend-only):
- `frontend/src/components/research/DataFreshnessSection.tsx` — us_market 수동 갱신 카드
  (us_market → us_market_refresh 매핑, 마지막 실행·최근 오류 표시, 수동 갱신 버튼, 성공 후 refetch)
- `frontend/src/index.css` — 수동 갱신 카드 스타일(모바일)
- backend/migration/package 미변경. page load 자동 호출 없음. AutonomousJobsSection 미변경.

---

## Completed: C-OPS-3.2

구현 완료 파일 (frontend-only):
- `frontend/src/components/research/JobEnableConfirm.tsx` (신규) — ON 확인 게이트 패널
- `frontend/src/components/research/jobRiskLabels.tsx` (신규) — 공용 라벨/배지 추출
- `frontend/src/components/research/AutonomousJobsSection.tsx` — ON 경로 게이팅(disable/SAFE_ON/run-now 미변경)
- `frontend/src/index.css` — KEEP_OFF/MANUAL_FIRST 확인 패널 스타일
- 규칙: `recommended_state !== "ON_OK"` enable 시 확인. backend/scheduler/기본값 미변경.

---

## Completed: C-OPS-3.1

구현 완료 파일:
- `backend/app/scheduler/registry.py` — `ControllableJob`에 read-only 메타데이터 필드 + 17개 잡 채움
- `backend/app/services/scheduler_control_service.py` — `AutonomousJobStatus`에 메타데이터 전달
- `backend/app/api/v1/autonomous_jobs.py` — API 응답에 메타데이터 additive 노출
- `frontend/src/api/client.ts` — `AutonomousJob` 타입에 메타데이터 필드
- `frontend/src/components/research/AutonomousJobsSection.tsx` — 위험도/추천/특성 배지 + 설명 + 안전 고지
- `frontend/src/index.css` — 배지 스타일(모바일 wrap)
- `backend/tests/test_c3_1_job_metadata.py` (8 tests)
- 잡 기본 enabled 상태·scheduler 실행 동작·toggle/run-now 미변경. 실제로 잡을 켜지 않음.

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
