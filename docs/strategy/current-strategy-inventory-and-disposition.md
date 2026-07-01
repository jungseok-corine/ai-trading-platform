# Current Strategy Inventory & Disposition

> **STRATEGY-DOCS-1 — 문서 초안(docs only).** 코드/DB/주문/스케줄러 변경 0. 커밋 전 검토용 draft.
> 목적: 지금 존재하는 전략을 나열하고, 각각을 어떻게 처분(유지/일시정지/보관/신호만/후보)할지 결정한다.
> 관련: [운영 모델](strategy-scanner-operating-model.md) · [AI 정책](ai-review-and-strategy-evolution-policy.md) ·
> [EOD 요약 2026-07-01](../operations/eod-paper-trading-summary-2026-07-01.md).

> ✅ **인벤토리 수치는 라이브 DB(Postgres, Docker)로 검증됨 — 2026-07-01 (STRATEGY-DOCS-2).**
> read-only SELECT만 사용했다. DB write/코드/스케줄러/주문 변경 없음. 서버(PID 86433, :8000)는
> 건드리지 않았다. 재확정이 필요하면 § 0 쿼리를 다시 실행한다.

---

## 0. 라이브 인벤토리 쿼리 (재확인용 read-only)

```sql
-- 상태별 버전 수
SELECT status, count(*) FROM strategy_versions GROUP BY status ORDER BY status;

-- 실행/무장 상태 버전 상세
SELECT id, strategy_id, status,
       parameters->>'strategy_type'       AS stype,
       parameters->>'symbol_code'         AS sym,
       parameters->>'enabled'             AS enabled,
       parameters->>'auto_trade_enabled'  AS auto_trade,
       parameters->>'universe_auto_trade' AS universe_auto_trade,
       parameters ? 'universe'            AS has_universe
FROM strategy_versions
WHERE (parameters->>'auto_trade_enabled')='true'
   OR (parameters->>'universe_auto_trade')='true'
   OR status IN ('active','testing')
ORDER BY id;

-- 계좌 전체 자동주문 무장 수 (0이어야 안전)
SELECT count(*) FROM strategy_versions WHERE (parameters->>'auto_trade_enabled')='true';
```

---

## 1. 전략 인벤토리 (라이브 DB 확정, 2026-07-01)

**집계**
* strategies: **13** · strategy_versions: **25**
* status 분포: **testing 20 · draft 5** (active 0)
* **`auto_trade_enabled=true`: 0** (계좌 전체 자동주문 정지) ✅
* **`universe_auto_trade=true`: 0** (broad universe 자동매매 전부 disarmed) ✅
* `enabled` 분포: true 23 · null 2 (null 2건은 draft rsi_reversion)
* strategy_type 분포: rsi_reversion 10 · breakout_high 7 · moving_average_cross 3 · pullback_trend 2 · macd_trend 2 · momentum_surge 1
* symbol_code: `005930` 3건(ma_cross 327/328 draft + 329) · 나머지 22건은 universe(빈 symbol)
* account_id: 230 → 17건 · null 8건

**v329 (SMOKE_TEST) — pause 확인**
* id 329 / strategy_id 295 / moving_average_cross / **005930** / status **testing**
* `enabled=true` · **`auto_trade_enabled=false`(pause)** · `universe_auto_trade=false` ·
  universe key **absent** · account 230 · `timeframe=1m`
* trades: 297 BUY qty1 @320,000 filled / 298 BUY qty1 @319,500 filled /
  299 SELL qty2 @316,000 filled, pnl_amount −1,233 (position realized 포함 −8,829) → flat

**Broad universe 8종 (PAPER-RESUME-UNIVERSE-OFF 대상) — type 확정**

| version | strategy_type | universe | status | auto_trade | universe_auto_trade | 분류 |
|---|---|---|---|---|---|---|
| 298 | macd_trend | watchlist | TESTING | false | false | SIGNAL_ONLY/ARCHIVE |
| 300 | pullback_trend | watchlist | TESTING | false | false | SIGNAL_ONLY/ARCHIVE |
| 302 | macd_trend | scanner_candidates | TESTING | false | false | SIGNAL_ONLY/ARCHIVE |
| 304 | pullback_trend | scanner_candidates | TESTING | false | false | SIGNAL_ONLY/ARCHIVE |
| 315 | rsi_reversion | scanner_candidates | TESTING | false | false | SIGNAL_ONLY/ARCHIVE |
| 316 | rsi_reversion | watchlist | TESTING | false | false | SIGNAL_ONLY/ARCHIVE |
| 317 | breakout_high | watchlist | TESTING | false | false | SIGNAL_ONLY/ARCHIVE |
| 318 | breakout_high | scanner_candidates | TESTING | false | false | SIGNAL_ONLY/ARCHIVE |

> **정정**: 이전 스냅샷은 "8개만 disarmed"로 좁게 봤으나, 라이브 확인 결과 **testing universe
> 버전은 총 19개**(297/298/299/300/302/303/304/306/307/308/309/310/312/313/314/315/316/317/318)이며
> **전부 `universe_auto_trade≠true`(disarmed) + single-symbol 아님(universe key 보유)**. 위 8종은
> 그중 명시적으로 처리된 대표군. 나머지 universe testing 버전도 동일하게 SIGNAL_ONLY/ARCHIVE 범주다.

**Draft 5종**
* 327 / 328: moving_average_cross / 005930 — 개발·테스트 산물(synthetic) → **DEV_ONLY**
* 301 / 305 / 311: rsi_reversion / (universe) — draft 관찰 산물 → **DEV_ONLY / ARCHIVE**

**안전 상태 확인 (read-only)**
* `KIS_REAL_TRADING_ENABLED=false` ✅
* account 230 RiskConfig: `emergency_stop=false`, max_daily_loss 100,000, max_open_positions 5, max_trades_per_day 10
* `auto_trade_enabled=true` 전략 0 · `universe_auto_trade=true` 전략 0 ✅

---

## 2. 처분 카테고리 정의

| 카테고리 | 의미 | 조치 |
|---|---|---|
| **SMOKE_TEST** | 자동매매 **엔진** 검증용. 수익 전략 아님. | 필요 시 pause 상태로 보존. 수익 목적 최적화 금지. |
| **PAUSE** | 잠시 멈춤. 재개 여지 있음. | `auto_trade_enabled=false` 유지, status 보존. |
| **ARCHIVE** | 더 안 쓸 전략. | status archive/보관. 삭제는 신중(데이터 손실 위험). |
| **SIGNAL_ONLY** | 신호만 관찰(주문 안 함). | `auto_trade_enabled=false`, 필요 시 signal-only 러너로 관찰. |
| **PAPER_CANDIDATE** | paper 실행 후보(제한된 실주문). | 가설·SL/TP·노출 한도 충족 + 사람 승인 후에만. |
| **PROFIT_CANDIDATE** | 수익성 검증 단계 진입 전략. | 충분한 clean 데이터 + reviewer 승인 후. |

---

## 3. 처분 결정 (현재)

* **v329 → SMOKE_TEST.** 엔진(신호→리스크→주문→체결→청산→정합) 검증에 성공했고 그것으로 역할을 다했다.
  **v329를 수익 전략으로 최적화하지 않는다.** pause 유지(`auto_trade_enabled=false`).
* **모든 broad universe testing 버전(19종) → SIGNAL_ONLY 또는 ARCHIVE.** 8종
  (298/300/302/304/315/316/317/318) type은 위 표에서 확정(macd_trend·pullback_trend·rsi_reversion·breakout_high).
  전부 `universe_auto_trade=false`로 실행 후보 아님. rsi_reversion·breakout_high가 신호량 대부분을
  차지(§ 4) → 관찰 가치 있는 소수만 SIGNAL_ONLY, 나머지는 ARCHIVE 권장.
* **327/328/301/305/311 → DEV_ONLY.** draft 테스트/관찰 산물. 실행/후보 아님.
* **새 PAPER_CANDIDATE는 아직 없음.** 다음 후보 방향은 [AI 정책 문서](ai-review-and-strategy-evolution-policy.md) 참조
  (장 초반 강세주 눌림/유동성 회복).

---

## 4. 축적 데이터 분류

데이터는 **목적에 따라 분리**한다. 섞으면 수익성 판단이 오염된다.

| 분류 | 정의 | 예시 | 용도 |
|---|---|---|---|
| **Engine Validation** | 파이프라인 정상 동작을 확인하는 데이터. 전략 품질과 무관. | v329의 오늘 사이클(297 BUY / 298 BUY / 299 SL SELL, realized −8,829) | 엔진 안정성 근거. **수익성 판단에 쓰지 않는다.** |
| **Strategy Profitability** | 가설을 갖춘 전략의 실제 성과 데이터. | (아직 없음 — PAPER_CANDIDATE 실행 후 축적) | 승률·평균손익·MDD 산출, 실전 후보 판정. |
| **Noise / Invalid** | 오염·중복·비정상 조건에서 나온 데이터. | UI drift 기간 신호, app stuck 구간, 장 마감 후 broker ERROR BUY, 미보유 SELL REJECTED | 분석에서 제외. 원인 기록용으로만 보존. |

**라이브 데이터 볼륨(2026-07-01)**
* `signal_logs`: **137,991건**(최근 7일 96,678). 대부분 universe testing 버전의 관찰 신호
  (297=21,824 / 312=15,182 / 317=12,950 …). → **Engine Validation / 관찰 데이터**(수익성 아님).
* `trades`: **38건**(최근 7일 8). v329가 3건(297/298/299). 나머지는 과거 산발 테스트.
  → 검증된 가설·clean 실행이 아니므로 **Strategy Profitability 데이터로 쓰지 않는다**.
* `risk_events`: **19,156건**(최근 7일 13,317). 리스크 룰 평가 로그 → 엔진/리스크 검증 데이터.

* **오늘(2026-07-01) v329 데이터는 전부 Engine Validation.** 수익성 데이터가 아니다.
* 장 마감 부근/이후 broker ERROR BUY, 미보유 데드크로스 SELL REJECTED 등은 **Noise/Invalid**.
* **13만 건의 signal_logs는 수익성 데이터가 아니다** — 검증된 가설·clean 실행 조건이 아닌
  universe 관찰 신호이므로 Engine/관찰 데이터로 분류한다.
* Strategy Profitability 데이터는 **PAPER_CANDIDATE가 가설·SL/TP·노출 한도를 갖추고 clean
  하게 실행된 이후**에야 쌓이기 시작한다.

---

## 5. Scanner / Candidate 인벤토리 (라이브 확정)

| 테이블 | count | 비고 |
|---|---|---|
| `scanner_rules` | 3 | **전부 `[예시]` 시드**(거래량 급증 등), KR, enabled=true |
| `scanner_rule_versions` | 9 | 시드 규칙의 버전 |
| `scanner_rule_proposals` | 6 | 제안(미채택) |
| `candidate_events` | 462 | **최근 7일 0건**(stale) — 과거/시드 후보 |
| `intelligence_candidates` | 0 | 비어 있음 |
| `leader_trend_candidate_events` | 0 | 비어 있음 |
| `candidate_strategy_proposals` | 0 | 비어 있음 |
| `watchlists` / `watchlist_symbols` | 4 / 110 | universe resolver source(watchlist) |

* **UniverseResolver source**: `scanner_candidates`(candidate_events 기반) · `watchlist`(watchlists/symbols). 둘 다 broad.
* **현재 스캐너는 실전 운영 상태가 아니다.** 규칙 3개가 전부 `[예시]` 시드이고 candidate_events가
  stale(최근 0건)이다. → 스캐너 데이터는 **후보 탐색/엔진 검증 데이터**이며 **전략 수익성 데이터가 아니다**.
* **다음 전략군(장 초반 강세주 눌림/유동성 회복)에 맞춰 스캐너를 새로 좁혀야 한다.** 시드 예시 규칙을
  실전 후보 발굴에 그대로 쓰지 않는다(새 scanner_rule_version으로 좁게 정의).

---

## 6. 다음 조치

1. broad universe testing 19종 중 **SIGNAL_ONLY로 남길 소수**를 고르고 나머지는 **ARCHIVE**.
2. 다음 PAPER_CANDIDATE 전략 패밀리 1개 선정([AI 정책 문서] 방향: 장 초반 강세주 눌림/유동성 회복).
3. 그 전략군에 맞는 **좁은 scanner_rule_version** 신규 정의(시드 예시 대체, 별도 승인).
4. 데이터 파이프라인에 **분류 태깅**(engine/profitability/noise) 도입 검토(별도 승인).
