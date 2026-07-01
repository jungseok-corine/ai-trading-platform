# Strategy Disposition Plan — Keep Signal-Only vs Archive

> **STRATEGY-DISPOSITION-PLAN-1 — 제안 문서(docs only).** 코드/DB/주문/스케줄러 변경 0.
> read-only SELECT로 확인한 현재 상태에 근거한 **처분 제안**이며, 실제 DB 변경은 별도 승인
> 작업(`STRATEGY-ARCHIVE-PLAN-1` → `STRATEGY-ARCHIVE-APPLY-1`)에서 수행한다.
> 관련: [운영 모델](strategy-scanner-operating-model.md) · [인벤토리·처분](current-strategy-inventory-and-disposition.md) ·
> [AI 정책](ai-review-and-strategy-evolution-policy.md).

---

## 1. 목적

* 지금 **TESTING 전략이 20개**라 signal/risk/noise 데이터가 계속 쌓인다(7일 signal 96,787 · risk 13,310).
* 다음 단계로 가기 전에 **전략 수를 줄이는 운영 결정**이 필요하다(구현이 아니라 결정).
* **자동주문 대상은 0개 유지**(`auto_trade_enabled=true` = 0).
* **signal-only 후보도 소수만 유지**(다음 전략군과 관련된 것만).
* 나머지는 **archive 후보**로 둔다(삭제가 아니라 "운영 대상 제외").

---

## 2. 현재 전략 상태 (라이브 read-only, 2026-07-01)

| 항목 | 값 |
|---|---|
| strategy_versions total | 25 |
| testing | 20 |
| draft | 5 |
| active | 0 |
| `auto_trade_enabled=true` | **0** ✅ |
| `universe_auto_trade=true` | **0** ✅ |
| `enabled=true` | 23 (나머지 2는 draft, null) |
| signal_logs (24h / 7d / total) | 19,352 / 96,787 / 138,115 |
| risk_events (24h / 7d / total) | 460 / 13,310 / 19,156 |
| trades (24h / 7d / total) | 3 / 8 / 38 |

**testing strategy_type 분포**: rsi_reversion 7 · breakout_high 7 · pullback_trend 2 · macd_trend 2 · moving_average_cross 1 · momentum_surge 1

**버전별 활동량 (testing 20개, 7일 기준)**

| id | type | universe | signal 7d | signal 24h | risk 7d | trades(all) | 신호 성격 |
|---|---|---|---|---|---|---|---|
| 312 | rsi_reversion | watchlist | 13,081 | 2,856 | 0 | 4 | 고빈도 노이즈 |
| 317 | breakout_high | watchlist | 11,580 | 2,134 | 6,451 | 1 | 고빈도 + 리스크평가 도달 |
| 310 | breakout_high | watchlist | 11,279 | 2,128 | 0 | 0 | 고빈도 노이즈 |
| 316 | rsi_reversion | watchlist | 10,253 | 2,099 | 3,930 | 2 | 고빈도 + 리스크평가 |
| 306 | rsi_reversion | watchlist | 9,580 | 2,567 | 0 | 4 | 고빈도 노이즈 |
| 297 | rsi_reversion | watchlist | 9,576 | 2,567 | 0 | 5 | 고빈도 노이즈 |
| 299 | breakout_high | watchlist | 9,514 | 2,311 | 0 | 0 | 고빈도 노이즈 |
| 309 | rsi_reversion | watchlist | 4,990 | 1,179 | 0 | 0 | 중빈도 |
| 308 | breakout_high | watchlist | 3,610 | 736 | 0 | 0 | 중빈도 |
| 313 | rsi_reversion | watchlist | 3,189 | 625 | 0 | 0 | 중빈도 |
| 315 | rsi_reversion | scanner_candidates | 3,155 | 0 | 1,476 | 2 | 중빈도(오늘 0) |
| 318 | breakout_high | scanner_candidates | 2,600 | 0 | 1,448 | 0 | 중빈도(오늘 0) |
| 314 | breakout_high | scanner_candidates | 2,593 | 0 | 0 | 1 | 중빈도(오늘 0) |
| 303 | breakout_high | scanner_candidates | 1,354 | 0 | 0 | 0 | 저빈도(오늘 0) |
| 307 | momentum_surge | watchlist | 121 | 16 | 0 | 0 | 저빈도 |
| **329** | **moving_average_cross** | **(single 005930)** | 27 | 27 | 5 | 3 | **SMOKE_TEST** |
| 298 | macd_trend | watchlist | 0 | 0 | 0 | 0 | **무신호(dormant)** |
| 300 | pullback_trend | watchlist | 0 | 0 | 0 | 0 | **무신호(dormant)** |
| 302 | macd_trend | scanner_candidates | 0 | 0 | 0 | 0 | **무신호(dormant)** |
| 304 | pullback_trend | scanner_candidates | 0 | 0 | 0 | 0 | **무신호(dormant)** |

> 핵심 관찰: **rsi_reversion·breakout_high가 signal_logs의 대부분(고빈도 매 캔들 평가)** 을 만든다.
> **pullback_trend·macd_trend는 7일 0신호**(조건이 거의 안 걸리거나 실질적으로 idle).
> `status` enum 값: `draft · testing · active · retired · archived` — **`archived` 사용 가능**.

---

## 3. 분류 기준

| 분류 | 조건 | 조치(제안) |
|---|---|---|
| **KEEP_SIGNAL_ONLY** | 검토 가치 있음 · 다음 전략군 관련 · 노이즈 과하지 않음 · 자동주문 금지 | signal만 유지, `auto_trade_enabled=false` |
| **ARCHIVE_CANDIDATE** | 가설 약함 · 목적 불분명 · 데이터가 노이즈에 가까움 · 현재 방향과 불일치 · 계속 쌓아도 분석가치 낮음 | 운영 대상 제외(삭제 아님) |
| **SMOKE_TEST** | 엔진 검증용 · 수익 최적화 대상 아님 | pause 유지(v329) |
| **DEFER** | 지금 판단하기엔 정보 부족 | 조건/코드 확인 후 결정 |

---

## 4. 처분 제안 (버전별)

### SMOKE_TEST (1)
* **329** (moving_average_cross / 005930) — pause 유지, profit 후보 제외.

### KEEP_SIGNAL_ONLY (3) — 다음 전략군과 정렬된 최소 집합
* **300** (pullback_trend / watchlist) — 눌림목 계열, 다음 전략군에 가장 근접.
* **304** (pullback_trend / scanner_candidates) — 눌림목 계열 + scanner source 관찰용.
* **317** (breakout_high / watchlist) — 돌파 확인 보조. 유일하게 risk_event 평가에 다수 도달(6,451)해
  파이프라인 관찰 가치가 있는 breakout 대표 1개만 남김.

> pullback 2종은 현재 **무신호**지만, 다음 전략군(눌림/유동성 회복)의 **레퍼런스·재튜닝 대상**으로
> 남길 가치가 있다(조건을 좁혀 재정의 예정). breakout는 대표 1개만.

### ARCHIVE_CANDIDATE (15)
* **rsi_reversion 7종**: 297 · 306 · 309 · 312 · 313 · 315 · 316
  — 평균회귀 가설로 **눌림목/유동성 회복(강세 지속)** 방향과 상충. signal_logs 최대 노이즈원.
* **breakout_high 6종(대표 317 제외)**: 299 · 303 · 308 · 310 · 314 · 318
  — 동일 type 중복. 관찰은 317 하나로 충분.
* **macd_trend 2종**: 298 · 302 — 7일 무신호, 분석가치 낮음, 방향과 약한 연관.

### DEFER (1)
* **307** (momentum_surge / watchlist) — 저빈도(121/7d). "장 초반 강세주"와 개념적으로 닿을 수
  있으나 진입 메커니즘이 다름. **조건 코드 확인 후** KEEP vs ARCHIVE 결정.

### Draft (5) — 참고
* 327 · 328 (ma_cross/005930 synthetic) · 301 · 305 · 311 (rsi_reversion) → **DEV_ONLY**. testing 20개
  대상은 아니나, archive 정리 시 함께 정돈 권장.

**요약**: SMOKE_TEST 1 · KEEP_SIGNAL_ONLY 3 · DEFER 1 · ARCHIVE_CANDIDATE 15 (= testing 20).
→ **signal-only 관찰 대상을 20 → 최대 4(3 keep + 1 defer)로 축소** 제안.

---

## 5. Type-Level 판단

| type | 시장 가설 | 다음 목표(장 초반 강세주 눌림/유동성 회복)와 정합 | 권장 |
|---|---|---|---|
| **pullback_trend** | 상승 추세 중 눌림목 재진입 | **가장 근접**(눌림 = pullback) | **1순위 KEEP_SIGNAL_ONLY** (300/304), 조건 재튜닝 |
| **breakout_high** | 전고점 돌파 추격 | 보조(돌파 확인) | **대표 1개(317) KEEP**, 나머지 ARCHIVE |
| **momentum_surge** | 급등 모멘텀 | 개념적 근접하나 메커니즘 상이 | **DEFER**(307, 조건 확인 후) |
| **macd_trend** | MACD 추세 전환 | 약한 연관, 무신호 | ARCHIVE_CANDIDATE |
| **rsi_reversion** | 과매도 평균회귀 | **상충**(강세 지속 아님) + 최대 노이즈 | ARCHIVE_CANDIDATE(우선) |
| **moving_average_cross** | 골든/데드크로스 | 엔진 검증용 | SMOKE_TEST(v329) |

**권장 방향**: signal-only는 **pullback_trend(1순위) + breakout_high 대표 1개(2순위)** 로 좁힌다.
**macd_trend·rsi_reversion은 보류/archive**. 자동주문은 전부 OFF 유지.

---

## 6. 다음 실전 후보 전략군 선정 기준

* **다음 전략군: 장 초반 강세주 눌림 / 유동성 회복 진입** (1개로 집중).
* 기존 type 매핑:
  * **1순위: pullback_trend / liquidity-recovery 계열** — 눌림목 개념이 직접 대응. 단 현재 버전은
    무신호이므로 **조건(진입 트리거·유동성 필터·시간대)을 새로 좁혀 재정의** 필요.
  * **2순위: breakout_high(confirmation)** — 눌림 후 회복 확인 보조 신호로 결합 가능.
  * **보류: macd_trend · rsi_reversion** — 우선순위 낮음(방향 불일치/추세지연).
* **단, 최종 결정은 실제 전략 코드·진입/청산 조건 확인 후**(`NEXT-STRATEGY-1`에서 문서화).

---

## 7. 기존 데이터 정책

| 데이터 | 분류 | 처리 |
|---|---|---|
| v329 2026-07-01 trades (297/298/299) | **Engine validation** | 파이프라인 검증 근거. **profit 분석 제외.** |
| UI parameter drift 구간 신호 | **Noise / invalid** | profit 분석 제외. 원인 기록용. |
| 장 마감 후 broker ERROR BUY | **Noise** (market-hours guard 필요성 데이터) | profit 분석 제외. guard 설계 근거로만. |
| 미보유 데드크로스 SELL REJECTED | **Noise** | profit 분석 제외. |
| broad universe signal_logs (13.8만) | **Strategy observation** | **스캐너/전략 목적 불분명한 것은 AI 분석 대상에서 제외.** rsi/breakout 고빈도는 특히 노이즈. |
| trades 38 | **혼합 — 분류 필요** | 버전별로 태깅(대부분 rsi_reversion testing/draft). **수익성 분석 전 data quality flag 필수.** |

* **AI review eligible data**: 현재는 사실상 없음(수익성 데이터 미축적). AI는 **engine/observation 데이터
  요약·이상탐지(reviewer)** 까지만. profit 판단은 clean PAPER_CANDIDATE 실행 이후.
* **historical data 삭제 금지.** archive는 "운영 대상 제외"이지 데이터 삭제가 아니다.

---

## 8. 권장 운영 결정

### 지금 (변경 없음, 유지)
* `auto_trade_enabled=true` **0개 유지**.
* **v329 pause 유지**(SMOKE_TEST).
* 기존 TESTING signal-only 대상을 **20 → 최대 4로 줄일 준비**(이번엔 제안만).
* **UI parameter 편집 금지**(drift 위험).

### 다음 승인 작업 후보
* **`STRATEGY-ARCHIVE-PLAN-1`** — 실제 DB write 없이 § 4 archive 대상(15+DEFER 결과)을 확정하고
  적용 방식(enabled=false vs status=archived)을 설계.
* **`STRATEGY-ARCHIVE-APPLY-1`** — 별도 승인 후 archive/disable 적용(reversible 우선).
* **`NEXT-STRATEGY-1`** — 장 초반 강세주 눌림/유동성 회복 전략을 코드 조건 확인 후 문서 정의.

---

## 9. 실제 DB 변경 전 고려사항 (별도 승인 작업에서 확정)

* **status enum 확인됨**: `draft · testing · active · retired · archived` — `archived` 값 존재(사용 가능).
* **어떤 방식이 안전한가**:
  * **`enabled=false`** (parameters) — 러너가 `_run_version`에서 스킵(신호 생성 중단). **reversible, status 보존.** → **1순위 권장.**
  * **`status='archived'`** — `list_active()`(active+testing) 범위에서 제외되어 스케줄러/러너 대상에서 빠짐. 더 강한 제외이나 상태 변경 수반.
* **enabled=false만으로 signal generation이 멈추는지** 코드로 재확인 필요(러너 게이트가 `enabled` 기준인지 status 기준인지 양쪽 확인).
* **testing 유지 + enabled=false**가 status 변경보다 보수적/가역적이므로 archive 1차 수단으로 검토.
* **historical data(signal_logs/trades/risk_events) 삭제 금지.** archive = 운영 제외.
* 모든 적용은 **paper-only · 사람 승인 · 자동주문 0 유지** 전제.
