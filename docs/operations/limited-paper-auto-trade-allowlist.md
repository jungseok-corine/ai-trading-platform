# Limited Paper Auto-Trade Allowlist

> **PAPER-RESUME-2 — 설계/분석 문서만.** 코드/DB/`auto_trade_enabled`/`universe_auto_trade`/scheduler 변경 0.
> 관련: [4일 로드맵](../roadmap/four-day-paper-trading-stabilization-plan.md) ·
> [resume readiness checklist](paper-auto-trading-resume-checklist.md) ·
> [수동 매도 reconciliation](manual-app-sell-reconciliation.md).

## Purpose

제한된 paper 자동 주문 재개를 위해 **이번주에 켜도 되는 전략/종목 범위(allowlist)**를 정의한다.
allowlist는 "켜도 되는 후보"를 정하는 것이지 실제로 켜는 작업이 아니다. 실제 enable은
사람 승인 후 별도 작업(PAPER-RESUME-4)에서만 한다.

## Why Not Full-Universe

> `full-universe` means broad automated signal/order coverage across many symbols, large dynamic
> universes, or strategy versions that can emit orders for many symbols without a small explicit allowlist.

이번주 금지: 많은 KOSPI/KOSDAQ 종목 자동주문 · US universe 자동주문 ·
`universe_auto_trade=true`로 광범위 심볼 dispatch · 보유하지 않은 종목에 SELL attempt ·
예측 못 한 대량 BUY attempts · 사람이 모르는 strategy version 자동주문 · full dispatcher enable 후 관찰.

## Allowed Candidate Criteria (모두 만족해야 함)

* `account_id = 230`, account type = **paper**, market = **KR**
* live trading off (`KIS_REAL_TRADING_ENABLED=false`)
* strategy/version이 명확히 식별됨(이름·목적을 사람이 이해)
* 대상 symbol 수가 **작음**(명시적 소수 allowlist; broad universe 아님)
* 최근 broker error 없음
* RiskConfig 존재 + `max_position_size` cap 적용 가능
* `max_daily_loss` / `max_trades_per_day` 내에서 운영 가능
* 사용자가 이해하고 승인한 종목/전략
* KIS/DB reconciliation mismatch 없음(또는 사람이 확인 완료)
* BUY/SELL 동작이 예측 가능

## Excluded Candidate Criteria (이번주 제외)

* live account
* US/overseas universe strategy
* `universe_auto_trade=true` + broad universe(`watchlist` / `scanner_candidates`)
* broker error가 반복된 전략/심볼
* `DRAFT` 상태 실험/synthetic 후보
* 생성 이유를 모르는 전략
* 대상 symbol 수가 많은 전략
* open position 정리 전 신규 BUY를 낼 가능성이 큰 전략
* AI 자동 생성 candidate를 바로 auto-trade로 연결
* full-universe scanner/order path

## Current Strategy/Version Findings (read-only, 2026-07-01)

* **auto-trade enabled versions = 8, 전부 universe**(`universe_auto_trade=true`, `auto_trade_enabled=false`,
  account 230, market KR, status `testing`): vid 298/300/302/304/315/316/317/318.
  * universe = `watchlist` 또는 `scanner_candidates` → **broad/dynamic = full-universe 위험**.
  * `max_orders_per_run=5`. 일부(315/316/317/318)만 `stop_loss_pct=1.0`/`take_profit_pct=1.5` 보유,
    나머지(298/300/302/304)는 손절/익절 파라미터 **없음**.
* **single-symbol non-universe versions = 2개뿐**: vid 327/328 모두
  `SYNTHETIC DEMO ... [NOT_TRADING_EVIDENCE][DEV_ONLY]`, status `draft`, symbol 005930 → **dev/synthetic, 제외**.
* version status: testing 19 · draft 5 (archived 제외).
* **최근(2일) trade_attempt error는 전부 US 심볼**(WFC/UBER/CSCO/GE/DIS/KO/T/JPM …, 각 8~10건) —
  보유 없는 US 종목 SELL/주문이 overseas 경로에서 실패. signal 분포: KR-like 31,250 / US-like 9,155.
* 6개 KR open positions(현대차 등)의 SELL 신호는 `not_attempted` — 이들을 낸 단일종목 전략은 현재
  non-archived single-symbol allowlist 후보에 없음(archived 이거나 universe 픽).

### 위험/후보 분류
* **자동주문 켜면 위험(제외):** 8개 universe 전략 전부(broad universe, 일부 손절/익절 없음, US 혼입·error 유발).
  synthetic draft 2개.
* **이번주 제한 resume 후보:** **현재 DB에 ready-made 후보 없음**(소수 명시 symbol KR paper auto-trade 전략 부재).

## Update (2026-07-01) — broad universe auto-trade disabled

PAPER-RESUME-UNIVERSE-OFF: 이번주 limited paper scope를 위해 account 230의 **broad universe
auto-trade 8개 전부 비활성화**했다(`universe_auto_trade: true → false`, parameters JSONB만 변경,
**status는 testing 유지**라 signal 관찰은 남음). 대상 version: 298/300/302/304/315/316/317/318.
auto-trade attempt(risk_events)는 더 이상 생성되지 않는다(이전 24h 316/317 risk_events 2,587 → 차단).
**full-universe는 계속 금지.** limited single-symbol **v329는 signal-only 그대로 유지**(미변경).
helper: `limited_paper_candidate.disable_universe_auto_trade`(broad universe·paper·true→false 가드).

## Recommended Allowlist Candidates

| candidate | strategy/version | symbols | market | reason | risk | recommendation |
|---|---|---|---|---|---|---|
| (none ready) | — | — | KR | 현재 DB에 소수-심볼·명시 allowlist·KR·paper·error-free auto-trade 전략이 없음 | — | **후보 없음 / 추가 확인·구성 필요** |
| (future) narrowed universe | 예: vid 316(RSI, 손절/익절 보유) | **명시 1~3종목으로 축소** | KR | 손절/익절 파라미터 보유 + KR + paper | 중(축소 전 broad) | PAPER-RESUME-4에서 **명시 symbol allowlist로 축소** 후에만 |
| (future) new limited strategy | 신규 단일/소수 종목 KR 전략 | 사용자 선택 1~3종목 | KR | 통제 가능한 최소 범위 | 낮음(소수) | 신규 구성(DB write) → 사람 승인 필요 |

> 보수적 결론: **이번주 바로 켤 수 있는 안전한 기존 후보는 없다.** universe 전략을 명시 소수 종목으로
> 축소하거나, 소수 종목 KR paper 전략을 새로 구성하는 것이 전제다(둘 다 DB write → 별도 승인).

## Enable Policy (값 변경 없이 정책만)

### Proposed enable sequence
1. KIS/DB reconciliation report 확인 (`/account/{id}/reconciliation-report`)
2. PAPER-RESUME-1 readiness checklist 확인 (`/account/{id}/paper-resume-readiness`)
3. allowlist 후보 1~2개만 선택(소수 종목)
4. 후보의 symbol/strategy/version을 사용자에게 제시
5. 사용자 명시 승인
6. 별도 작업에서 **해당 후보만** `auto_trade_enabled=true`(또는 universe를 소수 symbol로 축소)
7. scheduler/dispatcher 상태 확인
8. 첫 운영은 소량·짧은 시간
9. post-run report 작성
10. 문제 시 즉시 disable

### Disable conditions (즉시 중단/비활성화)
broker error · unexpected BUY · unexpected SELL · risk reject 폭증 · `max_daily_loss` 근접 ·
`max_trades_per_day` 근접 · reconciliation mismatch 발생 · KIS/DB position 불일치 ·
allowlist 밖 symbol 신호 생성 · live trading 관련 경고.

## Next Steps

* **PAPER-RESUME-3** — human-approved allowlist selection report: 실제 DB 값 변경 없이 사용자가 고를 후보 표 제공.
  **(설계 완료)** [`limited-paper-candidate-selection-plan.md`](limited-paper-candidate-selection-plan.md) —
  결론: universe 축소는 코드 미지원이라 **single-symbol 모드 신규 후보(Option D)** 가 권장 경로, **exit/reconcile 선행**.
* **PAPER-RESUME-4** — human-approved limited `auto_trade_enabled` enable: 사용자가 승인한 strategy/version만
  enable(또는 universe를 소수 symbol로 축소). **DB write 발생**, scheduler/dispatcher enable 여부 별도 확인, 테스트/rollback 포함.
* **PAPER-RESUME-5** — limited paper auto-order post-run report: 재개 후 신호/주문/체결/risk 결과 요약, unexpected behavior 확인.
