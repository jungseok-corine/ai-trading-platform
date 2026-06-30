# Limited Paper Candidate Selection Plan

> **PAPER-RESUME-3 — 설계/분석 문서만.** 코드/DB/Strategy/StrategyVersion/`auto_trade_enabled`/
> `universe_auto_trade`/scheduler 변경 0. 주문 0. read-only 분석 기반.
> 관련: [allowlist 설계](limited-paper-auto-trade-allowlist.md) ·
> [resume readiness checklist](paper-auto-trading-resume-checklist.md) ·
> [수동 매도 reconciliation](manual-app-sell-reconciliation.md) ·
> [4일 로드맵](../roadmap/four-day-paper-trading-stabilization-plan.md).

## Purpose

제한된 paper 자동 주문 재개를 위해 어떤 strategy/version/symbol 조합을 **만들거나 선택할지**를
사람 승인 가능하게 구체화한다. 이번 작업은 후보를 **정하는 설계**일 뿐 실제 생성/enable이 아니다.

## Current Findings (read-only, 2026-07-01)

### 종목 해석 구조 (핵심)
`StrategyRunnerService._resolve_symbols`(`app/services/strategy_runner_service.py:74`)는 두 모드만 지원한다:
* **universe 모드**: `params.universe` = `scanner_candidates` 또는 `watchlist` →
  `UniverseResolver.resolve`(`app/services/universe_resolver.py`)가 **broad/dynamic** 종목 집합 반환.
  `universe_market`(KR/US) 미설정이면 **전 시장**(→ US 혼입). **명시적 소수 symbol allowlist universe는 미지원.**
* **single-symbol 모드**: `params.universe` 없음 + `params.symbol_code` 설정 → 해당 1종목만.

→ **결론: 1~3개로 제한하려면 universe를 줄이는 게 아니라 single-symbol 모드(symbol_code)로 가야 한다.**
  universe에 "작은 allowlist"를 넣는 기능은 코드에 없다(있다면 별도 구현·승인 필요).

### 전략/버전 현황
* auto-trade enabled = **8개 전부 universe**(`universe_auto_trade=true`, `auto_trade_enabled=false`,
  account 230, KR, testing, universe=`watchlist`/`scanner_candidates`). 298/300/302/304는 손절/익절 **없음**,
  315/316/317/318은 `stop_loss_pct=1.0`/`take_profit_pct=1.5`. vid 317은 `universe_market` 미설정(US 혼입 원인).
* single-symbol non-universe = **2개뿐**, 모두 `SYNTHETIC DEMO ...[DEV_ONLY][NOT_TRADING_EVIDENCE]` draft(005930) → 운영 부적합.
* 최근 broker error = 전부 US 심볼(WFC/UBER/CSCO/GE/DIS/KO/T/JPM …).
* 6개 KR open positions는 정리 대상(현재 ≥ max_open_positions=5).

### 분류
* **reusable candidates: 없음**(즉시 켤 수 있는 소수-심볼 KR paper auto-trade 전략 부재).
* **unsafe(제외): 8개 universe 전략 전부**(broad·US 혼입·일부 손절/익절 없음), synthetic draft 2개.
* **파생 후보로 쓸 수 있는 로직**: universe 전략들의 `strategy_type`(MACD/눌림목/RSI/전고점돌파)은 재사용 가능 —
  단 single-symbol 모드로 새 버전을 구성할 때.

## Option Comparison

| option | 내용 | 판단 |
|---|---|---|
| **A. 기존 universe version 그대로 enable** | broad watchlist/scanner_candidates 자동매매 | **비추천/금지** — full-universe·US error·예측불가 BUY/SELL, 이번주 scope 위반 |
| **B. universe version 복제 후 소수 KR로 제한** | universe에 작은 allowlist 적용 | **현 코드 미지원** — resolver에 explicit-list 모드 없음. "제한"하려면 결국 single-symbol 모드(=Option D). 별도 코드 없이는 broad 유지 위험 |
| **C. 기존 single-symbol draft 전환** | vid 327/328 활용 | **부적합** — synthetic/DEV_ONLY draft, 배경 불명확 |
| **D. 신규 limited KR paper single-symbol version 생성** | symbol_code 기반 1~3 버전, 손절/익절 명시, auto_trade=false | **가장 명확/지원됨** — 단 DB write(PAPER-RESUME-4) + 사람 승인 필요 |
| **E. 자동매매 보류, exit/reconcile 먼저** | 6개 포지션 정리 + 정합성 확인 후 시작 | **가장 보수적/선행 권장** — max_open_positions 문제 제거, 정합성 확보 |

## Recommended Path

1. **먼저 6개 open positions 정리**(앱 직접 매도 또는 human-approved paper SELL — RISK-FIX-2D).
   → 신규 BUY는 어차피 `max_open_positions`(6≥5)로 막히므로, 정리 전 BUY 재개는 무의미·위험.
2. **RECON-2 report**로 KIS/DB 정합성 확인.
3. **PAPER-RESUME-1 readiness checklist** 확인(BLOCK 없음).
4. 그다음 **Option D**로 limited candidate 구성: 기존 broad universe를 켜지 말고 **single-symbol 모드 1~3개 KR 버전**.
5. candidate는 처음에 **`auto_trade_enabled=false`** 로 생성.
6. 사람 승인 후 **별도 단계(PAPER-RESUME-4C)** 에서만 enable.
7. 첫 운영은 하루/짧은 시간만.
8. **post-run report**(PAPER-RESUME-5) 작성.

> 신규 BUY 재개 가능 여부에 대한 답: **6개 포지션 정리 전에는 신규 BUY 재개 비권장**(MOP로 차단·운영 혼란).
> 정리 후 single-symbol candidate로 재개.

## Candidate Symbol Criteria

허용: KR only · 사용자가 직접 모니터링 가능 · 유동성 충분 · 스프레드 과도하지 않음 ·
최근 broker error 없음 · KIS paper 주문 가능 · `max_position_size`(1,000,000) 내 수량 ≥1 ·
현재 KIS/DB mismatch 없음 · 신호 폭주하지 않음.

제외: US/overseas · KIS paper 경로 불안정 · 최근 broker error · 현재 DB/KIS mismatch ·
고가라 quantity cap이 0 되는 종목(단가 > 1,000,000) · 급등 테마주/비정상 변동성 · 모니터링 불가 다수 종목.

> **후보 symbol은 사람 입력 필요.** (자동 추천 보류 — 운영 종목 선택은 사용자 판단.)
> 참고 sanity: max_position_size=1,000,000 기준 단가 100,000원 종목은 ≤10주, 500,000원 종목은 ≤2주로 cap됨.
> 단가 > 1,000,000원 종목은 cap 결과 0 → 후보 부적합.

## Proposed Candidate Options

| option | source | symbols | strategy/version | pros | cons | recommendation |
|---|---|---|---|---|---|---|
| D-1 | 신규 single-symbol | 사용자 선택 1종목(KR, 단가 ≤ 한도) | 신규 version(예: RSI 평균회귀 로직, 손절1.0/익절1.5) | scope 최소, 지원됨, 손절/익절 명시 | DB write·사람 승인 필요 | **권장(가장 작게 시작)** |
| D-3 | 신규 single-symbol ×2~3 | 사용자 선택 2~3종목 | 종목별 single-symbol version | 약간 더 넓은 검증 | 버전 수 증가, 모니터링 부담 | 1종목 안정 후 확대 |
| E | (보류) | — | — | 정합성·포지션 우선 | 재개 하루 지연 | **선행 권장** |

> 구체 symbol/strategy_type/수량/손절·익절은 **PAPER-RESUME-4A preflight**에서 사용자 입력으로 확정.

## Required Human Decisions

* 6개 open positions를 **먼저 정리할지**(권장: 예)
* candidate **symbols**(KR, 1~3개) — 사람 입력
* 어떤 **strategy_type** 로직을 쓸지(MACD/눌림목/RSI/전고점돌파 중)
* `stop_loss_pct` / `take_profit_pct`(기본 제안: -1.0% / +1.5%)
* **max symbols**(권장 1로 시작)
* **first run duration**(권장: 하루/짧게)
* **enable timing**(reconciliation·readiness PASS 후)

## DB Write & Rollback (다음 단계에서 필요)

후보 생성에 필요한 DB write(전부 PAPER-RESUME-4, 사람 승인 후):
* 신규 `Strategy`(name 명확) + `StrategyVersion`(parameters: symbol_code, market=KR, account_id=230,
  stop_loss_pct/take_profit_pct, `auto_trade_enabled=false`, `universe_auto_trade=false`,
  quantity/quantity_mode, max_orders_per_run), status=`testing`.
* enable은 별도(4C): 해당 version parameters의 `auto_trade_enabled`만 true로.

rollback/disable:
* enable 후 문제 시 → `auto_trade_enabled=false`로 즉시 되돌림(또는 version status를 testing 유지·archived).
* 신규 strategy/version은 archived 처리로 비활성(기존 버전 덮어쓰기 금지 — 항상 새 버전).
* scheduler/dispatcher는 enable하지 않은 상태 유지(별도 확인).

## Next Implementation Tasks

* **PAPER-RESUME-4A** — limited candidate creation preflight: strategy/version/symbol/parameters 확정 + rollback plan.
* **PAPER-RESUME-4B** — human-approved limited candidate **생성**(DB write): single-symbol, KR, account 230,
  `auto_trade_enabled=false`, `universe_auto_trade=false`, 손절/익절 명시.
* **PAPER-RESUME-4C** — human-approved limited `auto_trade_enable`: 승인 candidate만 enable, broad universe 금지, rollback 포함.
* **PAPER-RESUME-5** — limited paper auto-order post-run report.
