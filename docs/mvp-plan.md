# MVP Plan

## 1. MVP 목표

KIS 모의투자(VTS) 환경에서 **단순 전략 1개가 자동으로 매매를 실행하고, 모든 거래/판단 데이터가 DB에 축적되는 상태**를 가능한 빠르게 만든다. 화면(UI)보다 데이터 파이프라인과 안전장치(RiskManager)를 우선한다.

## 2. MVP 범위 (In Scope)

- KIS API 토큰 발급/갱신
- 현재가 조회
- 분봉 데이터 조회 및 저장
- 모의투자 계좌 조회 (잔고, 보유 종목)
- 모의투자 매수/매도 주문
- 거래 기록 저장 (`trades` 테이블, 실거래 확장 필드 포함)
- Risk Management Layer (모든 주문은 RiskManager 통과 필수)
- 단순 전략 1개 자동 실행 (예: 이동평균 교차)
- 전략 버전/성과 기록 (`strategy_versions`)
- 서버/엔진 상태 조회, Emergency Stop
- Swagger UI 기반 API 테스트 (+ 선택적으로 최소 Web 화면)

## 3. MVP 범위 제외 (Out of Scope → 이후 단계)

| 항목 | 이동 단계 |
|---|---|
| AI 분석 리포트 (`ai_analysis_reports`) | 2차 목표 |
| 전략 개선 워크플로 | 2차 목표 |
| 백테스트 엔진 | 2차 목표 |
| TimescaleDB 전환 | 데이터 누적 후 (성능 이슈 시점) |
| Celery 도입 | AI/배치 규모 확대 시 |
| 고급 Web 대시보드 (차트, 실시간 WebSocket) | 3차 목표 |
| LiveTradingEngine / KISRealBrokerClient 구현 | 3차 목표 (인터페이스만 MVP에서 정의) |
| iOS 앱 | 4차 목표 |

## 4. MVP 예시 전략

**이동평균 교차 전략 (Moving Average Crossover)**
- 분봉 데이터 기반 단기/장기 이동평균선 계산
- 골든크로스 → 매수 시그널, 데드크로스 → 매도 시그널
- 파라미터(`short_window`, `long_window`, 종목코드 등)는 `strategy_versions.parameters` JSONB에 저장

선택 이유: 구현이 단순해 RiskManager·TradingEngine·Broker 연동 흐름 전체를 빠르게 검증하는 데 적합. 전략 자체의 성능보다 **파이프라인 동작 검증**이 MVP의 목적.

## 5. MVP API 목록

```
GET  /api/v1/market/price/{symbol_code}           # 현재가 조회
GET  /api/v1/market/candles/{symbol_code}          # 분봉 조회
GET  /api/v1/account                                # 모의투자 계좌 조회
POST /api/v1/orders                                  # 수동 주문 (RiskManager 통과)
GET  /api/v1/trades                                  # 거래 기록 조회
GET  /api/v1/strategies
POST /api/v1/strategies
GET  /api/v1/strategies/{id}/versions
POST /api/v1/strategies/{id}/versions
PATCH /api/v1/strategies/{id}/versions/{vid}        # active/inactive 전환
GET  /api/v1/risk-config/{account_id}
PATCH /api/v1/risk-config/{account_id}
POST /api/v1/risk-config/{account_id}/emergency-stop
GET  /api/v1/engine/status
```

## 6. 우선순위 Task 목록

### Phase 0 — 프로젝트 기반
1. 백엔드 레포 구조 생성 (FastAPI 스켈레톤, `pyproject.toml`)
2. `docker-compose.yml` (PostgreSQL only)
3. `core/config.py` — KIS API 키, 모의투자 계좌번호, base URL(VTS) 환경변수 관리
4. Alembic 셋업 + 최초 마이그레이션 베이스

### Phase 1 — KIS API 연동 (조회)
5. KIS 접근토큰 발급/캐싱/갱신 로직 (`KISPaperBrokerClient.get_token`)
6. 현재가 조회 연동 → `/api/v1/market/price/{symbol_code}`
7. 분봉 데이터 조회 연동 → `/api/v1/market/candles/{symbol_code}`
8. 모의투자 계좌 조회(잔고/보유종목) → `/api/v1/account`

### Phase 2 — 데이터 모델
9. `accounts`, `strategies`, `strategy_versions`, `trades`, `market_data`, `risk_configs`, `risk_events` 테이블 정의 + 마이그레이션
10. Repository 계층 (각 테이블별 기본 CRUD)

### Phase 3 — Risk Management Layer
11. `RiskConfig`, `RiskContext`, `RiskCheckResult` 모델 정의
12. `RiskRule` 구현: EmergencyStop, MaxDailyLoss, MaxPositionSize, MaxOpenPositions, MaxTradesPerDay, ConsecutiveLossLimit
13. `RiskManager` 조립 + 단위 테스트 (DB 없이 로직 검증)
14. `RiskContextBuilder` (trades/accounts 조회 → RiskContext 생성)
15. `/api/v1/risk-config` 조회/수정 + emergency-stop 토글 API

### Phase 4 — 주문 실행 (모의투자)
16. `BrokerClient` ABC 정의 (`base.py`)
17. `KISPaperBrokerClient`: 매수/매도 주문 API 연동 (VTS)
18. `TradeService.execute_order()`: 주문 → `trades` 저장 (order_status, broker_order_id 등)
19. `POST /api/v1/orders` — 수동 주문 테스트용 엔드포인트 (RiskManager 경유)
20. `GET /api/v1/trades` — 거래 기록 조회

### Phase 5 — TradingEngine + 전략
21. `TradingEngine` ABC 정의 (`base.py`)
22. `PaperTradingEngine` 구현 (`KISPaperBrokerClient` 사용)
23. `Strategy` ABC + `MovingAverageCrossStrategy` 구현
24. `strategies` / `strategy_versions` API (생성, 버전 관리, active 전환)
25. `StrategyService.evaluate_and_trade()` — Signal 생성 → RiskManager → TradingEngine → Broker → DB 저장 전체 흐름 통합

### Phase 6 — 자동 실행 + 상태 조회
26. APScheduler 설정 — 분봉 주기에 맞춰 `evaluate_and_trade` 실행 등록
27. `GET /api/v1/engine/status` — 실행 여부, 마지막 시그널/주문, 리스크 상태 요약
28. `ReportService`, `AnalysisService` 인터페이스 스텁 작성 (구현 없음, 2차 목표 대비)

### Phase 7 — 검증
29. Swagger UI로 전체 흐름 수동 검증: 토큰 발급 → 시세 조회 → 전략 자동 실행 → 주문 → `trades`/`risk_events` 저장 확인
30. (선택) 최소 Web 화면: 거래 기록 테이블, 엔진 상태, Emergency Stop 버튼

---

이 순서대로 진행하면 Phase 0~4 완료 시점에 "수동 주문이 RiskManager를 거쳐 모의투자에 반영되고 기록되는" 상태가 되고, Phase 5~6 완료 시 "전략이 자동으로 주기 실행되며 데이터가 축적되는" MVP 목표가 달성된다.
