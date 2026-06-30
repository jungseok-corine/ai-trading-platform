# No Trades After 2026-06-26 - Risk Circuit Breaker Diagnosis

> read-only 진단 (M2.15-DIAG-1 / DIAG-2). 코드/DB/RiskConfig 변경 없음. 수정 설계는
> [`docs/design/RISK-FIX-1-risk-reducing-exit-policy.md`](../design/RISK-FIX-1-risk-reducing-exit-policy.md).

## Summary

2026-06-26 이후 매매가 멈춘 직접 원인은 strategy/signal 생성 중단이 아니라 **RiskManager reject**다.

* signals continue after 2026-06-26
* BUY/SELL signals exist
* trade attempts continue
* risk approvals after 2026-06-26: **0**
* trades after 2026-06-26: **0**

핵심 reject:

* `consecutive_loss_limit: 연속 손실 5 >= 3`
* `max_open_positions: 6 >= 5`
* `max_position_size > 1,000,000`

## Current Risk State

* active account id: 230 (paper, "KIS VTS")
* emergency_stop: false
* consecutive_loss_limit: 3
* current consecutive loss streak: 5
* max_open_positions: 5
* current open positions: 6
* max_position_size: 1,000,000
* last trade: 2026-06-25 08:31 KST
* approvals after 2026-06-26: 0

## Risk Reject Breakdown After 2026-06-26

| risk rule              | count | note           |
| ---------------------- | ----: | -------------- |
| consecutive_loss_limit |  5149 | 연속 손실 5 >= 3   |
| max_position_size      |  2350 | 주문금액 1M 초과     |
| max_open_positions     |   951 | 보유 종목 수 6 >= 5 |

일별 분해 (KST): 06-26 (cll 1965 / mps 706 / mop 361) · 06-27 (cll 2) ·
06-29 (cll 1745 / mps 928 / mop 333) · 06-30 (cll 1437 / mps 716 / mop 257).
모든 날 `consecutive_loss_limit`이 1순위 차단.

## Loss Streak Finding

누적 trade 35건 중 청산 exit 8건:

* 1승 7패
* 실현손익 합계 약 -2,809 KRW
* 많은 패배는 entry_price == exit_price, pnl_pct = 0.0000%인 **수수료성 break-even round-trip**
  (예: 032830 465,000→465,000 pnl -907 · 010140 25,050→25,050 pnl -49 · 214150 45,400→45,400 pnl -89)
* 현재 `_count_consecutive_losses`(`app/trading/risk/context.py`)가 `pnl_amount < 0`이면 손실로 카운트
* 결과적으로 실질 가격 손실이 아니라 수수료성 손실이 연속 손실 제한을 트립시킴

## Open Position State

현재 open position 6개 (qty>0):

| symbol | quantity | avg_price | unrealized | sell order value | note                      |
| ------ | -------: | --------: | ---------: | ---------------: | ------------------------- |
| 005380 |        3 |    531333 |    -152500 |         ~1497000 | exceeds max_position_size |
| 373220 |        4 |    374250 |    -171000 |         ~1468000 | exceeds max_position_size |
| 145020 |        4 |    251500 |      +4000 |         ~1060000 | exceeds max_position_size |
| 011070 |        1 |    943000 |     -12000 |          ~931000 | within limit              |
| 017670 |        1 |     89300 |      +1300 |           ~90600 | within limit              |
| 096770 |        1 |     94400 |      -4900 |           ~89500 | within limit              |

closed-처리 버그가 아니라 **실제로 열린 포지션**이며, 미실현 합계 약 -335,000 KRW
(대부분 현대차 005380 · LG에너지솔루션 373220). 닫히지 못하고 있다.

## Critical Design Flaw

현재 risk rule(`app/trading/risk/rules.py`)의 핵심 문제:

1. `ConsecutiveLossLimitRule`이 BUY뿐 아니라 SELL/exit에도 적용된다 (side 가드 없음).
2. `MaxPositionSizeRule`이 BUY뿐 아니라 SELL/exit에도 적용된다 (side 가드 없음).
3. 따라서 손절/청산 신호가 나와도 risk rule이 막을 수 있다.
4. 그 결과 포지션을 줄일 수 없어 `max_open_positions`도 계속 걸리는 데드락이 된다.

데드락 체인:

```text
수수료성 평탄청산 5건
→ consecutive_losses=5 >= 3
→ ConsecutiveLossLimitRule이 매수/매도 전부 차단
→ MaxPositionSizeRule이 1M 초과 손절 매도 차단
→ 6종목 청산 불가
→ max_open_positions 6 >= 5 고정
→ 신규 매수도 차단
→ 2026-06-26 이후 승인 0
```

증거 (max_position_size로 거부된 손절 SELL signal_snapshot):
`373220 sell qty4 @367,000 = 1,468,000 > 1,000,000`, reason `손절 (평가손익률 -1.94% ≤ -1.0%)`.
참고로 `MaxOpenPositionsRule`은 `side == BUY` 신규 진입에만 적용되어 정상.

## Expected vs Bug

부분적으로 expected:

* risk breaker가 매매를 멈춘 것은 정상

하지만 bug/design flaw:

* risk-reducing SELL/exit까지 차단하는 것은 리스크 관리 목적과 반대
* 수수료성 break-even round-trip을 무조건 연속 손실로 보는 것은 과도함

## Recommended Fix Direction

우선순위:

1. SELL/exit는 `consecutive_loss_limit`에서 제외하거나 risk-reducing action으로 허용
   — **(RISK-FIX-1C 적용 완료)** `ConsecutiveLossLimitRule`은 이제 BUY 진입만 차단하고 SELL/exit는 허용한다.
2. SELL/exit는 `max_position_size`에서 제외하거나 분할청산 로직으로 처리
   — **(RISK-FIX-1D 적용 완료)** `MaxPositionSizeRule`은 이제 BUY 진입만 한도 적용하고 SELL/exit는 허용한다.
3. `_count_consecutive_losses`에서 수수료성 break-even 손실을 손실 streak에서 제외하는 기준 추가
   — **(RISK-FIX-1E 적용 완료)** 방향 손익률(pnl_pct/entry·exit) 기준으로 실질 손실만 카운트, fee-only는 제외.
4. entry sizing에서 `max_position_size`를 넘지 않도록 사전 캡 적용
   — **(RISK-FIX-1F 적용 완료)** BUY 진입 수량을 risk check 직전에 cap하고, 0이 되면 no-trade(브로커 미호출).
5. RiskConfig 한도 상향은 마지막 선택지

### 진행 상태 (2026-06-30)

* RISK-FIX-1C addressed the `consecutive_loss_limit` SELL/exit block.
* RISK-FIX-1D addressed the `max_position_size` SELL/exit block.
* RISK-FIX-1E addressed fee-only break-even loss counting.
* RISK-FIX-1F addressed entry sizing cap.
* 위 수정으로 DIAG-2에서 확인된 risk-rule exit 데드락 + fee-only 손실 트립 + 고가주 진입금액 초과로 인한
  reject 문제가 모두 해소되었다(코드 레벨).
* Remaining issues:
  * actual paper trading resume requires human approval and possibly a RiskConfig/current-position decision
  * AI-assisted stop-loss/take-profit design (RISK-AI-1) remains future work after the safe exit/sizing path

## Safety Notes

* DIAG-2에서 code changed: no
* DB write: no
* RiskConfig modified: no
* consecutive loss reset: no
* Trade/Order/SignalLog/CandidateEvent created: no
* broker/KIS called: no
* scheduler modified: no

## Decision

* RiskConfig를 바로 완화하지 않는다.
* consecutive loss streak를 바로 reset하지 않는다.
* 먼저 risk rule design fix를 설계한다.
* 다음 단계는 [`RISK-FIX-1`](../design/RISK-FIX-1-risk-reducing-exit-policy.md) 설계 문서다.
