# Limited Single-Symbol Candidate Preflight

> **PAPER-RESUME-4A — preflight 문서만.** Strategy/StrategyVersion 생성/수정 0 · DB write 0 ·
> `auto_trade_enabled`/`universe_auto_trade` 변경 0 · scheduler 0 · 주문 0.
> 관련: [candidate selection plan](limited-paper-candidate-selection-plan.md) ·
> [allowlist](limited-paper-auto-trade-allowlist.md) ·
> [resume readiness](paper-auto-trading-resume-checklist.md) ·
> [4일 로드맵](../roadmap/four-day-paper-trading-stabilization-plan.md).

## Purpose

제한된 paper 자동주문 재개를 위해 **single-symbol KR candidate를 만들기 전** 필요한 필드·파라미터·
strategy_type·rollback을 확정한다. 이번 작업은 생성도 enable도 하지 않는다(다음 단계 PAPER-RESUME-4B/4C).

## Current Findings (read-only, 2026-07-01)

* ready-made limited candidate 없음. universe는 explicit 1~3 symbol로 제한 불가(`UniverseResolver`는
  `scanner_candidates`/`watchlist` broad만 지원) → **single-symbol 모드 필요**.
* **두 개의 안전 게이트 확인**:
  1. `StrategyRunnerService.run_once`는 `list_active()`(status **active/testing**)만 실행한다 →
     **DRAFT 버전은 스케줄러가 아예 돌리지 않음**(신호조차 생성 안 함).
  2. status가 testing/active여도 `auto_trade_enabled=false`면 신호만 로깅, **주문 시도 안 함**
     (`strategy_runner_service.py:277` `if not auto_trade_enabled: return`).
  → 따라서 **DRAFT + `auto_trade_enabled=false`로 생성하면 이중으로 안전**(프로젝트 불변식과 일치).
* SL/TP는 **runner-level**(`_check_sl_tp(holdings, stop_loss_pct, take_profit_pct, symbol)`) — 보유 종목
  pnl_rate 기준으로 손절/익절 SELL을 만든다. 즉 **어떤 single-symbol strategy_type이든 params로 SL/TP 적용 가능**.
* 6개 open positions(005380/011070/017670/096770/145020/373220)은 정리 대상 → **candidate symbol로 쓰면
  재진입/추가매수 혼동 위험** → 정리 전엔 후보에서 제외.

## Required Fields (PAPER-RESUME-4B에서 생성할 객체)

생성 경로: `StrategyService.create_strategy(name, description)` → `StrategyService.create_version(strategy_id, parameters, status=...)`.

* **Strategy**: `name`(명확, 예: `[LIMITED PAPER] 단일종목 후보 (RESUME-4)`), `description`(목적 명시).
* **StrategyVersion**: `strategy_id`(생성된 Strategy), `version_no`(create_version이 자동 +1),
  `parameters`(아래 dict), `status`(**DRAFT 권장**), `change_description`(옵션).

### parameters (single-symbol 모드)
| key | value | 비고 |
|---|---|---|
| `strategy_type` | (선택, 아래 표) | registry 등록 type |
| `symbol_code` | **USER_SELECTED** | KR, 단가 ≤ 한도 |
| `market` | `"KR"` | |
| `account_id` | `230` | paper |
| `quantity` | `1` (또는 strategy default) | 이후 `max_position_size`로 cap |
| `short_window`/`long_window` 등 | strategy_type별 기본 | MA류 |
| `stop_loss_pct` | `1.0` | runner SL |
| `take_profit_pct` | `1.5` | runner TP |
| `max_orders_per_run` | `1` | 회당 1건 |
| `auto_trade_enabled` | **`false`** | 절대 true 금지(이 단계) |
| `universe_auto_trade` | **`false`** | 절대 true 금지 |
| `universe` | **(키 자체를 넣지 않음)** | 넣으면 universe 모드로 broad 동작 |

### 절대 true(또는 설정)로 두면 안 되는 필드
* `auto_trade_enabled` → **false**
* `universe_auto_trade` → **false**
* `universe` → **부재**(single-symbol 보장)
* live 관련 설정 변경 금지 (`KIS_REAL_TRADING_ENABLED` 불변)

## Strategy Type Options

registry 등록 type: `moving_average_cross` · `volume_confirmed_ma_cross` ·
`flow_confirmed_volume_ma_cross` · `rsi_reversion` · `macd_trend` · `breakout_high` ·
`pullback_trend` · `momentum_surge`. SL/TP는 모두 runner-level로 공통 적용.

| strategy_type | single-symbol | SL/TP (runner) | signal freq risk | existing tests | recommendation |
|---|---|---|---|---|---|
| `moving_average_cross` | yes | yes | moderate | yes | **권장(가장 단순·검증 용이)** |
| `rsi_reversion` | yes | yes | moderate | yes | 권장 대안(universe 315/316이 SL1.0/TP1.5로 사용) |
| `macd_trend` | yes | yes | moderate | yes | 가능 |
| `volume_confirmed_ma_cross` | yes | yes | moderate(거래량 의존) | yes | 가능 |
| `breakout_high` | yes | yes | 높음(돌파 추격) | yes | 주의 |
| `momentum_surge` | yes | yes | 높음(급등 추격) | yes | 주의 |
| `pullback_trend` | yes | yes | moderate | yes | 가능 |
| `flow_confirmed_volume_ma_cross` | yes(flow 데이터 의존) | yes | depends | yes | **제외(외부 flow 의존, 복잡)** |

> 권장: **`moving_average_cross`**(가장 단순, 신호 빈도 적정) 또는 `rsi_reversion`(SL/TP 운영 정렬)으로 시작.

## Candidate Symbol Criteria

허용: KR only · paper 230 주문 가능 · 현재가가 한도 내(단가 ≤ 1,000,000 → cap ≥1주) · 유동성 충분 ·
사용자 모니터링 가능 · 최근 broker error 없음 · KIS/DB mismatch 없음 · single-symbol.

제외: US/overseas · 최근 broker error · **단가 > 1,000,000원(cap=0)** · 현재 KIS/DB mismatch ·
synthetic/dev-only · 급등 테마주 · 다수 종목 · **현재 6개 open positions(재진입 혼동)**.

### cap sanity (max_position_size=1,000,000, 로컬 종가 2026-06-30 기준 · 참고용)
| symbol | name | local close | 1M 내 최대 수량 | 후보 적합 |
|---|---|---|---|---|
| 005930 | 삼성전자 | 333,000 | 3 | ✅ |
| 000660 | SK하이닉스 | 2,643,000 | **0** | ❌ (단가 초과) |
| 035420 | NAVER | 199,500 | 5 | ✅ |
| 105560 | KB금융 | 160,100 | 6 | ✅ |
| 055550 | 신한지주 | 96,300 | 10 | ✅ |

> 위 후보들은 현재 6개 open positions와 겹치지 않아 재진입 혼동이 없다. 단 **최종 symbol은 사용자 입력 필요**
> (운영 종목 선택은 사용자 판단 — 자동 확정하지 않음). 실행 시 최신 시세로 cap 재확인.

## Candidate Draft (preflight only — DO NOT EXECUTE)

```json
{
  "strategy_name": "[LIMITED PAPER] 단일종목 후보 (RESUME-4)",
  "strategy_version": {
    "status": "draft",
    "parameters": {
      "strategy_type": "moving_average_cross",
      "symbol_code": "USER_SELECTED",
      "market": "KR",
      "account_id": 230,
      "quantity": 1,
      "short_window": 5,
      "long_window": 20,
      "stop_loss_pct": 1.0,
      "take_profit_pct": 1.5,
      "max_orders_per_run": 1,
      "auto_trade_enabled": false,
      "universe_auto_trade": false
    }
  }
}
```

> 실제 DB write 명령이 아니다. `symbol_code`는 USER_SELECTED. 사용자 명시 승인 전 사용 금지.

## Rollback / Disable Plan

### Before enable
* candidate는 생성돼도 `auto_trade_enabled=false` · `universe_auto_trade=false` · `universe` 부재 · status **DRAFT**.
* DRAFT라 스케줄러 미실행(신호조차 없음). 문제 시 version을 그대로 두거나 `archived`로 전환(기존 버전 덮어쓰기 금지).
* scheduler/dispatcher unchanged.

### After enable (4C 이후)
문제 발생 시: `auto_trade_enabled=false`로 즉시 되돌림 → scheduler/dispatcher 상태 확인 → broker error 확인
→ signal/trade/risk_events 확인 → RECON-2 실행 → PAPER-RESUME-1 실행 → 필요 시 version status 변경(archived).

### 중단 조건
unexpected BUY/SELL · allowlist 밖 symbol 발생 · broker error · risk reject 폭증 ·
`max_daily_loss` 근접 · `max_trades_per_day` 근접 · KIS/DB mismatch 발생.

## Required Human Approval (다음 단계 PAPER-RESUME-4B 승인 문구)

```text
승인합니다. PAPER-RESUME-4B로 진행하세요.
paper account 230에서 limited single-symbol KR paper candidate를 생성합니다.
symbol_code는 ______ 입니다.
strategy_type은 ______ (기본: moving_average_cross) 입니다.
stop_loss_pct는 -1.0, take_profit_pct는 +1.5로 시작합니다.
status=draft, auto_trade_enabled=false, universe_auto_trade=false, universe 키 없음으로 생성하세요.
생성만 하고 자동주문은 켜지 마세요.
scheduler/dispatcher는 변경하지 마세요.
live trading은 절대 건드리지 마세요.
```

## PAPER-RESUME-4B Result (생성 완료, dormant)

사용자 승인(symbol 005930, moving_average_cross)으로 dev DB에 dormant candidate를 생성했다:

| 항목 | 값 |
|---|---|
| strategy_id | **295** (`limited-paper-005930-moving-average-cross`) |
| strategy_version_id | **329** (version_no 1) |
| status | **DRAFT** |
| symbol_code / market / account_id | 005930 / KR / 230 |
| strategy_type | moving_average_cross |
| quantity / SL / TP / max_orders_per_run | 1 / 1.0 / 1.5 / 1 |
| auto_trade_enabled | **false** |
| universe_auto_trade | **false** |
| `universe` key | **없음** |

dormant 검증: status DRAFT(스케줄러 `list_active`(active/testing) 대상 아님 → 신호 생성 안 함) ·
auto_trade_enabled=false(주문 시도 안 함) · v329 참조 trades/signal_logs 0 · 6개 open positions 불변.
생성 helper: `app/services/limited_paper_candidate.py::create_dormant_limited_candidate`(안전 불변식 강제 + 중복 방지).

rollback: DRAFT + 참조 0 이므로 `StrategyService.delete_version`(hard delete) 또는 `archive_version` 가능.

**다음 단계는 enable이 아니라 PAPER-RESUME-4C preflight**(enable 전 최종 확인). enable 없이는 거래 발생 없음.

## Next Steps

* **PAPER-RESUME-4B** — (완료) candidate 생성됨(strategy 295 / version 329, dormant).
* **PAPER-RESUME-4C** — human-approved enable: 승인 candidate만 status testing 승격 + `auto_trade_enabled=true`,
  broad universe 금지, rollback 포함.
* **PAPER-RESUME-5** — limited paper auto-order post-run report.
