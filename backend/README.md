# AI Trading Platform — Backend

KIS Open API 기반 AI 주식 자동매매 연구 플랫폼의 백엔드. 현재까지 진행 상태:

- **Phase 0 (프로젝트 기반)**: FastAPI 서버 + PostgreSQL 연결 + Alembic 마이그레이션 환경
- **Phase 1 (KIS 모의투자 연동)**: KISPaperBrokerClient — 접근토큰 발급/캐싱/자동갱신, 현재가/분봉/계좌 조회 API
- **Phase 2 (핵심 도메인 모델 + DB 마이그레이션)**: accounts, strategies, strategy_versions, trades, market_data, risk_configs, risk_events 테이블 및 기본 CRUD Repository
- **Phase 3 (Risk Management Layer)**: RiskContext/RiskContextBuilder, 6개 RiskRule, RiskManager, risk_events 기록, Risk Config API
- **Phase 4 (주문 실행 - 모의투자)**: BrokerClient.place_order(), KIS VTS 매수/매도 주문(지정가) 연동, TradeService(Signal 변환 → RiskManager 검증 → 주문 실행 → trades 저장), 수동 주문 API (`POST /api/v1/orders`, `GET /api/v1/trades`, `GET /api/v1/trades/{id}`)
- **Phase 5A (Strategy Engine MVP)**: Strategy 인터페이스 + MovingAverageCrossStrategy(이동평균 골든/데드크로스), MarketDataService(분봉 조회 + SMA 계산), SignalService(Signal 생성 → signal_logs 저장), Signal 조회 API (`POST /api/v1/signals/generate`, `GET /api/v1/signals`, `GET /api/v1/signals/{id}`). 아직 자동 주문/스케줄러는 없음
- **Phase 5B (APScheduler 기반 자동 Signal 생성)**: FastAPI lifespan에서 `AsyncIOScheduler` 시작/종료, `StrategyRunnerService`(활성 strategy_versions 주기 실행 → MovingAverageCrossStrategy → signal_logs 저장), candle_ts 기반 중복 Signal 방지, Engine 상태/수동 실행 API (`GET /api/v1/engine/status`, `POST /api/v1/engine/run-once`). 자동 주문은 여전히 없음 (signal_logs 저장까지만)

## 요구 사항

- Python 3.12
- Docker / Docker Compose (PostgreSQL 실행용)

## 로컬 실행 방법

### 1. 가상환경 생성 및 의존성 설치

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
```

필요 시 `.env` 값을 수정한다 (DB 기본값은 docker-compose 설정과 일치).

KIS Open API를 사용하려면 [KIS Developers 포털](https://apiportal.koreainvestment.com)에서 **모의투자(VTS)** 앱키/앱시크리트를 발급받아 `.env`의 `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`(모의투자 계좌번호, `12345678-01` 형식)를 채운다. 자세한 사전 준비사항은 본 문서 하단의 "KIS 계정 연결 전 준비사항" 참고.

### 3. PostgreSQL 실행

```bash
docker compose up -d
```

### 4. DB 마이그레이션

```bash
alembic upgrade head
```

### 5. 서버 실행

```bash
uvicorn app.main:app --reload
```

서버 실행 후:

- Swagger UI: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

### KIS API 테스트 (Swagger)

`/docs`에서 다음 엔드포인트를 호출해본다 (모두 KIS 모의투자 VTS 서버를 호출):

- `GET /api/v1/market/price/{symbol_code}` — 현재가 조회 (예: `005930` 삼성전자)
- `GET /api/v1/market/candles/{symbol_code}` — 당일 분봉 조회
- `GET /api/v1/account` — 모의투자 계좌 잔고/보유종목 조회
- `POST /api/v1/orders` — 수동 주문 (RiskManager 검증 → 승인 시 KIS VTS 주문 실행)
- `GET /api/v1/trades`, `GET /api/v1/trades/{trade_id}` — 주문/거래 내역 조회
- `POST /api/v1/signals/generate` — MovingAverageCrossStrategy로 Signal 생성 시도 (교차 없으면 `null`)
- `GET /api/v1/signals`, `GET /api/v1/signals/{signal_id}` — 생성된 Signal 로그 조회
- `GET /api/v1/engine/status` — 스케줄러 상태(실행 여부/등록된 작업/마지막 실행 시각/에러/활성 전략 수) 조회
- `POST /api/v1/engine/run-once` — 활성 전략을 즉시 1회 실행 (테스트용, 자동 주문 없음)

최초 호출 시 접근토큰을 발급받아 `backend/.cache/kis_token.json`에 캐싱하고, 이후 만료 5분 전까지는 캐시된 토큰을 재사용한다.

## DB 마이그레이션 명령어

```bash
# 모델 변경 후 마이그레이션 파일 자동 생성
alembic revision --autogenerate -m "설명"

# 마이그레이션 적용
alembic upgrade head

# 한 단계 롤백
alembic downgrade -1
```

## 프로젝트 구조

```
backend/
├── app/
│   ├── main.py            # FastAPI 앱 진입점, BrokerClient/Scheduler 라이프사이클
│   ├── core/
│   │   ├── config.py       # 환경설정 (pydantic-settings, KIS 설정, 스케줄러 설정 포함)
│   │   └── logging.py      # 로깅 설정
│   ├── db/
│   │   └── session.py      # SQLAlchemy async engine/session, Base
│   ├── domain/
│   │   ├── models/          # SQLAlchemy 모델 (accounts, strategies, trades, market_data, risk...)
│   │   └── repositories/     # 기본 CRUD Repository
│   ├── scheduler/
│   │   ├── lifecycle.py    # AsyncIOScheduler 시작/종료
│   │   └── jobs.py         # 주기 실행 작업 (StrategyRunnerService 호출)
│   ├── services/
│   │   ├── risk_service.py        # RiskContext 생성 + RiskManager 판정 + risk_events 기록
│   │   ├── trade_service.py       # Signal 변환 → RiskManager 검증 → 주문 실행 → trades 저장
│   │   ├── market_data_service.py # 분봉 조회 + SMA 계산 (Strategy가 사용)
│   │   ├── signal_service.py      # Strategy 실행 → Signal 생성 → signal_logs 저장 (중복 방지 포함)
│   │   └── strategy_runner_service.py # 활성 strategy_versions 조회 → 전략 실행 → SignalService 위임
│   ├── api/
│   │   ├── deps.py          # BrokerClient 의존성 주입
│   │   └── v1/
│   │       ├── market.py    # 현재가/분봉 조회 API
│   │       ├── account.py   # 계좌 조회 API
│   │       ├── risk_config.py # Risk Config 조회/수정/비상정지 API
│   │       ├── orders.py    # 수동 주문 API (POST /orders, GET /trades)
│   │       ├── signals.py   # Signal 생성/조회 API (POST /signals/generate, GET /signals)
│   │       └── engine.py    # Engine 상태/수동 실행 API (GET /engine/status, POST /engine/run-once)
│   └── trading/
│       ├── broker/
│       │   ├── base.py       # BrokerClient 추상 인터페이스 (place_order 포함)
│       │   ├── kis_client.py # KIS 공통 클라이언트 (토큰 발급/캐싱/갱신, GET/POST 요청)
│       │   ├── kis_paper.py  # KISPaperBrokerClient (VTS) — 시세/계좌/주문
│       │   ├── schemas.py    # 응답 스키마 (PriceQuote, MinuteCandle, AccountBalance, OrderRequest/Result...)
│       │   └── exceptions.py # KISAPIError
│       ├── order/
│       │   └── schemas.py    # 주문 API 요청/응답 스키마 (OrderCreateRequest, TradeRead, OrderResponse)
│       ├── strategy/
│       │   ├── base.py                  # Strategy 인터페이스, Signal dataclass
│       │   ├── indicators.py            # calculate_sma 등 지표 계산 함수
│       │   ├── moving_average_cross.py  # MovingAverageCrossStrategy (골든/데드크로스)
│       │   └── schemas.py               # Signal API 요청/응답 스키마 (SignalLogRead 등)
│       └── risk/
│           ├── context.py    # RiskContext, RiskContextBuilder
│           ├── rules.py       # RiskRule 인터페이스 + 6개 규칙
│           ├── manager.py     # RiskManager
│           └── schemas.py     # Risk Config API 요청/응답 스키마
├── tests/                 # pytest (RiskManager/TradeService/Strategy 단위 테스트 + 통합 테스트)
├── alembic/               # DB 마이그레이션
├── docker-compose.yml     # PostgreSQL
├── .env.example
└── pyproject.toml
```

## 현재 범위

- **Phase 0**: FastAPI 스켈레톤 + health check, PostgreSQL 연결 (async SQLAlchemy), Alembic 마이그레이션 환경
- **Phase 1**: `KISPaperBrokerClient` (모의투자 VTS) — 접근토큰 발급/파일 캐싱/자동 갱신, 현재가·분봉·계좌 조회. DB 저장은 아직 하지 않음 (조회 전용)
- **Phase 2**: 핵심 도메인 모델(accounts, strategies, strategy_versions, trades, market_data, risk_configs, risk_events) + Alembic 마이그레이션 + 기본 CRUD Repository
- **Phase 3**: Risk Management Layer — `RiskContextBuilder`, 6개 `RiskRule`, `RiskManager.validate()`, `risk_events` 기록, Risk Config API. 주문 실행/TradingEngine/Strategy 로직은 아직 없음
- **Phase 4**: 주문 실행(모의투자) — `BrokerClient.place_order()` (KIS VTS 매수/매도, 지정가), `TradeService` (Signal 변환 → RiskManager 검증 → 승인 시 KIS 주문 → trades 저장 / 거부 시 risk_events에만 기록), 수동 주문 API. TradingEngine/Strategy 자동 실행 로직은 아직 없음
- **Phase 5A**: Strategy Engine MVP — `Strategy` 인터페이스, `MovingAverageCrossStrategy`(SMA 5/20 골든·데드크로스), `MarketDataService`(분봉 조회 + SMA 계산), `SignalService`(Signal 생성 → `signal_logs` 저장), Signal 조회 API. 자동 주문/스케줄러(APScheduler)/TradingEngine은 아직 없음
- **Phase 5B**: APScheduler 기반 자동 Signal 생성 — FastAPI lifespan에서 `AsyncIOScheduler` 시작/종료, `StrategyRunnerService`가 활성(`active`/`testing`) `strategy_versions`을 주기적으로 실행해 `signal_logs`에 저장, `candle_ts` 기준 중복 Signal 방지(앱 레벨 체크 + DB unique 제약), `GET /api/v1/engine/status`/`POST /api/v1/engine/run-once`. 자동 주문(RiskManager/TradeService 연결)은 아직 없음

TradingEngine 자동 주문 연결, 포지션/체결 동기화 등은 이후 Phase에서 추가된다. 자세한 내용은 `../docs/mvp-plan.md`, `../docs/risk-management.md` 참고.

## 테스트 실행

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_risk_rules.py`는 DB 없이 RiskManager/RiskRule 판정 로직만 검증하고, `tests/test_risk_service.py`는 실제 PostgreSQL에 대해 risk_events 기록까지 검증한다 (각 테스트는 트랜잭션 롤백으로 격리되어 DB에 흔적을 남기지 않음). PostgreSQL이 실행 중이어야 한다 (`docker compose up -d`).

## KIS 계정 연결 전 준비사항

1. [KIS Developers 포털](https://apiportal.koreainvestment.com)에서 회원가입 후 **모의투자(VTS) 앱키/앱시크리트** 발급
   - 실전투자 앱키와 모의투자 앱키는 별개이므로 반드시 모의투자용으로 발급
2. 한국투자증권 HTS/MTS에서 **모의투자 계좌 개설** (계좌번호 형식: `12345678-01`)
3. 발급받은 정보를 `.env`에 입력
   - `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`
4. 접근토큰 발급은 빈번하게 호출 시 KIS 측에서 제한될 수 있으므로, 앱을 재시작해도 `backend/.cache/kis_token.json`에 캐싱된 토큰이 재사용됨을 확인
5. 모의투자는 실제 장 운영시간(평일 09:00~15:30)에만 시세/체결 데이터가 정상적으로 채워짐 — 장 마감 후에는 분봉 조회 결과가 비어있을 수 있음
