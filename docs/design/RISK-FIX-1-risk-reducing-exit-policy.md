# RISK-FIX-1 Risk-Reducing Exit Policy Design

> **설계 문서만.** risk rule 코드 수정 0 · RiskConfig 수정 0 · DB write 0 · consecutive loss reset 0 ·
> position/trade 수정 0 · scheduler/broker/KIS 0 · migration 0 · frontend 0.
> 진단 근거: [`docs/diagnostics/no-trades-after-2026-06-26-risk-circuit-breaker.md`](../diagnostics/no-trades-after-2026-06-26-risk-circuit-breaker.md).

## 1. Purpose

2026-06-26 이후 매매 중단 원인인 risk deadlock을 해결하기 위한 설계다.

핵심 목표:

* 위험을 늘리는 신규 진입은 계속 제한한다.
* 위험을 줄이는 청산/손절은 risk rule 때문에 막히지 않도록 한다.
* 수수료성 break-even round-trip이 연속 손실 제한을 과도하게 트립하지 않도록 한다.
* max_position_size가 청산을 막는 데드락을 방지한다.

## 2. Non-goals

이번 설계의 비목표:

* risk limit 완화
* emergency stop 해제
* consecutive loss streak 수동 reset
* open position 수동 수정
* 실거래 활성화
* 자동 주문 활성화
* 전략 수익성 개선
* AI 분석 연결
* scheduler 활성화

## 3. Problems Found

### Problem A: ConsecutiveLossLimit blocks exits

현재 `ConsecutiveLossLimitRule`(`app/trading/risk/rules.py`)이 side/action 구분 없이 작동하여 SELL/exit까지 막는다.

문제:

* 손절이 필요한 상황에서도 손절이 막힘
* 포지션을 줄일 수 없음
* max_open_positions도 계속 걸림

### Problem B: MaxPositionSize blocks exits

현재 `MaxPositionSizeRule`이 order_amount(`price * quantity`) 기준으로 SELL/exit까지 막는다.

문제:

* 이미 보유 중인 고가 포지션을 청산하려 할 때 주문금액이 1M을 넘으면 청산이 막힘
* 리스크를 줄이는 매도 주문이 오히려 risk rule에 의해 거부됨

### Problem C: Fee-only break-even losses trip consecutive loss limit

현재 `_count_consecutive_losses`(`app/trading/risk/context.py`)가 `pnl_amount < 0`이면 손실로 카운트한다.

문제:

* entry_price == exit_price이고 pnl_pct == 0%인데 수수료/세금 때문에 pnl_amount만 음수인 경우도 손실 streak로 카운트
* 실질 가격 방향 손실이 아닌데 circuit breaker가 과도하게 트립됨

### Problem D: Entry sizing does not fully prevent future exit deadlock

고가주에서 진입 수량이 작아도 order_value가 max_position_size에 근접하거나 초과할 수 있다.
진입은 통과하지만 이후 청산 주문금액이 한도를 넘어 Problem B 데드락을 유발한다.

## 4. Proposed Policy

### Policy 1: Risk-increasing vs risk-reducing action 구분

risk check context에 action nature를 명시한다.

예시:

* `BUY_OPEN`
* `BUY_INCREASE`
* `SELL_REDUCE`
* `SELL_CLOSE`
* `SELL_SHORT`는 현재 미지원이면 금지

초기 단순 정책:

* BUY는 risk-increasing
* SELL은 existing long position을 줄이는 경우 risk-reducing
* risk-reducing SELL은 `consecutive_loss_limit`과 `max_position_size`에서 제외 또는 완화
* 단, emergency_stop은 모든 action을 막을지 별도 정책 필요

### Policy 2: ConsecutiveLossLimit should block new entries, not exits

권장:

* `ConsecutiveLossLimitRule`은 신규 BUY/진입만 차단
* SELL/exit는 허용
* 단, SELL이 포지션을 늘리는 구조가 없다는 전제 필요

### Policy 3: MaxPositionSize should apply to entries, not reducing exits

권장:

* `MaxPositionSizeRule`은 BUY/open/increase에만 적용
* SELL/reduce/close는 기존 포지션을 줄이는 행위이므로 차단하지 않음
* 필요 시 max order notional rule과 position size rule을 분리

### Policy 4: Fee-only break-even should not count as consecutive loss

권장:

* consecutive loss count는 다음 중 하나로 계산:
  * `directional_return_pct < -epsilon`
  * 또는 `pnl_pct < -epsilon`
  * 또는 `pnl_amount < 0 AND pnl_pct < -epsilon`
* epsilon 예시:
  * 0.01%
  * 0.05%
  * 프로젝트 데이터 기준으로 결정

주의:

* 수수료성 손실을 완전히 무시할지, 별도 fee_drag 지표로 관리할지 결정 필요
* 실제 자본 손실은 맞지만 전략 방향 손실과 구분해야 함

### Policy 5: Entry sizing cap

진입 수량 계산 시:

* `price * quantity <= max_position_size`
* 위 조건을 만족하도록 quantity를 줄인다.
* quantity가 0이 되면 trade attempt reject:
  * reason: `quantity_below_min_after_position_size_cap`

## 5. Recommended Implementation Breakdown

순서:

* RISK-FIX-1A: design only (이 문서)
* RISK-FIX-1B: unit tests for current deadlock reproduction
* RISK-FIX-1C: ConsecutiveLossLimitRule exits allowed
* RISK-FIX-1D: MaxPositionSizeRule exits allowed
* RISK-FIX-1E: consecutive loss calculation with fee-only break-even tolerance
* RISK-FIX-1F: entry sizing cap design
* RISK-FIX-1G: paper trading resume decision, human approval only

## 6. Test Plan

필수 테스트:

* consecutive loss limit blocks BUY
* consecutive loss limit allows SELL close
* max position size blocks BUY above limit
* max position size allows SELL close above notional limit
* max open positions blocks new BUY
* max open positions does not block SELL close
* emergency stop behavior explicitly tested
* fee-only break-even trade not counted as directional loss
* real directional loss still counted
* existing reject behavior for risky BUY remains intact
* no broker/KIS/order call in risk unit tests
* no DB write in pure risk tests

## 7. Safety Gates

구현 전 확인:

* paper/live 모두에 적용 가능한가
* SELL이 실제로 long position reduce인지 확인 가능한가
* short sell/unsupported sell은 어떻게 처리할 것인가
* emergency_stop은 exits를 허용할지, 모든 것을 막을지 결정 필요
* quantity sizing cap이 기존 전략 결과와 충돌하지 않는지 확인 필요

## 8. Final Recommendation

권장:

1. RiskConfig 한도를 올리지 말 것
2. consecutive loss streak를 수동 reset하지 말 것
3. 먼저 risk-reducing exit policy를 구현할 것
4. 그 다음 fee-only break-even 손실 카운트 기준을 수정할 것
5. 마지막으로 entry sizing cap을 설계할 것

## 9. Final Decision

* SAFE TO IMPLEMENT RISK-FIX-1B TESTS NEXT: yes
* SAFE TO CHANGE RISK RULES NOW WITHOUT TESTS: no
* SAFE TO MODIFY RISKCONFIG NOW: no
* SAFE TO RESET LOSS STREAK NOW: no
* SAFE TO ENABLE TRADING NOW: no

## 10. RISK-FIX-1B Characterization Tests

현재 동작을 고정하는 characterization test가 추가되었다
(`backend/tests/test_risk_fix_1b_risk_deadlock_characterization.py`). 모두 **현재 코드 기준 PASS**:

* `ConsecutiveLossLimitRule` currently blocks SELL/exit — 손절 매도까지 거부함을 고정
* `MaxPositionSizeRule` currently blocks SELL/exit — 1M 초과 손절 매도까지 거부함을 고정
* `MaxOpenPositionsRule` already behaves as entry-only — SELL/exit는 막지 않고 신규 BUY만 막음을 고정
* fee-only break-even loss currently counts as loss — `_count_consecutive_losses`가 평탄 청산도 손실로 셈을 고정
* deadlock chain reproduced — 위험을 줄이는 어떤 청산도 통과 못 하고 신규 진입도 막힘을 조합 테스트로 고정

다음 단계는 **RISK-FIX-1C**(ConsecutiveLossLimitRule이 risk-reducing exit를 허용하도록 변경)이며,
그때 위 기대값들이 바뀐다.

## 11. RISK-FIX-1C Implementation Note

* `ConsecutiveLossLimitRule` now blocks risk-increasing BUY entries after the loss limit.
* `ConsecutiveLossLimitRule` no longer blocks SELL/exit in the current long-only model.
* long-only 전제: 현재 시스템에는 별도 action field가 없고 `Signal.side: TradeSide`만 있다.
  전략의 SELL 신호는 데드크로스/손절 등 청산 의도이며 short open 경로가 없다(positions.quantity는 long-only).
  side가 SELL이 아니거나 알 수 없으면 보수적으로 기존 한도를 적용한다.
* This reduces one part of the exit deadlock (소액 청산은 이제 통과 가능).
* However, `MaxPositionSizeRule` can still block SELL/exit above the notional limit.
  Therefore **RISK-FIX-1D remains required**.
* Fee-only break-even loss counting is unchanged and remains for **RISK-FIX-1E**.
* No RiskConfig was modified. No DB state was modified. No trading was enabled.
* Tests: `test_risk_fix_1c_consecutive_loss_exit.py` (new behavior) +
  `test_risk_fix_1b_risk_deadlock_characterization.py` (남은 데드락/미변경 동작 고정, Test 1 의미는 1C 파일로 이전).

## 12. RISK-FIX-1D Implementation Note

* `MaxPositionSizeRule` now blocks risk-increasing BUY entries above the notional limit.
* `MaxPositionSizeRule` no longer blocks SELL/exit in the current long-only model.
* Together with RISK-FIX-1C, this removes the main risk-rule exit deadlock found in DIAG-2
  (고가 보유 포지션의 손절/청산이 risk rule에 막히던 문제 해소).
* `ConsecutiveLossLimitRule` remains BUY-only after RISK-FIX-1C.
* `MaxOpenPositionsRule` remains entry-only.
* long-only 전제 유지: SELL은 short open이 아니라 보유 long 포지션의 축소/청산이며, side가 SELL이
  아니거나 알 수 없으면 보수적으로 기존 한도를 적용한다.
* SELL 허용은 주문 실행이 아니라 risk rule이 막지 않는다는 의미일 뿐이다. 실제 주문/체결/position
  close는 별도 trade/order path의 책임이다.
* Fee-only break-even loss counting is unchanged and remains for **RISK-FIX-1E**.
* Entry sizing cap is unchanged and remains for **RISK-FIX-1F**.
* No RiskConfig was modified. No DB state was modified. No trading was enabled.
* Tests: `test_risk_fix_1d_max_position_size_exit.py` (new behavior) +
  `test_risk_fix_1b_...`/`test_risk_fix_1c_...` 의 해당 기대값 갱신(삭제가 아니라 의미 이전).

## 13. RISK-FIX-1E Implementation Note

* `_count_consecutive_losses` no longer counts fee-only break-even exits as consecutive losses.
* Consecutive loss streak now focuses on directional/percent loss when available
  (`pnl_pct` = (exit_price - entry_price) / entry_price * 100, percent point, **수수료 미포함**;
  pnl_pct가 없으면 entry/exit price로 방향 손익률 계산).
* 판정: `directional_return_pct < -epsilon` → 손실, `|directional| <= epsilon` → break-even(손실 아님).
  epsilon = `CONSECUTIVE_LOSS_BREAK_EVEN_EPSILON_PCT = Decimal("0.01")` (= 0.01%p).
* If directional data is unavailable, the code falls back conservatively to `pnl_amount < 0`.
* Real directional losses still count.
* `ConsecutiveLossLimitRule` remains BUY-only after RISK-FIX-1C.
* `MaxPositionSizeRule` remains BUY-only after RISK-FIX-1D.
* Entry sizing cap is unchanged and remains for **RISK-FIX-1F**.
* No RiskConfig was modified. No DB state was modified. No trading was enabled.
* 변경 위치: `app/trading/risk/context.py`의 `_count_consecutive_losses` +
  새 helper `_is_directional_streak_loss`(순수 함수). `ConsecutiveLossLimitRule`(rules.py)은 미변경.
* Tests: `test_risk_fix_1e_consecutive_loss_fee_only.py` (new behavior) +
  `test_risk_fix_1b_...`의 fee-only 기대값을 1E 파일로 의미 이전(삭제 아님).

## 14. RISK-FIX-1F Implementation Note

* BUY entry quantity is capped before risk check so `price * quantity * fx_rate <= max_position_size`.
* SELL/exit quantity is not capped because SELL is risk-reducing in the current long-only model.
* If BUY quantity would become 0 after cap, the trade attempt is rejected/no-trade and broker is not called
  (reason `max_position_size_quantity_cap_zero` / `quantity_below_min_after_position_size_cap`).
* `MaxPositionSizeRule` remains as a defense-in-depth check for uncapped BUY orders.
* 구현 위치: 순수 helper `app/trading/risk/sizing.py::cap_buy_quantity_by_position_size` +
  `TradeService.execute_signal`에서 **risk check 직전** 적용(전략 output은 미변경 — execution/risk layer에서 조정).
  US 주문은 `MaxPositionSizeRule`과 동일하게 `usd_krw_rate`로 환산한 기준을 사용한다.
* price<=0 또는 max_position_size<=0이면 보수적으로 cap하지 않고 원래 수량을 둔다(MPS가 방어선).
* DB schema 변경 없음 — 새 log field 추가 없이 cap 사실은 로그/Trade.quantity(=조정 수량)로만 남긴다.
* No RiskConfig was modified. No DB state was modified (테스트 DB 제외). No trading was enabled.
* Tests: `test_risk_fix_1f_entry_sizing_cap.py`(pure helper + rule) +
  `test_trade_service.py`(service-level: zero→no broker call / cap→reduced trade qty / SELL 미cap).

## Future Work: RISK-AI-1 AI-assisted Stop-Loss / Take-Profit Policy

### Purpose

AI 또는 분석 모듈이 종목별 변동성, 현재 포지션 손익, 52주 위치, 최근 신호 품질, 시장 상황을 참고해
stop-loss / take-profit percent를 제안하도록 한다.

### Important Precondition

AI가 손절/익절 퍼센트를 제안하더라도, 실제 SELL/exit가 risk rule에 막히면 의미가 없다.
따라서 AI 손절/익절 설계 전에 반드시 선행되어야 한다.

1. `ConsecutiveLossLimitRule`이 risk-reducing SELL/exit를 막지 않아야 한다.
2. `MaxPositionSizeRule`이 risk-reducing SELL/exit를 막지 않아야 한다.
3. 수수료성 break-even 청산이 연속 손실로 과도하게 집계되지 않아야 한다.
4. entry sizing이 `max_position_size`를 사전에 반영해야 한다.
5. paper trading에서 exit path가 정상 동작해야 한다.

### Proposed Inputs

* symbol
* current_price
* avg_entry_price
* unrealized_pnl_pct
* unrealized_pnl_amount
* volatility
* ATR or recent average range
* 52w high/low position
* drawdown_from_52w_high_pct
* low_52w_gain_pct
* recent signal quality
* recent win/loss streak
* max_position_size
* current open positions
* market regime
* sector/theme context
* existing stop-loss/take-profit config
* risk profile

### Proposed Output

* recommended_stop_loss_pct
* recommended_take_profit_pct
* trailing_stop_pct
* confidence
* reasoning
* risk_level
* should_reduce_position_now
* should_block_new_entries

주의:

* `should_reduce_position_now`는 주문 실행이 아니라 검토 플래그다.
* AI는 주문을 직접 실행하지 않는다.
* AI는 RiskConfig를 자동 수정하지 않는다.
* live trading 적용은 human approval 없이는 금지다.

### Safety Policy

* recommendation only
* paper trading first
* human approval required
* no direct order placement
* no automatic RiskConfig mutation
* no live trading application
* every recommendation must be logged
* every applied value must be versioned

### Suggested Implementation Breakdown

* RISK-AI-1A: design only
* RISK-AI-1B: static rule-based baseline
* RISK-AI-1C: volatility-based stop-loss/take-profit calculator
* RISK-AI-1D: AI recommendation prompt design
* RISK-AI-1E: paper-only recommendation storage
* RISK-AI-1F: human approval API/UI design
* RISK-AI-1G: paper trading application only
* RISK-AI-1H: live trading review gate
