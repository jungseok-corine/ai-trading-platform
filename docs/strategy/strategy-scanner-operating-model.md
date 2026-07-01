# Strategy & Scanner Operating Model

> **STRATEGY-DOCS-1 — 문서 초안(docs only).** 코드/DB/주문/스케줄러 변경 0. 커밋 전 검토용 draft.
> 목적: "전략을 몇 개 돌릴까 / 스캐너와 전략은 어떻게 연결되나 / 같은 종목에 신호가 겹치면 어떻게 하나 /
> 쌓이는 데이터는 어떻게 분류하나 / AI는 언제 무엇을 하나"를 결정하기 위한 운영 모델.
> 관련: [exposure/arbitration 설계](../design/symbol-exposure-and-signal-arbitration.md) ·
> [현 전략 인벤토리·처분](current-strategy-inventory-and-disposition.md) ·
> [AI 리뷰·진화 정책](ai-review-and-strategy-evolution-policy.md) ·
> [EOD 요약 2026-07-01](../operations/eod-paper-trading-summary-2026-07-01.md).

---

## A. 핵심 원칙

1. **AI가 분석·실험하고, 사람이 실전 배치를 승인한다.** 스캐너·전략·신호는 주문을 직접
   실행할 권한이 없다. 실행은 사람이 명시적으로 옵트인한 좁은 경로(paper + 종목 화이트리스트 +
   회당 상한)에서만 일어난다.
2. **적게, 집중해서 시작한다.** 여러 전략을 난립시키지 않는다. 초기에는 **하나의 전략 패밀리**만
   실제 실행 후보로 둔다. 나머지는 signal-only(관찰) 또는 archive.
3. **계층을 분리한다.** Scanner(발굴) / Strategy(의견) / Signal(기록) / Arbiter(조정) /
   Risk(한도) / Order(의도) / Broker(전송)는 서로 다른 책임을 가진다. 하나가 다른 하나를
   건너뛰지 않는다.
4. **모든 실행은 가설을 동반한다.** 전략은 "무엇을 노리고, 어떤 조건에서 이기고 지는지"를
   명시해야 한다. 가설 없는 전략은 실행 후보가 아니라 실험 대상이다.
5. **데이터는 목적에 따라 분류한다.** 엔진 검증용 데이터와 수익성 검증용 데이터를 섞지 않는다
   (§ 인벤토리 문서의 데이터 분류 참조).
6. **안전 불변식은 코드/제안 어디서도 자동으로 바뀌지 않는다.** `KIS_REAL_TRADING_ENABLED=false`,
   scheduler 기본 비활성, universe auto-trade 기본 off, 실주문 TR 호출 금지.

---

## B. 파이프라인 (계층 흐름)

```text
Scanner
  → Candidate Store
    → Strategy Signal Generator
      → Signal Store
        → Execution Arbiter        (신규 · 미구현)
          → Risk Manager
            → Order Intent          (신규 · 미구현)
              → Broker Executor
```

| 계층 | 역할 | 주문? | 현 상태 |
|---|---|---|---|
| **Scanner** | 시장에서 종목 후보 발굴(뉴스/수급/가격/거래량 등) | ✗ | 인프라 존재(candidate_events, scanner_rule(_version)s, watchlists) |
| **Candidate Store** | 같은 symbol 후보 dedup, scanner별 score/source 기록 | ✗ | candidate_events 존재, dedup 정책 미정립 |
| **Strategy Signal Generator** | strategy_version별 BUY/SELL/HOLD 의견 생성 | ✗ | StrategyRunnerService.run_once |
| **Signal Store** | 전략별 signal 기록, 같은 candle_ts 중복 방지 | ✗ | SignalLog(+unique) 존재 |
| **Execution Arbiter** | 같은 account/symbol 다중 signal 취합·충돌 해결·우선순위 | ✗ | **없음(직결)** |
| **Risk Manager** | 전략/종목/계좌 한도, pending 포함 exposure, daily loss/trades/positions | ✗ | 존재하나 pending·aggregate exposure 미반영 |
| **Order Intent** | 주문 의도 기록 + idempotency + 상태(승인/거절/실행) | ✗ | **없음** |
| **Broker Executor** | 승인된 order intent만 broker 전송 | ✓ | TradeService.execute_signal → broker.place_order(paper) |

> 현재는 **StrategyRunnerService._attempt_auto_trade → TradeService.execute_signal →
> RiskManager → broker.place_order**로 Arbiter/Order Intent 없이 직결된다. 각
> (strategy_version, symbol, candle) 신호가 독립적으로 주문을 시도한다. 이 문서의 B~E는
> **목표 모델**이며, 구현은 exposure/arbitration 설계의 E1~E7 단계(별도 승인)로 진행한다.

---

## C. Scanner 설계

**Scanner = "무엇을 볼지"를 좁히는 계층.** 주문·전략 판단을 하지 않는다.

* **입력**: 시장 데이터(가격/거래량/수급/뉴스/공시/거시).
* **출력**: candidate(종목 + score + source + 발굴 근거 + 타임스탬프).
* **원칙**:
  * 스캐너는 **전략과 1:1로 묶이지 않는다.** 하나의 후보 풀을 여러 전략이 소비할 수 있다.
  * 같은 symbol을 여러 스캐너가 낼 수 있으므로 **Candidate Store에서 dedup**(symbol 기준
    합치고 scanner별 score/source 보존).
  * 스캐너 규칙은 **버전 관리**(scanner_rule_versions)한다. 규칙을 덮어쓰지 않고 새 버전.
  * 초기에는 스캐너를 **좁게**(예: 장 초반 강세 + 유동성 충분 종목) 둔다. 넓은 유니버스는
    노이즈·과노출을 만든다.
* **주의**: scanner_candidates / watchlist 유니버스는 **broad**다. 좁은 실행에는 종목
  화이트리스트(symbol_code 모드)를 쓴다.
* **현 상태(2026-07-01 라이브 확인)**: `scanner_rules` 3개가 **전부 `[예시]` 시드**이고
  `candidate_events`는 stale(최근 0건)이다. 즉 스캐너는 **실전 운영 상태가 아니다**. 다음
  전략군에 맞춰 **좁은 scanner_rule_version을 새로 정의**해야 한다. 상세는
  [인벤토리 문서](current-strategy-inventory-and-disposition.md) § 5.

---

## D. Strategy 설계 (가설 필수)

**Strategy = "후보에 대해 언제 사고/팔지" 의견을 내는 계층.** 실행 권한 없음.

각 strategy_version은 다음을 **명시**해야 한다:

| 항목 | 설명 |
|---|---|
| **가설(hypothesis)** | 무엇을 노리는가(예: "장 초반 강세주의 첫 눌림에서 유동성 회복 시 반등"). |
| **진입 조건** | 구체적 트리거(지표·시간대·거래량 조건). |
| **청산 조건** | 목표/손절/시간 청산. SL/TP는 필수. |
| **이기는 장 / 지는 장** | 어떤 국면에서 작동하고 어떤 국면에서 깨지는가. |
| **노출 한도** | 종목/전략당 최대 노출(exposure limit과 연결). |
| **평가 지표** | 승률·평균손익·MDD·거래빈도 등 성공/실패 판정 기준. |

* **버전 불변식**: 개선은 항상 **새 버전**으로 만든다. 기존 StrategyVersion 파라미터를
  덮어쓰지 않는다.
* **상태 게이트**: `enabled`(러너가 이 버전을 돌릴지)와 `auto_trade_enabled`(신호를 실제
  주문으로 보낼지)는 **별개 필드**다. UI "활성화" 체크박스는 `enabled`에 매핑된다(UI drift 주의).
* **초기 정책**: 실제 auto-trade 후보는 **한 번에 하나의 전략 패밀리**만. 나머지는 signal-only.

---

## E. 같은 종목 다중 신호 처리 (arbitration)

같은 account/symbol/time-window에 신호가 겹칠 때의 규칙. (설계는
[exposure/arbitration 문서](../design/symbol-exposure-and-signal-arbitration.md) § 5와 일치.)

| 케이스 | 규칙 |
|---|---|
| **BUY + BUY** | aggregate exposure cap **이내에서만** 채택. 초과분 거절. 피라미딩은 `allow_pyramiding`/`max_add_count`로 **명시** 제어. (현 v329가 cap 부재로 2주 누적한 사례.) |
| **BUY + SELL (충돌)** | **리스크 축소 SELL 우선**, SL/TP SELL **최우선**. 동일 symbol에 BUY·SELL 동시 존재 시 신규 BUY 보류(netting 또는 HOLD). |
| **SELL + SELL** | 중복 청산 방지 — **최종 sell qty ≤ 실제 보유 수량**. (현 guard는 미보유 SELL만 스킵; 보유 초과 중복 SELL은 arbiter가 합산 제한.) |
| **pending order 존재** | 같은 symbol에 pending BUY/SELL 있으면 신규 BUY 보류. pending **timeout 정책** 필요. |

**권장 우선순위**: `SL/TP SELL > 일반 SELL(risk-reducing) > BUY(risk-increasing)`.

**Exposure 계산**(pending 포함):
```text
current_exposure(symbol) =
    broker holding value
  + DB open position value
  + pending BUY order value
  - pending SELL order value
```
broker/DB mismatch 시 paper는 최소 WARN, 보수적으로 BLOCK 권장. pending은 항상 포함.

**현 상태**: Arbiter/Order Intent/aggregate exposure cap/pending-aware 계산은 **미구현**.
현재 있는 방어는 (1) 기존 RiskRule(주문당 notional·심볼 수·daily loss/trades·CLL),
(2) SELL-without-holding guard, (3) SignalLog unique/dedup. 다중 신호 arbitration은
E3~E5 단계에서 도입한다.

---

## F. 운영 원칙 (요약)

1. **한 번에 하나의 전략 패밀리**만 실제 실행 후보로 둔다. 검증 전 확장 금지.
2. **스캐너는 좁게** 시작한다. broad universe는 관찰(signal-only)로만.
3. **모든 실행 후보는 가설·SL/TP·노출 한도·평가 지표**를 갖춘다.
4. **같은 종목 다중 신호**는 arbiter가 조정(§ E). arbiter 없는 동안은 종목 화이트리스트 +
   회당 상한 + small qty로 노출을 물리적으로 제한한다.
5. **엔진 검증과 수익성 검증을 분리**한다(데이터 오염 방지).
6. **재개 조건**: reconciliation mismatch 0 · readiness BLOCK 0 · 단일 앱 인스턴스 ·
   가능하면 E3 per-symbol exposure cap 적용 후.
7. **AI는 초기엔 reviewer/analyst.** 자율 제어는 나중 단계(사람 승인·제한 범위 이후).
