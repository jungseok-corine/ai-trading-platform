# AI Review & Strategy Evolution Policy

> **STRATEGY-DOCS-1 — 문서 초안(docs only).** 코드/DB/주문/스케줄러 변경 0. 커밋 전 검토용 draft.
> 목적: AI가 전략 운영에서 **언제 무엇을 하는지** 단계별로 정의하고, 전략을 몇 개 돌릴지에 대한
> 정책과 다음 권장 방향을 기록한다.
> 관련: [운영 모델](strategy-scanner-operating-model.md) · [인벤토리·처분](current-strategy-inventory-and-disposition.md) ·
> [EOD 요약 2026-07-01](../operations/eod-paper-trading-summary-2026-07-01.md).

---

## A. 대전제

> **AI는 약한 전략을 자동으로 수익 전략으로 바꾸지 못한다.**

AI는 로그·성과 분석과 제안에 유용하지만, 초기 단계에서는 **reviewer/analyst**다.
자율 제어(스캐너/전략을 스스로 켜고 끄고 배치)는 **clean data pipeline + 사람 승인 +
제한 범위**가 갖춰진 나중 단계의 일이다. 안전 불변식은 AI 제안으로도 우회되지 않는다
(제안은 항상 pending → 승인해도 DRAFT + auto_trade=False).

---

## B. AI 역할 단계 (Stage 0–8)

각 단계는 **이전 단계가 검증된 뒤에만** 다음으로 넘어간다. 앞 단계를 건너뛰지 않는다.

| Stage | 이름 | AI가 하는 일 | 권한 | 전제 |
|---|---|---|---|---|
| **0** | Observer | 로그·신호·체결·정합 데이터를 읽고 요약 | 읽기만 | 엔진 검증 완료 |
| **1** | Reviewer | 전략 성과 리뷰, 이상 징후(오염·중복·과노출) 지적 | 읽기 + 리포트 | clean/noise 데이터 분류 |
| **2** | Analyst | 승률·손익·MDD 등 지표 산출, 가설 검증 결과 제시 | 읽기 + 분석 | Strategy Profitability 데이터 축적 |
| **3** | Proposer | 새 전략/파라미터 **제안**(pending) | 제안만(자동적용 금지) | 지표 근거 존재 |
| **4** | Scanner Tuner | 스캐너 규칙 조정 **제안**(새 버전) | 제안만 | 후보 품질 데이터 |
| **5** | Backtest/Sim | 제안을 backtest/paper sim으로 검증 | sim 실행(실주문 아님) | sim 인프라 |
| **6** | Paper Pilot 제안 | 검증된 제안을 제한 paper 후보로 **제안** | 제안 + 사람 승인 필요 | exposure cap · 단일 인스턴스 |
| **7** | Supervised Auto | 사람이 승인한 좁은 범위에서 자동 운영 감독(중단 권고) | 감독 + 중단 제안 | E3~E5 arbiter/exposure |
| **8** | Constrained Autonomy | 명시적·제한된 범위에서 후보 켜고/끄기 자동 | 제한 자율(사람 override 상시) | 장기 신뢰 + 강한 가드레일 |

* **현재 위치: Stage 0–1.** 엔진 검증(v329 smoke test)이 끝났고, 이제 Observer/Reviewer로서
  데이터 분류·리뷰를 할 수 있다. Stage 2(Analyst) 이상은 **Strategy Profitability 데이터**가
  쌓여야 의미가 있다(현재 없음).
* Stage 3+ 제안은 **항상 pending**, 승인해도 **DRAFT + auto_trade=False**. Stage 8조차
  사람 override가 상시 우선한다.

---

## C. 전략 개수 정책

* **초기: 실제 실행 후보 = 1개 전략 패밀리.** 여러 전략 난립 금지. 검증되지 않은 전략을
  동시에 실행하면 데이터가 오염되고 노출이 겹친다.
* signal-only(관찰) 전략은 여러 개 둘 수 있으나, **auto_trade_enabled=true는 한 번에 하나의
  집중 패밀리**로 제한한다.
* 개수를 늘리는 조건: (1) 현 후보가 clean 데이터로 가설 검증, (2) exposure cap(E3) 적용,
  (3) arbiter(E5)로 다중 신호 조정 가능, (4) 사람 승인.
* **버전은 늘려도 되지만 덮어쓰지 않는다.** 개선 = 새 버전.

---

## D. 다음 권장 방향

* **v329는 engine smoke test로 종료** — 수익 목적으로 최적화하지 않는다.
* 다음 실전 후보는 **하나의 집중된 전략 패밀리**로 시작한다.
  * **후보: 장 초반 강세주의 눌림목 / 유동성 회복 진입 전략.**
    * 가설: 장 초반 강한 종목이 첫 눌림에서 유동성이 회복될 때 반등 확률이 높다.
    * 스캐너: 장 초반 강세 + 충분한 유동성(거래량/스프레드) 종목으로 **좁게**.
    * 진입: 눌림 후 유동성 회복 트리거. 청산: SL/TP 필수 + 시간 청산 고려.
    * 노출: single-symbol 또는 소수 화이트리스트 + 회당 상한 + small qty로 시작.
* **AI는 이 전략의 reviewer/analyst**부터(로그·성과 분석, 제안). 자율 제어는 나중.

---

## E. 진행 전제 조건 (게이트)

새 PAPER_CANDIDATE를 켜기 전 모두 충족:

1. **reconciliation mismatch 0** (broker=DB).
2. **readiness BLOCK 0** (paper-resume-readiness).
3. **단일 앱 인스턴스**(중복 uvicorn = 이중 스케줄러 = 중복 주문 위험 방지).
4. **가능하면 E3 per-symbol exposure cap 적용** 후(누적 매수 방지).
5. **가설·SL/TP·노출 한도·평가 지표** 명시.
6. **사람 승인**(paper + 종목 화이트리스트 + 회당 상한).

안전 불변식(`KIS_REAL_TRADING_ENABLED=false`, scheduler 기본 비활성, universe auto-trade
기본 off, 실주문 TR 호출 금지, AI 제안 자동적용 금지)은 어느 단계에서도 유지된다.
