# Manual App Sell Reconciliation

> **MANUAL-SELL-RECON-1 — 설계/운영 문서만.** 코드/DB/주문 변경 0 · 동기화 실행 0 · 스케줄러 enable 0.
> 진단 맥락: [`docs/diagnostics/no-trades-after-2026-06-26-risk-circuit-breaker.md`](../diagnostics/no-trades-after-2026-06-26-risk-circuit-breaker.md).
> See [`docs/roadmap/four-day-paper-trading-stabilization-plan.md`](../roadmap/four-day-paper-trading-stabilization-plan.md) for the short-term limited paper auto-trading resume plan.

## Purpose

한국투자증권 **모의투자 앱에서 사용자가 직접 매도**한 뒤, broker(KIS 모의계좌) 잔고와 우리 시스템 DB
상태가 어긋나는 문제를 안전하게 다루기 위한 운영 절차다.

## Why This Matters

* 앱 직접 매도는 우리 시스템의 `TradeService`/Order path를 거치지 않는다.
* 따라서 DB의 `positions`/`trades`가 자동으로 갱신되지 않을 수 있다.
* 방치 시: 자동매매 재개 시 잘못된 보유 판단 · 손익 계산 오류 · `max_open_positions` 오류 ·
  exit signal 중복 · strategy performance 왜곡 · AI ground truth 오염.
* 자동매매 재개 전 반드시 broker holdings와 DB positions를 비교해야 한다.

## Current Context (2026-07-01)

수동 앱 매도 후보 6개 KR open positions (account 230, paper):

| 권장 순서 | symbol | name | qty |
|--:|---|---|--:|
| 1 | 145020 | 휴젤 | 4 |
| 2 | 011070 | LG이노텍 | 1 |
| 3 | 096770 | SK이노베이션 | 1 |
| 4 | 017670 | SK텔레콤 | 1 |
| 5 | 373220 | LG에너지솔루션 | 4 |
| 6 | 005380 | 현대차 | 3 |

(권장 순서·이유는 RISK-FIX-2C/2D-PREFLIGHT 참고: 이익 우선 → 현대차 마지막. 현대차 단독 실현손실이
일일 손실 한도 100,000원을 초과하므로 먼저 팔면 안 됨.)

## Source of Truth

* **Broker/KIS holdings** = 실제 현재 보유의 source of truth (수량/평단/평가금액).
* **Local DB** (`trades`, `positions`, `signal_logs`) = 시스템의 거래 이력·전략 상태의 source of truth.
* 어느 쪽도 **자동으로 상대를 덮어쓰면 안 된다**(특히 trade 이력).

### 중요한 현 구조 (read-only 확인 결과)

* **risk 엔진은 broker 잔고를 실시간으로 읽는다.** `RiskContextBuilder.build`(`app/trading/risk/context.py`)는
  `broker.get_account_balance()`로 `open_positions_count` / `current_position_value`를 만든다.
  → **앱에서 매도하면 `max_open_positions` 계산은 broker 기준으로 자동 정상화**된다(DB 기준이 아님).
* 반면 DB `positions`/`trades`는 앱 매도를 자동 반영하지 않으므로 **stale**해진다. 특히 **앱 매도의 실현손익은
  `trades`에 기록되지 않는다**(strategy/order path를 안 거침) → 전략 성과·실현 PnL 이력이 비게 된다.
* 읽기 전용 조회 경로 존재: `GET /api/v1/account`(`app/api/v1/account.py`) → `broker.get_account_balance()`.

### 이미 존재하는 reconciliation 컴포넌트 (C-2.11)

* `PositionReconciliationService.reconcile(account_id)`
  (`app/services/position_reconciliation_service.py`): `broker.get_broker_positions()` vs DB `positions` 비교.
  mismatch 타입: `BROKER_POSITION_NOT_IN_DB` · `DB_POSITION_NOT_IN_BROKER` · DB qty > broker qty(미동기 매도) ·
  `AVG_PRICE_MISMATCH` · `OK`. **paper 계좌는 불일치 시 DB를 broker 기준으로 동기화**하는 로직이 있다.
* `TradingStateSyncService`(`app/services/trading_state_sync_service.py`): `OrderSyncService` +
  `PositionReconciliationService`를 묶은 파이프라인. 스케줄러 `trading_state_sync_scheduler_enabled = **False**`(기본 비활성).
* `PositionService.sync_from_broker_positions(account_id)`(`app/services/position_service.py`).

> 즉 **포지션 수량** 정합화 인프라는 이미 있고 paper는 broker 기준 동기화까지 한다. **부족한 부분은
> 앱 매도의 "거래 이력/실현손익" 캡처**다(아래 Policy B/D). 그리고 위 동기화는 스케줄러 비활성이라
> **자동으로 돌지 않는다**(명시 실행/승인 필요).

## Mismatch Types

운영 관점에서 다루는 불일치 유형(괄호 안은 기존 `ReconciliationMismatchType` 매핑):

1. `broker_sold_db_open` — KIS 보유 없음 + DB open position 있음. **앱 직접 매도 가능성 높음**.
   (= `DB_POSITION_NOT_IN_BROKER`)
2. `broker_qty_less_than_db_qty` — KIS 수량 < DB 수량. 일부만 앱 매도. (= DB qty > broker qty 미동기 매도)
3. `broker_qty_more_than_db_qty` — KIS 수량 > DB 수량. 외부 매수 또는 DB 누락.
4. `broker_holding_db_missing` — KIS 보유 있음 + DB position 없음. 앱 직접 매수 또는 DB 누락.
   (= `BROKER_POSITION_NOT_IN_DB`)
5. `price_basis_mismatch` — 평단가가 KIS와 DB에서 다름(수수료/세금/체결 기준 차이). (= `AVG_PRICE_MISMATCH`)
6. `realized_pnl_missing` — 앱 직접 매도의 실현손익이 DB `trades`에 반영되지 않음. **기존 reconciliation이
   다루지 않는 핵심 gap**.

## Reconciliation Policy (human-approved, no silent write)

기본 원칙:

* Broker 잔고 = broker-side source of truth. DB = trade history source of truth.
* 불일치 발견 시 **자동으로 DB를 수정하지 않는다**(먼저 read-only report).
* 사용자가 승인한 경우에만 **별도 단계**에서 DB reconciliation 수행. reconciliation DB write는 반드시 별도 작업.

### Policy A — Read-only reconciliation report

* KIS holdings ↔ DB open positions 비교 → mismatch table. **DB 수정 없음.**

### Policy B — Human-approved external manual sell sync

앱 직접 매도가 확인된 경우:

* DB open position을 닫기 위한 **별도 reconciliation event / manual external trade record**가 필요하다.
* 이 기록은 자동매매 trade와 **구분**되어야 한다. source = `manual_app_sell` 또는 `external_broker_action`.
* strategy performance 포함 여부는 **별도 결정**(기본: 제외 권장).

### Policy C — Do not silently create a normal Trade

수동 앱 매도를 일반 strategy `Trade`로 넣지 않는다. 이유: 전략이 생성/실행한 trade가 아니고 ·
broker/order path를 거치지 않았으며 · AI/strategy 성과가 오염될 수 있다.

### Policy D — Reconciliation audit trail (필드 후보)

* `source: manual_app_sell`
* `broker_account_id`
* `symbol`
* `broker_quantity_before` / `broker_quantity_after`
* `db_quantity_before` / `db_quantity_after`
* `detected_at` / `reconciled_at`
* `user_approved`
* `note`
* `linked_trade_id` (optional)
* `exclude_from_strategy_performance` (true/false)

> 주의: 위 audit trail의 **DB schema/저장은 이번 작업 범위가 아니다**(migration 금지). 필요 시 별도 승인 단계.

## Safe Operating Procedure

1. 사용자가 KIS 모의투자 앱에서 직접 매도.
2. 사용자가 앱에서 **체결 완료를 확인**.
3. 시스템이 **read-only**로 KIS holdings 조회(`GET /api/v1/account` 또는 `broker.get_account_balance()`).
4. 시스템이 **read-only**로 DB open positions 조회.
5. **reconciliation report** 생성(Policy A) — DB write 없음.
6. mismatch가 있으면 **사람이 확인**.
7. 사람 승인 후 **별도 DB reconciliation 작업** 진행(Policy B/D).
8. **자동매매 재개는 reconciliation 이후 검토**(RISK-FIX-1G/1H 체크리스트 참고).

## What Not To Do

* 앱 매도 후 바로 scheduler를 켜지 말 것.
* DB open positions를 자동으로 삭제하지 말 것(read-only report 먼저).
* manual sell을 normal strategy trade로 몰래 넣지 말 것(Policy C).
* RiskConfig를 바로 완화하지 말 것.
* 실거래 계좌와 모의계좌를 섞지 말 것.

## Future Implementation

* **MANUAL-SELL-RECON-2**: read-only KIS vs DB reconciliation 설계(기존 `PositionReconciliationService` 활용 방안 포함).
* **MANUAL-SELL-RECON-3**: read-only reconciliation report API.
* **MANUAL-SELL-RECON-4**: manual external sell sync 설계(Policy B/D, audit trail schema 결정).
* **MANUAL-SELL-RECON-5**: human-approved DB reconciliation 구현.
* **MANUAL-SELL-RECON-6**: post-reconciliation 자동매매 재개 체크리스트.

> 이번 작업(MANUAL-SELL-RECON-1)은 **설계 문서까지만** 한다. endpoint/DB write 구현 없음.

## Final Recommendation

앱에서 직접 매도해도 된다. 다만 매도 후 **반드시 read-only reconciliation report를 먼저** 만들고,
DB 동기화는 **별도 human-approved 작업**으로 수행한다. `max_open_positions` 등 risk 계산은 broker 잔고
기준이라 자동 정상화되지만, **DB `positions`/`trades`와 실현손익 이력은 수동 매도를 자동 반영하지 않으므로**
reconciliation 전에는 strategy performance/AI 분석에 그대로 쓰면 안 된다.
