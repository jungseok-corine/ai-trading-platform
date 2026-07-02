# POSITION-DISPOSITION-1: Open Position Investigation & Disposition Policy

> **작성일**: 2026-07-02  
> **작업 유형**: read-only 조사 + 문서 작성 (DB write 없음, 코드 변경 없음, commit 없음)  
> **선행 문서**: `docs/strategy/strategy-archive-application-plan.md`

---

## Executive Summary

DB `trades` 테이블에 `exit_time IS NULL`인 레코드가 29개 존재하지만, **실제 open position은 0개**다.

- `positions` 테이블: 모든 symbol quantity = 0
- KIS paper broker reconciliation: `broker_holdings_count = 0`
- `position_events` 테이블: 모든 symbol이 sell_fill 또는 sync로 종결됨

**결론**: 29개 전체가 `trades.exit_time`이 갱신되지 않아 남은 **DB accounting artifact**다.  
실제 청산/주문은 불필요하다. 필요한 작업은 별도 승인 하에 `trades.exit_time` 보정뿐이다.

---

## Part 1. Preflight 결과

| 항목 | 결과 |
|------|------|
| HEAD | `679ae5e` ✅ |
| origin/main | `679ae5e` ✅ |
| working tree | clean ✅ |
| DB reachable | ✅ |
| API server | `{"status":"ok","env":"development"}` ✅ |
| KIS_REAL_TRADING_ENABLED | `False` ✅ |
| auto_trade_enabled=true | 0 ✅ |
| universe_auto_trade=true | 0 ✅ |
| pending orders | 0 ✅ |
| emergency_stop (paper 230) | `false` ✅ |

---

## Part 2. Open Position 전체 인벤토리

### 2-1. trades 테이블 기준 (exit_time IS NULL)

총 29 rows (strategy_version + symbol + side 조합):

| version_id | strategy_id | sv_status | strategy_type | symbol | side | open_count | open_qty | first_open (UTC) | last_open (UTC) |
|---|---|---|---|---|---|---|---|---|---|
| 297 | 275 | testing | rsi_reversion | 005380 | buy | 1 | 1 | 2026-06-23 02:38 | 2026-06-23 02:38 |
| 297 | 275 | testing | rsi_reversion | 015760 | buy | 1 | 1 | 2026-06-23 02:37 | 2026-06-23 02:37 |
| 297 | 275 | testing | rsi_reversion | 066570 | buy | 1 | 1 | 2026-06-23 02:38 | 2026-06-23 02:38 |
| 297 | 275 | testing | rsi_reversion | 145020 | buy | 1 | 1 | 2026-06-23 02:39 | 2026-06-23 02:39 |
| 297 | 275 | testing | rsi_reversion | 373220 | buy | 1 | 1 | 2026-06-23 02:37 | 2026-06-23 02:37 |
| 301 | 279 | **draft** | rsi_reversion | 005380 | buy | 1 | 1 | 2026-06-23 02:38 | 2026-06-23 02:38 |
| 301 | 279 | **draft** | rsi_reversion | 015760 | buy | 1 | 1 | 2026-06-23 02:36 | 2026-06-23 02:36 |
| 301 | 279 | **draft** | rsi_reversion | 066570 | buy | 1 | 1 | 2026-06-23 02:38 | 2026-06-23 02:38 |
| 301 | 279 | **draft** | rsi_reversion | 145020 | buy | 1 | 1 | 2026-06-23 02:38 | 2026-06-23 02:38 |
| 301 | 279 | **draft** | rsi_reversion | 373220 | buy | 1 | 1 | 2026-06-23 02:36 | 2026-06-23 02:36 |
| 305 | 279 | **draft** | rsi_reversion | 005380 | buy | 1 | 1 | 2026-06-23 02:39 | 2026-06-23 02:39 |
| 305 | 279 | **draft** | rsi_reversion | 145020 | buy | 1 | 1 | 2026-06-23 02:40 | 2026-06-23 02:40 |
| 305 | 279 | **draft** | rsi_reversion | 373220 | buy | 1 | 1 | 2026-06-23 02:37 | 2026-06-23 02:37 |
| 306 | 275 | testing | rsi_reversion | 015760 | buy | 1 | 1 | 2026-06-23 02:37 | 2026-06-23 02:37 |
| 306 | 275 | testing | rsi_reversion | 066570 | buy | 1 | 1 | 2026-06-23 02:39 | 2026-06-23 02:39 |
| 306 | 275 | testing | rsi_reversion | 145020 | buy | 1 | 1 | 2026-06-23 02:39 | 2026-06-23 02:39 |
| 306 | 275 | testing | rsi_reversion | 373220 | buy | 1 | 1 | 2026-06-23 02:37 | 2026-06-23 02:37 |
| 311 | 279 | **draft** | rsi_reversion | 010140 | buy | 1 | 1 | 2026-06-24 03:09 | 2026-06-24 03:09 |
| 311 | 279 | **draft** | rsi_reversion | 017670 | buy | 1 | 1 | 2026-06-24 03:09 | 2026-06-24 03:09 |
| 311 | 279 | **draft** | rsi_reversion | 032830 | buy | 1 | 1 | 2026-06-24 03:09 | 2026-06-24 03:09 |
| 311 | 279 | **draft** | rsi_reversion | 096770 | buy | 1 | 1 | 2026-06-24 03:09 | 2026-06-24 03:09 |
| 311 | 279 | **draft** | rsi_reversion | 214150 | buy | 1 | 1 | 2026-06-24 03:03 | 2026-06-24 03:03 |
| 312 | 275 | testing | rsi_reversion | 010950 | buy | 1 | 1 | 2026-06-24 03:09 | 2026-06-24 03:09 |
| 312 | 275 | testing | rsi_reversion | 011070 | buy | 1 | 1 | 2026-06-24 03:09 | 2026-06-24 03:09 |
| 312 | 275 | testing | rsi_reversion | 051900 | buy | 1 | 1 | 2026-06-24 02:48 | 2026-06-24 02:48 |
| 312 | 275 | testing | rsi_reversion | 086790 | buy | 1 | 1 | 2026-06-24 02:48 | 2026-06-24 02:48 |
| 316 | 275 | testing | rsi_reversion | 017670 | **sell** | 1 | 1 | 2026-06-24 23:30 | 2026-06-24 23:30 |
| 329 | 295 | testing | moving_average_cross | 005930 | buy | **2** | **2** | 2026-07-01 04:27 | 2026-07-01 05:11 |

**합계**: 28 rows (단, v329 open_count=2이므로 실제 trades rows 기준 29개)

### 2-2. 신규 발견: DRAFT 버전 open positions

> **이전 계획(strategy-archive-application-plan.md)에 누락됨.**  
> v301, v305, v311이 status=draft임에도 open trades 보유.

| version_id | sv_status | strategy_id | open_count |
|---|---|---|---|
| 301 | **draft** | 279 | 5 |
| 305 | **draft** | 279 | 3 |
| 311 | **draft** | 279 | 5 |

draft 버전은 `list_active()` 대상이 아니므로 runner/review/daily_analysis에서 제외됨.  
단, trades 테이블 레코드로 DB에 남아 있다.

### 2-3. Symbol별 open trade 집계

| symbol | open_buy_trades | open_sell_trades | positions_qty (authoritative) |
|---|---|---|---|
| 005380 | 3 | 0 | **0** |
| 005930 | 2 | 0 | **0** |
| 010140 | 1 | 0 | **0** |
| 010950 | 1 | 0 | **0** |
| 011070 | 1 | 0 | **0** |
| 015760 | 3 | 0 | **0** |
| 017670 | 1 | 1 (cancelled) | **0** |
| 032830 | 1 | 0 | **0** |
| 051900 | 1 | 0 | **0** |
| 066570 | 3 | 0 | **0** |
| 086790 | 1 | 0 | **0** |
| 096770 | 1 | 0 | **0** |
| 145020 | 4 | 0 | **0** |
| 214150 | 1 | 0 | **0** |
| 373220 | 4 | 0 | **0** |

**모든 symbol의 positions_qty = 0. broker_holdings_count = 0 (reconciliation 확인).**

---

## Part 3. v329 특별 조사

### 3-1. 예상 상태 vs 실제 상태

| 항목 | 예상 | 실제 |
|------|------|------|
| BUY 거래 수 | 2 | 2 ✅ |
| SELL 거래 수 | 1 (qty=2) | 1 ✅ |
| SELL order_status | filled | filled ✅ |
| SELL exit_time | 설정됨 | 2026-07-01 05:39:27 ✅ |
| BUY exit_time | 설정됨 (closed) | **NULL** ❌ → artifact |
| positions qty (005930) | 0 | 0 ✅ |
| broker holding | 0 | 0 (broker_holdings_count=0) ✅ |

### 3-2. trades 테이블 상세

| trade id | symbol | side | qty | order_status | entry_price | exit_price | entry_time (UTC) | exit_time |
|---|---|---|---|---|---|---|---|---|
| 297 | 005930 | buy | 1 | filled | 320,000 | — | 2026-07-01 04:27:25 | **NULL** ← artifact |
| 298 | 005930 | buy | 1 | filled | 319,500 | — | 2026-07-01 05:11:52 | **NULL** ← artifact |
| 299 | 005930 | sell | 2 | filled | 316,000 | 316,000 | 2026-07-01 05:39:27 | 2026-07-01 05:39:27 ✅ |

### 3-3. position_events 이력 (005930)

| event_type | qty_delta | before_qty | after_qty | realized_pnl_delta | created_at (UTC) |
|---|---|---|---|---|---|
| buy_fill | +1 | 0 | 1 | — | 2026-07-01 04:30:12 |
| buy_fill | +1 | 1 | 2 | — | 2026-07-01 05:16:20 |
| sell_fill | -2 | 2 | 0 | -7,596 | 2026-07-01 05:40:20 |

→ `position_events`는 완전한 open/close 이력을 가지고 있다. 005930 position은 정상 종결됨.

### 3-4. 원인 분류

| 가능한 원인 | 해당 여부 |
|---|---|
| 실제 open position | ❌ (positions qty=0, broker=0) |
| trade close linkage 누락 | **✅ 이것이 원인** — SELL trade(299)의 체결 시 BUY trade(297,298)의 exit_time이 갱신되지 않음 |
| position aggregation query 기준 오류 | ❌ (positions/broker 모두 0으로 일치) |
| broker/DB 정합성 문제 | ❌ (reconciliation mismatch=0) |

### 3-5. v329 결론

- **v329는 실제 flat 상태** (positions qty=0, broker=0)
- `trades` 테이블의 BUY 레코드 2개(trade id 297, 298)가 exit_time 미갱신으로 "open" 표시
- SELL trade(299)는 정상 closed 상태 (exit_time, exit_price, pnl_amount 모두 설정)
- **처분 정책**: `DB_RECONCILE_REQUIRED` — trade 297, 298의 exit_time을 trade 299의 exit_time (2026-07-01 05:39:27)으로 설정
- v329 자체는 SMOKE_TEST로 계속 유지 (`status=testing`, `enabled=true`, `auto_trade_enabled=false`)

---

## Part 4. DEFER_OPEN_POSITION 조사

### 4-1. 공통 관찰

4개 버전 모두:
- `status=testing`, `enabled=true`, `auto_trade_enabled=false`
- 모든 관련 symbol의 `positions_qty = 0`
- `broker_holdings_count = 0`
- **실제 paper holding 없음 → 전부 DB artifact**

### 4-2. v297 (strategy_id=275, rsi_reversion)

trades 조사:

| trade id | symbol | side | qty | order_status | entry_price | entry_time (UTC) | exit_time |
|---|---|---|---|---|---|---|---|
| 264 | 015760 | buy | 1 | filled | 37,250 | 2026-06-23 02:37 | **NULL** |
| 265 | 373220 | buy | 1 | filled | 374,500 | 2026-06-23 02:37 | **NULL** |
| 272 | 005380 | buy | 1 | filled | 531,000 | 2026-06-23 02:38 | **NULL** |
| 273 | 066570 | buy | 1 | filled | 210,000 | 2026-06-23 02:38 | **NULL** |
| 274 | 145020 | buy | 1 | filled | 251,500 | 2026-06-23 02:39 | **NULL** |

position_events 종결 방식:
- 015760, 066570: `sell_fill` (2026-06-24) — 실제 SELL 체결
- 005380, 145020, 373220: `sync -N` (2026-07-01) — 브로커 동기화로 qty=0

**결론**: 5개 BUY trade 전부 exit_time 미갱신 artifact. 실제 보유 없음.  
**처분**: `DB_RECONCILE_REQUIRED` → exit_time 보정 후 `ARCHIVE_AFTER_POSITION_RESOLVED`

### 4-3. v306 (strategy_id=275, rsi_reversion)

trades 조사:

| trade id | symbol | side | qty | order_status | entry_price | entry_time (UTC) | exit_time |
|---|---|---|---|---|---|---|---|
| 266 | 015760 | buy | 1 | filled | 37,250 | 2026-06-23 02:37 | **NULL** |
| 267 | 373220 | buy | 1 | filled | 374,000 | 2026-06-23 02:37 | **NULL** |
| 275 | 066570 | buy | 1 | filled | 210,000 | 2026-06-23 02:39 | **NULL** |
| 276 | 145020 | buy | 1 | filled | 251,500 | 2026-06-23 02:39 | **NULL** |

position_events 종결 방식:
- 015760, 066570: `sell_fill` (2026-06-24)
- 145020, 373220: `sync -N` (2026-07-01)

**결론**: 4개 BUY trade 전부 exit_time 미갱신 artifact. 실제 보유 없음.  
**처분**: `DB_RECONCILE_REQUIRED` → exit_time 보정 후 `ARCHIVE_AFTER_POSITION_RESOLVED`

### 4-4. v312 (strategy_id=275, rsi_reversion)

trades 조사:

| trade id | symbol | side | qty | order_status | entry_price | entry_time (UTC) | exit_time |
|---|---|---|---|---|---|---|---|
| 281 | 051900 | buy | 1 | filled | 222,000 | 2026-06-24 02:48 | **NULL** |
| 282 | 086790 | buy | 1 | filled | 114,100 | 2026-06-24 02:48 | **NULL** |
| 290 | 010950 | buy | 1 | filled | 102,000 | 2026-06-24 03:09 | **NULL** |
| 291 | 011070 | buy | 1 | filled | 943,000 | 2026-06-24 03:09 | **NULL** |

position_events 종결 방식:
- 051900, 086790: `sell_fill` (2026-06-24)
- 010950: `sell_fill` (2026-06-25)
- 011070: `sync -1` (2026-07-01)

**결론**: 4개 BUY trade 전부 exit_time 미갱신 artifact. 실제 보유 없음.  
**처분**: `DB_RECONCILE_REQUIRED` → exit_time 보정 후 `ARCHIVE_AFTER_POSITION_RESOLVED`

### 4-5. v316 (strategy_id=275, rsi_reversion) — 특별 케이스

trades 조사:

| trade id | symbol | side | qty | order_status | entry_price | entry_time (UTC) | exit_time |
|---|---|---|---|---|---|---|---|
| 294 | 010140 | **sell** | 1 | **filled** | 25,050 | 2026-06-24 23:30:56 | 2026-06-24 23:30:56 ✅ |
| 295 | 017670 | **sell** | 1 | **cancelled** | 92,700 | 2026-06-24 23:30:59 | **NULL** |

v316 특이사항:
- **v316에는 BUY trade가 없다.** SELL만 존재.
- 017670 BUY는 v311(DRAFT)이 실행 — 다른 strategy_version이 매수한 포지션을 v316이 SELL 시도
- SELL trade 295 (017670)는 `order_status=cancelled`, `exit_time=NULL`
- 이는 "취소된 SELL 주문" 레코드가 exit_time 미갱신으로 남은 것

position_events 종결 방식 (017670):
- `buy_fill` +1 (2026-06-24 03:23, 아마 v311 BUY가 position_events에 집계됨)
- `sync -1` (2026-07-01) → qty=0으로 종결

**결론**: 
- v316의 "open position"은 017670에 대한 **취소된 SELL 주문 artifact**
- 실제 017670 포지션은 별도로 sync로 종결됨
- v316 자체에는 BUY가 없으므로 "보유 포지션이 있는 버전"이 아님
- **Archive Safety Rule 재검토**: v316은 실질적으로 archive 가능 (보유 포지션 없음, 취소 SELL 레코드만 있음)
- **처분**: `DB_RECONCILE_REQUIRED` (trade 295 exit_time 보정) → `ARCHIVE_AFTER_POSITION_RESOLVED`

---

## Part 5. DRAFT 버전 open trades (신규 발견)

> 이전 계획 문서에 누락됨. v301, v305, v311은 DEFER_OPEN_POSITION 분류 대상에 포함되지 않았음.

### v301 (strategy_id=279, DRAFT)

5개 BUY trade (005380, 015760, 066570, 145020, 373220), 2026-06-23. exit_time=NULL.  
Position_events: 015760/066570은 sell_fill, 005380/145020/373220은 sync로 종결.

### v305 (strategy_id=279, DRAFT)

3개 BUY trade (005380, 145020, 373220), 2026-06-23. exit_time=NULL.  
Position_events: 005380/145020/373220은 sync로 종결.

### v311 (strategy_id=279, DRAFT)

5개 BUY trade (010140, 017670, 032830, 096770, 214150), 2026-06-24. exit_time=NULL.  
Position_events: 010140/032830/214150는 sell_fill, 017670/096770은 sync로 종결.

**공통 결론**: 3개 DRAFT 버전 전부 exit_time 미갱신 artifact. runner 대상이 아님.  
**처분**: `DB_RECONCILE_REQUIRED` → exit_time 보정. 이후 DRAFT 상태 유지 또는 별도 검토.

---

## Part 6. Broker/DB Reconciliation

### 6-1. 종결 방식 분류

| 종결 방식 | symbol | 종결일 (UTC) | 해당 버전 |
|---|---|---|---|
| **sell_fill** (실제 SELL 체결) | 015760 | 2026-06-24 | v297/v301/v306 |
| **sell_fill** (실제 SELL 체결) | 066570 | 2026-06-24 | v297/v301/v306 |
| **sell_fill** (실제 SELL 체결) | 051900 | 2026-06-24 | v312 |
| **sell_fill** (실제 SELL 체결) | 086790 | 2026-06-24 | v312 |
| **sell_fill** (실제 SELL 체결) | 010140 | 2026-06-25 | v311 |
| **sell_fill** (실제 SELL 체결) | 010950 | 2026-06-25 | v312 |
| **sell_fill** (실제 SELL 체결) | 032830 | 2026-06-25 | v311 |
| **sell_fill** (실제 SELL 체결) | 214150 | 2026-06-25 | v311 |
| **sell_fill** (실제 SELL 체결) | 005930 | 2026-07-01 | v329 |
| **sync** (브로커 qty=0 감지) | 005380 | 2026-07-01 | v297/v301/v305 |
| **sync** (브로커 qty=0 감지) | 145020 | 2026-07-01 | v297/v301/v305/v306 |
| **sync** (브로커 qty=0 감지) | 017670 | 2026-07-01 | v311 |
| **sync** (브로커 qty=0 감지) | 373220 | 2026-07-01 | v297/v301/v305/v306 |
| **sync** (브로커 qty=0 감지) | 011070 | 2026-07-01 | v312 |
| **sync** (브로커 qty=0 감지) | 096770 | 2026-07-01 | v311 |
| **cancelled** (취소 주문) | 017670 | 2026-06-24 | v316 |

### 6-2. Reconciliation 분류

#### MATCHED_PAPER_POSITION (실제 paper holding 있음)
**없음.** `broker_holdings_count=0`, 모든 symbol `positions_qty=0`.

#### DB_ACCOUNTING_ARTIFACT (DB trades 레코드만 남음)
**모든 29개 open trade** — exit_time이 설정되지 않은 채로 남음.

| 아티팩트 유형 | 설명 | 해당 trade ids |
|---|---|---|
| BUY after sell_fill | SELL이 실제 체결됐으나 BUY의 exit_time 미갱신 | 264,265,266,267,272,273,274,275,276,281,282,286,287,288,289,290,291,297,298 |
| BUY after sync | sync가 qty=0으로 보정했으나 BUY의 exit_time 미갱신 | 263,268,269,270,271,277,278 등 |
| cancelled SELL | SELL 주문이 취소됐으나 exit_time 미갱신 | 295 |

#### BROKER_ONLY_HOLDING (broker에만 있음)
**없음.** broker_holdings_count=0.

#### UNCLEAR
**없음.** positions/broker/position_events 세 소스가 일치.

### 6-3. 원인 분석

`trades.exit_time`이 갱신되지 않는 패턴은 두 가지:

1. **SELL fill이 BUY를 역방향으로 close하지 않는 경우**:  
   trade service가 SELL 주문을 기록할 때 SELL trade의 exit_time은 설정하지만,  
   대응 BUY trade의 exit_time을 돌아가서 갱신하지 않는다.  
   (SELL trade 자체가 별도 레코드로 생성되고, BUY는 그대로 남음)

2. **Sync/브로커 동기화로 position이 0이 된 경우**:  
   position_events에 sync 이벤트로 qty=0을 기록하지만,  
   해당 sync와 연결된 BUY trade id를 추적하지 않아 exit_time 미갱신.

---

## Part 7. 처분 정책 제안

> **현재 이 문서에서는 어떠한 처분도 실행하지 않는다.** 정책 제안만.

### KEEP_OBSERVE
해당 없음 (모든 open trade가 artifact로 확인됨).

### MANUAL_PAPER_CLOSE_REQUIRED
해당 없음 (broker_holdings=0, 실제 청산 불필요).

### DB_RECONCILE_REQUIRED (전체)

**모든 29개 open trade**에 대해 별도 승인 후 `trades.exit_time` 보정 필요.

| 버전 | 아티팩트 수 | 보정 방법 제안 |
|------|-------------|----------------|
| v297 | 5 (BUY) | exit_time = position_events의 해당 symbol 종결 시각 |
| v301 (draft) | 5 (BUY) | 동상 |
| v305 (draft) | 3 (BUY) | 동상 |
| v306 | 4 (BUY) | 동상 |
| v311 (draft) | 5 (BUY) | 동상 |
| v312 | 4 (BUY) | 동상 |
| v316 | 1 (SELL cancelled) | exit_time = entry_time (취소 시각, 혹은 sync 시각) |
| v329 | 2 (BUY) | exit_time = trade 299의 exit_time (2026-07-01 05:39:27) |

**주의**: `exit_time` 보정은 DB write (UPDATE)이므로 별도 승인 필요. 이 문서에서는 실행하지 않는다.

### ARCHIVE_AFTER_POSITION_RESOLVED

`DB_RECONCILE_REQUIRED` 완료 후 archive 가능한 버전:

| 버전 | 현재 분류 | 보정 후 |
|------|-----------|---------|
| v297 | DEFER_OPEN_POSITION (testing) | DB 보정 → archive 가능 |
| v306 | DEFER_OPEN_POSITION (testing) | DB 보정 → archive 가능 |
| v312 | DEFER_OPEN_POSITION (testing) | DB 보정 → archive 가능 |
| v316 | DEFER_OPEN_POSITION (testing) | DB 보정 → **즉시 archive 가능** (실보유 없음 확인, 취소 SELL만 있음) |

**v316 Archive Safety Rule 재검토**:  
v316에는 BUY trade가 없다. "open position"이 취소된 SELL 주문 artifact뿐이므로, 실질적으로는 Archive Safety Rule 조건(open position 존재)을 충족하지 않는다. DB 보정(trade 295 exit_time 설정) 후 즉시 archive 가능.

### KEEP_SMOKE_TEST_PAUSED

**v329**: DB_RECONCILE_REQUIRED(BUY trade 2개 exit_time 보정) 후 `SMOKE_TEST` 상태 유지.  
보정은 필요하지만 archive 불필요. 계속 SMOKE_TEST로 운영.

---

## Part 8. 후속 작업 설계

### POSITION-DISPOSITION-APPLY-1

**목표**: `trades.exit_time` 보정으로 DB accounting artifact를 정리한다.

**방법**:
- 직접 SQL UPDATE (별도 승인 필요)
- 또는 reconciliation service 활용 (코드 확인 필요)
- `historical trade records는 삭제하지 않는다` — exit_time과 exit_reason만 보정
- `pnl_amount`, `exit_price`는 positions/position_events 기반으로 역산 (sell_fill 경우)  
  또는 NULL 유지 (sync 경우 — 정확한 exit_price 없음)

**보정 우선순위**:
1. v329 (SMOKE_TEST) — BUY 2개, 즉시 영향 있음 (runner 대상이므로)
2. v297, v306, v312 (DEFER_OPEN_POSITION testing) — archive 전 필수
3. v316 (DEFER_OPEN_POSITION testing) — archive 가능 여부 확인됨, 보정 후 즉시 archive
4. v301, v305, v311 (DRAFT) — 우선순위 낮음 (runner 대상 아님)

**DB write 범위**:
- `UPDATE trades SET exit_time = ..., exit_reason = 'reconciled' WHERE id IN (...)`
- 직접 SQL UPDATE이므로 별도 승인 필요
- archive API는 이 단계에서 사용하지 않음 (보정 후 archive는 기존 API 사용)

### POST-ARCHIVE-DOCS-1

**목표**: STRATEGY-ARCHIVE-APPLY-1 완료 후 운영 현황 문서 업데이트.

현재 상태:
```
strategy_versions: 25
archived:  11 (ARCHIVE_NOW 완료)
testing:    9 (297, 300, 304, 306, 307, 312, 316, 317, 329)
draft:      5 (포함 v301, v305, v311 — open trade 보유)
active:     0

open trades (artifact, 실제 보유 없음): 29
runner 대상: 9개
weekly signal noise 제거: ~33,691 (11개 archive 효과)
```

---

## Part 9. 최종 보고

### Files Changed

- `docs/strategy/position-disposition-plan.md` (신규)

### Safety Confirmation

| 항목 | 결과 |
|------|------|
| code changed | ❌ 없음 |
| DB write performed | ❌ 없음 (read-only 조사만) |
| migration created | ❌ 없음 |
| StrategyVersion modified | ❌ 없음 |
| RiskConfig modified | ❌ 없음 |
| open positions modified | ❌ 없음 |
| trades modified | ❌ 없음 |
| scheduler/job touched | ❌ 없음 |
| broker/KIS order touched | ❌ 없음 |
| broker/KIS read-only touched | ✅ reconciliation-report 엔드포인트 조회 (read-only) |
| Trade/Order path touched | ❌ 없음 |
| run-once called | ❌ 없음 |
| commit/push performed | ❌ 없음 |
| secrets printed | ❌ 없음 |

### Final Judgment

**SAFE** — read-only 조사 + 문서 작성만 수행. DB write, 코드 변경, commit 없음.

---

## Appendix A. Open Position Inventory (수정 전 전체)

> 이 인벤토리는 `trades.exit_time IS NULL` 기준 2026-07-02 조사 시점 스냅샷.

```
v297 (testing, strategy_id=275, rsi_reversion):
  005380 BUY 1 filled  entry=2026-06-23 02:38  exit=NULL
  015760 BUY 1 filled  entry=2026-06-23 02:37  exit=NULL
  066570 BUY 1 filled  entry=2026-06-23 02:38  exit=NULL
  145020 BUY 1 filled  entry=2026-06-23 02:39  exit=NULL
  373220 BUY 1 filled  entry=2026-06-23 02:37  exit=NULL

v301 (draft, strategy_id=279, rsi_reversion):
  005380 BUY 1 filled  entry=2026-06-23 02:38  exit=NULL
  015760 BUY 1 filled  entry=2026-06-23 02:36  exit=NULL
  066570 BUY 1 filled  entry=2026-06-23 02:38  exit=NULL
  145020 BUY 1 filled  entry=2026-06-23 02:38  exit=NULL
  373220 BUY 1 filled  entry=2026-06-23 02:36  exit=NULL

v305 (draft, strategy_id=279, rsi_reversion):
  005380 BUY 1 filled  entry=2026-06-23 02:39  exit=NULL
  145020 BUY 1 filled  entry=2026-06-23 02:40  exit=NULL
  373220 BUY 1 filled  entry=2026-06-23 02:37  exit=NULL

v306 (testing, strategy_id=275, rsi_reversion):
  015760 BUY 1 filled  entry=2026-06-23 02:37  exit=NULL
  066570 BUY 1 filled  entry=2026-06-23 02:39  exit=NULL
  145020 BUY 1 filled  entry=2026-06-23 02:39  exit=NULL
  373220 BUY 1 filled  entry=2026-06-23 02:37  exit=NULL

v311 (draft, strategy_id=279, rsi_reversion):
  010140 BUY 1 filled  entry=2026-06-24 03:09  exit=NULL
  017670 BUY 1 filled  entry=2026-06-24 03:09  exit=NULL
  032830 BUY 1 filled  entry=2026-06-24 03:09  exit=NULL
  096770 BUY 1 filled  entry=2026-06-24 03:09  exit=NULL
  214150 BUY 1 filled  entry=2026-06-24 03:03  exit=NULL

v312 (testing, strategy_id=275, rsi_reversion):
  010950 BUY 1 filled  entry=2026-06-24 03:09  exit=NULL
  011070 BUY 1 filled  entry=2026-06-24 03:09  exit=NULL
  051900 BUY 1 filled  entry=2026-06-24 02:48  exit=NULL
  086790 BUY 1 filled  entry=2026-06-24 02:48  exit=NULL

v316 (testing, strategy_id=275, rsi_reversion):
  017670 SELL 1 cancelled  entry=2026-06-24 23:30  exit=NULL

v329 (testing, strategy_id=295, moving_average_cross):
  005930 BUY 1 filled  entry=2026-07-01 04:27  exit=NULL  [trade id 297]
  005930 BUY 1 filled  entry=2026-07-01 05:11  exit=NULL  [trade id 298]
  (SELL trade 299: 005930 SELL 2 filled exit=2026-07-01 05:39 ← 이미 closed)
```
