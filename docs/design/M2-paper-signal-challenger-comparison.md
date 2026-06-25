# M2 Design — Paper Signal Version Comparison / Challenger Flow

> **Status:** design-only (no code). Produced during a guarded autonomous session at HEAD `c92fafa`.
> **Scope boundary:** this document designs the *next* paper-signal research-loop step. It implements
> nothing. No migration, no version creation, no approval, no session start, no scheduler, no trading.

## 0. Problem statement

The paper-signal track now reaches: candidate → proposal → review → DRAFT paper experiment → readiness →
PaperSignalSession → signal_logs → outcome board → AI analysis input → AI analysis run → report review →
**PENDING improvement proposal (M1)**.

To close the loop we eventually need: *PENDING proposal → safe challenger → signal-only comparison →
(later) human-gated promotion*. The **danger** is the existing materialization path:

- `ProposalService.approve(proposal_id)` creates a new `StrategyVersion` with **`status=TESTING`** (and
  forces `auto_trade_enabled=False`).
- `StrategyVersionRepository.list_active()` selects **`status IN (ACTIVE, TESTING)`**, and the
  default-enabled `strategy_runner` job runs those versions.
- Therefore **approving a paper-signal proposal via the existing flow makes the new version
  runner-eligible** — it would start generating `signal_logs` (and, if `auto_trade_enabled` were ever true
  + a real broker, orders). For the *signal-only* track we must avoid runner eligibility entirely.

## 1. Current approval / materialization behavior (verified)

| Aspect | Reality (verified in code) |
|---|---|
| What `ProposalService.approve` does | Creates a new `StrategyVersion` from `proposal.suggested_parameters`, sets `proposal.status=APPROVED`, `created_version_id`. |
| DRAFT or TESTING? | **TESTING** (`StrategyVersionStatus.TESTING`, hardcoded in `approve`). |
| Runner-eligible? | **Yes** — `list_active()` = ACTIVE/**TESTING**; the strategy_runner job (default enabled) evaluates TESTING versions and writes `signal_logs`. |
| `auto_trade_enabled` forced false? | **Yes** — `approve` sets `params["auto_trade_enabled"]=False` before creating the version. |
| Residual risk even with auto_trade=false | The TESTING version is **picked up by the live runner** → continuous `signal_logs` (background "execution effect"); it appears in active-version counts/operations; and it sits one flag-flip away from order capability. This is exactly the coupling rolled back during the readiness/activation milestones (see D-12). |
| Reuse existing approve for paper-signal proposals? | **No, not as-is.** It produces a TESTING (runner-eligible) version. The signal-only track must stay **DRAFT** (runner-invisible). |

**Key enabling facts (also verified):**
- `StrategyService.create_version(..., status=StrategyVersionStatus.DRAFT)` *can* create a DRAFT version
  directly — DRAFT is **not** in `list_active()`, so the runner never sees it.
- `CandidateProposalExperimentService.prepare` already implements the proven safe pattern: create a
  **DRAFT** version (`auto_trade_enabled` forced false) + DRAFT experiment + variant — runner-invisible.
- `PaperSignalOutcomeService.session_outcomes(session_id, horizon)` already computes per-session signal
  outcomes by filtering `signal_logs.paper_signal_session_id` (read-only, via `SignalOutcomeService`).

## 2. Option comparison

| Option | Safety | Size | Migration | UI complexity | ProposalsSection compat | PaperSignalSession compat | Runner/order risk | Promotion future |
|---|---|---|---|---|---|---|---|---|
| **A. Reuse `approve` but force DRAFT for `source="paper_signal_analysis"`** | ⚠️ Med — changes a shared, trade-adjacent approval path | Small | No | Low | ✅ | ✅ | Low if correct, but edits the critical approve flow | OK |
| **B. New `prepare-signal-challenger` → DRAFT-only version** | ✅ High — isolated; never calls `approve`; DRAFT only | Medium | No | Med | additive | ✅ (reuse prepare/readiness) | **None** (DRAFT not in `list_active`) | OK |
| **C. Keep `approve` (TESTING) + readiness gate before session** | ❌ Accepts TESTING runner-eligibility; relies only on auto_trade=false | Small | No | Med | ✅ | partial | **Elevated** (TESTING runs) | OK |
| **D. New `PaperSignalChallenger` entity (source_session/run/proposal, baseline/challenger version, comparison_status)** | ✅ High traceability | Large | **Yes (table)** | High | new | ✅ | None | ✅ richest |
| **E. Read-only comparison only (no new versions yet)** | ✅✅ Highest — pure read, no creation | Small | No | Low (read) | n/a | ✅ | **None** | Foundation |

**Why A is risky:** it modifies the single, shared `ProposalService.approve` that the *strategy* track and
intelligence track also use. A conditional-on-source DRAFT branch inside that critical path is the kind of
trade-adjacent change this project treats with extreme caution. Avoid editing `approve` for V1.

**Why C is rejected:** it deliberately makes the challenger TESTING/runner-eligible — the exact thing the
problem statement says to avoid.

**Why D is deferred:** a dedicated table gives the best traceability and is the right long-term home, but it
needs a migration and a new UI; not the smallest safe first step.

## 3. Recommended M2 V1 — **Option E first, then Option B (two safe increments)**

Split M2 into two separately-approved, incremental commits, smallest/safest first:

### M2.1 (recommended V1) — **Read-only Paper Signal Comparison** (Option E)
- A **read-only** comparison of two existing `PaperSignalSession`s (a baseline vs another), reusing
  `PaperSignalOutcomeService` for each side and presenting a side-by-side signal-outcome table
  (win_rate / avg·best·worst forward return / analyzed vs pending / by_action).
- **Creates nothing.** No version, no session, no experiment, no migration, no runner exposure. Pure read.
- This delivers the *measurement* the loop needs while touching zero creation/execution paths.

### M2.2 (next, separately human-approved) — **DRAFT-only Signal Challenger preparation** (Option B)
- From a **PENDING** (or APPROVED, read-only) `StrategyProposal`, a confirm-gated endpoint creates **only a
  DRAFT** `StrategyVersion` from `suggested_parameters` (via `create_version(status=DRAFT)`,
  `auto_trade_enabled` forced false) — **never** `approve`, **never** TESTING. It does **not** start a
  session and does **not** enable any job.
- The user then starts a challenger `PaperSignalSession` through the *existing* readiness/session gates
  (already human-gated, default-disabled job), and compares it against the baseline via M2.1.
- Reuses the proven `CandidateProposalExperimentService.prepare` DRAFT pattern; optionally registers the
  challenger as a second `ExperimentVariant` on the baseline's DRAFT experiment for traceability (no status
  change).

This ordering keeps each step independently reviewable and ensures **no runner-eligible version is ever
created** in the signal track. The richer `PaperSignalChallenger` table (Option D) remains a possible later
consolidation once M2.1/M2.2 prove the shape.

## 4. Proposed API (no implementation)

**M2.1 (read-only comparison):**
- `GET /api/v1/paper-signal-sessions/{baseline_id}/compare/{challenger_id}?horizon_minutes=30`
  → `{ baseline: <session outcome>, challenger: <session outcome>, deltas: { win_rate, avg_return_pct, ... }, horizon_minutes, generated_at }`. 404 if either session missing; 422 invalid horizon. **No writes.**
- *(optional)* `GET /api/v1/paper-signal-comparisons?baseline_id=&challenger_id=` convenience listing — read-only.

**M2.2 (DRAFT challenger; separate approval):**
- `POST /api/v1/strategy-proposals/{id}/prepare-signal-challenger`
  Request `{ confirmed: true, confirmed_by: "manual_user" }` → creates **DRAFT** version only; 201 returns the DRAFT version id. 422 on gate/validation; 409 if a DRAFT challenger already exists for the proposal. **Does not** call `approve`, set TESTING/ACTIVE, start a session, or enable a job.

## 5. Proposed UI (no implementation)

**M2.1 — in the PaperSignalSession panel:** a read-only "비교 대상 선택" picker (choose another session) →
a baseline-vs-challenger outcome table with deltas. Labels: "비교 (읽기 전용) · 신호 outcome · 주문 없음".

**M2.2 — in `ProposalsSection` / `StrategyProposalReportCard`:** a confirm-gated **"Signal Challenger 준비"**
button with copy "DRAFT challenger만 생성 · 자동매매 아님 · runner 미대상 · 전략/주문/세션 상태 변경 없음",
then "DRAFT 버전 #id 생성됨 — 세션 시작·비교는 별도 단계". **No** approve/apply/materialize/ACTIVE button.

**Forbidden labels (must not appear):** 전략 적용 / 자동 적용 / 자동매매 시작 / 주문 실행 / 실전 연결 /
ACTIVE 전환 / 승인하면 즉시 실행 / AI가 전략 수정. Negative disclaimers only.

## 6. Test plan (for eventual implementation)

**M2.1 (read-only):** comparison endpoint is read-only (no row created in any table); filters strictly by
`paper_signal_session_id` for each side; 404 unknown session; 422 invalid horizon; deltas computed
correctly; no SignalLog/Trade/Order/Version/Experiment created; no status mutation; no scheduler/job change.

**M2.2 (DRAFT challenger):** preparation creates **DRAFT** version only (assert `status==DRAFT`, never
TESTING/ACTIVE); `auto_trade_enabled` forced false; **not runner-eligible** (assert 0 ACTIVE/TESTING
versions added; the version is absent from `list_active()`); no Experiment created unless explicitly
designed (and if a variant is added, no status change); no SignalLog/Trade/Order; `approve` never called;
duplicate challenger → 409; confirm/confirmed_by gates; frontend `npm run build`.

## 7. Safety proof

- **No runner picks up the challenger:** the challenger version is **DRAFT**; `list_active()` selects only
  ACTIVE/TESTING; the strategy_runner therefore never loads it → no signal generation, no auto-trade path.
- **No orders can happen:** no `TradeService`/`OrderService`/`broker`/`place_order` is touched; even paper
  orders require a runner-eligible version + `auto_trade_enabled=true` + an account — none of which exist
  here (`auto_trade_enabled` forced false, version DRAFT, `KIS_REAL_TRADING_ENABLED=false`).
- **No status mutation beyond the intended DRAFT creation:** M2.1 writes nothing; M2.2 only inserts a DRAFT
  version (and optionally a variant row) — it changes no session/version/experiment **status** and never
  calls `approve`.
- **Proposal review stays human-gated:** approval/materialization remains the existing, separate,
  human-driven `ProposalsSection` flow; M2 does not auto-approve and does not materialize.
- **Comparison is read-only:** M2.1 reads `signal_logs` + `market_data` via `SignalOutcomeService`/
  `PaperSignalOutcomeService` and returns a computed payload; it persists nothing.

## 8. Deferred items (explicitly NOT in M2)

Live trading; real orders; `auto_trade_enabled=true`; `StrategyVersion` ACTIVE; broad TESTING runner
enrollment; automatic proposal approval; automatic StrategyVersion creation without a human gate; automatic
session start; scheduler/job enablement; promotion to live; any paper *order* trading. The
`PaperSignalChallenger` dedicated table (Option D) and any change to `ProposalService.approve` are also
deferred (the latter is a shared trade-adjacent path to be touched only with explicit approval).

## 9. Migration & implementation notes

- **M2.1 needs no migration** (pure read; reuses existing models/services).
- **M2.2 needs no migration** in its minimal form (reuses `StrategyVersion` DRAFT + existing
  experiment/variant tables; traceability via the proposal's `ai_analysis_run_id`/`base_version_id` and the
  new DRAFT version). A future `PaperSignalChallenger` table (Option D) *would* need a migration — defer.
- **Do not implement during the unattended session.** Both M2.1 and M2.2 require explicit human approval
  before production code is written (M2.2 especially, as it creates a StrategyVersion — even DRAFT).

## 10. Recommendation

Implement **M2.1 (read-only comparison) first** as the smallest, zero-risk increment, then **M2.2 (DRAFT-only
challenger) as a separate, explicitly-approved commit**. Never edit `ProposalService.approve` for the
signal track; never create a TESTING challenger. Suggested commit (when implemented):
`feat: add read-only paper signal session comparison` (M2.1), later
`feat: prepare DRAFT signal challenger from proposal` (M2.2).
