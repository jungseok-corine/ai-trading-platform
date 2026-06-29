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

**M2 전체 완료(M2.1 읽기 전용 비교 + M2.2 DRAFT-only challenger 준비).**

**M2.3 — Challenger → Session → Comparison 워크플로 갭 분석 (`설계만 완료`, 구현 미승인)**: 준비된 DRAFT
challenger를 사람-게이트 PaperSignalSession으로 옮겨 baseline과 비교하는 다음 단계의 **갭 분석**.
설계 문서: **`docs/design/M2.3-challenger-session-workflow-gap.md`**.

- **핵심 결론**: M2.3 *기능적 브리지*는 **명시적 마이그레이션 승인 없이는 구현 불가**다. 이유: (1) 현재
  PaperSignalSession 생성은 **CandidateStrategyProposal + Experiment + readiness**에 묶여 있고(세션 시작
  API/모델 모두), (2) M2.2 challenger는 **StrategyProposal.created_version_id**만 가진다(Experiment/variant/
  candidate proposal/readiness 없음), (3) `PaperSignalSession.candidate_strategy_proposal_id`는 **NOT NULL**,
  (4) 시작 경로는 버전을 **ExperimentVariant** 경유로 찾는다, (5) **per-proposal duplicate-active 가드** 때문에
  baseline의 candidate proposal을 재사용하면 baseline·challenger 세션이 공존 불가, (6) **'준비됨/비실행' 세션
  상태가 없음**(active/stopped만).
- **권장**: Option B(UI 전용 헬퍼)는 안전하지만 기능 갭을 닫지 못함. **기능적 브리지는 마이그레이션 승인
  전까지 이연.** 향후 방향(Option C/E): 사람-게이트 challenger 세션 *준비* + `prepared` 비실행 상태 +
  nullable/별도 source 링크 + 세션 자동시작 없음 + 잡 활성 없음 + prepare 시 SignalLog 0 + TESTING/ACTIVE 없음
  + 주문/거래 경로 없음.
- **다음에 필요한 결정(사람)**: challenger 세션 워크플로용 **마이그레이션 승인 여부**. 구현 미착수.

**M2.4 — Challenger Session Workflow 스키마 설계 (`설계만 완료`, 마이그레이션 미승인)**: M2.3 갭을 닫기 위한
**가장 작은 안전한 스키마 변경** 설계. 설계 문서: **`docs/design/M2.4-challenger-session-schema-design.md`**.

- **핵심 발견**: 런너(`run_due_sessions`/`list_active`)는 `status=="active"` + `strategy_version_id` +
  `symbol_code`만 본다 — **`candidate_strategy_proposal_id`를 읽지 않는다.** 따라서 (a) candidate FK를
  nullable로 풀고, (b) source/추적 컬럼을 additive로 추가하고, (c) 런너가 안 보는 **`"prepared"` 상태**를
  도입하는 것이 최소 안전 변경이다. 새 세션 테이블·Experiment 불필요.
- **권장 = Option A**: `paper_signal_sessions`에 `candidate_strategy_proposal_id` nullable화 +
  `source_type`(기본 `candidate_proposal`) + `source_strategy_proposal_id`(nullable FK) +
  `baseline_session_id`(nullable self-FK) 추가, `strategy_version_id`(기존) 재사용, `status`에 `"prepared"`
  값 추가(문자열 — enum 마이그레이션 없음). 상태기계: prepared →(사람 시작)→ active →(사람 중지)→ stopped.
  기존 candidate 세션은 그대로 동작(backfill `source_type='candidate_proposal'`).
- **거부**: B(side table — NOT NULL 블로커 미해소, A 필요), D(병렬 세션 테이블 — M2.1 비교/런너/outcome가
  두 형태 union 필요, 회귀 위험 큼), E(D-19). C(워크플로 오케스트레이션 테이블)는 A 위 후속 단계로 이연.
- **다음에 필요한 결정(사람)**: Option A additive 마이그레이션 **승인 여부**. 승인 시 Phase 1(마이그레이션+모델)
  부터 단계별 진행.

**M2.5 Phase 1 — Option A 스키마/모델 호환 기반 (`DONE`)**: challenger 세션을 안전하게 표현하기 위한
**스키마 기반만** 구현했다. **challenger 세션 워크플로/prepare·start 엔드포인트/UI는 아직 없음.**

- 마이그레이션 `p1q2r3s4t5u6` (additive/constraint-relaxing, head): `paper_signal_sessions`에서
  `candidate_strategy_proposal_id` **nullable**화 + `source_type`(NOT NULL, server_default
  `candidate_proposal` → 기존 행 backfill) + `source_strategy_proposal_id`(nullable FK→strategy_proposals,
  SET NULL) + `baseline_session_id`(nullable self-FK, SET NULL) + 인덱스 3개. downgrade는 NULL candidate
  행(challenger)이 있으면 **중단**(데이터 손상 방지). upgrade→downgrade→re-upgrade 라운드트립 검증.
- 모델 `paper_signal_session.py`: 위 컬럼 추가, `candidate_strategy_proposal_id` Optional화, status 주석에
  `prepared`(런너 비대상) 추가. `PaperSignalSessionRead.candidate_strategy_proposal_id`도 Optional화(직렬화
  하위호환). 리포지토리/서비스 변경 없음 — `list_active`는 이미 `status=="active"`만 잡아 `prepared` 자동 제외.
- 테스트 `tests/test_paper_signal_session_source_schema.py` (6): 기존 candidate 세션 create/source_type
  backfill/find_active_for_proposal/duplicate 가드 유지, `prepared` 세션이 list_active 비대상, challenger
  행 표현(candidate FK NULL + source 추적), **StrategyVersion/Experiment/SignalLog/Trade/AssignmentLog
  미생성**. 전체 1553 passed.
- **이 단계 효과 없음**: prepare/start 엔드포인트 없음, 세션 생성/시작 없음, SignalLog 없음, 잡 활성 없음,
  주문/거래 없음, TESTING/ACTIVE 없음. 스키마 기반만. (D-20)
- **다음(별도 단계)**: Phase 2 `PaperSignalChallengerSessionService.prepare_challenger_session`(prepared 세션만
  생성) → Phase 3 start(prepared→active) + M2.1 비교 UI 연결.

**M2.5 Phase 2 — Prepared Challenger Session (`DONE`)**: M2.2가 만든 DRAFT challenger에 대해 사람이 명시
확인하면 **비실행(prepared) PaperSignalSession**을 만든다. **세션 시작 아님 — runner 미대상 · SignalLog/주문/
자동매매/잡 없음.**

- 서비스 `paper_signal_challenger_session_service.py`(`PaperSignalChallengerSessionService.prepare_from_strategy_proposal`):
  confirmed+confirmed_by 게이트, 제안 존재(404), source paper_signal_analysis(422), status PENDING(422),
  ai_analysis_run + target_type paper_signal_session(422), run.target_id의 baseline PaperSignalSession 존재(422),
  `created_version_id` 존재(422 — M2.2 선행 필요) + challenger 버전 존재·**DRAFT**·auto_trade off·동일 strategy(422),
  같은 source 제안에 이미 prepared/active challenger 세션이면 **409**. 생성 세션: `status="prepared"`,
  `candidate_strategy_proposal_id=NULL`, `source_type="signal_challenger"`, `source_strategy_proposal_id=proposal.id`,
  `baseline_session_id`=run.target_id, `strategy_version_id`=created_version_id, `symbol_code`=baseline 세션 심볼.
  StrategyVersion/Experiment/SignalLog/Trade/Order/AssignmentLog 미생성, approve 미호출, 잡 미활성.
- 리포지토리: `find_open_challenger_for_strategy_proposal`(prepared/active 중복 가드) 추가. `list_active`는
  여전히 `status=="active"`만 → prepared 세션 런너 비대상.
- API: `POST /strategy-proposals/{id}/prepare-challenger-session`(201; 404/422/409). payload: session_id·
  status(=prepared)·source_type(=signal_challenger)·source_strategy_proposal_id·baseline_session_id·
  challenger_version_id·symbol_code·runner_eligible(=false)·warnings. **start 엔드포인트 없음(이 단계).**
- 프론트(`StrategyProposalReportCard`): M2.2 challenger 준비 성공 블록 안에 확인 체크박스("prepared 세션만
  생성하며 신호 기록 시작/주문/자동매매는 하지 않습니다") + "Paper Signal Session 준비" → 성공 시 prepared 세션
  #id · runner 미대상 · 기준 세션 id · "비교는 신호 기록 후 가능 · 시작은 별도 단계". **시작/실행 컨트롤 없음.**
- 테스트 `tests/test_paper_signal_challenger_session.py` (16): 게이트/404/422(source·pending·created_version·
  target·baseline·not-draft·auto_trade)/409 중복/prepared 1개 생성·필드 검증·**list_active 비대상**·제안 불변
  (PENDING·created_version 유지)·**StrategyVersion/Experiment/SignalLog/Trade/AssignmentLog 미생성·baseline·
  challenger 상태 불변**/API. 전체 1569 passed.
- **다음(별도 단계, 미착수)**: Phase 3 start(prepared→active, 사람-게이트) + M2.1 비교 UI 연결.

**M2.5 Phase 3 — Prepared Session Activation (`DONE`)**: 사람이 명시 확인하면 prepared challenger 세션을
**active로 전환**한다(런너 대상 자격만 부여). **활성화는 신호를 즉시 만들지 않는다 — 잡 미활성 ·
run_due_sessions 미호출 · 주문/거래 없음 · status만 변경.**

- 서비스 `PaperSignalChallengerSessionService.activate_prepared_session(session_id, confirmed, confirmed_by)`:
  confirmed+confirmed_by 게이트, 세션 존재(404), source_type signal_challenger(422), status prepared(422),
  링크 일관성(candidate FK NULL·source 제안·baseline·version 존재, 422), 버전 DRAFT·auto_trade off(422),
  연결 제안 paper_signal_analysis·PENDING·created_version 일치(422), (현재 세션 외) active challenger 중복(409).
  **세션 status만 prepared→active**(started_by/started_at 갱신). baseline/proposal/version/experiment 무변경,
  SignalLog/Trade/Order/AssignmentLog 미생성, 잡 미활성, run_due_sessions 미호출.
- 리포지토리: `find_active_challenger_for_strategy_proposal`(현재 세션 제외 active 중복 가드) 추가.
- 안전: 활성화는 `list_active`에 세션을 포함시켜 **런너 대상 자격만** 준다 — 실제 SignalLog는 default-OFF
  `paper_signal_session_runner` 잡이 켜지고 실행될 때만 `run_due_sessions`가 생성. 응답에 `runner_eligible=true`,
  `runner_currently_enabled`(현재 config 플래그) + warnings("activation does not create signals immediately"
  등). 잡 설정·auto_trade 변경 없음. (D-21)
- API: `POST /paper-signal-sessions/{session_id}/activate`(200; 404/422/409). 라벨은 activate(start/run/trade
  아님).
- 프론트(`StrategyProposalReportCard`): prepared 세션 성공 블록 안에 확인 체크박스("신호 세션을 active로
  전환합니다. 신호 생성은 별도 runner 실행 시에만 발생하며 주문/거래는 생성하지 않습니다") + "신호 세션 활성화"
  → 성공 시 active 세션 #id · runner 대상 자격 · runner 현재 상태 · "신호 생성은 별도 runner 실행 시 · 주문/거래
  없음". 자동매매/주문/매매 시작 라벨 없음.
- 테스트 `tests/test_paper_signal_challenger_session_activate.py` (12): 게이트/404/422(non-challenger·
  not-prepared·inconsistent·not-draft·auto_trade·proposal-not-pending)/409 중복/**status만 prepared→active·
  started_by 갱신·list_active 포함·SignalLog/Trade/Experiment/AssignmentLog 미생성·버전 DRAFT·제안 PENDING·
  baseline 불변·runner 플래그 불변**/API. 전체 1581 passed.
- **다음(별도 단계, 미착수)**: M2.1 비교 UI 연결(active challenger vs baseline). runner 잡 활성은 사람 별도 결정.

**M2.6 — Baseline ↔ Active Challenger Comparison Wiring (`DONE`, frontend-only)**: challenger 세션
(prepared/active)을 그 baseline 세션과 **읽기 전용**으로 비교하는 UI를 기존 M2.1 compare API로 연결한다.
**백엔드 변경 없음 · 마이그레이션 없음 · 세션/버전/제안 무변경 · runner 미실행 · SignalLog/주문/거래 없음.**

- 데이터 출처: Phase 2 prepare 응답(`baseline_session_id`+challenger `session_id`)과 Phase 3 activate 응답
  (`status`·`runner_currently_enabled`)이 이미 필요한 id를 준다 → **백엔드 헬퍼 불필요**(M2.1
  `GET /paper-signal-sessions/{baseline}/compare/{challenger}` 그대로 재사용).
- 프론트(`StrategyProposalReportCard`): prepared 세션 성공 블록 안에 `ChallengerComparison`(읽기 전용) 추가 —
  기준/challenger 세션 id + challenger status + horizon(5/15/30/60) + "신호 성과 비교 보기" → M2.1 호출 →
  지표/델타 표 + warnings. 상태별 안내: prepared면 "아직 active가 아니므로 신호 기록 대상이 아닙니다.",
  active+runner off면 "active 상태지만 runner가 꺼져 있으면 새 신호는 생성되지 않습니다.", 분석 0이면
  "아직 비교할 신호 결과가 부족합니다…". `ChallengerSessionActivate`는 `onActivated` 콜백으로 활성화 status·
  runner 플래그를 비교 UI에 전달. 라벨: "읽기 전용 · 주문 없음 · 거래 없음 · 자동매매 아님 · runner 별도".
  runner/잡 활성·매매·주문 컨트롤 없음.
- 검증: `npm run build`(typecheck) 통과. 백엔드 무변경 — 기존 M2.1/Phase2/Phase3 테스트 39 sanity passed.
- **다음(별도 단계, 미착수)**: runner 잡 활성(사람 별도 결정) 후 실제 신호 누적 → 비교가 의미 있어짐. 활성화 ≠
  runner 활성 ≠ 신호 생성 분리 유지(D-21).

**M2.7 — Paper Signal Runner Operation Gate (`설계만 완료`, 구현 미승인)**: active 세션에 대해 SignalLog를
안전하게 생성해 baseline↔challenger 비교를 의미 있게 만드는 **사람-게이트 운영 흐름 설계**. 설계 문서:
**`docs/design/M2.7-paper-signal-runner-operation-gate.md`**.

- **핵심 발견(코드 검증)**: `run_due_sessions`는 `list_active`(active 전부, source_type 무관)에 대해 DRAFT +
  auto_trade off + 등록 strategy_type인 세션만 **SignalLog만** 생성한다(주문/Trade/TradeService 없음;
  broker는 캔들 시세 조회 전용). 세션/버전 status 변경 없음(카운터만). candle 단위 dedupe
  (`exists_for_candle`), 장 마감 staleness 가드(신호 미생성). **이미 `POST /autonomous-jobs/{job_id}/run`
  (`run_now`)이 enabled 플래그와 무관하게 잡을 1회 실행**할 수 있으나, 이는 **모든 active 세션**을 돌린다(범위 큼).
- **권장 = Option B(세션 단위 run-once)**: `POST /paper-signal-sessions/{id}/run-once`(confirmed+confirmed_by,
  active만, DRAFT+auto_trade off, KIS_REAL false) — **선택한 1개 active 세션만** 1회 신호 평가. 스케줄러 미활성,
  주문/거래 경로 없음, status 무변경(카운터만), dedupe/staleness 그대로. 거부: Option C(스케줄러 상시 활성 —
  더 위험, 후속 별도 승인), Option E(baseline+challenger 페어 배치 — 후속). Option A(전체 run-once)는 기존
  run-now로 이미 가능하나 범위가 넓어 challenger 테스트엔 부적합.
- **다음에 필요한 결정(사람)**: 세션 단위 run-once(Option B) 구현 **승인 여부**. → M2.8에서 구현됨.

**M2.8 — Session-specific Paper Signal Run-Once (`DONE`)**: 사람이 명시 확인하면 **선택한 단일 active
PaperSignalSession**에 대해 신호를 **1회만** 평가한다(M2.7 Option B / D-22). **선택 세션만 · SignalLog만 ·
주문/거래 없음 · 스케줄러/잡 미활성 · 반복 아님 · 세션 status 불변.**

- 서비스 `paper_signal_run_once_service.py`(`PaperSignalSessionRunOnceService.run_once`): confirmed+
  confirmed_by 게이트, 전역 게이트(`kis_real_trading_enabled`/`paper_signal_session_runner_enabled` true면
  **422**), 세션 존재(404)·active(422)·strategy_version 존재(422)·**DRAFT**(422)·auto_trade off(422)·등록
  strategy_type(422)·symbol(422). **선택한 1개 세션만** 기존 `SignalService.generate_and_log_signal`로 평가 —
  `list_active`/`run_due_sessions`/스케줄러 `run_now` **미사용**. 최대 1개 SignalLog 생성(생성 시
  `paper_signal_session_id`=세션). dedupe/staleness/무신호는 `signal_created=false`(skipped, 사유), 시세 오류는
  예외 흡수해 skipped(크래시 아님). 카운터(run_count/signal_count/last_run_at/last_error)만 갱신 — **세션/버전/
  제안/실험 status 무변경**, 주문/거래/AssignmentLog/version/experiment 미생성.
- API: `POST /paper-signal-sessions/{session_id}/run-once`(200 성공/skipped; 404/422). DI는 broker 시세 조회용
  `SignalService`(market-data only, **TradeService 미구성**)를 구성. 응답: session_id·status(=active)·
  signal_created·signal_id?·reason?·orders_created(=0)·trades_created(=0)·runner_enabled(=false)·warnings
  ("This run creates SignalLog only." 등). **autonomous-jobs run-now/잡 활성 API 미변경.**
- 프론트(`StrategyProposalReportCard` M2.6 비교 블록): active 세션이면 확인 체크박스("선택한 세션 1개에 대해
  신호를 1회 기록합니다. 주문/거래는 생성하지 않습니다") + "신호 1회 기록" → 결과(생성 signal #id / skipped 사유 ·
  orders 0 · trades 0 · 다시 비교). prepared면 "active 전환 후 가능". 라벨: "선택 세션만 · SignalLog만 · 주문
  없음 · 거래 없음 · 자동매매 아님 · 반복 실행 아님". runner/잡/매매/주문 시작 컨트롤 없음.
- 테스트 `tests/test_paper_signal_run_once.py` (15): 게이트(confirmed·404·not-active·not-draft·auto_trade·
  unsupported·real-trading·runner-enabled)/성공 1개 SignalLog·선택 세션만 평가·다른 active 세션 불변·카운터
  갱신·status 불변/무신호·시세오류 skipped/**Trade·Order·AssignmentLog·Experiment·StrategyVersion 미생성·
  버전 status 불변**/API. 전체 1596 passed.
- **다음(별도 단계, 미착수)**: runner 상시 활성(Option C, 사람 별도 결정), baseline+challenger 페어 run-once(M2.9 설계).
  세션 단위 run-once 우선 원칙 유지(D-22).

**M2.9 — Baseline ↔ Challenger Pair Run-Once (`설계만 완료`, 구현 미승인)**: baseline와 challenger 세션을
**한 번의 사람 트리거**로 각각 1회씩 신호 기록해 공정한 비교 데이터를 쌓는 흐름 설계. 설계 문서:
**`docs/design/M2.9-pair-run-once-operation-design.md`**.

- **핵심 결론**: 단일 세션 run-once는 baseline/challenger를 서로 다른 시점에 샘플링해 비교가 불공정해질 수 있다.
  → 한 요청에서 두 세션을 같은 시장 시점·같은 종목·강제된 baseline↔challenger 관계로 평가.
- **권장 = Option B(백엔드 페어 엔드포인트)**: `POST /paper-signal-sessions/{baseline_id}/compare/{challenger_id}/run-once-pair`.
  서버가 관계 검증(challenger.source_type=signal_challenger·baseline_session_id 일치·동일 symbol·둘 다 active·둘 다
  DRAFT+auto_trade off·KIS_REAL false·runner false)을 먼저 한 뒤 **두 세션만** M2.8 코어로 1회씩 평가. 검증 실패는
  **실행 전 전체 거부(422)**, 런타임 skip(중복/장마감/무신호)은 정상 결과로 계속. `list_active`/`run_due_sessions`/
  스케줄러 `run_now` 미사용 · 최대 2 SignalLog · 주문/거래 없음 · 잡 미활성 · status 무변경(카운터만).
- **거부**: A(프론트 전용 — 관계/심볼 검증이 클라이언트에 흩어짐), D(현상 유지 — 불공정 위험). C(백엔드+테스트
  먼저, UI 후속)는 UI가 커지면 폴백.
- **다음에 필요한 결정(사람)**: Option B(백엔드 페어) vs Option A(프론트 전용) 선택. → M2.10에서 Option B 구현됨.

**M2.10 — Backend Baseline ↔ Challenger Pair Run-Once (`DONE`, backend/API/tests)**: 사람이 명시 확인하면
**명시한 baseline + challenger 두 active 세션만** 각각 1회씩 신호를 평가한다(M2.9 Option B / D-23).
**두 세션만 · SignalLog만(최대 2개) · 주문/거래 없음 · 스케줄러/잡 미활성 · 반복 아님 · status 무변경.**

- M2.8 리팩터: `PaperSignalSessionRunOnceService`에서 검증/평가 코어를 추출(`check_confirmation`/
  `check_global_gates`/`validate_session`/`evaluate_session` — 후자는 **커밋 안 함**). `run_once`는 이를
  조합(behavior 동일, M2.8 테스트 15 유지). → **검증 드리프트 방지**.
- 서비스 `paper_signal_pair_run_once_service.py`(`PaperSignalPairRunOnceService.run_pair`): confirm+전역 게이트,
  baseline/challenger 존재(404×2), challenger.source_type=signal_challenger(422)·baseline_session_id 일치(422)·
  동일 symbol(422), **두 세션 모두 validate_session(active·DRAFT·auto_trade off·strategy_type·symbol)**을 **평가 전**
  수행(한쪽 실패 시 어느 쪽도 평가 안 함). 그 뒤 baseline→challenger 순으로 `evaluate_session`(skip 정상, 성공
  SignalLog 롤백 안 함), **한 트랜잭션 1회 커밋**. `list_active`/`run_due_sessions`/`run_now` 미사용.
- API: `POST /paper-signal-sessions/{baseline_id}/compare/{challenger_id}/run-once-pair`(200 성공/partial/skipped;
  404×2/422). 응답: baseline·challenger{session_id·signal_created·signal_id·reason} + orders_created(=0)·
  trades_created(=0)·runner_enabled(=false)·comparison_ready_hint·warnings. market-data only SignalService DI.
- 테스트 `tests/test_paper_signal_pair_run_once.py` (20): 게이트(confirm·404×2·active×2·source_type·baseline
  불일치·symbol 불일치·not-draft·auto_trade·unsupported·real-trading·runner)/**한쪽 게이트 실패 시 양쪽 미평가**/
  성공 2 SignalLog·정확 귀속·**페어만 평가(2회)**·다른 active 세션 불변·카운터·status 불변/partial(한쪽 skip)/
  시세오류 skipped/**Trade·Order·AssignmentLog·Experiment·version·status 무변경**/API. 전체 1616 passed.
- **프론트 미구현**: 페어 UI 와이어링은 **M2.11로 이연**(backend/API/tests/docs only). → M2.11에서 구현됨.

**M2.11 — Frontend Pair Run-Once UI Wiring (`DONE`, frontend-only)**: M2.10 페어 엔드포인트를 비교 블록 UI로
연결한다. **백엔드 변경 없음 · 마이그레이션 없음 · 스케줄러/잡 미활성 · 주문/거래 없음.**

- API/타입(`research.ts`): `runPaperSignalPairOnce(baselineSessionId, challengerSessionId, {confirmed, confirmed_by})`
  → `POST .../compare/{challenger}/run-once-pair`; `PaperSignalPairRunOnceResult` 타입(baseline/challenger
  sub-object + orders/trades=0 + runner_enabled + comparison_ready_hint + warnings).
- 프론트(`StrategyProposalReportCard`): `ChallengerComparison` 안에 **권장 동작** `PairRunOnce`(active일 때) 추가 —
  확인 체크박스("기준 세션과 challenger 세션을 각각 1회 신호 기록합니다. 주문/거래는 생성하지 않습니다") +
  "페어 신호 1회 기록" → 기준/Challenger 각 결과(생성 SignalLog #id / skipped 사유) · orders 0 · trades 0 ·
  runner false · warnings · "결과 확인을 위해 신호 성과 비교를 다시 실행하세요". prepared면 "페어 신호 기록은
  active 전환 후 가능합니다." 단일 세션 run-once(M2.8)는 `<details>` 보조/디버그용으로 강등(페어가 기본 권장).
  라벨: "공정 비교용 · 기준/챌린저 각각 1회 · SignalLog만 · 주문 없음 · 거래 없음 · 자동매매 아님 · 반복 실행 아님".
- 검증: `npm run build`(typecheck) 통과. 백엔드 무변경 — M2.10 페어 테스트 20 contract sanity 유지.
- **다음(별도 단계, 미착수)**: M2.14B-3 무인 디스패처(명시 승인).

**M2.15D-2 Leader Trend Real-Market Reference Comparison (`DONE`, read-only review + docs)**: 저장 paper/dev 일봉을
**KIS 실전(production) 도메인 read-only 시세**(`get_current_price`, `real_trading_enabled=False`)와 대조. **주문 TR 0 ·
place_order 0 · DB write 0 · 레퍼런스/후보 영속화 0 · 스캐너 런타임 변경 0 · 마이그레이션 0 · 스케줄러/디스패처 0 ·
`KIS_REAL_TRADING_ENABLED` 미변경(false) · M2.14B-3d 미승인.** 후보는 매수 신호 아님.

- 결과: **5종 현재가가 실전 도메인 시세와 ≤0.7% 일치**(전부 `matches_reference`): 005930 323,000=323,000, 000660
  2,610,000 vs 2,628,000(-0.7%), 035420/005380/051910 ≤0.7%. → D-1 스케일 우려는 **현재가 한정으로 완화**, 운영 B는
  paper-only 아티팩트 아님.
- 한계(정직): ① 비교는 **현재가만**(실전 get_current_price는 당일 시세) — **52주 저점/이력 미검증**(B 분류 핵심
  드라이버); ② **KIS 외 독립 소스 부재**(pykrx/yfinance 미설치) → 실전 도메인이 진짜 production인지 dev와 동일
  데이터 공유인지 독립 확인 불가; ③ 모델 cutoff(2026-01) < sim(2026-06-29).
- 권고: **Option B — research-only 노출 + 강한 데이터 출처 경고**(현재가 검증·52주/독립성 미검증). Option C(차단)
  기각(실전과 일치), A(클린) 미채택. DB 불변(1d 1,260·005930 체크섬·Trade 35). 산출물:
  `docs/reports/M2.15D-2-real-market-reference-comparison.md`. DECISIONS 미갱신. 코드/스키마/마이그레이션 변경 없음.
- **다음(별도 승인): M2.15D-3 — (3A) 실전 read-only 과거 일봉으로 52주 실측 대조, 또는 (3B) research-only 후보
  읽기 전용 노출(출처 경고+"매수 신호 아님" 라벨, 주문/자동제안 없음).** 종목 확장은 미승인.

**M2.15D-1 Leader Trend Data Realism / Scale Consistency Review (`DONE`, read-only review + docs)**: 5종 가격 스케일
일관성(1d ↔ 5m ↔ 라이브 현재가) 검토. **DB write 0 · 후보 영속화 0 · API/UI 노출 0 · 스캐너 런타임 변경 0 ·
SignalLog/Trade/Order 0 · KIS 주문/place_order 0 · 마이그레이션 0 · 스케줄러/디스패처 0 · M2.14B-3d 미승인.**

- 결과: **3소스(일봉·5m·라이브 현재가) 스케일 1:1 일치**(비율 1.000~1.006, ≤0.6%). 배율 불일치 없음. 1m만 ~7일
  stale(age, 스케일 아님). 라이브 `get_current_price`(read-only `/quotations/inquire-price`, TR FHKST01010100) 5종
  순차, 모두 성공·시크릿 미출력.
- 판정: **000660·005930의 운영 B는 스케일 이슈가 아님**(데이터 내부 일관+라이브 확인). 단 005930 1년 5.6배·000660
  ~10배는 실제 시장과 동떨어진 **paper/dev 데이터**로 보여 **시장 현실성 미검증** → 5종 모두 `usable_for_research_only`.
- 권고: **Option D — 노출 전 백테스트/실측 데이터-벤더 현실성 검증**(스케일 가드/차단 B·C는 불필요). Option A(읽기
  전용 노출)는 research-only+데이터출처 경고 명시 시에만.
- DB 불변(1d 1,260·005930 체크섬·Trade 35). 산출물: `docs/reports/M2.15D-1-leader-trend-data-realism-scale-review.md`.
  DECISIONS 미갱신(가역 검토). 코드/스키마/마이그레이션 변경 없음.
- **다음(별도 승인): M2.15D-2 — 실측 데이터 대조 검증 또는 읽기 전용 백테스트 골격**(주문/Trade 없음), 그 뒤
  M2.15D-3 research-only 후보 노출. 종목 확장은 미승인.

**M2.15C-4 Leader Trend Layered Warning Model (`DONE`, read-only scanner refactor + tests, no migration)**: 스캐너
경고/분류를 **3계층**(hard_errors / adjustment_warnings / strategy_extreme_warnings)으로 분리(D-28). **스캐너 읽기 전용
유지 · DB write 0 · 라이브 KIS 0 · 후보 영속화 0 · SignalLog/Trade/Order 0 · 주문/스케줄러 0 · 마이그레이션 0 ·
프론트 0 · M2.14B-3d 미승인.** 후보는 매수 신호 아님.

- 정책: hard(nonpositive/high<low/close범위밖/null/중복일)→`invalid_data`; **분할 의심(일일점프>50%)만 운영 차단**
  (`*_raw_needs_adjusted_review`, safe=False); **range>4·gain>500%는 비차단 `strategy_extreme`**(is_strategy_extreme만).
  `operationally_safe = is_data_valid AND ready_for_52w AND not is_adjustment_suspect`. 연구/운영 버킷 분리,
  `candidate_bucket`은 운영 별칭(하위호환).
- 5종 read-only 재스캔: **000660·005930 → 운영 `B`(safe=True, strategy_extreme, adj_suspect=False)**,
  035420/005380/051910 → none. 운영 후보 0→2개(둘 다 high-extension). DB 불변(1d 1,260·005930 체크섬·Trade 35).
- 테스트: c1 갱신(hard_errors/전략-극단 비차단) + `test_m2_15c4_...`(16). **전체 백엔드 1784 passed**. DECISIONS **D-28** 추가.
- 산출물: `docs/reports/M2.15C-4-layered-warning-scanner.md` + `leader_trend_scanner.py`/CLI/테스트. 스키마/마이그레이션 변경 없음.
- **다음(별도 승인): M2.15D — 후보 읽기 전용 노출(API/UI) 또는 CandidateEvent 재사용 영속화**(승인 없는 자동 제안
  없음·주문/배치 없음), 또는 데이터 현실성/백테스트 점검. 종목 확장은 미승인.

**M2.15C-3 Leader Trend Threshold / Strategy-Intent Review (`DONE`, docs-only decision)**: 스캐너가 대형 52주
gain/range 경고를 어떻게 다뤄야 하는지 정책 리뷰. **런타임 코드/임계값 미변경 · 테스트 미변경 · 후보 영속화 0 ·
라이브 KIS 0 · DB write 0 · 마이그레이션 0 · SignalLog/Trade/Order 0 · 스케줄러/디스패처 0 · M2.14B-3d 미승인.**

- 진단(read-only): **5종 모두 max 일일 종가 점프 ≤19.1%**(분할 같은 불연속 없음), 차단된 005930·000660 저가 구간은
  다일 연속(21·33일 near-low), OHLCV 완전, adjusted=raw(M2.15C-2). → **데이터 무결성 결함 0건**; 현 차단은 100%
  range/gain **전략-극단 임계값** 탓. Candidate B는 의도적으로 큰 gain 허용 → 큰 gain 단독으로 invalid 처리하면 전략 무력화.
- 권고: **Option B(데이터 무결성 ↔ 전략-극단 분리)** — 하드 invalid는 엄격 유지하되 range>4·gain>500%는 데이터가
  깨끗하면 **비차단 `strategy_extreme` 경고로 강등**(005930·000660이 `B`로 노출, safe=true). 구현은 **Option C의 필드
  분리**(`is_data_valid`/`is_adjustment_suspect`/`is_strategy_extreme`/`candidate_bucket_research`/
  `candidate_bucket_operational`)로 M2.15C-4에서. Option A(현 하드 블록) 기각, Option D(프로파일) 보류.
- DB 불변(1d 1,260·005930 체크섬·Trade 35). 산출물: `docs/reports/M2.15C-3-threshold-strategy-intent-review.md`.
  DECISIONS 미갱신(C-4 구현·검증 후 기록). 코드/스키마/마이그레이션 변경 없음.
- **다음(별도 승인): M2.15C-4 — 스캐너 경고 모델 계층화 리팩터(읽기 전용 유지) + 테스트 + 5종 재스캔 검증.** 종목
  확장·후보 영속화는 미승인.

**M2.15C-2 Adjusted Daily Candle Read-Only Probe / Price Policy Decision (`DONE`, live read-only probe + docs)**:
5종 파일럿에 `adjusted=True`(`FID_ORG_ADJ_PRC=1`) 라이브 read-only 프로브 + 인메모리 메트릭 계산 + raw 대조.
**adjusted 봉 미적재 · raw 봉 미덮어쓰기 · DB write 0 · 마이그레이션 없음 · 후보 영속화 없음 ·
SignalLog/Trade/Order 0 · KIS 주문/place_order 0 · 스케줄러/디스패처 0 · M2.14B-3d 미승인.**

- 결과: 5/5 success, 각 252봉/3페이지/중복0/OHLCV완전, EGW00201 미관측. **adjusted=True가 경고를 해소하지 못함** —
  high_52w·low_52w가 **raw와 정확히 일치**(005930 380000/57600, 000660 3002000/242000). close/gain/dd 미세차는
  진행 중 당일봉 라이브 갱신 탓(수정주가 효과 아님). 000660·005930는 adjusted에서도 `B_raw_needs_adjusted_review`
  (safe=False), 나머지 none. **운영 후보 raw 0·adjusted 0(동일).**
- 추가 진단(read-only): 저가 구간은 단일 이상치 아님(005930 ~57,600은 2025-06 다일 연속; 중앙값 close 110,100) →
  대형 range/gain은 **데이터 내 실제 1년 상승추세**.
- 결정: **Option B — raw 유지 + 스캐너 운영 분류 차단 유지**(수정주가 도입 실익 없음). 단 경고 임계값이 실제 강한
  주도주를 데이터 의심으로 묶는 한계 → raw-vs-adjusted 아님, **임계값/전략의도·데이터 현실성** 문제. 저장/스키마
  변경(예 `1d_adj`/`adjustment_mode`) 실익 없어 **미구현**.
- DB 불변(1d 1,260·005930 체크섬·schema·Trade 35). 산출물: `docs/reports/M2.15C-2-adjusted-daily-candle-readonly-probe.md`.
  코드/스키마/마이그레이션 변경 없음.
- **다음(별도 승인): M2.15C-3 — 경고 임계값/전략의도 재검토 + 데이터 현실성 점검**(이 paper 일봉이 실제 시장 스케일과
  부합하는지). 종목 확장·후보 영속화·adjusted 적재는 미승인. DECISIONS 변경 없음(가역적 운영 결정).

**M2.15C-1 Leader Trend Metric Calculator / Read-Only Candidate Scanner (`DONE`, backend service+CLI+tests, no migration)**:
적재된 5종 일봉(`market_data` 1d)만으로 52주 지표 계산 + 후보 A/B 분류하는 **읽기 전용** 스캐너. **DB write 0 ·
라이브 KIS 0 · SignalLog/Trade/Order 0 · broker/주문 경로 미사용 · 스케줄러/디스패처 0 · 마이그레이션 없음 · 후보
영속화 없음 · 후보는 매수 신호 아님 · M2.14B-3d 미승인.**

- 구현: `app/services/leader_trend_scanner.py`(`compute_metrics` 순수 + `LeaderTrendScanner.scan`) ·
  `scripts/scan_leader_trend_candidates.py`(읽기 전용 CLI, execute/provider 플래그 없음) ·
  `tests/test_m2_15c1_leader_trend_scanner.py`(14). 공식은 M2.15A와 동일(low_52w_gain_pct·drawdown). bucket:
  A/B/`*_raw_needs_adjusted_review`/none/insufficient_data/invalid_data.
- 데이터 품질/원주가 경고: range_ratio>4 · gain>500% · 일일점프>50% → `operationally_safe_for_classification=False`,
  후보는 review 라벨로 유지(데이터 보존). hard invalid(nonpositive/high<low/중복일/null)→invalid_data.
- dev DB 5종 read-only 스캔: **000660·005930 = raw Candidate B이나 원주가 경고로 `B_raw_needs_adjusted_review`
  (safe=False)** · 035420/005380/051910 = none(safe). → **운영 분류 가능한 raw 후보 0개**(설계상 의도된 가드 작동).
  DB 불변(1d 1,260·005930 체크섬·Trade 35), 전체 백엔드 **1768 passed**.
- 산출물: `docs/reports/M2.15C-1-leader-trend-metric-scanner.md`. 스키마/마이그레이션/프론트/API 변경 없음.
- **다음(별도 승인): M2.15C-2 — 수정주가(adjusted=True/`FID_ORG_ADJ_PRC=1`) 도입 결정/프로브**(경고 해소 확인) 또는
  읽기 전용 API/UI 스캐너. 종목 확장(20/110/전체)·후보 영속화는 미승인. DECISIONS 변경 없음.

**M2.15B-9 Five-Symbol Daily Candle Execute-Pilot (`DONE`, dev DB, no migration)**: 신규 4종
(000660·035420·005380·051910)을 KIS read-only 일봉으로 dev DB `market_data` `1d`에 **종목별 순차 멱등 적재**(005930은
control 유지·재실행 안 함). **20/110/전체 미실행 · 마이그레이션 없음 · 런타임 코드/프론트 변경 없음 ·
SignalLog/Trade/Order 미생성 · KIS 주문/place_order 미호출 · 스케줄러/디스패처 없음 · production 미접촉 · M2.14B-3d 미승인.**

- 실행: 000660→035420→005380→051910 각 1회(`--execute --confirm-daily-candle-collection`, count=252), 매 종목 후
  검증 + sleep 5s. 결과 4/4 success, 각 fetched=252/inserted=252/conflicts=0. EGW00201 미관측.
- DB: `1d` 252→**1,260**(5×252), distinct symbols 1→5, 각 신규 252, 비선정 0, 중복 0, null 0. **005930 체크섬
  `3789bed6…` 불변**(재실행 안 함). 본 작업 일봉 insert 1,008(=4×252). **SignalLog 본작업 0 · Trade 35 불변**
  (절대수 증가는 무관 백그라운드).
- coverage(post): 5종 전부 `daily_candles=252`, `has_20/50/120/252=True`, `ready_for_52w=True`. 52주 메트릭(read-only,
  미저장) 5종 모두 계산 가능·부분/의심 데이터 없음 → **M2.15C 메트릭 계산기 준비 완료**.
- 산출물: `docs/reports/M2.15B-9-five-symbol-daily-candle-execute-pilot.md`. 코드/스키마/마이그레이션 변경 없음.
- **다음(별도 승인): M2.15C — 주도주 추세추종 메트릭 계산기/스캐너 readiness**(저장 5종 252봉으로 52주 지표·조건 A/B
  read-only 계산). 20/110/전체 확장은 미승인(확장 전 M2.15B-8a CLI 스로틀 권장). DECISIONS 변경 없음.

**M2.15B-8 Five-Symbol Daily Candle Execute-Pilot Plan (`DONE`, docs/design only, no execution)**: 다음 단계
(M2.15B-9, 별도 승인)의 5종목 일봉 execute-pilot 설계. **실행 0 · 추가 종목 미수집 · DB write 0 · 마이그레이션 없음 ·
런타임 코드/프론트 변경 없음 · SignalLog/Trade/Order 미생성 · KIS 주문/place_order 미호출 · 스케줄러/디스패처 없음 ·
M2.14B-3d 미승인.**

- 선정 5종(모두 watchlist 110종에 실재 + 인트라데이 데이터 확인): **005930(control, 이미 252)** + 신규 4종
  `000660·035420·005380·051910`(대형·고유동 KOSPI; 일봉 0). 최종 리스트 `005930,000660,035420,005380,051910`.
- 실행정책: dev DB only · count=252 · adjusted=False · overwrite=False · **순차(concurrency=1)** · 종목 간 sleep ·
  stop-on-failure. CLI 갭 확인: `--sleep`/`--end-date`/오케스트레이션 stop 미지원, `_collect_one`이 종목별 예외
  흡수 → **권장(A) 종목별 순차 수동 실행 + 매 종목 검증**(코드 변경 불필요). 대안(B) 다종목 단일 명령은 8a 이후.
- 당일봉 정책: 확정봉 immutable, 당일봉 drift는 overwrite=False로 conflict 보고·무덮어쓰기(정상). overwrite 미구현.
- 기대: `1d` 252→**1,260**(5×252), `symbols_with_daily=5`, 각 `ready_for_52w=true`. 252 미만 반환 종목은 정직히
  `ready_for_52w=false` 기록. EGW00201은 provider backoff로 복구, 반복 시 중단·보고.
- 산출물: `docs/reports/M2.15B-8-five-symbol-execute-pilot-plan.md`. 코드/스키마/마이그레이션 변경 없음.
- **다음(별도 승인): M2.15B-9 — 5종목 execute-pilot 실행**(권장 A). 또는 **M2.15B-8a — 안전 CLI 옵션(sleep/end-date/
  stop-on-error)+테스트**(20종+ 확장 시 우선). 5종목 execute-pilot은 미승인. DECISIONS 변경 없음.

**M2.15B-7 Daily Candle Idempotency / Post-Persistence Smoke — 005930 (`DONE`, 1 re-execute, dev DB, no migration)**:
이미 적재된 005930 일봉(252봉)에 execute 경로를 1회 재실행해 멱등성 검증. **추가 종목 미수집 · 마이그레이션 없음 ·
런타임 코드/프론트 변경 없음 · SignalLog/Trade/Order 미생성 · KIS 주문/place_order 미호출 · 스케줄러/디스패처 없음 ·
production DB 미접촉 · M2.14B-3d 미승인.**

- 가드: CLI에 `--end-date` 없음 → 라이브 read-only **count=1 프리체크**(DB 쓰기 0)로 provider 최신 거래일 20260629가
  적재 최신과 일치(newer 아님) 확인 후에만 재실행 → 순수 멱등성 조건 충족.
- 재실행(1회) 결과: **writes=0 · inserted=0 · 중복 0**, `1d` 252 유지, **행 체크섬 `3789bed6…` 적재 전후 동일**
  (DB 바이트 단위 불변). status는 `skipped_fresh`가 아니라 **`conflict`(conflicts=1)** — 251 확정봉은 정확 일치→skip,
  **당일봉 20260629만 close 323000→324000 / volume 51,942,901→53,360,736로 갱신**됐고 collector가 `overwrite=False`로
  **미덮어쓰기**(보수적·정상 동작; 결함 아님).
- 안전: SignalLog 98,025 불변 · Trade 35 불변 · 인트라데이 1m/5m 미수정 · coverage `ready_for_52w=True` 유지 ·
  52주 메트릭 baseline과 동일(체크섬 불변).
- 참고(차후 분리): 당일봉 최신화는 `--overwrite` 필요 → 과거 확정봉 보존+당일봉만 갱신하는 **별도 승인 증분 정책**으로.
  산출물: `docs/reports/M2.15B-7-daily-candle-idempotency-smoke-005930.md`. 코드/스키마/마이그레이션 변경 없음.
- **다음(별도 승인): M2.15B-8 — 5종목 execute-pilot 계획.** 5종목 execute-pilot은 미승인. DECISIONS 변경 없음.

**M2.15B-6 Daily Candle Execute Pilot — 005930 (`DONE`, first real execute, dev DB, no migration)**: 1종목
(005930) 일봉 252봉을 KIS read-only로 받아 dev DB `market_data` `timeframe="1d"`에 멱등 적재(첫 실제 execute-pilot).
**5/20/110/전체 유니버스 미실행 · 마이그레이션 없음 · 런타임 코드/프론트 변경 없음 · SignalLog/Trade/Order 미생성 ·
KIS 주문 API/place_order 미호출 · 스케줄러/디스패처 없음 · production DB 미접촉 · M2.14B-3d 미승인.**

- 명령: `collect_daily_candles.py --symbols 005930 --count 252 --execute --confirm-daily-candle-collection`
  (1회). 결과: status=success, fetched=252, inserted=252, conflicts=0, signals/trades/orders=0. 3 페이지 호출,
  `EGW00201` 1회 → 내장 backoff 복구.
- DB: market_data `1d` 0→**252**(005930), 중복 그룹 0, OHLCV/volume 결측 0, 거래일 KST 2025-06-18~2026-06-29.
  인트라데이 1m(2274)/5m(3127) 불변. total 277,974→278,279(+252 본작업 +~53 무관 백그라운드). **SignalLog 95,110
  불변 · Trade 35 불변.**
- coverage(post): `daily_candles=252`, `has_20/50/120/252=True`, `ready_for_52w=True`. 52주 지표(read-only 계산,
  미저장): current_close 323000, high_52w 380000, low_52w 57600, low_52w_gain 460.76%, drawdown 15.0%, MA20 335800,
  MA50 289370 → **M2.15C 메트릭 계산기 준비됨**.
- adjusted=False(원주가) 적재, trading_value 미저장(컬럼 없음 — 별도 승인). 산출물:
  `docs/reports/M2.15B-6-daily-candle-execute-pilot-005930.md`. 코드/스키마/마이그레이션 변경 없음.
- **다음(별도 승인): M2.15B-7 — (a) 멱등성/포스트-영속 스모크(005930 재-execute → inserted=0/skipped_fresh) 또는
  (b) 5종목 execute-pilot 계획.** 5종목 execute-pilot은 미승인. DECISIONS 변경 없음.

**M2.15B-5 Daily Candle Live Read-Only Pagination Probe (`DONE`, live read-only probe + docs)**: M2.15B-4
페이지네이션을 실제 KIS read-only로 1종목(005930) 검증. **DB 쓰기 0 · execute-pilot 미실행 · 일봉 row 미삽입
(1d 0 유지) · SignalLog/Trade/Order 미생성 · KIS 주문 API/place_order 미호출 · 마이그레이션 없음 · 런타임 코드
변경 없음 · 스케줄러/디스패처 없음 · 시크릿 미출력 · 3 플래그 false · M2.14B-3d 미승인.**

- 방법: 일회성 인라인 호출로 `get_daily_candles("005930", count=252, adjusted=False)` 1회(collector execute/upsert
  미경유, 결과 미영속). `_fetch_daily_page` 래핑으로 페이지 호출 수 계측.
- 결과: **252봉 요청 → 252봉 반환**, provider_page_calls=**3**, business_date 중복 **0**, 최신일 우선 정렬 ✅,
  OHLCV/volume/trading_value 완전. 기간 20250618~20260629(252 영업일 ≈ 1년) → **52주 지표 부트스트랩 충분**.
- rate-limit: `EGW00201` 1회 관측 → `_request` 내장 backoff가 자동 재시도하여 복구(최종 성공, 데이터 손실 없음).
- adjusted=False(원주가 `FID_ORG_ADJ_PRC=0`)로 호출 — 수정주가 채택 여부는 M2.15B-6에서 결정.
- DB 불변: market_data `1d` 0→0, Trade 35→35. total/SignalLog 소폭 증가는 무관한 백그라운드 작업(프로브는 read-only
  HTTP만, 어떤 쓰기도 없음).
- 산출물: `docs/reports/M2.15B-5-daily-candle-live-pagination-probe.md`. 코드/스키마/마이그레이션 변경 없음.
- **다음(별도 승인): M2.15B-6 execute-pilot — 우선 1종목 → 이후 1~5종목**으로 라이브 read-only 수집 결과를
  `market_data timeframe="1d"`에 멱등 적재. M2.15B-5a(페이지네이션 수정)는 불필요(실패 없음). DECISIONS 변경 없음.

**M2.15B-4 Daily Candle Pagination Implementation (`DONE`, backend, no migration)**: KIS 1회 ~100봉 한도를 넘어
최대 252봉을 모으도록 `get_daily_candles`에 **end-date 페이지네이션 + business_date dedupe** 추가. **라이브 KIS
미호출 · execute-pilot 미실행 · 일봉 row 미삽입(1d 0 유지) · 마이그레이션 없음 · 프론트/스케줄러/API 없음 ·
SignalLog/Trade/Order 없음 · 주문 TR/place_order 미사용 · M2.14B-3d 미승인.**

- 구현: `_fetch_daily_page`(단일 윈도우 조회)로 분리 + `get_daily_candles`가 cur_end를 뒤로 옮기며 페이징
  (윈도우 `DAILY_PAGE_LOOKBACK_DAYS=200`). dedupe(business_date), 최종 **business_date 내림차순(최신일 우선)**,
  **무한 루프 가드**(빈 페이지·진척 없음(oldest 미이동)·`MAX_DAILY_PAGES=8`), 요청 count 상한 `MAX_DAILY_COUNT=400`.
  여전히 read-only quotations · 주문 무관 · 결측 행 skip · trading_value DTO 보존.
- collector/script 무변경(페이지네이션은 provider 내부 투명; dry_run_plan est_requests가 ceil(count/100)으로 이미
  페이지 수 반영 — 252×2종 = 6). dry-run 기본·coverage 읽기·execute 가드 유지.
- 테스트(+9, `test_m2_15b4_daily_candle_pagination.py`): 단일 페이지 20 · 252 다중 페이지 합산/dedupe/정렬 ·
  count cap · 빈 페이지 중단 · 진척 없음 중단(무한 루프 방지) · MAX_PAGES 호출 상한 · 결측 행 skip · trading_value
  보존 · 후속 페이지 500 안전 raise. MockTransport(실 KIS/실 키 미사용). B-2 14 + **전체 백엔드 1754 passed.**
  수동 스모크: dry-run/coverage-only만 → **market_data 1d 0 유지·Trade 35 불변**.
- **다음(별도 승인): M2.15B-5 라이브 read-only 페이지네이션 프로브(005930, DB 쓰기 0)** → 그 뒤 별도로 M2.15B-6
  execute-pilot(1~5종목). DECISIONS 변경 없음.

**M2.15B-3 Daily Candle Live Read-Only Probe (`DONE`, read-only probe + docs)**: `get_daily_candles`가 실제 KIS
read-only로 일봉을 가져오는지 005930 1종목만 검증. **DB 쓰기 0 · execute-pilot 미실행 · 일봉 row 미삽입 ·
SignalLog/Trade/Order 미생성 · KIS 주문 API 미호출 · 마이그레이션 없음 · 스케줄러/디스패처 없음 · 시크릿 미출력 ·
M2.14B-3d 미승인.**

- 산출물: `docs/reports/M2.15B-3-daily-candle-live-readonly-probe.md`.
- **프로브 성공**: 엔드포인트 `inquire-daily-itemchartprice`(TR `FHKST03010100`) 동작 확인. count=20→20봉
  (20260601~0629), count=252→**100봉**(20260129~0629, KIS 1회 ~100봉 한도) · OHLCV 완전 · volume·**trading_value
  존재** · rate-limit 미관측 · 코드 TODO(엔드포인트 재확인) **실증 완료**.
- **252봉엔 페이지네이션 필요**(1회 100봉 한도 — M2.15B-1 예상 갭 확인). DB 검증: market_data `1d` **0→0(프로브
  쓰기 0)** · Trade 35 불변(total/SignalLog 소폭 증가는 무관한 백그라운드 작업).
- **다음(별도 승인): M2.15B-4 — `get_daily_candles` 페이지네이션 추가(252봉 다중 호출/dedupe) + 테스트**, 그 뒤
  execute-pilot(1~5종목, 라이브 read-only 수집→`1d` 적재)도 별도 승인 시. 수정주가/trading_value 컬럼은 4단계 설계.
  **execute-pilot 여전히 미승인.** DECISIONS 변경 없음.

**M2.15B-2 Daily Candle Collector Implementation (`DONE`, backend, no migration)**: M2.15B-1 설계대로 일봉
수집기 1차 구현. **dry-run 기본 · 라이브 KIS 미호출 · dev DB execute 미실행(일봉 0 유지) · 마이그레이션 없음 ·
프론트 없음 · API 실행 엔드포인트 없음 · 스케줄러/잡 없음 · SignalLog/Trade/Order 미생성 · 주문 TR/place_order
미사용 · M2.14B-3d 미승인.**

- KIS read-only 메서드 `KISPaperBrokerClient.get_daily_candles(symbol, ..., count=252, adjusted)` 추가 — 일봉
  차트 엔드포인트(`inquire-daily-itemchartprice`, TR `FHKST03010100`) **라이브 전 KIS 문서 재확인 TODO 명시**.
  결측/비정상 행 안전 skip(`_parse_daily_row`), 방어적 count 상한. **주문 경로 미사용**(기존 `_request` 재사용).
  신규 `DailyCandle` DTO(schemas.py).
- 서비스 `services/market_data_daily_collector.py`: 파일럿 유니버스 빌드(symbols/--limit/--from-watchlist,
  기본 005930·000660) · dry-run 계획(무쓰기·무 KIS) · coverage report(읽기, 20/50/120/252) · execute 수집
  (provider 주입 시). **멱등 upsert**(market_data `timeframe="1d"`, PK ON CONFLICT) · **인트라데이 1m/5m 미덮어쓰기**
  · 동일값 skip · **충돌 보존(overwrite=False면 미덮어쓰기·conflict 보고)** · per-symbol status(success/
  skipped_fresh/conflict/failed_transient/failed_permanent/insufficient_data) · 부분 성공 · 시크릿 마스킹(sanitize).
- 스크립트 `scripts/collect_daily_candles.py`: **dry-run 기본**. execute는 `--execute`+
  `--confirm-daily-candle-collection`+hard guard(APP_ENV non-prod·3 플래그 false·DB URL local/dev/test) 통과 시만.
  `--coverage-only` 읽기. (M2.15B-2에선 dev DB execute 미실행.)
- 테스트(+14, `test_m2_15b2_daily_candle_collector.py`): 파싱/매핑(MockTransport·실 키 미사용·키 미노출) ·
  dry-run 무쓰기 · coverage 임계 · 멱등 upsert·재실행 무중복 · **인트라데이 미덮어쓰기** · 충돌 보존/overwrite ·
  부분 성공·transient/permanent 분류 · insufficient · 가드(confirm/execute/prod/플래그/DB URL) · SignalLog/Trade 0.
  **전체 백엔드 1745 passed.** 수동 스모크: dry-run/coverage-only만 실행 → **market_data `1d` count 0 유지**.
- **다음(별도 승인): M2.15B-3 dry-run/coverage 운영 스모크 또는 execute-pilot(5종)로 실제 일봉 수집**(라이브 KIS
  read-only). 252봉 적재 후에만 M2.15C 스캐너. DECISIONS 변경 없음.

**M2.15B-1 Daily Candle Collector Design (`DONE`, docs/design-only)**: M2.15B(NOT_READY) 이후 52주 분석용 일봉
수집을 안전·rate-limit 인지로 설계. **수집기 구현 없음 · 마이그레이션 없음 · 라이브 KIS 호출 없음 · broker/KIS
주문 없음 · SignalLog/Trade/Order 없음 · 스케줄러/디스패처 없음 · M2.14B-3d 승인 아님.**

- 산출물: `docs/design/M2.15B-1-daily-candle-collector-design.md`(저장·trading_value 결정·KIS 일봉 API 계약·
  파일럿 유니버스·rate-limit/retry/캐시·운영 모드·구현 배치·테스트·M2.15C readiness gate·open questions).
- 저장: 기존 `market_data`에 **`timeframe="1d"`로 무마이그레이션 적재**(PK `(symbol, timeframe, ts)` 멱등 upsert,
  인트라데이 행과 분리·미덮어쓰기, ts=거래일). 스키마 한계상 `trading_value`/`source`/수정주가 컬럼 없음.
- trading_value: **옵션 A(권장)** — 첫 수집기는 OHLCV만, 유동성은 volume(+close×volume 근사); 정밀 거래대금
  컬럼/마이그레이션은 별도 승인 보류.
- KIS 일봉: 신규 read-only `get_daily_candles(symbol, ..., count=252)` 메서드 필요(분봉 `inquire-time-itemchartprice`
  대응 일봉 `inquire-daily-itemchartprice`/`FHKST03010100` **추정 — 구현 시 확정**). M2.14O 하드닝(transient 분류·
  bounded 재시도·마스킹·degraded·가짜 데이터 금지) 재사용. 페이지네이션(252봉 분할) 필요.
- 파일럿: WatchlistSymbol 단계(5→20→110), 전체 시장은 rate-limit 검증 후. 초기 스케줄러/전체 루프/API 실행 없음.
- 운영 모드: dry-run(기본·무쓰기) / execute-pilot(--confirm, 일봉만 멱등 upsert) / coverage report(읽기) /
  repair(미래·승인). 구현 배치: KIS 메서드 + `market_data_daily_collector` 서비스 + `scripts/collect_daily_candles.py`
  (M2.14L 가드 패턴). 프론트/스케줄러/API 실행 없음.
- **M2.15C gate**: 일부 종목 252 일봉 + OHLCV 완전성 + 중복통제 + coverage report + Trade/Order/주문 거동 0 일 때만.
  20~50봉뿐이면 52주 스캐너 금지(단기 프로토타입만).
- **다음 권장(별도 승인): M2.15B-2 일봉 수집기 구현**(KIS read-only 메서드+서비스+스크립트, dry-run 기본).
  DECISIONS 변경 없음(컬럼 마이그레이션 필요 시 그때 별도 승인).

**M2.15B Leader Trend Following Data Readiness Diagnostic (`DONE`, read-only + docs)**: 주도주 추세추종 V1
구현 전 데이터 준비도를 읽기 전용으로 진단. **스캐너/전략 구현 없음 · SignalLog/Trade/Order 없음 · broker/KIS
주문 미호출(라이브 프로브 생략) · 마이그레이션 없음 · 런타임 변경 없음 · 플래그 false 유지 · M2.14B-3d 미승인.**

- 산출물: `docs/reports/M2.15B-leader-trend-data-readiness.md`.
- **판정: NOT_READY.** 측정(읽기 전용): `market_data` 269,636행이 **전부 1m/5m 인트라데이**(일봉 0) · 데이터
  ~10 거래일(252 불가) · KIS 클라이언트에 **일봉 OHLCV fetch 메서드 없음**(`get_minute_candles`만) ·
  `trading_value` 컬럼 없음 · `Theme`/`SymbolThemeMembership`=0(테마 V2) · 유니버스는 `WatchlistSymbol` 110종.
- 결론: 52주 high/low·MA20/MA50·20일 신고가·거래대금을 **어떤 종목으로도 신뢰성 있게 계산 불가**. **지금 스캐너/
  전략 구현 금지** — 일봉 수집 인프라 선행 필요.
- **다음 권장(데이터 선행)**: M2.15B-1 일봉 수집기 설계(KIS read-only 일봉 엔드포인트 `inquire-daily-itemchartprice`
  류 + 신규 메서드 계약 + rate-limit 인지 배치/캐시-first, M2.14O backoff/마스킹 패턴) → 110 워치리스트(또는 5~20종)
  파일럿으로 `market_data` `1d` 적재 → 252봉 충분 후에만 **M2.15C 스캐너 지표(SignalLog 없음)**. (`trading_value`
  추가 필요 시 별도 승인 마이그레이션.) DECISIONS 변경 없음.

**M2.15A Leader Trend Following Strategy Design (`DONE`, docs/design-only)**: 주도주 추세추종 paper 연구 전략군의
설계. **백엔드/프론트 구현 없음 · 마이그레이션 없음 · SignalLog/Trade/Order 없음 · broker/KIS 없음 · 스케줄러/
디스패처 없음 · 실거래 없음 · M2.14B-3d 승인 아님 · paper SignalLog-only(궁극).**

- 산출물: `docs/design/M2.15A-leader-trend-following-strategy-design.md`(아키텍처 적합성·개념 정식화·V1 스캐너·
  V1 추세추종 신호·연구 리스크·데이터 요건/갭·단계 통합 계획·M2.14 루프 적합·안전 제약).
- 두 부분 분리: (1) **주도주 스캐너**(신규 scanner facts/condition로 52주 지표 계산 → CandidateEvent;
  현 facts엔 52주 high/low 없음 — 신규 필요), (2) **추세추종 신호**(신규 `Strategy` 서브클래스
  `leader_trend_following`을 registry 등록 → 기존 paper 경로로 **SignalLog만**). 후보 필터(Condition A/B)와
  진입/청산 신호를 분리.
- 개념: `low_52w_gain_pct=(price/low52-1)*100`, `drawdown_from_52w_high_pct=(high52-price)/high52*100`.
  A: gain≤200 & drawdown≤10 / B: gain≥200 & drawdown≤20. **후보 필터일 뿐 매수 신호 아님.**
- 데이터 갭: 종목별 **일봉 ~252개**(52주 high/low)가 핵심 — 현 SignalLog 경로는 분봉 중심이라 일봉 대량 수집·
  rate-limit이 변수. **V1 신규 마이그레이션 불필요**(MarketData/ScannerRule/StrategyVersion/Theme 재사용);
  후보 영속 전용 테이블이 필요해지면 별도 승인.
- 단계: A(설계)→B(데이터 준비 진단)→C(스캐너 지표, SignalLog 없음)→D(후보 영속/읽기)→E(추세추종 paper 전략,
  SignalLog-only)→F(UI 읽기)→G(baseline 비교)→H(수동 tick 수집)→이후 자동화는 충분한 실 표본+별도 승인.
- **다음 권장: M2.15B 데이터 준비 진단**(일봉 252·52주 가용성·KIS rate-limit, 읽기 전용). DECISIONS 변경 없음.

**M2.14O US Market Refresh FRED 500 Hardening (`DONE`, backend, no migration)**: FRED 5xx/transient 실패가
미국장 갱신/자동잡 흐름 전체를 깨고 **API 키를 예외/로그/DB에 노출**하던 문제를 수정. **거래/주문/스케줄러
무관 · 마이그레이션 없음 · 프론트 변경 없음 · 플래그 불변(false) · M2.14B-3d 승인 아님.**

- 근본원인: `FredProvider._series`의 `resp.raise_for_status()`가 500에서 `httpx.HTTPStatusError`를 던지고,
  `fetch_snapshot`이 `f"FRED request failed: {e}"`로 감싸면서 **URL의 `api_key` 값이 그대로** 예외 메시지에
  들어감 → 잡의 `except`가 이를 로그·`app.state.us_market_refresh_last_error`·`scheduler_runs` 요약에 저장
  (키 누출). 또한 단일 시리즈 5xx가 갱신 전체를 hard-fail.
- 수정: (1) **`redact_api_key()`** 로 `api_key=<값>`→`api_key=***REDACTED***` 마스킹, 모든 예외 메시지에 적용
  (방어적으로 refresh 결과 reason도 재마스킹). (2) `UsMarketProviderError(transient=...)` 분류 + `_series`에
  **bounded 재시도**(5xx/429/timeout/네트워크만, 최대 3회, 소폭 backoff; 4xx는 재시도 안 함). (3)
  `UsMarketRefreshService.refresh()`가 `UsMarketProviderError`를 잡아 **degraded RefreshResult**(updated=False·
  degraded=True·transient·stale_session_date) 반환 — 잡을 FAILED로 만들지 않고 **기존 캐시 스냅샷 보존**(upsert
  안 함 → 좋은 값을 null로 덮어쓰지 않음). 키 없음(`FRED_API_KEY` 미설정)도 안전 degraded.
- 테스트(+10): redact 마스킹 · 500 transient(재시도 3회·키 미노출) · 429 transient · timeout transient ·
  4xx non-transient(재시도 0·키 미노출·상태코드 포함) · 키 없음 degraded · "."/빈 observations 처리 · refresh
  500 degraded+stale 캐시 보존 · 캐시 없을 때 degraded · 정상 시 upsert 유지. 실 FRED/실 키 미사용(MockTransport).
  **전체 백엔드 1731 passed.**
- 운영 노트: **로그/채팅/출력에 FRED API 키가 노출됐다면 즉시 키를 회전(rotate)할 것.** FRED 5xx는 외부 provider
  저하로 취급(전략 실패 아님). 안전: place_order/Trade/Order/스케줄러 토큰 없음 · 실 키 미커밋 · 플래그 false 유지.

**M2.14N Demo Manual Tick One-time Run (`DONE`, dev-DB ops, docs-only commit)**: SYNTHETIC/DEMO 페어로 수동
recurring-plan tick 흐름을 end-to-end 검증(prepared→active→tick-once→skip). **코드 변경 없음 · 마이그레이션
없음 · Trade/Order 미생성 · broker 주문 미호출 · 스케줄러/디스패처 미활성 · tick 1회만 · M2.14B-3d 승인 아님 ·
합성 결과는 거래/성과 증거 아님.**

- 흐름: 계획 #1 활성화(`activate_plan`, confirmed) → status prepared→**active** · next_run_at 설정 ·
  SignalLog/Trade 불변. 그 뒤 **수동 tick 1회**(`tick_plan_once` = 엔드포인트와 동일 경로, signal-only
  SignalService 주입) → 양쪽 **skip**("no actionable strategy signal, stale/closed market, or duplicate candle").
- 결과: 계획 #1 status **active** · completed_runs **0→1**(시도 카운트) · last_run_at 설정 · next_run_at +60s.
  baseline/challenger 둘 다 signal_created=false(skip). **SignalLog 80880→80880(delta 0)** · **Trade 35→35** ·
  orders_created 0 · trades_created 0. (KIS rate-limit은 **읽기 전용 캔들 시세** 조회에서 발생 → skip 흡수; 주문
  경로 미호출.) 제3 세션 무영향(sessions 2 유지).
- 안전: dispatcher readiness 여전히 비실행(can_execute false · scheduler_job_registered false ·
  api_execution_endpoint_registered false) · 3 플래그 false 유지 · 스케줄러 잡 0 · 디스패처 활성 0 · 파일 변경 0.
- **데모 흐름 검증일 뿐 — 수익성 판단·M2.14B-3d 정당화 불가.** 시세 가용 환경에서 반복 tick하면 SignalLog가
  쌓이나, 그 역시 합성 페어라 거래 증거 아님. **M2.14B-3d 계속 미승인.** DECISIONS 변경 없음(D-24~27 커버).

**M2.14M Dev Synthetic Pair Creation (`DONE`, dev-DB ops, docs-only commit)**: M2.14L 스크립트를 dev DB에
`--execute`로 **1회** 실행해 라벨된 SYNTHETIC/DEMO 페어 1개 + prepared 계획 1개를 생성. **코드 변경 없음 ·
마이그레이션 없음 · SignalLog/Trade/Order 미생성 · broker/KIS 미호출 · 수동 tick 미실행 · 계획 활성화 안 함 ·
스케줄러/디스패처 미활성 · M2.14B-3d 승인 아님.**

- 생성된 데모 레코드(dev DB): Strategy #294 · StrategyVersion #327(baseline)/#328(challenger, DRAFT·
  auto_trade off·moving_average_cross·`_synthetic`) · PaperSignalSession #10(baseline·active·candidate_proposal·
  005930)/#11(challenger·active·signal_challenger·baseline #10 연결) · PaperSignalRecurringRun #1(**prepared**·
  completed_runs 0·next_run_at null·interval 60·max_runs 30). 모든 레코드 라벨 5종(SYNTHETIC/DEMO/
  NOT_TRADING_EVIDENCE/NOT_REAL_PERFORMANCE/DEV_ONLY)·`started_by=dev_synthetic_bootstrap`.
- 안전 불변식 검증: 실행 전/후 SignalLog **80880 불변** · Trade **35 불변**(기존 이력, 부트스트랩이 안 건드림) ·
  PaperSignalSession 0→2 · RecurringRun 0→1. 2회차 `--execute`는 **reused=true**(중복 0). 플래그 3종 false 유지.
- **이 데이터는 거래/성과 증거가 아니다(DEMO).** 수익성 판단·M2.14B-3d 정당화·실 비교 증거로 쓰지 않는다.
- **다음(별도 승인)**: M2.14N — 이 prepared 계획을 active 전환 + 데모 라벨된 수동 tick **1회** 시연(데모임을
  명시). 실 수집은 여전히 실 상류 데이터+(모의)시세 필요. **M2.14B-3d 계속 미승인.** DECISIONS 변경 없음.

**M2.14L Dev-only Synthetic Pair Bootstrap (Implementation) (`DONE`, dev-script + tests, no migration)**: M2.14K
설계대로 **dev 전용 SYNTHETIC** 부트스트랩 스크립트 구현. **프론트 변경 없음 · 마이그레이션 없음 · SignalLog/
Trade/Order 미생성 · broker/KIS 미호출 · 스케줄러/디스패처 미활성 · 실 dev DB에 영속 합성 데이터 미생성(--execute
미실행) · M2.14B-3d 승인 아님.**

- 스크립트: `backend/scripts/dev_seed_synthetic_signal_pair.py`(import 가능·테스트 가능). 기본 **dry-run**(읽기
  전용·계획 출력). 쓰기에는 `--confirm-dev-synthetic-bootstrap` + `--execute` 둘 다 + hard guard 통과 필요.
  hard guard(`evaluate_guards`): APP_ENV production 거부 · confirm/execute 누락 거부 · KIS real/runner/dispatcher
  플래그 true면 거부 · DB URL 비-local/dev/test 거부. 실패 시 **롤백**(부분 데이터 없음).
- 생성(execute·서비스 경유): Strategy ×1 + StrategyVersion ×2(DRAFT·strategy_type=moving_average_cross·
  symbol·auto_trade off·`_synthetic` 등 메타) + PaperSignalSession ×2(active·같은 종목·challenger=signal_challenger·
  baseline 연결·`started_by=dev_synthetic_bootstrap`) + 반복 계획 ×1(`create_prepared_pair_plan`로 **prepared**).
  스캐너/후보/제안 미생성(검증상 불필요). **SignalLog/Trade/Order/스케줄러 잡 절대 미생성 · tick 안 함.**
- 라벨 5종(SYNTHETIC/DEMO/NOT_TRADING_EVIDENCE/NOT_REAL_PERFORMANCE/DEV_ONLY)을 name/description/note/버전
  params/started_by에. 출력에 "거래 증거 아님·수익성 판단 불가·3d 정당화 불가" 명시. idempotent(라벨/started_by/
  symbol로 재사용, `--force-new`로 분리). cleanup **미구현**(미래엔 라벨된 합성만·reset/purge 없음).
- 테스트: `backend/tests/test_dev_seed_synthetic_signal_pair.py`(11) — 가드(confirm/execute/production/플래그/
  DB URL)·테스트 DB seed(허용 레코드만·라벨·도메인 유효·계획 prepared·SignalLog/Trade 0)·idempotent·force-new·
  빈 DB find None. **전체 백엔드 1721 passed.** dry-run 스모크(dev DB, --execute 없음): DB 무변경(sessions=0 유지).
- **사용법**: dry-run `python -m scripts.dev_seed_synthetic_signal_pair`(읽기 전용). 쓰기(DEV/DEMO 전용, 명시
  승인 없이 실행 금지) `... --confirm-dev-synthetic-bootstrap --execute`. **출력은 거래 증거 아님.**
- **다음(별도 승인)**: 환경에서 `--execute`로 데모 페어 생성 후 데모 라벨된 M2.14H 수동 tick 시연. 실 수집은
  여전히 실 상류 데이터+(모의)시세 필요. **M2.14B-3d 계속 미승인.** DECISIONS 변경 없음(D-24~27 커버).

**M2.14K Dev-only Synthetic Pair Bootstrap (Design) (`DONE`, docs/design-only)**: 빈 dev DB에서 수동 tick UI
흐름을 시연할 최소 baseline/challenger/계획 레코드를 만드는 **dev 전용 SYNTHETIC** 부트스트랩의 **계약 설계**.
**스크립트 미구현 · DB 데이터 미생성 · 런타임/마이그레이션 변경 없음 · 가짜 SignalLog/Trade/Order 없음 ·
broker/KIS 없음 · 스케줄러/디스패처 활성 없음 · M2.14B-3d 승인 아님.**

- 산출물: `docs/design/M2.14K-dev-synthetic-pair-bootstrap-design.md`(검증이 요구하는 최소 레코드 · 부트스트랩
  계약 · hard guards · 라벨링 · idempotency · cleanup · 검증 기대 · 리스크/완화 · 권고 · non-goals).
- 검증 최소 레코드(코드 확인): Strategy ×1 + StrategyVersion ×2(DRAFT·strategy_type=moving_average_cross·
  symbol·auto_trade off) + PaperSignalSession ×2(active·같은 종목·challenger=signal_challenger·baseline 연결·
  버전 연결) + 반복 계획(서비스 `create_prepared_pair_plan`로 prepared). 스캐너/후보/제안은 nullable FK라
  **검증엔 선택**(제안 카드 UI 진입 필요 시만 최소 추가). **SignalLog/Trade/Order/스케줄러 잡 절대 미생성.**
- 제안 스크립트(미구현): `backend/scripts/dev_seed_synthetic_signal_pair.py` — 기본 dry-run·`--confirm` 필수·
  APP_ENV/DB URL/3 플래그/스케줄러 잡 hard guard · 모든 레코드에 SYNTHETIC/DEMO/NOT_TRADING_EVIDENCE/
  NOT_REAL_PERFORMANCE/DEV_ONLY 라벨 · idempotent(`--force-new`) · 라벨된 합성만 cleanup(reset/purge 없음).
- 권고: **구현 가치 있음(dev 데모 언블록 한정)** — 별도 작업 M2.14L(가칭)로 명시 승인 후 작게·강하게 가드.
  구현 뒤 **데모 라벨된 M2.14H 시연 1회**. 실 수동 수집은 여전히 실 상류 데이터 + (모의)시세 필요.
  **M2.14B-3d 계속 미승인** — 합성 데이터는 자동화를 정당화하지 못함. DECISIONS 변경 없음(D-24~27 커버).

**M2.14J Data Collection Prerequisite Checklist (`DONE`, docs/ops-only)**: 수동 tick 수집 *전* 환경/데이터 준비를
확인하는 체크리스트(Session 1이 빈 DB에서 못 돈 원인 재발 방지). **런타임 변경 없음 · 마이그레이션 없음 ·
합성 데이터/가짜 SignalLog 없음 · Trade/Order 없음 · 스케줄러/잡 없음 · 실행 엔드포인트 없음 · reset/purge 명령 없음.**

- 산출물: `docs/runbooks/M2.14J-data-collection-prerequisite-checklist.md`(목적 · 빠른 판단 · 필요 환경 ·
  필요 데이터 · 데이터 출처(실데이터 선호/합성은 라벨·거래증거 불가) · 빈 DB 진단 기록 · **읽기 전용** 준비
  프로브(SELECT/count만) · Go/No-Go · M2.14H/부트스트랩/3d 관계).
- Session 1 진단 캡처: `sessions=0 · signal_challenger=0 · active_challenger=0 · recurring_plans=0 ·
  active_plans=0` → 정직하게 모을 표본 없음, **날조 금지**. Go는 유효 페어≥1 + 계획 가능 + 플래그 false +
  시세 접근(유용 SignalLog 기대 시) + 운영자가 "단발 비교≠누적" 이해 시에만.
- 다음 권장 행동: (1) M2.14J로 환경 준비 확인 → (2) 유효 페어 있으면 M2.14H 수동 tick 수집 → (3) 빈 DB가
  지속되면 **실 상류 데이터 준비** 또는 **dev 전용 SYNTHETIC 부트스트랩(별도 명시 승인)** 중 택1 → (4) 3d는
  아직 진행 안 함. **M2.14B-3d 여전히 미승인.** DECISIONS 변경 없음(D-24~27 커버).

**M2.14H Manual Data Collection Quickstart (`DONE`, docs/ops-only)**: 스케줄러 자동화 결정 전 운영자가 수동
tick으로 유용한 데이터를 모으는 한 장짜리 퀵스타트. **런타임 변경 없음 · 마이그레이션 없음 · 스케줄러/잡 없음 ·
API 실행 엔드포인트 없음 · 프론트 실행 컨트롤 없음 · 이 문서가 SignalLog/Trade/Order를 만들지 않음.**

- 산출물: `docs/runbooks/M2.14H-manual-data-collection-quickstart.md`(~95줄 · 세션 준비 · tick 루틴 · 최소 표본
  가이드 · tick별 기록 항목 · 판단 기준 · 안전 정지 기준 · 3d 재고 기준 · 가벼운 마크다운 로그 템플릿).
- 핵심: 데이터 수집은 **"계획 누적용 1회 기록"**으로(단발 비교는 누적 안 됨). 표본 <10 부족 / 10~29 관찰 /
  ≥30 비교 시작. 페어 1~3개 × ~30 tick 권장. 안전 정지(Trade/Order/broker 등장 · 수동 tick 없이 SignalLog/
  completed_runs 증가 · 플래그/잡/엔드포인트/버튼 출현). 로그는 마크다운 표일 뿐(DB/CSV/export 아님).
- **다음 권장 행동: 퀵스타트로 실제 수동 tick 데이터를 모은다**(페어 1~3개 × ~30 tick). 유용한 표본이 쌓이고
  3d 재고 기준이 모두 충족된 **뒤에만**, 사람 명시 승인 + 런북 §7 스모크로 M2.14B-3d 재고. **M2.14B-3d는
  여전히 미승인·미착수.** DECISIONS 변경 없음(D-24~27 커버).

**M2.14G Small UI Cleanup for operator clarity (`DONE`, frontend-only)**: M2.14F가 찾은 UI 마찰을 줄이는
프론트 명료화. **백엔드 런타임 변경 없음 · 마이그레이션 없음 · 스케줄러/잡 없음 · API 실행 엔드포인트 없음 ·
프론트 실행 버튼/config 토글 없음 · SignalLog/Trade/Order 거동 변경 없음 · 자동 폴링/useEffect mutation 없음.**

- A 섹션 그룹화: `ChallengerComparison`의 기록/상태 영역을 4개 그룹으로 시각 분리(`SectionGroup` 헬퍼) —
  **단발 비교**(PairRunOnce, "반복 계획에 누적 안 됨") / **계획 누적**(RecurringPlanControls, "수동으로 누를 때만
  1회") / **디스패처 상태(읽기 전용)**(status 패널, "이 화면에서는 실행 안 함") / **고급·디버그**(단일 세션,
  기본 접힘). 기존 M2.14E 인라인 범례 대체.
- B 디스패처 status 과밀 축소: 상단에 **컴팩트 요약**(실행 가능 여부 불가 / 스케줄러 없음 / API 실행 엔드포인트
  없음 / 프론트 실행 버튼 없음 / 자동매매 아님) + "due 계획이 있어도 자동 실행되지 않습니다" 노출, 원시 상세
  (config 플래그·full plan_counts·safety_invariants·warnings)는 중첩 `<details> "원시 상태 자세히"`로 접음.
  여전히 읽기 전용·GET만.
- C 단발 vs 계획 tick 구분: PairRunOnce 제목 "단발 비교용 1회 기록" + helper "현재 페어를 한 번 기록…
  completed_runs에는 누적되지 않습니다". recurring tick은 "계획 누적용 1회 기록"(기존) — 라벨 혼동 제거.
- D 표본 힌트: 비교 결과에 **참고용 표본 힌트**(paired=min(baseline,challenger) 신호 수: <10 표본 부족 /
  10~29 관찰 중 / ≥30 비교 시작 가능) + "표본이 적을수록 해석 불안정". **기존 카운트만 사용 — 새 백엔드 지표/
  필드 없음.**
- 무변경 증명: 기존 API 호출 동일(신규 POST/PATCH/DELETE 0 · dispatch/scheduler/config-toggle 호출 0) ·
  `useEffect`/`setInterval`/`setTimeout` 0 · 백엔드/마이그레이션 0. 금지 라벨 부재, "자동 실행"은 부정 카피만.
- 검증: `npm run build`(tsc+vite) 통과. 백엔드 무변경 — readiness contract 8 sanity 유지. DECISIONS 변경 없음.
- **M2.14B-3d(스케줄러 통합)는 여전히 미승인·미착수.** 이 작업은 명료화만 — 실행 능력 추가 없음.

**M2.14F Manual Operation Trial (`DONE`, docs-only)**: 현재 수동 흐름(create→activate→tick→readiness→비교)이
이해 가능·유용·안전한지 운영 관점에서 검증. **새 기능 없음 · 백엔드/프론트 런타임·마이그레이션 변경 없음 ·
스케줄러/잡/API 실행/프론트 실행 컨트롤 없음 · 플래그 활성 없음 · Trade/Order/broker/KIS 없음.**

- 산출물: `docs/reviews/M2.14F-manual-operation-trial.md`. 트라이얼 모드 **C(정적 워크스루) + 기존 e2e 테스트를
  런타임 증거로 사용**(라이브 UI/독립 서버 비실용 — 브라우저 없음·dev Postgres 영속 미확인). 운영 API 경로
  (create/activate/tick/readiness/dispatch-core) 커버 테스트 **60 passed**(플래그 미활성·트랜잭션 롤백·broker 미호출).
- 결과: 흐름 **이해 가능·안전·유용**. prepared/active(수동 기록 가능)/tick/완료 명확, tick당 ≤2 SignalLog ·
  Trade/Order 0 · broker 미호출 검증. 마찰: dispatcher status 패널 **정보 과밀** · 비교 카드 **집약(빽빽)** ·
  비교표에 **표본수/신뢰도 표식 부재**.
- 데이터 유용성: 수동 tick으로 충분히 수집 가능(페어당 ~30 tick이 비교 시작점, max_runs 기본 30과 정합).
  **스케줄러는 지금 필수 아님** — 표본 가속일 뿐 새 분석 능력 추가 아님.
- 권고: **3d 직행 안 함.** (1) 수동 tick 데이터 수집 지속 → (2) M2.14G(가칭) 소폭 UI 정리(status 핵심만 강조 +
  비교 카드 그룹 분리 + 표본수 힌트) → (3) M2.14 문서 통합 → (4) 그 후 + 사람 명시 승인 시에만 M2.14B-3d(런북 §7
  스모크). **M2.14B-3d는 이 트라이얼 후에도 미승인 유지** — 별도 명시 승인 필요. DECISIONS 변경 없음(D-24~27 커버).

**M2.14B-3d Go/No-Go Checklist & Operator Runbook (`DONE`, docs-only)**: 스케줄러 통합 착수 여부 결정 전
Go/No-Go 체크리스트 + 운영 런북. **스케줄러 통합 미구현 · 잡 미등록 · API 실행 엔드포인트 없음 · 프론트 실행
컨트롤 없음 · 백엔드/프론트 런타임·마이그레이션 변경 없음.**

- 산출물: `docs/runbooks/M2.14B-3d-dispatcher-go-no-go-runbook.md`(현 상태 · Go 체크리스트 A · No-Go
  체크리스트 B/C · 미래 스케줄러 잡 계약 · 운영 런북 14항 · 필수 스모크 계획 · 최종 권고 · non-goals · D-28 제안).
- Go 체크리스트 A: **17/17 GREEN**(3c/3e 스모크 통과, 코어 비활성, readiness 외부 실행 불가, 프론트 실행 버튼
  없음, API 실행 엔드포인트 없음, autonomous run-now 미재사용, 전역 런너 거부, Trade/Order·broker 도달 불가,
  3플래그 false, SignalLog-only 입증, row-lock/batch/max_runs/stop 테스트됨).
- 미래 잡 계약: `recurring_plan_dispatcher`(기본 비활성, env_enabled=dispatcher 플래그), **잡 함수 첫 줄에서
  플래그 검사**(run_now 우회 봉쇄), 코어 호출만(중복 평가 경로 신설 금지), `paper_signal_recurring_runs`만 선택,
  API/프론트 노출 없음.
- 판정: **GO-ABLE(조건부) — 즉시 착수 아님, 사람 명시 승인 게이트.** 승인 시 최소 범위(스케줄러 잡 1개·기본
  비활성·신규 API/프론트/마이그레이션 없음·§7 스모크 전부 통과). 미승인 시(권장 기본) 일시 정지 + 수동 tick
  데이터 수집/문서 통합/UI 단순화.
- **이 런북은 프로덕션 활성을 승인하지 않는다.** 3d 구현/활성은 별도 사람 명시 승인 필요. DECISIONS 변경 없음
  (D-27 커버); 3d 착수 승인 시 게이트 사양을 D-28로 기록 제안.

**M2.14B-3e — Read-only Frontend Dispatcher Status (`DONE`, frontend-only)**: 기존 readiness API를 프론트에
**읽기 전용 상태**로 노출한다. **백엔드 런타임 변경 없음 · 마이그레이션 없음 · 스케줄러/잡 없음 · API 실행
엔드포인트 없음 · 실행/활성화/설정 토글 버튼 없음 · 자동 폴링 없음 · SignalLog/Trade/Order 없음.**

- API 바인딩(`research.ts`): `getPaperSignalRecurringDispatcherReadiness()`(GET
  `/paper-signal-recurring-runs/dispatcher/readiness`, **읽기 전용 GET만**). 타입(`research.ts`):
  `RecurringDispatcherReadiness`/`...Config`/`...PlanCounts`/`...SafetyInvariants`.
- UI(`StrategyProposalReportCard` > `ChallengerComparison` 내 `RecurringDispatcherStatusPanel`,
  `<details> "디스패처 상태(읽기 전용)"`): 부제 "현재는 상태만 보여줍니다. 이 화면에서는 어떤 계획도 실행하지
  않습니다." 안전 배지 8종(읽기 전용/실행 버튼 없음/스케줄러 없음/API 실행 엔드포인트 없음/SignalLog 생성 없음/
  주문 없음/거래 없음/자동매매 아님). 상태 카드 7종(실행 가능 여부 can_execute=false+이유 · 서비스 코어
  존재하나 미연결 · 스케줄러 잡 미등록 · 설정 플래그 **표시 전용 토글 없음** · 계획 카운트 "due여도 자동 실행
  안 함" · 안전 불변식 · warnings). 컨트롤은 **"상태 새로고침"(수동 GET) 버튼 1개뿐.**
- 무실행/무변경: 컴포넌트는 GET readiness만 호출(POST/PATCH/DELETE 0). create/activate/tick/stop/dispatch/
  scheduler/config-toggle 호출 0. `useEffect`/`setInterval`/`setTimeout`/폴링 없음(페이지 로드 자동 호출 없음 —
  수동 새로고침만). 금지 라벨(디스패처 시작/실행하기/잡 활성화 등) 부재. "자동 실행"은 전부 부정 카피.
- 검증: `npm run build`(tsc+vite) 통과. 백엔드 무변경 — readiness contract 8 sanity 유지. 프론트 테스트
  프레임워크 없음(미작성). DECISIONS 변경 없음(D-27 커버).
- **M2.14B-3d(스케줄러 통합)는 여전히 미승인·미착수.** 이 UI는 컨트롤 표면이 아니라 상태 표면일 뿐.

**M2.14 Midpoint Review (`DONE`, docs-only)**: M2.14A~B-3c 누적 상태를 중간 점검한다(스케줄러 통합 전).
산출물 `docs/reviews/M2.14-midpoint-review.md`(현 상태·완료 단계·아키텍처·안전 경계·복잡도/드리프트·잔여
작업·권고·non-goals·리스크 레지스터·최종 판정).

- 판정: **ON TRACK — 자동화 추가 전 human checkpoint 권고.** 안전 경계 견고(실거래/주문/거래/스케줄/노출 전부
  도달 불가, 플래그 3종 기본 false, 디스패처 코어 비활성·비스케줄·비노출). 드리프트 없음(여전히 paper 신호
  연구/비교 도구). 복잡도는 단계 수에서 오나 결합도/리스크 낮음.
- **이 리뷰는 M2.14B-3d 스케줄러 통합을 승인하지 않는다.** 다음 작업은 **사람 검토 후 결정**. 권장 순서:
  사람 검토 → (선택) M2.14B-3e 읽기전용 프론트 dispatcher status(실행 버튼 없음) → 그 다음에만 별도 명시
  승인 + 엄격 게이트(기본 비활성·잡 첫 줄 플래그 검사·API 실행 라우트 없음·프론트 실행 버튼 없음·Trade/Order
  불가·autonomous run-now 미재사용·킬스위치·스모크)로 M2.14B-3d.
- DECISIONS 변경 없음(D-24/25/26/27이 커버). 3d 착수 승인 시 "스케줄러 통합 게이트 사양"을 D-28로 기록 고려.

**M2.14B-3c — Disabled-by-default Recurring Dispatcher Service Core (`DONE`, backend, no migration)**: due active
반복 계획을 1패스 처리하는 **디스패처 서비스 코어**를 추가한다. **기본 비활성 · 직접 테스트 호출 전용 ·
스케줄러/잡 미등록 · API 실행 엔드포인트 없음 · 프론트 없음 · 마이그레이션 없음 · SignalLog는 기존 tick 경로로만 ·
Trade/Order 불가.**

- 서비스 `dispatch_due_recurring_plans_once(now=None, batch_limit=10, triggered_by="dispatcher_test")` —
  스케줄러/잡/API/프론트에 **미연결**(테스트가 직접 호출할 때만 동작). batch_limit은 `[1, MAX_DISPATCH_BATCH=50]`로
  clamp. 게이트(선택/실행 전): `paper_signal_recurring_plan_dispatcher_enabled=false`→no-op(`dispatcher_disabled`),
  `KIS_REAL_TRADING_ENABLED=true`→`real_trading_enabled`, `paper_signal_session_runner_enabled=true`→
  `global_runner_enabled`. 차단 시 선택/실행 0 · SignalLog/Trade/Order 0.
- 선택: repo `select_due_for_dispatch(now, limit)` — **`paper_signal_recurring_runs`만** 스캔(D-27,
  PaperSignalSession.active 미스캔). due = active AND next_run_at≤now AND completed_runs<max_runs. prepared/
  stopped/completed/failed/next_run_at null/미래/소진 제외. `ORDER BY next_run_at ASC, id ASC` LIMIT ·
  **row-lock `with_for_update(skip_locked=True)`**(동시 패스 중복 처리 방지, 무마이그레이션). `running`/`locked_at`
  컬럼 미추가.
- 실행: 선택된 계획마다 **M2.14B-2 `tick_plan_once` 코어 재사용**(신호 생성 로직 중복 0 — 디스패처가 직접
  SignalLog/evaluate_session 호출 안 함). D-26 의미론 유지(completed_runs=시도 횟수, max_runs→completed +
  next_run_at null, 선택 페어만 ≤2 SignalLog, 제3 세션 무영향). 결과 객체: dispatcher_stage/can_execute/
  blocked_reason/selected·processed·completed·failed·skipped_plan_ids/plans_selected/plans_processed/
  signals_created/orders_created=0/trades_created=0/warnings.
- readiness API 갱신: `dispatcher_stage="service_core_direct_invocation_only"` + `service_core_implemented=true`
  · `scheduler_dispatcher_implemented=false` · `api_execution_endpoint_registered=false` · `can_execute=false`
  (외부/스케줄 실행 불가 유지) · 여전히 읽기 전용(실행 안 함).
- 테스트(+13, 파일 94): 비활성 no-op · real/runner 차단 · due 선택(적격만·batch·정렬) · row-lock SQL(FOR UPDATE
  SKIP LOCKED) · 직접 실행(≤2 SignalLog·completed_runs++·max_runs→completed·제3 세션 무영향·batch clamp) ·
  선택 소스=recurring repo만(list_active 미호출 스파이) · 순차 호출 중복 tick 없음 · readiness 읽기 전용 유지.
  **전체 백엔드 1710 passed.**
- 미구현(유지): 스케줄러 통합 · API 실행 라우트 · 프론트 컨트롤 · 프로덕션 디스패처 활성. 결정 변경 없음(D-27 커버).
- **다음(별도 명시 승인)**: M2.14B-3d(플래그 뒤 스케줄러 통합, 기본 false) → 3e(읽기전용 프론트 status).

**M2.14B-3b — Read-only Recurring Dispatcher Status/Readiness API (`DONE`, backend read-only, no migration)**:
디스패처 readiness/status를 **읽기 전용**으로 노출한다. **디스패처 실행/코어 미구현 · 스케줄러/잡 미등록 ·
마이그레이션 없음 · 프론트 없음 · SignalLog/Trade/Order 없음 · row-lock 미도입.**

- 신규 엔드포인트 `GET /api/v1/paper-signal-recurring-runs/dispatcher/readiness`(읽기 전용, body 없음,
  confirm 불필요 — 변경 없음). **정적 라우트를 `/{plan_id}`보다 먼저 등록**(plan_id로 파싱되지 않음 — 테스트로 보장).
- 신규 config 플래그 `paper_signal_recurring_plan_dispatcher_enabled: bool = False`(기본 OFF, 잡/실행에 미연결,
  readiness 보고용일 뿐). `paper_signal_session_runner_enabled`/`KIS_REAL_TRADING_ENABLED` 기본값 불변.
- 응답: `dispatcher_stage=readiness_api_only` · `dispatcher_implemented=false` · `scheduler_job_registered=false`
  · `can_execute=false`(플래그 True여도 false) · `execution_blocked_reason=dispatcher_execution_not_implemented`
  · `config`(3 플래그) · `plan_counts`(total/prepared/active/stopped/completed/failed/due_active/not_due_active/
  active_missing_next_run_at/active_exhausted/with_last_error) · `readiness_blockers` · `safety_invariants` ·
  `warnings`(read-only/no tick/no SignalLog·Trade·Order).
- 읽기 전용 보장: repo `readiness_counts(now)`는 `count(*) FILTER(...)` 집계만(row 변경 0, row-lock/FOR UPDATE
  미사용). 서비스 `dispatcher_readiness()`는 tick/evaluate_session/generate_and_log_signal/scheduler 미호출.
- 테스트(+7, 총 81 in file): 200 shape · 기본 플래그 안전 · 라우트 순서(plan_id 미파싱, `/dispatcher`→422) ·
  카운트 정확(8 plans, active 4종 배타) · **무변경**(plan/SignalLog/Trade 불변) · **무실행 경로**(tick_plan_once
  스파이 미호출) · 플래그 True여도 can_execute=false. **전체 백엔드 1697 passed.**
- 결정 변경 없음(D-27이 커버). **디스패처 실행 구현(3c~)은 여전히 별도 명시 승인 필요.**

**M2.14B-3a — Pair-Scoped Recurring Signal Dispatcher Design (`DONE`, docs-only)**: 무인 디스패처 설계 문서.
**구현 미착수 · 백엔드/마이그레이션/엔드포인트/잡/프론트 변경 없음 · SignalLog/Trade/Order 없음.**

- 산출물: `docs/design/M2.14B-3-recurring-plan-dispatcher-design.md`(현 상태 · non-goals · 리스크 15종 ·
  옵션 비교 · 권장 아키텍처 · 선택/잠금 · tick 의미론 · 에러/backoff · API/UI 함의 · 테스트 계획 · 단계 ·
  블로커 · 최종 권고).
- 권장: **Option C**(=`paper_signal_recurring_runs`만 스캔하는 파일-스코프 디스패처)만, 별도 명시 승인 후.
  **Option D(전역 런너 활성)는 영구 거부.** `tick_plan_once` 코어 재사용(새 평가 경로 금지), 선택 조건
  `active AND next_run_at<=now AND completed_runs<max_runs` + bounded batch, 기존
  `ix_psrr_status_next_run_at` 인덱스 활용. 동시성은 **row-lock `FOR UPDATE SKIP LOCKED`로 무마이그레이션**
  가능(`running`/`locked_at`/실패카운트는 선택적 후속 마이그레이션 — 별도 승인).
- 필수 미래 플래그: 신규 `paper_signal_recurring_plan_dispatcher_enabled=false`(잡 첫 줄 검사 → `run_now`
  우회돼도 no-op). 기존 `paper_signal_session_runner_enabled` 분리·false 유지. 디스패처 tick도
  `KIS_REAL_TRADING_ENABLED=false` 불변 · SignalLog-only · Trade/Order 도달 불가.
- 단계: 3a(설계, 본 작업) → 3b(읽기 status API only) → 3c(비활성 코어 + 테스트 직접 호출, 잡 없음) →
  3d(플래그 뒤 스케줄러 통합) → 3e(읽기전용 프론트 status). 각 단계 별도 승인 + push-후 스모크.
- 결정: **D-27**(디스패처는 recurring_runs만 스캔 · 전역 런너 V1 영구 금지 · 비활성 기본 플래그 + 명시 승인).
- **다음**: 설계 리뷰 또는 최소 안전 단계(M2.14B-3b 읽기 status API)만 — 디스패처 실행 구현은 명시 승인 전 금지.

**M2.14E — Recurring Plan UI Copy & Structure Cleanup (`DONE`, frontend-only)**: M2.14D가 찾은 UX 혼동을
줄이도록 **프론트 라벨/구조만** 정리한다. **백엔드/마이그레이션/엔드포인트 변경 없음 · 디스패처/스케줄러/잡 없음 ·
자동 호출 없음 · SignalLog/Trade/Order 거동 변경 없음.** API 계약·액션 게이팅·확인 체크 모두 유지.

- 카피: "반복 신호 기록 계획"→**"수동 누적 신호 기록 계획"**; status 한글 부제 매핑(`statusLabel`)
  prepared→준비됨/active→**수동 기록 가능**/stopped→중지됨/completed→완료됨/failed→실패(원시 status는
  디버그용으로 괄호 병기). 버튼: "준비 상태 계획 만들기"→**"수동 누적 계획 만들기"**, "계획 active 전환"→**"수동
  기록 가능 상태로 전환"**, "선택 계획 1회 신호 기록"→**"계획 누적용 1회 기록"**, "계획 중지" 유지.
- next_run_at: tick 결과/목록에서 "next"→**"다음 기준 시각"** + "디스패처가 없어 자동 실행되지 않습니다(수동 기록
  참고용 메타데이터)" 주석 — "예약됨" 오해 차단.
- 구조: 세 기록 동작 목적 구분 범례 추가(단발 비교용=계획 없이 한 번 비교 / 계획 누적용=선택 계획에 1회씩 수동
  누적 / 고급·디버그용=한쪽 세션만). PairRunOnce 제목→**"단발 비교용 페어 신호 1회 기록"** + helper("계획을
  만들지 않고…바로 비교"). recurring tick helper("completed_runs 1회↑, 기준/챌린저 각 ≤1 SignalLog").
- 배지 보강: 기존 7종 + **"자동 실행 없음"·"버튼 클릭 시에만"**, "dispatcher 없음"→"디스패처 없음",
  "scheduler/job 없음"→"스케줄러/잡 없음".
- 인간 게이트 유지: create/activate/tick/stop 확인 체크 그대로 · `useEffect`/`setInterval`/`setTimeout`/폴링
  없음 · 자동 create/activate/tick/stop 없음 · 목록 갱신은 사용자 액션 후 또는 수동 새로고침만.
- 검증: `npm run build`(tsc+vite) 통과. 백엔드 무변경. 금지어/위험 호출 검색 clean("자동 실행"은 전부 부정 카피).
  DECISIONS 변경 없음(D-24/25/26 유지). M2.14D readiness 체크리스트 미충족 3건(active=실행 아님 인지 ·
  next_run_at 메타데이터 · 두 "1회 기록" 구분) 본 작업으로 카피/구조에서 해소.
- **다음**: M2.14B-3(디스패처)는 여전히 별도 명시 승인 + 설계 문서부터. 무인 반복 금지 유지.

**M2.14D — Recurring Signal Plan End-to-End UX & Safety Review (`DONE`, docs-only)**: M2.14A~C로 완성된
pair-scoped 반복 신호 *계획* 흐름 전체를 검토한다. **코드/마이그레이션/엔드포인트/디스패처 변경 없음.**

- 산출물: `docs/design/M2.14-recurring-plan-flow-review.md`(현 흐름 요약 · 안전 불변식 전수 확인 · UX 명확성
  리뷰 · 혼동 라벨 · 중복/중첩 동작 · 정리 권고 · 디스패처 readiness 체크리스트 · 명시 권고).
- 안전 검토 결과: create/activate/stop=SignalLog 0 · tick=≤2 SignalLog(선택 계획만) · 스케줄러/잡/디스패처/전역
  런너/Trade/Order 부재 · `run_due_sessions`/autonomous run-now/`run_now`/`list_active` 실행 경로 미사용 ·
  `KIS_REAL_TRADING_ENABLED`·`paper_signal_session_runner_enabled` false 유지 — 전수 충족.
- UX 발견: (a) "반복" 단어가 자동 실행로 오해 여지, (b) `active` 라벨이 "켜짐"으로 읽힘, (c) `next_run_at`이
  디스패처 없는데도 "예약됨"으로 보임, (d) PairRunOnce("페어 신호 1회 기록", 단발 비교용)와 recurring
  tick("선택 계획 1회 신호 기록", 계획 누적용)이 둘 다 "1회 기록"이라 혼동 — 기능 중복 아님(목적 다름).
- 권고: **디스패처 착수 전 소폭 UI 카피/구조 정리(Option B+C) 먼저**, 그동안 수동 tick 데이터 수집(Option E).
  디스패처(M2.14B-3)는 **계속 blocked** — readiness 체크리스트 미충족 3건(active=실행 아님 인지 · next_run_at
  메타데이터 명확 · 두 "1회 기록" 구분)이 모두 카피/구조 정리로 닫힌 뒤 + 별도 명시 승인 시에만.
- **다음 안전 작업 후보**: M2.14E(가칭) — Recurring Plan UI Copy/Structure Cleanup(frontend-only). 그 후
  체크리스트 재확인 → 통과 시 M2.14B-3는 **설계 문서 only**부터(구현 아님).
- DECISIONS 변경 없음 — D-24/25/26이 "디스패처는 막아둔다"를 이미 커버(본 검토는 운영 확인 + UX 후속).

**M2.14C — Frontend UI for Pair-Scoped Recurring Signal Run Plans (`DONE`, frontend-only)**: M2.14A/B-1/B-2
백엔드 API를 비교 카드 UI로 연결한다. **백엔드/마이그레이션 변경 없음 · 디스패처/스케줄러/잡 없음 · 모든 동작
사람 클릭 전용(page-load 자동 호출·백그라운드 폴링·자동 tick 없음) · 주문/거래 없음.**

- API 바인딩(`research.ts`): `createPaperSignalRecurringRun` / `listPaperSignalRecurringRuns` /
  `getPaperSignalRecurringRun` / `activatePaperSignalRecurringRun` / `tickPaperSignalRecurringRunOnce` /
  `stopPaperSignalRecurringRun`. 타입(`PaperSignalRecurringRun`, `PaperSignalRecurringTickSide`,
  `PaperSignalRecurringTickResult`).
- UI(`StrategyProposalReportCard` > `ChallengerComparison` 내 `RecurringPlanControls`, `<details> "반복 신호 기록
  계획"`): challenger active일 때만 노출(아니면 "active 전환 후" 안내). 안전 배지(선택한 페어만/SignalLog만/주문
  없음/거래 없음/자동매매 아님/dispatcher 없음/scheduler/job 없음). 생성(interval 60/120/300/600, max_runs
  1/5/10/30/60 + 확인 체크 "아직 자동 실행되지 않으며…") → prepared. 현재 페어 계획 목록(클라이언트 필터) +
  라디오 선택. 선택 계획 상태별 액션: prepared→active 전환(확인 체크), active→1회 tick(확인 체크, "최대 2개
  SignalLog"), prepared/active→중지(확인 체크). tick 결과(기준/Challenger 생성·skip · completed/max · next ·
  orders 0/trades 0 · 경고 · 비교 재실행 힌트). 수동 "계획 상태 새로고침" 버튼만(자동 폴링 없음).
- 모든 mutation은 `onClick`에서만 호출. `useEffect` 없음 → on-mount 자동 호출 없음. interval state는
  `tickIntervalSec`로 명명(타이머 `setInterval` 아님).
- 검증: `npm run build`(tsc+vite) 통과. 백엔드 무변경 — recurring 74 + M2.10 contract sanity 유지. 프론트 테스트
  프레임워크 없음(미작성). 금지어/위험 호출 검색 clean. 결정 변경 없음(D-24/25/26이 커버).
- **M2.14B-3(무인 디스패처)는 별도 명시 승인 후에만.**

**M2.14B-2 — Manual Tick-Once for One Active Recurring Plan (`DONE`, backend, no migration)**: 선택한 active 계획을
사람이 confirm해 **1회 tick**한다. **디스패처/스케줄러 아님**: 전체 active 스캔/`list_active`/`run_due_sessions`/
`run_now` 미사용 · 선택한 두 세션만 각각 1회 평가(최대 2 SignalLog) · 주문/거래 없음 · 잡 미활성.

- **마이그레이션 없음.** 서비스 `tick_plan_once(plan_id, confirmed, confirmed_by)`: confirmed+confirmed_by ·
  전역 게이트(실거래 OFF + 상시 런너 OFF) · 계획 **active** 필수(아니면 422) · `completed_runs >= max_runs`면 422 ·
  **tick 시점 재검증**(`_load_and_validate_pair`로 M2.8/M2.10 검증 재사용) → **M2.8 `evaluate_session` 재사용**으로
  baseline·challenger 각각 1회 평가(commit-free) → 계획 메타데이터만 갱신 후 **단일 커밋**.
- SignalLog 생성은 주입된 signal-only SignalService(`evaluate_session` 경유)만 사용 — 재귀 서비스가 직접
  `SignalLog()`/`generate_and_log_signal`을 만들지 않음. create/activate/stop은 여전히 signal_service=None(평가 도달 불가).
- 메타데이터 의미: `completed_runs`는 **페어 tick 시도 횟수**(SignalLog 수 아님) — 양쪽 skip이어도 +1; 평가 전 검증
  실패/예외는 +0(커밋 전 예외 → 롤백). `max_runs` 도달 시 status=`completed` + `next_run_at`=NULL, 아니면 active 유지 +
  `next_run_at = now + interval`. 세션/버전/제안 status 불변(세션 카운터만 — M2.10과 동일).
- API: `POST /paper-signal-recurring-runs/{id}/tick-once`(200). 404 미존재 · 422 비-active/소진/재검증 실패.
  tick 전용 DI(`get_recurring_run_tick_service`)가 signal-only SignalService 주입. **run/dispatcher/scheduler/run-all/
  run-due 엔드포인트 없음.**
- 테스트 `tests/test_paper_signal_recurring_run.py`(74, +21): tick 성공(2 SignalLog·선택 세션만·제3 세션 무영향·
  completed 전이·next_run_at)/skip(증가 유지)/소진·상태 게이트/재검증/검증실패 무증가 + **Trade 0·세션/버전/제안 불변**.
  전체 백엔드 1690 passed. M2.1/M2.8/M2.10/M2.14A/B-1 호환 유지. 결정: **D-26**(tick은 디스패처 아님).
- **M2.14B-3(디스패처)는 별도 명시 승인 후에만.** 무인 반복/전체 active 실행은 여전히 금지.

**M2.14B-1 — Activate Recurring Signal Run Plans Without Execution (`DONE`, backend, no migration)**: 반복 계획에
**상태 전환만** 추가한다(prepared→active, active→stopped). **활성화는 실행이 아니다**: 디스패처/잡/스케줄러 없음 ·
SignalLog/Trade/Order 미생성 · `SignalService.generate_and_log_signal`/페어 평가/`run_due_sessions`/`run_now` 미호출.

- **마이그레이션 없음.** 활성화 감사(audit)는 status 전환 + `updated_at`으로만 추적(별도 `activated_by/at` 컬럼
  추가 안 함 — 불필요한 스키마 변경 회피, D-24 계열).
- 서비스 `activate_plan(plan_id, confirmed, confirmed_by)`: confirmed+confirmed_by · 전역 게이트(실거래 OFF +
  상시 런너 OFF) · 계획 prepared여야 함(아니면 422) · **활성화 시점 재검증**(생성 후 세션/버전 상태 변동 대비 —
  `_load_and_validate_pair`로 M2.8/M2.10 검증 재사용) · 같은 페어 active 중복 거부(409). status="active" +
  `next_run_at = now + interval_seconds`(미래 디스패처용 **메타데이터일 뿐**, 이 단계에선 아무도 읽지 않음).
  completed_runs 0 / last_run_at null 유지.
- 중지 확장: 이제 **prepared/active 모두** 중지 가능. 종료(stopped/completed/failed) 중지는 422. 중지 시
  `next_run_at`=NULL로 비운다. 세션/버전/제안 불변.
- 상태별 경고: prepared/active/terminal 각각 — active는 "no dispatcher exists in this phase / no SignalLogs by
  activation / no orders or trades". 응답 `orders_created=0`/`trades_created=0` 항상.
- API: `POST /paper-signal-recurring-runs/{id}/activate`(200). 404 미존재 · 422 비-prepared/재검증 실패 · 409 active
  중복. **activate는 상태 전환만 — run/dispatcher/scheduler 엔드포인트 여전히 없음.**
- 테스트 `tests/test_paper_signal_recurring_run.py`(53, +21): 활성화 게이트/재검증(세션·버전 상태 변동)/중복 active/
  stop-active/list active + **활성화·중지 모두 SignalLog/Trade 0 · 세션/버전/제안 status 불변**. 전체 백엔드
  1669 passed. M2.1/M2.8/M2.10/M2.14A 호환 유지. 결정: **D-25**(활성화 ≠ 실행).
- **M2.14B-2(디스패처)는 별도 명시 승인 후에만.** active 계획은 별도 승인된 디스패처 없이는 절대 돌지 않는다.

**M2.14A — Pair-Scoped Recurring Signal Run Plan Schema + Inert Plan Management (`DONE`, backend, migration 포함)**:
pair-scoped 반복 신호 *계획*을 정의·관리만 한다(D-24, Option E의 1단계). **계획은 실행되지 않는다(inert):
prepared만 생성 · SignalLog/Trade/Order 미생성 · 스케줄러/잡 미활성 · 디스패처/run-loop/APScheduler 없음.**

- 마이그레이션 `q1r2s3t4u5v6`(down_revision=p1q2r3s4t5u6, additive): 신규 테이블 `paper_signal_recurring_runs`
  (status[prepared/active/stopped/completed/failed]=prepared, scope_type, baseline/challenger FK,
  interval_seconds, max_runs, completed_runs, last_run_at, next_run_at, created_by, stopped_*, last_error, note,
  created_at/updated_at). CheckConstraint: interval>0 · max_runs>0 · completed_runs>=0 · baseline≠challenger.
  인덱스 5종. **upgrade/downgrade/upgrade 라운드트립 검증 완료.** DB/code head → `q1r2s3t4u5v6`.
- 모델 `paper_signal_recurring_run.py`(+`models/__init__.py` 등록), repo `find_open_for_pair`(prepared/active 중복
  가드), 서비스 `PaperSignalRecurringRunService`(create_prepared_pair_plan / stop_plan / get_plan / list_plans).
- **자격 검증은 M2.8 `check_confirmation`/`check_global_gates`/`validate_session` + M2.10 관계 예외 재사용**
  (드리프트 방지). validate는 SignalLog/주문을 만들지 않음(signal_service=None로 검증 전용). 게이트: confirmed +
  confirmed_by · 실거래 OFF · 상시 런너 OFF · 두 세션 active · 관계/symbol 일치 · 버전 존재+DRAFT+auto_trade off ·
  interval∈[60,3600] · max_runs∈[1,390] · 같은 페어 비종료 계획 중복 거부.
- 중지: M2.14A는 **prepared만** 중지 가능(이미 종료된 계획 중지는 422). 세션/버전/제안 불변. 종료된 계획이 있어도
  같은 페어 새 prepared 계획 허용. 응답에 `orders_created=0`/`trades_created=0` + 경고 3종(prepared only/실행 전엔
  SignalLog 없음/주문·거래 없음) 항상 명시.
- API `app/api/v1/paper_signal_recurring_runs.py`(main 등록): `POST /paper-signal-recurring-runs`(201) ·
  `GET .../{id}` · `GET ...` · `POST .../{id}/stop`(200). 404 미존재 · 409 중복 · 422 검증 실패. **activate/run/
  dispatcher/scheduler 엔드포인트 없음.**
- 테스트 `tests/test_paper_signal_recurring_run.py`(32): 게이트/범위/중복/중지/조회 + **SignalLog/Trade 0 · 세션/
  버전/제안 status 불변 · 정확히 1행 생성** + API 201/409/404/422. 전체 백엔드 1648 passed. M2.1/M2.8/M2.10 호환 유지.
- **M2.14B(디스패처/활성화)는 별도 명시 승인 후에만.** 전역 런너/run_due_sessions/run_now 미사용 유지.

**M2.13 — Recurring Paper Signal Runner Operation Design (`DONE`, docs-only)**: 상시(반복) 신호 운영을
설계만 한다. **코드/런타임/마이그레이션 변경 없음 · 런너 미활성/미실행 · SignalLog/Trade/Order 미생성.**

- 코드 검증: 전역 런너(`run_due_sessions`)는 `list_active()`(active 전체) 순회 · SignalLog만 · status 불변 ·
  세션별 에러 격리 · candle dedupe + stale 가드. **`SchedulerControlService.run_now`는 enabled 플래그를 보지
  않고 `job.func` 직접 실행** → 전역 1회 우회 가능(핵심 리스크).
- 옵션 비교 A~E. **권장 = Option E (pair-scoped, `max_runs` 제한, SignalLog-only 반복 계획)**; 전역 런너 활성
  (Option D)은 V1 부적절로 연기.
- 제안: `POST /api/v1/paper-signal-recurring-runs` (+ `/stop`, GET status), 신규 테이블
  `paper_signal_recurring_runs`(상태/페어/interval/max_runs/completed_runs/...), **단일 디스패처 잡**이 검증된
  페어 1회 평가(M2.8/M2.10 게이트 재사용)를 시간축으로 반복. APScheduler 계획별 잡 생성은 비권장.
- 산출물: `docs/design/M2.13-recurring-runner-operation-design.md`. 결정: **D-24**(전역 런너 V1 금지 ·
  pair-scoped max-run SignalLog-only 우선).
- **다음 결정 필요**: (1) Option E 설계 채택, (2) 신규 테이블/마이그레이션 수용 여부, (3) M2.14 구현 범위.

**M2.12 — Paper Signal Comparison UX Cleanup (`DONE`, frontend-only)**: 비교/challenger 카드의 흐름을
명확히 한다. **백엔드 변경 없음 · 새 엔드포인트 없음 · 마이그레이션 없음 · 스케줄러/잡 미활성 ·
주문/거래 없음 · 페어/단일/비교 모두 사람 클릭 게이트 유지.**

- 단일 파일만 수정: `StrategyProposalReportCard.tsx`. 새 API 호출 없음(기존 `runPaperSignalPairOnce` /
  `runPaperSignalSessionOnce` / `comparePaperSignalSessions`만 사용, page-load 자동 호출 없음).
- **단계 가이드**(`LifecycleGuide`): 준비→Active 전환→페어 신호 1회 기록→신호 성과 비교 보기→
  반복 runner는 별도 승인 후. 상태로 현재 단계 강조(prepared=Active 전환, active 미기록=페어 기록,
  active 기록/비교=비교 보기). 반복 runner 단계는 미강조(별도 승인).
- **안전 배지**(`SafetyBadges`): "SignalLog만 · 주문 없음 · 거래 없음 · 자동매매 아님 · runner 별도"를
  일관 표시(표시 전용, 어떤 동작도 트리거 안 함).
- **페어를 1차 동작으로**: "공정 비교를 위해 먼저 기준/챌린저를 각각 1회 기록하세요 (권장)". 단일 세션
  run-once는 `<details>` "고급/디버그용: 단일 세션만 기록"로 강등.
- **빈/저데이터 비교 안내**(신호 수 기준): 둘 다 0 → "아직 비교할 신호가 없습니다. 페어 신호 1회 기록 후
  다시 비교하세요." / 한쪽만 0 → "한쪽 세션에만 신호가 있어 비교가 편향될 수 있습니다. 페어 신호 기록을
  권장합니다." / compare warnings는 "통계 주의:"로 표기(에러 아님).
- **페어 기록 후 넛지**: 결과 표시 후 "이제 ‘신호 성과 비교 보기’를 다시 눌러 결과를 확인하세요"
  (자동 비교 실행 아님 — 비교는 여전히 사람이 버튼 클릭).
- 검증: `npm run build`(typecheck+vite) 통과. 백엔드 무변경 — M2.10 페어 테스트 20 contract sanity 유지.
  금지 토큰/라벨 검색 clean. 새 위험 호출(broker/place_order/run_now/run_due_sessions/approve) 없음.

⛔ `ProposalService.approve` 내부 수정 금지(공유 매매-인접 경로). TESTING/ACTIVE challenger 생성 금지. 사람
검토 없는 자동 머티리얼라이즈·세션 자동 시작·잡 활성 금지. **M2.2 challenger를 기존
CandidateStrategyProposal/Experiment 경로에 억지로 끼워넣지 말 것(D-19).** 스키마 변경은 사람만 승인(D-20).

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
