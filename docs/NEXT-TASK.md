# NEXT-TASK.md — Claude가 다음에 무엇을 할지 판단하는 기준 파일

> Claude는 세션 시작 시 이 파일을 먼저 읽는다.
> 작업 완료 시 이 파일의 Status를 DONE으로 갱신하고, "Next Task After Completion"을 새 Current Task로 업데이트한다.

---

## Current State

**Candidate → Strategy Assignment Proposal — 읽기 전용 미리보기(Option A) `DONE` + 영속 PENDING(Option B/V1) `DONE`**

**Option A (읽기 전용 미리보기, `DONE`)**: CandidatesSection의 각 후보 행에 **"전략 제안 보기"**
버튼 → 후보 `matched_conditions`/`score` 기반 검토 힌트 패널(`CandidateStrategyProposalPanel.tsx`).

**Option B / V1 (영속 PENDING 제안, `DONE`)**: 이제 미리보기 패널의 **"PENDING 제안으로 저장"**
버튼으로 제안을 *저장*할 수 있다. 새 테이블 `candidate_strategy_proposals`에 PENDING 레코드만
만든다. **실행/배정/버전 생성/실험/자동매매/주문이 전혀 없다.**

- 모델/마이그레이션: `candidate_strategy_proposal.py` / `k1l2m3n4o5p6_add_candidate_strategy_proposals`
  (candidate_event_id FK CASCADE, symbol_code, suggested_strategy_type, rationale, confidence,
  suggested_parameters JSONB, status[pending/approved/rejected]=pending, source, reviewed_*).
- 서비스: `candidate_strategy_proposal_service.py` — body 미지정 시 matched_conditions에서 안전한
  기본 strategy_type 유추, registered_types 검증, `auto_trade_enabled` 파라미터 제거,
  같은 후보+전략 PENDING 중복은 기존 것 반환. `review()`는 **status만** approved/rejected 갱신
  (어떤 실행도 안 함).
- API(candidates.py): `POST/GET /candidates/{id}/strategy-proposals`,
  `GET /candidate-strategy-proposals`, `PATCH /candidate-strategy-proposals/{id}/review`.
- 테스트: `tests/test_candidate_strategy_proposal.py` (12) — PENDING 생성, 필드 저장, 404,
  중복, **StrategyVersion/StrategyAssignmentLog/Trade 미생성**, review status-only.

**왜 별도 테이블인가**: 기존 어떤 제안 테이블도 `candidate_event`에 안 맞는다 —
`StrategyAssignmentLog`는 status 없는 *확정 로그*, `IntelligenceStrategyProposal`은
`intelligence_candidates`(NOT NULL FK) 종속, `StrategyProposal`은 `strategies`(NOT NULL FK)·
파라미터 변경용. force-fit 금지 규칙에 따라 신규 테이블로 분리.

**Proposal Review UX (frontend-only, `DONE`)**: `CandidateStrategyProposalPanel`의 "저장된 제안"
영역을 검토 리스트로 바꿨다. PENDING 제안마다 **검토 메모(선택) + "제안 승인" / "제안 거절"** 버튼이
있고, 클릭 시 `PATCH /candidate-strategy-proposals/{id}/review`로 **status만** approved/rejected로
바꾼다(`reviewed_by="manual_user"`). 결과로 "상태만 변경됨 — 실행/배정/전략 생성은 하지 않았습니다."
를 표시하고 목록을 refetch한다. backend 변경 없음(기존 PATCH 엔드포인트 사용). 버튼 라벨은
"제안 승인/거절"만 사용하며 실행을 암시하는 라벨은 쓰지 않는다.

**Paper Experiment Preparation (`DONE`)**: APPROVED 제안에서 사람이 명시적으로 **"Paper 실험 준비"**
하면 DRAFT paper 실험 골격을 만든다. **준비는 실행이 아니다.**

- 마이그레이션 `l1m2n3o4p5q6`: `candidate_strategy_proposals`에 `experiment_id`(FK experiments SET NULL)
  + `prepared_at` 추가(둘 다 nullable, additive).
- 서비스 `candidate_proposal_experiment_service.py` `prepare()`: APPROVED만 허용(pending/rejected→422),
  Strategy(paper 전용) + StrategyVersion(**DRAFT**, `auto_trade_enabled=False` 강제) +
  Experiment(**DRAFT**, started_at=None) + Variant(CHALLENGER) 생성, 제안에 experiment_id/prepared_at
  연결. 이미 준비됐으면 기존 반환(idempotent).
- API: `POST /candidate-strategy-proposals/{id}/prepare-paper-experiment`.
- 프론트: APPROVED 행에만 "Paper 실험 준비" 버튼 → 성공 시 "Paper 실험 준비됨 — 실행/자동매매 아님 (DRAFT)".
- 테스트 `tests/test_candidate_proposal_experiment.py` (8): pending/rejected 거부, DRAFT 실험/버전,
  auto_trade=False, idempotent, **runner의 list_active(ACTIVE/TESTING)에 안 잡힘**, StrategyAssignmentLog/
  Trade 미생성.

**안전 근거**: runner는 `list_active()`(ACTIVE/TESTING)만 실행 → DRAFT 버전은 절대 안 돌아간다.
Experiment도 DRAFT(RUNNING 아님) → 실행/오토파일럿 대상 아님. 주문/브로커/실계좌/AssignmentService 없음.

**Prepared Paper Experiment Review UI (frontend-only, `DONE`)**: 준비된 제안 행에서 **읽기 전용**으로
실험을 검토한다. `CandidateStrategyProposalPanel`의 `PreparedExperimentView`가 기존
`GET /experiments/{id}`로 실제 상태를 읽어 표시: "Paper 실험 준비됨" + 실험 #id + **DRAFT 상태** 배지 +
`started_at===null`이면 "실행 전" + 전략 타입/종목/variant 수 + 준비 시각 + "자동매매 아님 · 주문 없음 ·
검토용". **실행·시작·활성화·승격 버튼 없음(읽기 전용).** backend 변경 없음(기존 GET 재사용).

**Paper Experiment Readiness Gate (`DONE`, readiness-only)**: 준비된 DRAFT 실험을 사람이 **명시 확인**
(confirmed=true + confirmed_by)으로 "paper 테스트 준비됨"이라고 **승인 기록만** 한다. **어떤 상태도
바꾸지 않는다(non-runnable 유지) — 실행/자동매매/주문/실거래가 아니다.**

- **안전 분석(코드 확인)**: runner(`strategy_runner_service`)는 `list_active()`=ACTIVE/TESTING만
  실행한다. 즉 버전을 TESTING으로 올리면 default 활성인 `strategy_scheduler`가 잡아 매 tick
  `signal_logs`를 *계속 생성*한다(주문은 없지만 실질적 백그라운드 실행 효과). 그래서 이 단계는
  **버전을 TESTING으로 올리지 않는다.** 준비 승인은 상태를 바꾸지 않으므로 runner가 절대 잡지
  않는다(신호 기록 시작 없음).
- 서비스 `approve_paper_testing_readiness(proposal_id, confirmed, confirmed_by)`: confirmed/ confirmed_by
  필수, proposal approved + 준비됨 + 실험 DRAFT + 모든 버전 DRAFT(+자동매매 토글 off) 검증 후,
  승인 사실만 제안의 `suggested_parameters._paper_testing_ready_{at,by}`에 기록(마이그레이션 없음).
  **StrategyVersion/Experiment 상태·started_at 변경 없음.** 이미 승인됐으면 idempotent.
- API: `POST /candidate-strategy-proposals/{id}/approve-paper-readiness`.
- 프론트: DRAFT 준비 실험에 확인 체크박스("자동매매 없이 paper 테스트 준비만 승인합니다 (DRAFT 유지 ·
  신호 기록 시작 아님)") + "Paper 테스트 준비 승인" 버튼 → 성공 시 "준비 승인됨 — 아직 실행 전 · DRAFT
  유지 · 신호 기록 시작 아님 · 자동매매 아님 · 주문 없음". 배지는 "DRAFT 유지".
- 테스트 `tests/test_candidate_paper_readiness.py` (10): confirmed/ confirmed_by 게이트,
  pending/rejected/미준비 거부, **상태 불변(DRAFT 유지·started_at null)**, signal_logs/Trade/
  AssignmentLog 미생성, **runner 대상 0(ACTIVE/TESTING 없음)**, idempotent.

**Paper Signal Logging Start (Design B, `DONE`)**: 준비·준비승인된 제안에서 사람이 명시적으로
**Paper Signal Session**을 시작하면, 전용 signal-only 스케줄러 잡이 SignalLog만 기록한다.

- **안전 구조**: 연결된 StrategyVersion은 **DRAFT 그대로** 유지된다 → 기존 trade-capable runner
  (`list_active`=ACTIVE/TESTING)는 절대 보지 못한다. 전용 잡 `paper_signal_session_runner`는
  **TradeService를 구성하지 않고** `SignalService.generate_and_log_signal`만 호출한다 → 주문/체결/
  Trade/브로커 주문 없음. broker_client는 시세(캔들) 조회에만 쓰인다.
- 모델/마이그레이션: `paper_signal_session.py` / `m1n2o3p4q5r6_add_paper_signal_sessions`
  (proposal FK CASCADE, experiment/version/candidate FK SET NULL, status active/stopped, started_by,
  last_run_at, run_count, signal_count). additive only.
- 서비스 `paper_signal_service.py`: `start_session_from_candidate_strategy_proposal`(confirmed+
  confirmed_by+approved+prepared+**readiness 승인**+버전 DRAFT+자동매매 off, 중복 active 거부),
  `stop_session`, `list_sessions`, `run_due_sessions`(active 세션마다 SignalLog만, 상태 불변).
- 잡: `run_paper_signal_session_job` — **기본 비활성**(CONTROLLABLE_JOBS, MANUAL_FIRST), TradeService
  미구성. config `paper_signal_session_runner_enabled=False`.
- API: `POST /candidate-strategy-proposals/{id}/paper-signal-sessions`,
  `GET /paper-signal-sessions?status=`, `POST /paper-signal-sessions/{id}/stop`.
- 프론트: 준비승인 후 "Paper 신호 기록 시작"(확인 체크박스 "주문 없이 SignalLog만 기록합니다") +
  active 세션이면 "Paper 신호 기록 중 · 주문 없음 · 자동매매 아님" + "신호 기록 중지".
- 테스트 `tests/test_paper_signal_session.py` (13): 게이트, 상태 불변, run_due가 SignalLog만 생성·
  Trade/AssignmentLog 미생성·버전 DRAFT 유지, 중복 거부, 잡 기본 비활성.

**핵심 불변식**: 버전 DRAFT 유지 → trade-capable runner 비대상. 전용 잡은 TradeService/주문 클라이언트
미구성 → 주문 불가능. SignalLog만 기록. stop하면 신호 중단. 잡 기본 OFF.

**Paper Signal Session Outcome Board (`DONE`, read-only)**: 세션이 만든 SignalLog의 forward 수익률을
market_data로 계산해 세션 단위로 집계·표시한다.

- **추적(Design A)**: SignalLog에 `paper_signal_session_id`(FK SET NULL) 추가(마이그레이션
  `n1o2p3q4r5s6`). `run_due_sessions`가 생성한 신호에 세션 id를 남겨 **정확 귀속**(세션 재시작 시에도
  version_id로는 구분 불가 → 컬럼 필요). 일반 strategy_runner 신호는 NULL.
- 서비스 `paper_signal_outcome_service.py`(읽기 전용): SignalLog를 session_id로 모아
  `SignalOutcomeService`로 forward 수익률을 계산, horizon(5/15/30/60)별 집계. **Trade/Order/
  AssignmentLog 미생성, 상태 전환 없음, 스케줄러 미점화.**
- API: `GET /paper-signal-sessions/{id}/outcomes?horizon_minutes=30` → signal_count/analyzed/pending/
  win_rate/avg·best·worst_return_pct/by_action/recent_signals(signal_id,created_at,action,entry,
  return_pct,is_win,outcome_status).
- 프론트: 세션(active/stopped)에 outcome 요약(신호/분석/대기/승률/평균/최고/최저) 표시. 신호 없으면
  "아직 기록된 SignalLog가 없습니다". 읽기 전용 — run/start/enable 컨트롤 추가 없음.
- 테스트 `tests/test_paper_signal_outcomes.py` (8): empty/pending/analyzed/세션필터/읽기전용
  (Trade·AssignmentLog 미생성)/invalid horizon/404/API.

**Paper Signal Session AI Analysis Input (`DONE`, read-only 패키징)**: 세션 기준으로 LLM에 바로 넘길
수 있는 structured 분석 입력(payload)을 만든다. **AI 호출 없음, 제안 생성 없음, DB 쓰기 없음.**

- 서비스 `paper_signal_analysis_input_service.py`: 세션 + 연결된 candidate_strategy_proposal +
  candidate_event + experiment + strategy_version를 모아 결정론적 payload 구성. outcome 요약은
  기존 `PaperSignalOutcomeService` 재사용. recent_signals 등 bounded(상한 10).
- payload 섹션: session(메타) / candidate_proposal(후보·제안 추적: score·matched·facts·rationale·
  confidence·readiness·prepared_experiment) / experiment_version(상태·auto_trade=false·signal_only·
  trades_count=0) / outcome_summary(horizon·win_rate·avg/best/worst·by_action·recent_signals) /
  safety(real_trading=false·auto_trade=false·job disabled·trades=0) / limitations.
- API: `GET /paper-signal-sessions/{id}/analysis-input?horizon_minutes=30` (404/422), 읽기 전용 JSON.
- 프론트: outcome 요약 아래 "AI 분석 입력 보기"(접힘 JSON 미리보기, 읽기 전용 — "AI 호출/제안 생성 없음").
- 테스트 `tests/test_paper_signal_analysis_input.py` (9): 404/422/세션메타/추적/outcome/상한/
  **DB 무변경(AiAnalysisRun·AiModelResponse·Trade·SignalLog 미생성, 상태 불변)**.

**Paper Signal Session AI Analysis Run (V1, `DONE`, 리포트 전용)**: 사람이 명시 확인하면 세션
분석 입력으로 AI 분석 **리포트**를 생성·저장한다. **AI 제안 생성 없음, 전략/세션/실험/주문 변경 없음.**

- 기존 `AiAnalysisRun`/`AiModelResponse` 재사용(D-15). 마이그레이션 `o1p2q3r4s5t6`(additive enum):
  `analysis_target_type += paper_signal_session`, `analysis_run_type += paper_signal_session_analysis`,
  index `ix_ai_analysis_runs_target(target_type,target_id)`. enum 추가는 autocommit_block 사용,
  downgrade는 index만 제거(enum 값은 PG 관례상 유지).
- 서비스 `paper_signal_analysis_run_service.py`: confirmed+confirmed_by+horizon(5/15/30/60)+세션 검증 →
  `PaperSignalAnalysisInput` → bounded markdown prompt(`paper_signal_analysis_prompt_service.py`,
  20k 상한 + 실거래/주문/제안자동생성 금지 CRITICAL INSTRUCTIONS) → **provider factory**(기본 fake) 호출 →
  `AiAnalysisRun(target_type=paper_signal_session, target_id=session_id, strategy_version_id 추적)` +
  `AiModelResponse` 저장. provider 실패 시 FAILED run + error response.
- API: `POST/GET /paper-signal-sessions/{id}/analysis-runs`(+ 기존 `GET /analysis-runs/{id}` 재사용).
- 프론트: outcome 요약 아래 "AI 분석 리포트 생성"(확인 체크박스 "AI 분석만 생성하며 전략/주문/세션
  상태는 변경하지 않습니다") + 이전 run 목록 + 최근 리포트. 라벨: "분석 리포트 · 제안 생성 아님 ·
  자동매매 아님".
- 테스트 `tests/test_paper_signal_analysis_run.py` (10): 게이트/404/422/fake run+response/타깃 저장/
  payload·prompt bounded/목록/provider 실패→FAILED/**제안·전략·실험·신호·거래·배정 미생성·상태 불변**.

**AI Analysis Report Review UX (frontend-only, `DONE`)**: 세션 AI 분석 run을 사람이 검토하기 쉽게
표시한다. 기존 API(`GET /paper-signal-sessions/{id}/analysis-runs`, `GET /analysis-runs/{id}`)가 이미
충분한 필드를 주므로 **backend 변경 없음**.

- 최근 리포트 패널: 상태 배지(succeeded/failed/running) + 메타(provider/model·생성시각·latency·tokens·
  prompt 길이·잘림 여부). **성공이면 본문, 실패면 error_message(빨강), 실행 중이면 안내** — 실패 run도
  명확히 표시(이전엔 본문 없으면 사라졌음).
- 이전 분석 run 목록(접힘): run별 상태 배지 + 메타 + 실패 시 에러.
- 확인 게이트("AI 분석만 생성하며 전략/주문/세션 상태를 변경하지 않습니다")·"AI 분석 리포트 생성" 버튼
  유지. 라벨: "AI 분석 리포트 · 제안 생성 아님 · 자동매매 아님 · 전략 변경 없음".
- 프론트 type에 already-returned 필드(started/completed_at·truncated·warnings·prompt/completion_tokens·
  finish_reason) 노출. read-only — 새 mutation 없음(기존 gated 생성 버튼만).

**M1 — Paper Signal AI Improvement Proposal (`DONE`)**: 세션 AI 분석 run(succeeded)에서 사람이 명시
확인하면 **PENDING StrategyProposal 초안**을 만든다. **승인/머티리얼라이즈/버전 생성 없음.**

- 기존 `StrategyProposal` 재사용(D-16, 마이그레이션 없음). 추적: `ai_analysis_run_id` →
  `AiAnalysisRun.target_id`(=세션 id), `base_version_id`=세션 DRAFT 버전.
- 서비스 `paper_signal_improvement_proposal_service.py`: confirmed+confirmed_by 게이트, run succeeded +
  target=paper_signal_session + 본문 있는 응답 + 버전 링크 검증, 같은 run 중복 PENDING 거부(409).
  **구조화 경로**(리포트가 검증 가능한 JSON 가설이면 `AnalysisProposalService`로 검증된 param 변경 제안),
  **폴백**(근거 부족이면 현재 버전 파라미터 그대로의 무변경 초안 + "insufficient evidence — no parameter
  change recommended", source="paper_signal_analysis"). 파라미터를 지어내지 않는다. **PENDING만.**
- API: `POST/GET /analysis-runs/{id}/improvement-proposals`. 검토(승인/거절)는 기존 `ProposalsSection`에서.
- 프론트: succeeded 리포트 아래 확인 체크박스("검토용 제안만 생성하며 전략/주문/세션 상태는 변경하지
  않습니다") + "개선 제안 초안 만들기" → 생성 후 "검토 대기(PENDING) · 제안 #id · 승인 전까지 아무 것도
  적용되지 않음". approve/apply 버튼 없음.
- 테스트 `tests/test_paper_signal_improvement_proposal.py` (13): 게이트/404/422(failed·target·content·
  version)/409 중복/PENDING 생성/구조화·폴백/**approve 미호출·StrategyVersion·Experiment·Signal·Trade·
  AssignmentLog 미생성·상태 불변**.

**⛔ 명시적으로 이연(deferred)**: 제안 **승인 → DRAFT/TESTING 버전 생성/머티리얼라이즈**(기존
`proposal_service.approve`는 TESTING=runner-eligible이므로 별도 신중 처리 필요), 전략 버전 승격(ACTIVE),
실주문/자동매매, 실험 compare 자동화, 실전 승격은 다음 작업(별도 승인 게이트). M1은 **PENDING 초안
생성까지만** — 전략/세션/제안/실험 무변경, 주문/잡 효과 없음.

**M2.1 — Read-only Paper Signal Session Comparison (`DONE`)**: 두 기존 PaperSignalSession을 신호
outcome 지표로 나란히 비교한다. **순수 읽기 전용 — 생성/상태변경/주문/잡 효과 전혀 없음.**

- 서비스 `paper_signal_comparison_service.py`(`PaperSignalComparisonService.compare`): horizon(5/15/30/60)
  검증, 같은 세션 id 거부(`SameSessionError`→422), 각 세션에 기존 `PaperSignalOutcomeService.session_outcomes`
  재사용(없으면 `SessionNotFoundError`→404). baseline/challenger 요약 + deltas(challenger−baseline,
  by_action 포함) + warnings 구성. strategy_version_id는 세션 레코드에서 읽음. **DB 쓰기 없음.**
- warnings(실패 아님): 종목 상이 시 "different symbols…", 분석 신호 수 < 5면 "Low analyzed signal count…".
  매수/매도 추천·통계적 유의성 주장 없음.
- API: `GET /paper-signal-sessions/{baseline_id}/compare/{challenger_id}?horizon_minutes=30`
  (candidates.py 라우터 재사용). 200 payload / 404 세션 없음 / 422 같은 id·invalid horizon.
- 프론트(`CandidateStrategyProposalPanel`): 제안에 세션이 2개 이상이면 기준 세션 vs 사용자가 입력한
  비교 세션 id + horizon으로 "신호 성과 비교 보기" → 지표/델타 표 + 경고 표시. 라벨: "읽기 전용 · 주문 없음 ·
  자동매매 아님 · 전략/세션 상태 변경 없음". 생성/시작/승인 컨트롤 없음.
- 테스트 `tests/test_paper_signal_comparison.py` (11): 404(baseline/challenger)/422(same·horizon)/요약·델타·
  warning(symbol·low count)/**세션·SignalLog·StrategyVersion·Experiment·Trade·AssignmentLog 미생성·상태 불변**/API.
- 마이그레이션 없음. `approve` 미호출. challenger 버전/세션/실험 미생성. (D-17 §3)

**M2.2 — DRAFT-only Signal Challenger Preparation (`DONE`)**: paper_signal 트랙 PENDING
StrategyProposal에서 사람이 명시 확인하면 **DRAFT 전용** challenger StrategyVersion을 준비한다.
**제안 승인 아님 · 공유 approve(TESTING) 경로 미사용 · TESTING/ACTIVE 미생성 · 세션 시작/주문/잡 없음.**

- 서비스 `paper_signal_challenger_service.py`(`PaperSignalChallengerService.prepare_from_proposal`):
  confirmed+confirmed_by 게이트, 제안 존재(404), `source=="paper_signal_analysis"`(422), status PENDING(422),
  `ai_analysis_run_id` + run `target_type==paper_signal_session`(422), `base_version_id` + 버전 존재·동일
  strategy(422), 병합 파라미터 strategy_type 등록 검증(422), `created_version_id` 이미 있으면 409.
  파라미터 = **base 위에 suggested 덮어쓰기**(필수 base 필드 보존) + `auto_trade_enabled` **항상 False 강제**.
  `StrategyService.create_version(status=DRAFT)`로 **DRAFT** 버전 1개만 생성(`approve` 미호출). 추적은
  `proposal.created_version_id` 링크로만 — **상태는 PENDING 유지**(review 필드 미설정). auto_trade=true 요청은
  override + warning, base와 동일하면 no_change=true + "reviewable clone" warning.
- **approve-path 가드(D-18)**: 공유 `POST /strategy-proposals/{id}/approve`는 signal 트랙 제안을 **422**로 거부
  (approve가 TESTING=runner-eligible을 만들기 때문) → prepare-signal-challenger 사용 안내. bulk-review의
  **approve** 액션도 signal 트랙 id를 service에 넘기지 않고 `failed`로 격리. `ProposalService.approve` 내부는
  미변경(엔드포인트 레벨 가드).
- API: `POST /strategy-proposals/{id}/prepare-signal-challenger`(201; 404/422/409). payload: proposal_id·
  source_analysis_run_id·source_session_id·base_version_id·challenger_version_id·challenger_status(=draft)·
  auto_trade_enabled(=false)·proposal_status(=pending)·no_change·warnings.
- 프론트(`StrategyProposalReportCard`): `source==paper_signal_analysis` 제안은 공유 승인(TESTING) 블록을 숨기고
  확인 체크박스("DRAFT challenger만 생성하며 자동매매/주문/세션 시작은 하지 않습니다") + "Signal Challenger 준비"
  버튼 → 성공 시 challenger 버전 #id · DRAFT-only · runner 미대상 · 주문 없음 · 세션 별도 승인 후 시작 표시.
- 테스트 `tests/test_paper_signal_challenger.py` (18): 게이트/404/422(source·run·target·base·params·not-pending)/
  409 중복/DRAFT 1개 생성·auto_trade=false·PENDING 유지·created_version_id 링크/auto_trade override/no_change/
  **list_active 비대상·TESTING·ACTIVE·Experiment·ScannerRuleVersion·SignalLog·Trade·AssignmentLog 미생성·세션 불변**/
  approve 엔드포인트 거부/ bulk approve 격리/API.
- 마이그레이션 없음. (D-17 DRAFT-only, D-18 링크·가드)

**M2 전체 완료(M2.1 읽기 전용 비교 + M2.2 DRAFT-only challenger 준비).** 다음 단계(별도 승인): 준비된 DRAFT
challenger로 readiness→세션 게이트를 거쳐 challenger PaperSignalSession 시작 후 M2.1로 비교 — 모두 기존
사람-게이트 경로 재사용(신규 자동화 없음).

⛔ `ProposalService.approve` 내부 수정 금지(공유 매매-인접 경로). TESTING/ACTIVE challenger 생성 금지. 사람
검토 없는 자동 머티리얼라이즈·세션 자동 시작·잡 활성 금지.

---

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
