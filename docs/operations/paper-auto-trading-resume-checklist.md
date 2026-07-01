# Paper Auto-Trading Resume Checklist

> **PAPER-RESUME-1 — read-only checklist.** 자동매매를 켜지 않고, DB/RiskConfig/scheduler/settings를
> 수정하지 않으며, 주문/sync write 경로를 호출하지 않는다.
> 관련: [4일 로드맵](../roadmap/four-day-paper-trading-stabilization-plan.md) ·
> [수동 매도 reconciliation](manual-app-sell-reconciliation.md).

## Purpose

제한된 paper 자동 주문 재개 **전** 반드시 확인해야 하는 read-only checklist다.
시스템이 재개 가능한 상태인지 한 번에 점검한다.

* endpoint: `GET /api/v1/account/{account_id}/paper-resume-readiness`
* service: `app/services/paper_resume_readiness_service.py`
  (`PaperResumeReadinessService.build_checklist`)

## When To Use

* 앱 직접 매도 후
* DB reconciliation 전/후
* scheduler/dispatcher enable 전
* limited strategy `auto_trade_enabled` 설정 전
* 매일 장 시작 전

## Checklist Items

| key | 의미 | 대표 severity |
|---|---|---|
| `live_trading_disabled` | `KIS_REAL_TRADING_ENABLED` false 여부 | true면 **BLOCK** |
| `account_is_paper` | 계좌 존재 + paper 여부 | live/없음 **BLOCK** |
| `risk_config` | RiskConfig 존재 + 값(>0) 정상 | 없음/오류 **BLOCK** |
| `emergency_stop` | emergency_stop false 여부 | true면 **BLOCK** |
| `trading_guard_pause` | trading guard 미정지 여부 | paused면 **BLOCK** |
| `scheduler_dispatcher_state` | runner/dispatcher 상태(조회만) | broad on이면 WARN, off면 INFO |
| `auto_trade_scope` | auto_trade/universe 전략 수 | 0개면 WARN(allowlist 필요) |
| `full_universe_guard` | universe auto-trade 위험 | universe+dispatcher on **BLOCK** / universe만 WARN |
| `reconciliation_state` | KIS holdings vs DB positions | mismatch면 WARN |
| `current_trading_state` | 오늘 거래수/손실 한도 | 한도 도달 **BLOCK** |
| `buy_readiness` | open positions vs max_open_positions | 한도 이상이면 WARN(신규 BUY 차단=정상) |
| `sell_readiness` | SELL/exit 차단 여부 | RISK-FIX-1C/1D로 PASS (단 MaxDailyLoss는 SELL도 적용) |
| `recent_activity` | 최근 trade/signal(정보) | INFO |

## Interpretation (overall_status)

* `READY` — BLOCK/WARN 없음.
* `READY_WITH_WARNINGS` — BLOCK 없음, WARN 있음(검토 후 제한 재개 가능).
* `BLOCKED` — BLOCK 1개 이상(재개 불가, blocker 먼저 해결).

각 item status: `PASS` / `WARN` / `BLOCK` / `INFO`.

## Before Resume — universe auto-trade must be disarmed

resume 전 **broad `universe_auto_trade=true` 버전이 남아 있지 않은지** 확인한다(full-universe 금지).
2026-07-01 기준 account 230의 universe auto-trade 8개(298/300/302/304/315/316/317/318)는
PAPER-RESUME-UNIVERSE-OFF로 `universe_auto_trade=false` 처리됨. 새 universe 전략을 켤 때도 동일 점검.

## Before Resume — limited candidate parameters sane (UI drift 확인)

편집 폼 저장이 parameters를 전체 스키마로 덮어쓸 수 있으므로, resume 전 다음을 확인한다:
* **`enabled=true`** (상단 "활성화" = `enabled` 필드; false면 러너가 version을 스킵)
* **`timeframe` 유효** (`1m` 권장; `'5'` 같은 무효값 금지)
* single-symbol 후보는 **`universe` key 없음** · `universe_auto_trade=false`
* `auto_trade_enabled`는 별개 필드(자동 주문 여부)

## Before Resume — SELL-without-holding guard present

auto-trade enable 전 **미보유 종목 SELL이 broker 호출 전에 스킵되는 가드**가 있어야 한다
(PAPER-RESUME-4D-GUARD, `_attempt_auto_trade`). 보유 SELL(청산)·BUY는 영향 없음. broker 거부에 의존하지 않음.

## What This Endpoint Does Not Do

* does not enable trading
* does not place orders
* does not modify DB
* does not sync positions (기존 write-capable reconcile/sync 서비스 미호출)
* does not approve strategies
* does not call AI
* does not change settings / scheduler / RiskConfig

## Next Step

* **READY / READY_WITH_WARNINGS** → [limited paper auto-trade allowlist](limited-paper-auto-trade-allowlist.md)
  (PAPER-RESUME-2)로 진행해 켤 후보를 좁힌다.
* **BLOCKED** → blocker를 먼저 해결한다. **scheduler/dispatcher를 켜지 않는다.**
