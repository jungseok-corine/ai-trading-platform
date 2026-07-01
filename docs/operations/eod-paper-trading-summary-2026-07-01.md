# EOD Paper Trading Summary — 2026-07-01

> **EOD-REPORT-1 — 운영 기록(docs only).** 코드/DB/주문/스케줄러 변경 0.
> 관련: [4일 로드맵](../roadmap/four-day-paper-trading-stabilization-plan.md) ·
> [enable preflight/결과](limited-candidate-enable-preflight.md) ·
> [exposure/arbitration 설계](../design/symbol-exposure-and-signal-arbitration.md).

## 1. Executive Summary

* 오늘 **limited paper auto-trade smoke test 성공.** v329(005930 단일종목, moving_average_cross)가
  **BUY → 추가 BUY → stop-loss SELL → flat** 사이클을 실제 paper 주문으로 완주했다.
* **broker=DB reconciliation 정합**(0=0, mismatch 0), **readiness READY** 확인.
* **live trading off**, **broad universe auto-trade off** 유지.
* 사이클 검증 완료 후 **v329 pause**(`auto_trade_enabled=false`).
* ⚠️ 이번 결과는 **수익성 검증이 아니라 자동매매 엔진(신호→리스크→주문→체결→청산→정합)의 안정성 검증**이다.
  v329는 **engine smoke test 전략**이며 수익 전략이 아니다.

## 2. Timeline (2026-07-01 KST)

* v329 dormant 생성(DRAFT) → signal-only(TESTING) → **auto-trade enable**(11:42, `auto_trade_enabled=true`).
* signal-only 관찰 중 **미보유 데드크로스 SELL이 guard로 REJECTED** 확인(sell_without_holding).
* **UI parameter drift 발견**(13:00 UI 폼 저장이 `enabled=false`·`timeframe='5'`·`universe` key 주입 → v329 러너에서 스킵됨).
* **parameters sanitized restore**(13:10, 14 keys로 정리: `enabled=true`·`timeframe='1m'`·universe key 제거).
* **BUY Trade 297**(13:27, 골든크로스, 005930 qty1 @320,000, filled).
* **추가 BUY Trade 298**(14:11, 골든크로스, qty1 @319,500, filled) → 보유 2주.
* **app stuck process**(~13:47 이후 uvicorn 비서빙/스케줄러 정지) → 사용자 단일 인스턴스 재기동(중복 uvicorn=이중 스케줄러 위험이라 Claude는 미기동).
* **SL SELL Trade 299**(14:39, 손절 −1.25% ≤ −1.0%, qty2 전량청산 @316,000, filled) → **flat**.
* 재기동 후 **장 마감(15:30) 부근/이후 BUY 골든크로스가 broker ERROR**(risk approved, 미체결), 데드크로스 SELL은 계속 guard REJECTED.
* **v329 pause**(16:07, `auto_trade_enabled=false`).
* **exposure/arbitration 설계 문서 커밋**(`7d41d5f`).

## 3. Trading Result

| 항목 | 값 |
|---|---|
| symbol | 005930 |
| strategy_version_id / account_id | 329 / 230 (paper) |
| Trade 297 | BUY qty1 @320,000 filled (13:27) |
| Trade 298 | BUY qty1 @319,500 filled (14:11) |
| Trade 299 | **SELL qty2 @316,000 filled — stop-loss** (14:39), pnl −1,233 |
| today realized PnL (trades) | −1,233 |
| position realized_pnl (2매수+1매도, 수수료/세금 포함) | **−8,829** |
| final position | broker 0 · DB 0 |
| pending orders | 0 |
| reconciliation | mismatch 0 (broker=DB=0) |

> 손익은 소액이며 **max_daily_loss(−100,000) 대비 여유**. 목적은 손익이 아니라 파이프라인 검증.

## 4. What Worked

* paper broker order path (KIS VTS, broker_order_id 부여, filled)
* risk approval path (all_rules_passed) · BUY execution
* **보유 SELL 청산 execution**(SL/TP force-exit)
* **SL/TP 모니터링**(−1.0% 손절 발동)
* **sell_without_holding guard**(미보유 SELL broker 이전 스킵, 실운영 검증)
* broker=DB **reconciliation** · **readiness** endpoint
* **broad universe disarm** 유지 · **live trading guard**(REAL=false)
* **parameter restore helper**(오염 복구) · **docs-first exposure design**

## 5. What Broke / Discovered

* **UI parameter drift**: 상단 "활성화"=`enabled`(러너 게이트)로 **하단 `auto_trade_enabled`와 별개**. 편집 폼 저장이
  전체 스키마를 덮어써 `enabled=false`·`timeframe='5'`(무효)·`universe=None` key를 주입 → v329가 러너에서 스킵됨.
* **app stuck process**: 프로세스는 존재하나 HTTP/스케줄러 죽음. 중복 uvicorn 기동 시 **이중 스케줄러=중복 주문** 위험.
* **반복 BUY 누적**: 보유 중에도 골든크로스마다 추가 매수(오늘 2주) → **per-symbol exposure cap 부재**.
* **장 마감 후 broker ERROR**: 마감 부근/이후 BUY 시도가 broker error(미체결) → **auto_trade pause 필요성** 확인.
* 현재 MA-cross 전략은 **smoke-test 품질**이며 검증된 수익 전략이 아님.

## 6. Current Safe State (EOD)

* v329: status **TESTING** · `enabled=true` · **`auto_trade_enabled=false`(pause)** · `universe_auto_trade=false` ·
  universe key **absent** · `timeframe=1m` · 005930/KR/230/qty1/mopr1 (14 keys)
* **auto_trade_enabled=true strategy versions: 0** (계좌 전체 자동주문 정지)
* open position 0 · pending order 0 · broker=DB 0 · reconciliation mismatch 0
* **KIS_REAL_TRADING_ENABLED=false** · **broad universe disarm 유지**
* HEAD == origin/main == `7d41d5f`, working tree clean

## 7. Lessons Learned

* 전략이 **제한 없는 실행으로 직결되면 안 된다** — arbiter/exposure 계층이 필요.
* **Scanner / strategy / signal / order 계층 분리**가 더 명확해야 한다.
* **UI 파라미터 편집은 검증/sanitize 없이는 위험**(전체 스키마 덮어쓰기). 편집은 guarded helper 경로 권장.
* **app 단일 인스턴스 guard/runbook 필요**(중복=중복 주문 위험).
* 단순 "이미 보유 시 BUY skip"보다 **exposure limit(종목/전략/계좌)** 가 더 일반적·적합.
* v329 데이터는 **엔진 검증 데이터**로 분류(수익성 데이터 아님).
* AI는 로그 분석/리뷰에 유용하나 **약한 전략을 자동으로 수익 전략으로 바꾸지 못한다** — 초기엔 reviewer/analyst 역할.

## 8. Next Priorities

### Immediate
* 오늘은 **새 트레이딩 기능 추가하지 않음** · **v329 pause 유지** · **UI 파라미터 편집 지양** · **live/full-universe off 유지**.

### Next 1-2 Days
* **E1 read-only exposure audit endpoint**(broker+DB+pending, write 없음)
* **duplicate app instance runbook/guard**
* paper EOD report 포맷 정착
* 다음 "실전 후보" 전략 방향 결정

### Later
* **E2 ExposureLimit model → E3 BUY exposure cap → E4 OrderIntent → E5 ExecutionArbiter** → scanner/strategy integration.
* **AI 분석은 clean data pipeline 확보 이후.**

## 9. Recommended Strategic Direction

* **v329 = engine smoke test 전략** — 지금 v329를 수익 목적으로 최적화하지 않는다.
* 다음 "실전 후보"는 **하나의 집중된 전략 패밀리**로 시작(여러 전략 난립 금지).
  * 후보 예: **장 초반 강한 종목의 눌림목/유동성 회복 진입** 전략.
* **AI는 초기엔 reviewer/analyst**(로그·성과 분석, 제안). **자율 제어는 나중 단계**(사람 승인·제한 범위 이후).
* 재개 조건: reconciliation mismatch 0 · readiness BLOCK 0 · 단일 인스턴스 · 가능하면 **E3 exposure cap** 적용 후.
