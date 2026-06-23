# IMPLEMENTED-BUT-UNUSED.md — 구현됐지만 실사용 안 하는 기능 목록

> 마지막 갱신: 2026-06-23  
> "구현됨"은 코드+테스트+API가 존재함을 뜻한다.  
> "실사용 안 함"은 기본 비활성이거나, 프론트에서 노출 안 되거나,  
> 실제 운용 흐름에서 한 번도 트리거된 적 없음을 의미한다.

---

## 1. 스케줄러 잡 — 기본 비활성 (11/13개)

아래 잡들은 코드와 테스트가 완성되어 있지만, 서버 시작 시 자동으로 실행되지 않는다.  
"자율 잡 제어" UI에서 수동으로 켜야 한다.

| 잡 ID | 기본값 | 담당 기능 |
|-------|--------|-----------|
| `trading_state_sync` | `False` | TradingGuard 상태 동기화 |
| `daily_report` | `False` | 일일 리포트 생성 |
| `data_refresh` | `False` | 시세·지표 갱신 |
| `research_pipeline` | `False` | 후보 탐색 + 배정 |
| `scanner_review` | `False` | 스캐너 성과 검토 |
| `strategy_review` | `False` | 전략 성과 검토 + 회고 |
| `us_market_refresh` | `False` | 미장 데이터 갱신 |
| `operations_digest` | `False` | 운영 다이제스트 생성 |
| `dart_ingest` | `False` | DART 공시 수집 |
| `edgar_ingest` | `False` | SEC EDGAR 공시 수집 |
| `intraday_event_monitor` | `False` | 장중 이벤트 감지 |

> **의도**: 안전 정책. 새 잡은 기본 비활성으로 추가하는 게 이 레포의 규칙.

---

## 2. 전략 타입 — 정의됐지만 거의 사용 안 됨

현재 registry에 8개 전략 타입이 등록되어 있다.  
실제 운용 전략 대부분은 `moving_average_cross`이며, 나머지는 실험·후보 수준이다.

| 전략 타입 | 파일 | 운용 상태 |
|-----------|------|-----------|
| `moving_average_cross` | `moving_average_cross.py` | 실운용 (기준 전략) |
| `volume_confirmed_ma_cross` | `volume_confirmed_ma_cross.py` | 실험 중 |
| `flow_confirmed_volume_ma_cross` | `flow_confirmed_volume_ma_cross.py` | 실험 중 |
| `rsi_reversion` | `rsi_reversion.py` | 실험 중 |
| `macd_trend` | `macd_trend.py` | 실험 중 |
| `breakout_high` | `breakout_high.py` | 거의 미사용 |
| `pullback_trend` | `pullback_trend.py` | 거의 미사용 |
| `momentum_surge` | `momentum_surge.py` | 거의 미사용 |

---

## 3. 장중 이벤트 모니터 (intraday_event_monitor)

- **구현**: `IntradayEventMonitorService` + `IntraWeekDisclosureTrigger` 모델
- **기능**: 보유 종목의 장중 공시 이벤트를 감지해 중요도 점수가 임계값 이상이면  
  알림/트리거를 생성
- **미사용 이유**: 스케줄러 기본 비활성 + DART 수집기도 꺼져 있어 입력 데이터 없음
- **연결된 기능**: `disclosure_assessment_service.py` (공시 중요도 평가)

---

## 4. 실계좌 등록 서비스 (LiveAccountRegistrationService)

- **구현**: `live_account_registration_service.py`
- **기능**: KIS 실계좌를 시스템에 등록할 때 자동으로:
  - `RiskConfig.emergency_stop = True` 강제 설정
  - `TradingGuardState = paused` 강제 설정
- **미사용 이유**: `KIS_REAL_TRADING_ENABLED=False` 기본값으로 실계좌 운용 자체가 없음
- **위험도**: 이 서비스를 통해서만 실계좌를 등록해야 안전장치가 제대로 설정됨

---

## 5. 투자자 수급 데이터 (InvestorFlowService)

- **구현**: `investor_flow_service.py` + `KISInvestorFlowClient`
- **기능**: KIS API에서 외국인/기관/개인 매수 수급 데이터를 수집·저장
- **미사용 이유**: `data_refresh_scheduler=False` + 수집 잡이 꺼져 있어  
  DB에 데이터가 쌓이지 않음
- **활용 가능성**: MarketContext bundle에 포함 가능하나 현재 미연동

---

## 6. 포트폴리오 서비스 (PortfolioService)

- **구현**: `portfolio_service.py` + "포트폴리오" UI 섹션
- **기능**: 현재 보유 포지션의 종합 평가 (다계좌 집계)
- **현황**: UI는 있으나 브로커 연결 없이 DB 기반 집계만 제공.  
  실시간 평가금액은 broker.get_account_balance() 호출 필요

---

## 7. 거시 체제 분석 (MacroRegimeService)

- **구현**: `macro_regime_service.py` — KOSPI 추세 + 외환/금리 데이터로 체제 분류
- **기능**: 확장/수축/불확실 세 가지 체제를 판단해 AI 분석 bundle에 포함
- **현황**: 서비스 자체는 동작하지만 FRED/외부 API 의존으로 실제 운용 환경에서  
  데이터 갱신이 막혀 있을 수 있음 (네트워크 제한 환경)

---

## 8. 승격 준비도 체크리스트 (PromotionReadinessSection)

- **구현**: `PromotionReadinessSection.tsx` + 관련 API
- **기능**: DRAFT 전략이 ACTIVE 승격 준비가 됐는지 체크리스트 형태로 표시
- **현황**: UI는 있으나 체크리스트 기준이 하드코딩(실험 기간 7일, 최소 거래 10건 등)  
  — 실제 운용 기준으로 조정 필요

---

## 9. 뉴스 큐레이터 (NewsCuratorService) — RSS 미구현

- **구현**: `news_curator_service.py` — DART/EDGAR 공시 뉴스 큐레이션
- **현황**: 진짜 RSS/뉴스 피드 수집 없음. 수집된 공시(Disclosure) 데이터를  
  뉴스로 취급하는 방식으로 동작
- **갭**: 실제 한국 주식 뉴스(네이버 금융, 연합뉴스 등) RSS 연동 없음

---

## 10. 분석 감사 (AnalysisAuditService)

- **구현**: `analysis_audit_service.py` + "분석 감사" UI 섹션
- **기능**: LLM 분석 호출 이력, 입력 bundle 크기, 비용, 응답 품질 추적
- **현황**: 기능은 완성됐지만 AI 분석을 정기적으로 실행하지 않으면  
  데이터가 없어 화면이 비어 있음

---

## 요약표

| 카테고리 | 구현 완성도 | 실사용 여부 | 활성화 방법 |
|---------|------------|------------|------------|
| 자율 잡 (11개) | 완성 | X | 환경변수 or UI 토글 |
| 실계좌 등록 | 완성 | X | KIS_REAL_TRADING_ENABLED=true |
| 장중 이벤트 모니터 | 완성 | X | dart_ingest + intraday_event_monitor 활성화 |
| 투자자 수급 데이터 | 완성 | 부분 | data_refresh_scheduler 활성화 |
| RSS 뉴스 | 미구현 | X | 신규 구현 필요 |
| 포트폴리오 집계 | 완성 | 부분 | 실시간은 브로커 연결 필요 |
| breakout/pullback/momentum 전략 | 완성 | 실험 수준 | 버전 파라미터로 선택 가능 |
