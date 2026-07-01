# Symbol Exposure Limits & Multi-Strategy Signal Arbitration

> **EXPOSURE-DESIGN-1 — 설계 문서만.** 코드/DB/주문/스케줄러 변경 0. 구현은 별도 M단위 승인.
> 배경: v329 limited paper auto-trade 관찰 중 **동일 종목 보유 상태에서 추가 골든크로스 BUY가 누적**
> (13:27 BUY→14:11 BUY→2주→14:39 SL 청산)되는 특성 발견. 단순 "보유 중 BUY skip"보다 **exposure limit +
> arbitration**이 여러 스캐너/전략 확장에 더 맞다는 판단.

## 1. 문제 정의

* 여러 **scanner**가 같은 symbol을 candidate로 만들 수 있다.
* 여러 **strategy_version**이 같은 symbol에 BUY/SELL을 낼 수 있다.
* **같은 전략**이 같은 symbol을 (골든크로스마다) 반복 BUY할 수 있다(현재 v329가 그러함).
* scheduler 중복 실행/지연/재기동으로 같은 의도가 반복될 수 있다.
* **pending order(체결 전 주문)를 고려하지 않으면** 체결 전 주문까지 포함해 과노출된다.
* 단순 "보유 중 BUY 금지"는 안전하지만 경직적(피라미딩·분할매수·다전략 예산 배분 불가).
* 더 일반적인 해결책: **종목·전략·계좌 단위 exposure limit** + **signal arbitration** + **pending-aware 계산**.

예시(현재 구조에서 모두 개별 주문으로 나갈 수 있음):
```text
Scanner A → 005930 candidate
Scanner B → 005930 candidate
Strategy 1 → BUY 005930
Strategy 2 → BUY 005930
Strategy 3 → SELL 005930
```

## 2. 권장 아키텍처

```text
Scanner → Candidate Store → Strategy Signal Generator → Signal Store
       → Execution Arbiter → Risk Manager → Order Intent → Broker Executor
```

| 계층 | 역할 | 주문? |
|---|---|---|
| **Scanner** | 종목 후보 발굴 | ✗ |
| **Candidate Store** | 같은 symbol 후보 dedup, scanner별 score/source 기록 | ✗ |
| **Strategy Signal Generator** | strategy_version별 BUY/SELL/HOLD 의견 | ✗ |
| **Signal Store** | strategy별 signal 기록, 같은 candle_ts 중복 방지 | ✗ |
| **Execution Arbiter** *(신규)* | 같은 account/symbol의 다중 signal 취합·충돌 해결·우선순위·최종 order intent 후보 | ✗ |
| **Risk Manager** | 전략/종목/계좌 한도 확인, **pending 포함 exposure** 계산, daily loss/trades/positions | ✗ |
| **Order Intent** *(신규)* | 주문 의도 기록 + idempotency + 승인/거절/실행 상태 | ✗ |
| **Broker Executor** | 승인된 order intent만 broker 전송 | ✓ |

> 현재는 **StrategyRunnerService._attempt_auto_trade → TradeService.execute_signal → RiskManager → broker.place_order**로
> **Arbiter/Order Intent 계층 없이 직결**된다. 각 (strategy_version, symbol, candle) 신호가 독립적으로 주문을 시도한다.

## 3. Exposure Limit 설계

### Strategy-Symbol Limit
전략별 종목 한도(예: v329가 005930에 최대 500,000원).
필드 후보: `account_id` · `strategy_version_id` · `symbol_code` · `market` · `max_position_value` ·
`max_position_qty` · `max_buy_value_per_order` · `allow_pyramiding` · `max_add_count` · `enabled`.

### Account-Symbol Aggregate Limit
계좌 전체에서 한 종목 총 노출(예: account 230의 005930 총 보유금액 ≤ 1,000,000원 — 여러 전략 합산).
필드 후보: `account_id` · `symbol_code` · `market` · `max_total_position_value` ·
`max_total_position_qty` · `include_pending_orders` · `enabled`.

### Account-Level Limit
계좌 총 exposure(예: account 230 paper 총 노출 ≤ 5,000,000원).
필드 후보: `account_id` · `market` · `max_total_exposure_value` · `max_daily_buy_value` ·
`max_daily_loss` · `max_open_symbols` · `max_orders_per_day`.

> 세 계층은 **가장 엄격한 한도가 이긴다**(min). RiskConfig(계좌 기존 한도)와 별개 테이블로 두되 RiskManager가 함께 평가.

## 4. Exposure 계산 방식

```text
current_exposure(symbol) =
    broker holding value
  + DB open position value
  + pending BUY order value
  - pending SELL order value
```

broker/DB 불일치 시 정책(논의):
* **live**: broker를 source of truth, **mismatch면 BUY BLOCK**(안전).
* **paper**: mismatch면 최소 **WARN**, 보수적으로 **BLOCK** 권장.
* **pending order는 항상 포함**(체결 전 중복 주문 방지). 현재 pending = `trades.order_status='pending'`.

> 현 코드: `RiskContext.current_position_value`(broker holdings의 symbol→evaluation_amount)는 있으나
> **pending order를 포함하지 않음**. exposure 계산에 pending(=PENDING Trade) 합산이 추가돼야 한다.

## 5. Signal Arbitration 설계

같은 account/symbol/time-window 내 다중 signal 처리:

* **BUY + BUY**: aggregate exposure cap 내에서만. 정책: (a) 최고 confidence만 채택, 또는 (b) 전략별 budget 분할.
  **cap 초과분은 거절**. 피라미딩은 `allow_pyramiding`/`max_add_count`로 명시 제어.
* **BUY + SELL(충돌)**: **리스크 축소 SELL 우선**, **SL/TP SELL 최우선**. 동일 symbol에 BUY·SELL 동시 존재 시
  **신규 BUY 보류**(netting 또는 HOLD).
* **SELL + SELL**: 중복 청산 방지 — **최종 sell qty ≤ 실제 보유 수량**. (현 4D-GUARD는 미보유 SELL만 스킵; 여기서
  보유 초과 중복 SELL도 arbiter가 합산 제한.)
* **pending order 존재**: 같은 symbol pending BUY/SELL 있으면 **신규 BUY 보류**. pending **timeout 정책** 필요.

권장 우선순위: `SL/TP SELL > 일반 SELL(risk-reducing) > BUY(risk-increasing)`.

## 6. Idempotency / Lock 설계

* `account_id + market + symbol_code` 기준 **execution lock**(동시/중복 실행 직렬화).
* `strategy_version_id + symbol_code + candle_ts` **중복 방지**(현재 SignalLog unique + trade_attempt dedup 존재 → 유지·강화).
* **order_intent idempotency_key** — arbiter가 여러 signal을 합칠 수 있으므로 signal key와 **별도** 설계.
* scheduler 중복 실행 / app instance 중복 방어(APP-RESUME에서 실제로 중복 인스턴스 위험 관찰됨).
* pending order 중복 방어.

signal idempotency key 예:
```text
account_id:market:symbol_code:strategy_version_id:signal_candle_ts:side
```
order_intent key는 arbiter 산출물 기준(합산/충돌해결 후) 별도 생성.

## 7. 현재 코드와의 관계 (read-only audit)

### 이미 있는 것
* **RiskManager + RiskRule**(`app/trading/risk/rules.py`): `EmergencyStop · MaxDailyLoss · MaxPositionSize ·
  MaxOpenPositions · MaxTradesPerDay · ConsecutiveLossLimit`. `MaxPositionSize`는 **주문당 notional**(price×qty,
  BUY 전용, RISK-FIX-1D), `MaxOpenPositions`는 **심볼 수**(신규 BUY, `symbol_code not in current_position_value`).
* **RiskContext**(`app/trading/risk/context.py`): broker `get_account_balance()` 기반 `open_positions_count` +
  `current_position_value`(symbol→evaluation_amount) 보유.
* **Pending order 개념**: `trades.order_status ∈ {pending,filled,partial,cancelled,rejected}` +
  `OrderSyncService.sync_pending_orders()`(KIS 체결조회 VTTC0081R). 즉 pending 상태는 있으나 exposure에 미반영.
* **SELL-without-holding guard**(RISK-FIX-4D, `_attempt_auto_trade`): 미보유 SELL을 broker 이전 스킵.
* **읽기 전용 exposure 지표**: `portfolio_summary_service` / `operations_digest_service`의 `exposure_pct`(집중도 경고) — **표시용**, 주문 전 강제 아님.
* **Scanner/Universe**: candidate_events · scanner_rule_versions · `UniverseResolver`(scanner_candidates/watchlist).

### 부족한 것 (신규 필요)
* **per-symbol aggregate exposure cap rule** — 동일 종목 누적 매수 금액 상한(현재 없음 → v329가 2주 누적한 원인).
* **pending-aware exposure 계산** — pending BUY/SELL 반영.
* **ExecutionArbiter** — 다중 strategy/scanner의 same account/symbol 신호 취합·충돌·우선순위.
* **OrderIntent model** — 주문 전 의도 + idempotency + 상태(승인/거절/실행).
* **account/symbol execution lock** — 중복 실행/인스턴스/재기동 방어.

### 변경하면 위험한 곳
* `RiskManager`/기존 RiskRule의 SELL 면제(RISK-FIX-1C/1D)와 `_count_consecutive_losses`(1E) 의미를 깨지 말 것.
* `execute_signal`을 대규모 리팩토링하면 수동 주문 API·SL/TP force-exit 경로와 충돌 위험 → arbiter는 **execute_signal 앞단**에 삽입.
* 안전 불변식: paper/live 게이트, `KIS_REAL_TRADING_ENABLED=false`, 스케줄러 기본 비활성.

## 8. 구현 단계 제안 (M단위)

* **E1. Read-only exposure audit** — account/symbol exposure(broker+DB+pending) 계산 endpoint. **write 없음.**
* **E2. ExposureLimit model/config** — strategy-symbol / account-symbol / account-level 한도 테이블(migration 필요). 기본 비활성/미설정 시 기존 동작 유지.
* **E3. BUY exposure cap rule** — BUY 주문 전 aggregate(+pending) exposure cap 확인(신규 RiskRule 또는 pre-check). SELL은 노출 감소라 허용(RISK-FIX 원칙 유지).
* **E4. OrderIntent model** — 주문 의도·idempotency·상태. broker 호출 전 기록, 중복 방지.
* **E5. ExecutionArbiter** — 다중 signal 취합·BUY/SELL 충돌·최종 order intent 생성. execute_signal 앞단.
* **E6. Scanner/Strategy integration** — candidate dedup + multi-strategy arbitration rollout.
* **E7. UI/Runbook** — exposure dashboard, per-symbol/account limits 표시, override 절차.

각 단계는 **paper-only + 사람 승인 + full test**로 진행. E3부터 실주문 영향 → 신중.

## 9. v329에 대한 당장 권장

* **Option A. Immediate BUY-holding guard**(보유 중 BUY skip): 빠르고 안전하나 너무 단순·일반화 약함.
* **Option B. Exposure cap design first**(본 문서): 사용자 의도(전략/종목별 최대 노출)에 부합, 다전략 확장에 적합, 구현 전 설계 필요.

**권장: Option B**(설계 우선). 단 paper 관찰 중이라면:
* v329는 계속 **small qty(1)** 로만 운영하고,
* 추가 매수 누적이 우려되면 **임시로 (a) `E3 per-symbol exposure cap`을 먼저 구현**하거나
  **(b) v329 `auto_trade_enabled=false` 로 일시 rollback** 후 설계/구현을 진행한다(둘 다 별도 승인).
* 현재 노출은 소액(paper, 1~2주 × ~320k)이며 SL(−1.0%)이 작동함이 확인됨 → 급박한 위험은 아님.
