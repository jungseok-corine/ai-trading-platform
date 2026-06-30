# Four-Day Limited Paper Auto-Trading Resume Plan

> **ROADMAP-4DAY-1B — 로드맵 문서만.** 코드/DB/주문/스케줄러 변경 0. live trading 금지.
> 관련: [RISK-FIX-1 설계](../design/RISK-FIX-1-risk-reducing-exit-policy.md) ·
> [수동 매도 reconciliation](../operations/manual-app-sell-reconciliation.md) ·
> [risk circuit breaker 진단](../diagnostics/no-trades-after-2026-06-26-risk-circuit-breaker.md).

## Current State

* HEAD `846efed`. RISK-FIX-1C~1F 완료(코드 레벨에서 risk-rule exit 데드락 해소):
  CLL/MPS는 SELL/exit 면제, fee-only break-even은 연속손실에서 제외(streak 5→0), BUY 수량은 max_position_size로 cap.
* RISK-FIX-1G/1H/2C/2D-PREFLIGHT · MANUAL-SELL-RECON-1 완료(전부 read-only/문서).
* 6개 KR open positions 미정리(145020/011070/096770/017670/373220/005380, account 230 paper).
* 자동 주문 실행/dispatch 경로는 아직 제한적·미재개. live trading은 계속 OFF(`KIS_REAL_TRADING_ENABLED=false`).

## Revised Goal (This Week)

이번주 목표는 **"최종 완성형 AI 자동매매 플랫폼"이 아니다.** 이번주 목표는:

* 제한된 paper 자동 주문 재개
* 현재 open positions 정리
* broker/KIS holdings와 DB 상태 정합성 확인
* 자동매매 재개 전 checklist 확보
* 기본 손절/익절 퍼센트 운영 정책 정의
* AI 손절/익절은 recommendation-only 설계
* live trading은 계속 OFF

> **Automatic order execution is a core part of the system and should be resumed this week, but only in a
> constrained paper-trading scope after position/reconciliation safety checks.**

## What Full-Universe Means

> `full-universe` means running automated screening/signals/orders across a broad market universe, such as
> many KOSPI/KOSDAQ symbols or a large dynamic symbol set.

**이번주에는 full-universe 자동매매를 하지 않는다.** 이유: signal volume 폭증 · 예기치 않은 BUY/SELL 시도 ·
전략 성과 검증 부족 · reconciliation/risk 운영 안정화 전이라 위험 · full-universe는 나중에 단계적 확대.

이번주 허용 범위: 제한된 종목 · 제한된 전략 · paper account only · capped quantity · risk rules active ·
manual monitoring · emergency stop 유지 · full live trading 금지.

## Strategy Performance Validation — 관점 수정

* 모든 전략 성과 검증은 이번주에 **"완성"하는 작업이 아니다.** 운영 중 계속 누적되는 작업이다.
* 이번주 목표:
  * 전략 성과 검증을 끝내는 것 ✗
  * 성과 데이터가 계속 쌓이는 구조를 유지하는 것 ✓
  * paper trading 결과가 나중에 AI/전략 평가에 쓰일 수 있도록 **오염시키지 않는 것** ✓
  * manual app sell과 strategy trade를 **섞지 않는 것** ✓

## Automatic Order Resume — 이번주 핵심 목표

자동 주문 재개는 자동매매 프로그램의 **핵심**이다. 다만 이번주 재개 범위를 다음과 같이 제한한다.

### Allowed This Week
* paper account only
* limited symbols/strategies
* no live trading
* no full-universe expansion
* risk rules active (CLL / MPS / MOP / MaxDailyLoss / MaxTradesPerDay)
* max position size cap active (RISK-FIX-1F)
* max open positions active
* max daily loss active
* max trades per day active
* emergency stop available
* manual monitoring required

### Not Allowed This Week
* live trading
* full-universe auto-trading
* AI-controlled RiskConfig mutation
* scheduler/dispatcher 무작정 전체 enable
* unbounded BUY attempts
* strategy proliferation
* auto-promotion to live

## iOS Scope

iOS 앱은 중요하지만 **이번주 목표가 아니다.** 이번주에는 **서버 · DB · risk · order execution ·
reconciliation · paper runbook**이 우선이다. iOS는 나중에 **상태 확인 · strategy on/off · risk config 확인 ·
AI report 확인 · manual approval · emergency stop** 용도로 붙인다.

## Live Trading Scope

실거래 전환은 **이번주 범위 밖**이다. 전환 조건: 충분한 paper 데이터 · order/fill/sync 안정성 검증 ·
reconciliation 안정성 검증 · risk rules 검증 · daily loss/stop-loss/take-profit 검증 · emergency stop 검증 ·
rollback/runbook 준비 · 별도 human approval. **이번주에는 `KIS_REAL_TRADING_ENABLED=true` 같은 변경을 절대 하지 않는다.**

## Stop-Loss / Take-Profit Evolution

* **Stage 1. User-defined static settings** — 사용자가 기본 손절/익절 퍼센트 설정
  (예: `stop_loss_pct = -1.0%`, `take_profit_pct = +1.5%`), paper에서 먼저 검증.
* **Stage 2. AI recommendation-only** — AI가 종목/전략/시장상황에 따라 조정안을 **추천만**, 자동 적용 없음, 사람이 검토·승인.
* **Stage 3. Human-approved AI adjustment** — AI 추천값을 사람이 승인하면 paper RiskConfig/strategy parameter에 반영, audit trail 필요.
* **Stage 4. Bounded automatic AI adjustment** — 충분한 검증 후 **제한 범위 안에서만** 자동 조정
  (예: `stop_loss_pct ∈ [-3.0%, -0.8%]`, `take_profit_pct ∈ [+1.0%, +5.0%]`), live는 별도 승인.

**이번주 목표: Stage 1 운영 + Stage 2 설계. Stage 3/4는 future work.**

## Four-Day Plan

### Day 1 — Position Exit + Reconciliation
* 목표: 6개 KR open positions 정리 · 사용자 앱 직접 매도 또는 human-approved paper SELL · KIS holdings vs DB positions 비교 · 수동 매도 시 reconciliation gap 확인.
* 작업 후보: manual app sell 후 read-only reconciliation report · KIS vs DB mismatch 확인 · DB reconciliation 필요 여부 판단.
* 완료 기준: 물린 포지션이 정리되었거나 정리 안 된 이유가 명확 · KIS/DB 차이를 인지 · 재개 전 동기화 이슈 식별.

### Day 2 — Resume Safety Checklist + Limited Auto-Trade Scope
* 목표: paper 자동 주문 재개 전 checklist 확정 · 어떤 전략/종목만 허용할지 결정 · full-universe 금지 · live 금지.
* 작업 후보: paper resume checklist · limited strategy/symbol allowlist · `auto_trade_enabled` 정책 정리 · scheduler/dispatcher 상태 확인 · risk limits 재확인.
* 완료 기준: 제한된 paper 자동 주문 재개 조건이 명확.
* **진행:** PAPER-RESUME-1 readiness checklist 구현 완료. **PAPER-RESUME-2 allowlist 설계 완료** —
  [`docs/operations/limited-paper-auto-trade-allowlist.md`](../operations/limited-paper-auto-trade-allowlist.md).
  현재 8개 auto-trade 전략이 전부 broad universe(full-universe 위험)라 **즉시 켤 안전한 후보 없음** →
  소수 종목 KR paper 후보를 PAPER-RESUME-3/4에서 구성·승인해야 함.

### Day 3 — Limited Paper Auto-Order Resume
* 목표: 제한된 범위에서 paper 자동 주문 재개 · BUY/SELL risk rule이 실제 운영에서 작동하는지 확인 · 주문/체결/동기화 흐름 관찰.
* 작업 후보: limited paper resume dry-run · human-approved enable · small-scope paper auto-order 실행 · post-run report.
* 완료 기준: 자동 주문이 paper에서 제한 범위로 재작동 · 예상치 못한 BUY/SELL 폭주 없음 · risk reject/approve/trade flow 관찰 가능.
* **진행: PAPER-RESUME-4B 완료 — dormant limited candidate 생성됨**(strategy 295 / version 329, 005930,
  moving_average_cross, **DRAFT · auto_trade_enabled=false · universe_auto_trade=false**). 거래는 발생하지 않으며,
  enable은 PAPER-RESUME-4C 사람 승인 단계에서만 한다.

### Day 4 — Stop/Take-Profit Baseline + AI Recommendation Design + Runbook
* 목표: 기본 손절/익절 정책 확정 · AI는 recommendation-only 설계 · 이번주 운영 결과를 runbook으로 정리.
* 작업 후보: RISK-AI-1A · static stop-loss/take-profit baseline · paper operating runbook · next-week plan.
* 완료 기준: 다음주부터 AI-assisted paper trading으로 넘어갈 수 있음 · live trading은 여전히 OFF.

## Do Not Do This Week

* live trading
* `KIS_REAL_TRADING_ENABLED=true`
* full-universe auto-trading
* AI automatic RiskConfig mutation
* AI automatic order execution
* unbounded scheduler/dispatcher enable
* RiskConfig 완화로 문제 덮기
* consecutive loss manual reset
* manual app sell을 normal strategy trade로 몰래 삽입
* iOS full app build
* full production deployment

## Recommended Next Task

1. **Position exit decision** — 앱 직접 매도 또는 human-approved paper SELL execution.
2. **MANUAL-SELL-RECON-2** — read-only KIS vs DB reconciliation report.
   **(구현 완료)** `GET /api/v1/account/{account_id}/reconciliation-report` — DB write 없음.
3. **PAPER-RESUME-1** — limited paper auto-trading resume checklist.
   **(구현 완료)** `GET /api/v1/account/{account_id}/paper-resume-readiness` (read-only, DB write 없음) —
   상세: [`docs/operations/paper-auto-trading-resume-checklist.md`](../operations/paper-auto-trading-resume-checklist.md).
4. **PAPER-RESUME-2** — limited strategy/symbol allowlist design.
   **(설계 완료)** [`docs/operations/limited-paper-auto-trade-allowlist.md`](../operations/limited-paper-auto-trade-allowlist.md).
   **PAPER-RESUME-3** candidate selection plan **(설계 완료)** —
   [`docs/operations/limited-paper-candidate-selection-plan.md`](../operations/limited-paper-candidate-selection-plan.md):
   universe 축소는 코드 미지원 → single-symbol 신규 후보(Option D) + exit-first 권장.
   **PAPER-RESUME-4A** creation preflight **(완료)** —
   [`docs/operations/limited-single-symbol-candidate-preflight.md`](../operations/limited-single-symbol-candidate-preflight.md):
   DRAFT+auto_trade_enabled=false 이중 안전 게이트, 필드/파라미터/rollback/승인문구 확정.
5. **RISK-AI-1A** — AI stop-loss/take-profit recommendation-only design.
6. **OPERATIONS-1** — paper trading runbook.

## Final Recommendation

이번주는 **제한된 범위의 paper 자동 주문 재개**를 핵심 목표로 삼되, **(1) 포지션 정리 → (2) reconciliation 확인
→ (3) 재개 checklist → (4) 소규모 재개 → (5) 손절/익절 baseline + AI recommendation-only 설계** 순으로 진행한다.
full-universe·live·AI 자동 적용은 모두 이번주 범위 밖이며, risk rules와 emergency stop은 항상 active로 유지한다.
