# Limited Candidate Enable Preflight

> **PAPER-RESUME-4C-PREFLIGHT — read-only.** DB write 0 · status 변경 0 · `auto_trade_enabled` 변경 0 ·
> scheduler/dispatcher 0 · 주문 0 · broker/KIS 0. live trading 금지.
> 관련: [creation preflight](limited-single-symbol-candidate-preflight.md) ·
> [readiness checklist](paper-auto-trading-resume-checklist.md) ·
> [reconciliation](manual-app-sell-reconciliation.md) · [4일 로드맵](../roadmap/four-day-paper-trading-stabilization-plan.md).

## Purpose

dev DB에 dormant로 생성된 candidate **v329**(strategy 295)를 signal-only 또는 limited paper auto-trade
후보로 **전환하기 전** 마지막 점검. 이번 작업은 enable하지 않는다(다음 단계에서 사람 승인 후).

## Current Candidate (read-only 재검증, 2026-07-01)

* strategy_id **295** / strategy_version_id **329** / version_no 1 / status **DRAFT**
* symbol_code 005930 · market KR · account_id 230(paper) · quantity 1 · strategy_type moving_average_cross
* stop_loss_pct 1.0 · take_profit_pct 1.5 · max_orders_per_run 1
* `auto_trade_enabled=false` · `universe_auto_trade=false` · `universe` key 없음
* **active/testing list 대상 아님**(DRAFT) · v329 참조 Trade/SignalLog 0 · 중복 없음
* `KIS_REAL_TRADING_ENABLED=false` · account 230 paper

## Enable Requirements

| 무엇을 | 어떻게 | 비고 |
|---|---|---|
| **status requirement** | DRAFT → **TESTING**(컬럼) | TESTING/ACTIVE만 `list_active()`에 포함되어 `run_once`가 실행. ACTIVE는 이번주 금지 |
| **auto_trade requirement** | signal-only면 `auto_trade_enabled=false` 유지 / 주문까지면 parameters JSONB `auto_trade_enabled=true` | `auto_trade_enabled`는 컬럼이 아니라 **parameters JSONB 필드** |
| **scheduler/dispatcher requirement** | **변경 불필요** | `strategy_scheduler_enabled=true`라 strategy scheduler가 이미 `run_once`를 주기 실행 → status를 TESTING으로 바꾸면 **다음 interval에 자동 포함**(restart 불필요). dispatcher/session_runner는 건드리지 않는다 |

> 즉 enable은 **StrategyVersion 한 행의 변경**으로 충분하다: (A) status=TESTING, 또는 (B) status=TESTING + parameters.auto_trade_enabled=true.
> scheduler/dispatcher/RiskConfig/settings는 변경하지 않는다.

## Expected Execution Path (enable 후)

1. strategy scheduler가 interval마다 `StrategyRunnerService.run_once` 호출(이미 enabled).
2. `list_active()`가 ACTIVE/TESTING version 조회 → v329(TESTING) 포함.
3. v329는 single-symbol 모드(005930, KR) → 005930 캔들 조회.
4. `moving_average_cross`가 골든/데드크로스 시 Signal 생성.
5. **SignalLog 생성**(trade_attempt_status=not_attempted 기본).
6. `auto_trade_enabled=true`이면 `_attempt_auto_trade` → `TradeService.execute_signal` 호출.
7. `RiskService.validate_signal` → RiskConfig 검사(CLL/MPS/MOP/MaxDailyLoss/MaxTradesPerDay).
8. BUY 수량은 `max_position_size`로 cap(RISK-FIX-1F).
9. 승인 시 `broker.place_order`(paper) → **Trade 생성**.

> enable 후에는 실제 SignalLog(그리고 auto-trade 시 Trade/Order)가 생길 수 있다. **따라서 4C-PREFLIGHT에서는 enable하지 않는다.**

### ⚠️ 중요한 현재 제약 (BUY 차단)
현재 account 230은 **open positions 6 ≥ max_open_positions 5**이고 **005930은 미보유**다. 005930 BUY는
**신규 종목 진입**이라 `MaxOpenPositionsRule`이 **거부**한다(6≥5). 즉 지금 auto_trade_enabled=true로 켜도
**005930 BUY는 체결되지 않는다**(SELL은 미보유라 해당 없음). → **포지션을 5개 미만으로 정리하기 전에는
auto-trade enable이 무의미**하며, signal-only(Option A) 관찰만 가능하다.

## Readiness Checks (enable 전 반드시 — 사람이 실행)

* RECON-2 `GET /account/230/reconciliation-report` → `mismatch_count == 0`
* PAPER-RESUME-1 `GET /account/230/paper-resume-readiness` → overall **not BLOCKED**
* account 230 paper · live trading false · emergency_stop false
* max_position_size valid · max_open_positions 여유(현재 6≥5 → **BUY 막힘, 정리 필요**)
* today trades < max_trades_per_day(현재 0/10) · today realized loss > -max_daily_loss(현재 0)
* 최근 broker error 없음 · 005930 현재가 기준 qty1이 cap 내(333,000 ≤ 1,000,000) · 005930 KIS paper 주문 가능
* **현재 6개 open positions 정리 여부** · DRAFT candidate 중복 없이 하나만 존재(확인됨)

## Enable Options

| option | 변경 | 효과 | 위험 | 추천 |
|---|---|---|---|---|
| **A. TESTING + auto_trade_enabled=false** | status만 TESTING | signal/SignalLog 생성 가능, **주문 없음**(dry-run 관찰) | SignalLog DB write·로그 누적, 주문 없음 | **가장 보수적 첫 단계** |
| **B. TESTING + auto_trade_enabled=true** | status TESTING + parameters flag true | 신호 + risk 통과 시 paper 주문/Trade | 실제 paper order/trade, broker error/risk reject 가능. **단 현재 BUY는 MOP로 차단** | Option A 관찰 + 포지션 정리 후 사람 승인 하에 |
| **C. ACTIVE + auto_trade_enabled=true** | status ACTIVE | 운영 후보처럼 동작 | 너무 빠름 | **이번주 금지** |
| **D. scheduler/dispatcher 추가 enable** | session_runner/dispatcher on | 실행 경로 확대 | full-universe/예상외 실행 | **이번 단계 금지** |

## Recommended Path

1. **현재 6개 포지션 정리**(앱 직접 매도 또는 human-approved paper SELL).
2. RECON-2 report 실행(mismatch 0 확인).
3. PAPER-RESUME-1 readiness 실행(not BLOCKED).
4. v329를 **Option A(TESTING + auto_trade_enabled=false)** 로 전환 → 짧은 시간 **signal-only 관찰**.
5. post-signal report 작성(신호 빈도·품질 확인).
6. 사람 승인 후 **Option B(auto_trade_enabled=true)**.
7. 첫 운영: 005930 1주 / max_orders_per_run 1 / 짧은 시간.
8. 문제 시 즉시 `auto_trade_enabled=false`(및 필요 시 status DRAFT) rollback.

## Rollback Plan

### Signal-only 단계
* status DRAFT로 복귀(→ run_once 대상에서 제외) · auto_trade_enabled false 유지.
* 생성된 SignalLog는 **삭제하지 않고 기록 유지**(이력 보존) · scheduler 변경 없음.

### Auto-trade 단계
* `auto_trade_enabled=false` 즉시 복귀 → 필요 시 status DRAFT.
* RECON-2 / PAPER-RESUME-1 실행 · trades/orders/risk_events 확인 · broker/KIS holdings 확인.
* 문제 시 자동매매 재개 중단(version archived 가능, 기존 버전 덮어쓰기 금지).

## Required Human Approval

### Safer signal-only approval (PAPER-RESUME-4C)
```text
승인합니다. PAPER-RESUME-4C로 진행하세요.
strategy_version_id=329를 TESTING으로 전환하되 auto_trade_enabled=false를 유지하세요.
목적은 signal-only 관찰입니다.
주문은 절대 실행하지 마세요.
scheduler/dispatcher 설정은 변경하지 마세요.
live trading은 절대 건드리지 마세요.
```

### Actual limited paper auto-trade approval (PAPER-RESUME-4D)
```text
승인합니다. PAPER-RESUME-4D로 진행하세요.
strategy_version_id=329를 TESTING 상태에서 auto_trade_enabled=true로 전환하세요.
paper account 230, KR 005930, quantity 1, max_orders_per_run 1만 허용합니다.
full-universe는 금지입니다.
scheduler/dispatcher 설정은 변경하지 마세요.
실행 중 broker error, risk reject 폭증, unexpected symbol, MaxDailyLoss/MaxTrades 접근 시 즉시 중단하고 보고하세요.
live trading은 절대 건드리지 마세요.
```

> 주의: BUY 체결은 open positions가 5 미만으로 줄어든 뒤에야 가능(현재 6≥5로 MOP 차단). 4D 전 포지션 정리 권장.

## PAPER-RESUME-4D Result (limited paper auto-trade ENABLED)

사용자 승인으로 v329의 `auto_trade_enabled`를 **false → true**로 전환했다(2026-07-01 11:42 KST).
* strategy_version_id **329**: `auto_trade_enabled=true` · **status TESTING 유지** · `universe_auto_trade=false` 유지 ·
  `universe` key 없음 유지 · symbol 005930 · account 230(paper) · quantity 1 · max_orders_per_run 1 · SL 1.0 / TP 1.5.
* enable 직후(≈27s): v329 신규 SignalLog/Trade/RiskEvent **0**(다음 005930 MA 교차 신호에서 주문 시도 예정).
* 안전 유지: broad universe_auto_trade=true **0** · universe 버전 auto_trade_enabled=true **0** ·
  **ate=true는 v329 하나뿐** · RiskConfig 불변 · open positions 0 · scheduler/dispatcher 불변 · KIS_REAL_TRADING_ENABLED=false.
* 예상 동작: 골든크로스 **BUY → paper 주문**(qty1, max_position_size cap); 미보유 데드크로스 **SELL → guard 스킵(REJECTED)**.
* enable 경로: `limited_paper_candidate.enable_limited_auto_trade`(TESTING·single-symbol·KR·paper·non-universe 가드).
* rollback: 문제 시 즉시 `auto_trade_enabled=false`.

**다음 단계: PAPER-RESUME-5 post-run report** — 첫 주문/스킵/리스크 결과를 관찰한다.

## PAPER-RESUME-4D-GUARD Result (SELL-without-holding guard added)

auto-trade enable(4D) 전 필수 가드를 구현했다: `StrategyRunnerService._attempt_auto_trade`에서
**SELL 신호인데 브로커 보유수량이 0이면 `execute_signal`(broker) 호출/risk 검증 전에 스킵**한다.
* 보유수량 판정은 SL/TP와 동일하게 `trade_service.get_holdings`(브로커 잔고) 기준 → DB 불일치에 의존하지 않음.
* **BUY 미영향** · **보유 포지션 SELL(청산)은 기존 경로 유지**(RISK-FIX-1C/1D 원칙 보존) · broker 거부에 의존하지 않음.
* SignalLog `trade_attempt_status`는 `REJECTED`로 기록, `result.rejection_reason`에 `sell_without_holding` 명시.
* 미보유 SELL은 Trade/Order/risk_event를 만들지 않는다.
* 코드: `app/services/strategy_runner_service.py`. 테스트: `test_sell_without_holding_guard.py`(6).
* v329는 여전히 `auto_trade_enabled=false`(미변경). 이제 4D 시 005930 미보유 SELL은 코드에서 안전 스킵되고,
  골든크로스 BUY만 실제 진입 대상이 된다.

## PAPER-RESUME-4C Result (signal-only enabled)

사용자 승인으로 v329를 signal-only로 전환했다(status 컬럼만 변경, parameters 미변경):

* strategy_version_id **329**: status **DRAFT → TESTING**
* `auto_trade_enabled=false` 유지 · `universe_auto_trade=false` 유지 · `universe` key 없음 유지
* symbol/market/account 불변(005930/KR/230)
* **scheduler-visible**(status testing → `list_active` 대상, 다음 interval부터 신호 생성 가능)
* **order-disabled**(auto_trade_enabled=false → 주문 시도 없음 = signal-only)
* scheduler/dispatcher 설정 변경 없음(`strategy_scheduler_enabled=true`, runner/dispatcher false 그대로)
* side-effect: 전환 직후 v329 SignalLog 0 · Trade 0 · risk_events 0 · 6 open positions 불변.
  (Claude는 run-once를 직접 호출하지 않았다. 이후 SignalLog가 생긴다면 기존 scheduler의 signal-only 관찰 결과다.)
* 전환 경로: `limited_paper_candidate.enable_signal_only_testing`(status만 변경 + auto_trade/universe 가드).
* rollback: status를 DRAFT로 되돌리면 scheduler 대상에서 제외(주문은 애초에 비활성).

**다음 단계는 post-signal observation report(PAPER-RESUME-5 또는 별도)** — 신호 빈도/품질 관찰 후,
사람 승인 시에만 PAPER-RESUME-4D(auto_trade_enabled=true). 단 현재 6≥5 open positions로 005930 BUY는 MOP 차단.

## Next Steps

* **PAPER-RESUME-4C** — (완료) v329 signal-only TESTING.
* **PAPER-RESUME-4D** — human-approved auto-trade enable(auto_trade_enabled=true). DB write(1행) + 모니터링.
* **PAPER-RESUME-5** — limited paper auto-order post-run report.
