# Revised Architecture (MVP 기준)

이 문서는 최초 아키텍처 제안을 아래 방향으로 수정한 버전이다.

- MVP 범위 축소 (Paper Trading 자동매매 + 데이터 수집 우선)
- TimescaleDB 도입 보류 → PostgreSQL 단독, 단 `market_data` 스키마는 향후 hypertable 전환 가능하게 유지
- Celery 도입 보류 → FastAPI BackgroundTask + APScheduler, 서비스 계층으로 실행 방식과 로직 분리
- Risk Management Layer를 TradingEngine 앞단에 별도 모듈로 신설
- TradingEngine / BrokerClient의 Paper-Live 분리 구조는 처음부터 유지

---

## 1. 시스템 아키텍처

```
┌───────────────────────────────────────────────┐
│        Clients (Swagger UI / 최소 Web)          │
└────────────────────┬────────────────────────────┘
                     │ REST (WebSocket은 추후)
┌────────────────────▼────────────────────────────┐
│                 FastAPI App                       │
│  /market  /account  /orders  /trades              │
│  /strategies  /engine  /risk-config                │
└────────────────────┬────────────────────────────┘
                     │
   ┌─────────────────┼───────────────────────────┐
   ▼                 ▼                           ▼
┌──────────┐  ┌──────────────┐         ┌──────────────────┐
│ Strategy  │  │ RiskManager   │         │ Service Layer     │
│ (Signal   │─▶│ (주문 검증)    │         │ - StrategyService │
│  생성)    │  └──────┬───────┘         │ - TradeService    │
└──────────┘         │ approved        │ - ReportService*  │
                      ▼                  │ - AnalysisService*│
              ┌────────────────┐         │ (* 추후 AI/배치용  │
              │ TradingEngine   │         │   인터페이스만 정의)│
              │ - PaperTrading  │         └─────────┬─────────┘
              │ - LiveTrading*  │                   │
              └──────┬─────────┘                   │
                     ▼                              │
              ┌────────────────┐                   │
              │ BrokerClient    │                   │
              │ - KISPaper      │                   │
              │ - KISReal*      │                   │
              └──────┬─────────┘                   │
                     ▼                              ▼
              ┌──────────────────────────────────────────┐
              │              PostgreSQL                    │
              │ accounts / strategies / strategy_versions /│
              │ trades / market_data / risk_configs /      │
              │ risk_events                                 │
              └────────────────┬─────────────────────────┘
                               │
              ┌────────────────▼────────────────────────┐
              │     KIS Open API (모의투자 VTS 서버)       │
              └──────────────────────────────────────────┘

APScheduler: 주기적으로 시세 수집 + 전략 평가를 트리거 (추후 Celery로 교체 가능)

* 표시: MVP에서는 인터페이스/스켈레톤만 두고 구현은 2~3차 목표에서 진행
```

**주문 실행 흐름 (가장 중요한 변경)**

```
Strategy.generate_signal()
   → Signal
   → RiskManager.validate(signal, config, context)
        - emergency_stop 확인
        - maxDailyLoss / maxPositionSize / maxOpenPositions
          / maxTradesPerDay / consecutiveLossLimit 검증
   → (approved) TradingEngine.execute_signal(signal)
   → BrokerClient.place_order()  (KISPaperBrokerClient)
   → trades 테이블 저장 + risk_events 기록
```

RiskManager가 거부한 신호는 TradingEngine까지 전달되지 않으며, 거부 사유는 `risk_events`에 반드시 기록한다.

---

## 2. 기술 스택 (수정)

| 영역 | MVP 선택 | 비고 |
|---|---|---|
| 백엔드 | Python 3.12 + FastAPI | 변경 없음 |
| DB | **PostgreSQL 단독** | TimescaleDB는 시세 누적량/성능 이슈 발생 시 도입. `market_data` 테이블은 `(symbol_code, ts)` 복합키 + 인덱스로 설계해 추후 `create_hypertable()` 적용만으로 전환 가능하게 유지 |
| 캐시 | (MVP 보류, 필요 시 Redis) | 실시간 시세는 우선 DB polling/주기적 저장으로 처리. WebSocket·캐시는 2차 목표에서 검토 |
| 백그라운드 작업 | **FastAPI BackgroundTasks + APScheduler** | Celery는 AI 분석/배치 규모가 커지는 시점에 도입. 실행 트리거(스케줄러)와 실제 로직(Service 계층)을 분리해 교체 비용 최소화 |
| ORM/마이그레이션 | SQLAlchemy 2.0 (async) + Alembic | 변경 없음 |
| AI / 백테스트 | 보류 (2차 목표) | `ReportService`, `AnalysisService` 인터페이스만 선 정의 |
| 프론트엔드 | Swagger UI 우선, 최소 Web(선택) | 풀 대시보드는 3차 목표 |

---

## 3. 백엔드 프로젝트 구조 (MVP)

```
backend/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py          # KIS API 키, 모의/실전 모드 스위치, .env
│   │   ├── security.py
│   │   └── logging.py
│   ├── api/v1/
│   │   ├── market.py           # 현재가, 분봉 조회
│   │   ├── account.py          # 모의투자 계좌 조회
│   │   ├── orders.py           # 매수/매도 주문 (수동 테스트용)
│   │   ├── trades.py           # 거래 기록 조회
│   │   ├── strategies.py       # 전략 CRUD/버전
│   │   ├── engine.py           # 엔진 상태, 시작/중지
│   │   └── risk.py             # risk_config 조회/수정, emergency-stop
│   ├── domain/
│   │   ├── models/              # SQLAlchemy ORM
│   │   ├── schemas/              # Pydantic
│   │   └── repositories/
│   ├── trading/
│   │   ├── engine/
│   │   │   ├── base.py          # TradingEngine (ABC)
│   │   │   ├── paper.py         # PaperTradingEngine (구현)
│   │   │   └── live.py          # LiveTradingEngine (스켈레톤)
│   │   ├── broker/
│   │   │   ├── base.py          # BrokerClient (ABC)
│   │   │   ├── kis_paper.py     # KISPaperBrokerClient (구현)
│   │   │   └── kis_real.py      # KISRealBrokerClient (스켈레톤)
│   │   ├── risk/
│   │   │   ├── manager.py       # RiskManager
│   │   │   ├── rules.py         # 개별 RiskRule 구현
│   │   │   └── context.py       # RiskContext 빌더
│   │   └── strategy/
│   │       ├── base.py          # Strategy (ABC)
│   │       └── implementations/
│   │           └── moving_average.py
│   ├── services/
│   │   ├── strategy_service.py  # 전략 실행/평가 로직
│   │   ├── trade_service.py     # 신호→리스크검증→주문→기록 오케스트레이션
│   │   ├── market_data_service.py
│   │   ├── report_service.py    # 인터페이스만 (2차 목표)
│   │   └── analysis_service.py  # 인터페이스만 (2차 목표)
│   ├── scheduler/
│   │   └── jobs.py               # APScheduler: 시세 수집 / 전략 주기 실행
│   └── db/
│       ├── session.py
│       └── migrations/           # alembic
├── tests/
├── docker-compose.yml             # postgres만
└── pyproject.toml
```

---

## 4. 서비스 계층과 실행 방식 분리 (Celery 대비 설계)

원칙: **"무엇을 할지"(서비스 로직)와 "언제/어떻게 실행할지"(실행 방식)를 분리한다.**

```python
# services/strategy_service.py
class StrategyService:
    async def evaluate_and_trade(self, strategy_version_id: int) -> None:
        """시세 조회 → Signal 생성 → RiskManager 검증 → 주문 → 기록"""
        ...

# scheduler/jobs.py  (MVP: APScheduler)
scheduler.add_job(
    strategy_service.evaluate_and_trade,
    trigger="interval", seconds=60,
    args=[active_strategy_version_id],
)
```

추후 Celery로 전환 시:

```python
# tasks/strategy_tasks.py (미래)
@celery_app.task
def evaluate_and_trade_task(strategy_version_id: int):
    asyncio.run(strategy_service.evaluate_and_trade(strategy_version_id))
```

`StrategyService.evaluate_and_trade()` 자체는 변경되지 않고, 호출 주체(스케줄러 vs Celery beat/worker)만 교체된다. `ReportService`, `AnalysisService`도 동일한 패턴으로 — MVP에서는 메서드 시그니처와 책임만 정의해두고, 내부 구현(AI 호출 등)은 2차 목표에서 채운다.

---

## 5. 데이터베이스 설계 (MVP, PostgreSQL 단독)

```sql
-- 계좌 (모의/실전 구분, MVP는 paper만 사용)
accounts (
  id, account_type ENUM('paper','live'),
  broker_account_no, alias, created_at
)

-- 전략 (논리적 단위) / 버전 (변경 이력)
strategies (
  id, name, description, created_at
)

strategy_versions (
  id, strategy_id FK, version_no,
  parameters JSONB,
  change_description,
  effective_from, effective_to,
  win_rate, avg_profit, avg_loss, mdd,
  status ENUM('draft','testing','active','retired'),
  created_at, updated_at
)

-- 거래 기록 (실거래 확장 필드 포함, MVP에서도 컬럼은 미리 보유)
trades (
  id, account_id FK, strategy_version_id FK,
  symbol_code, symbol_name,
  side ENUM('buy','sell'),
  entry_time, exit_time,
  entry_price, exit_price, quantity,
  pnl_amount, pnl_pct,
  entry_reason TEXT, exit_reason TEXT,
  market_condition JSONB,
  ai_analysis_id INT NULL,        -- 2차 목표 전까지는 항상 NULL
  order_status ENUM('pending','filled','partial','cancelled','rejected'),
  broker_order_id,
  partial_fill JSONB,
  commission, tax, slippage,
  created_at
)

-- 시세 데이터 (PostgreSQL 일반 테이블, 추후 hypertable 전환 대비)
market_data (
  symbol_code TEXT,
  ts TIMESTAMPTZ,
  timeframe TEXT,        -- '1m', '1d' 등
  open, high, low, close, volume,
  PRIMARY KEY (symbol_code, timeframe, ts)
)
-- 인덱스: (symbol_code, timeframe, ts DESC)
-- 향후: TimescaleDB 설치 후 SELECT create_hypertable('market_data', 'ts') 만으로 전환

-- 리스크 설정 (계좌 단위)
risk_configs (
  id, account_id FK,
  max_daily_loss_amount NUMERIC,
  max_position_size NUMERIC,
  max_open_positions INT,
  max_trades_per_day INT,
  consecutive_loss_limit INT,
  emergency_stop BOOLEAN DEFAULT FALSE,
  updated_at
)

-- 리스크 검증 로그 (승인/거부 모두 기록)
risk_events (
  id, account_id FK, strategy_version_id FK,
  signal_snapshot JSONB,
  context_snapshot JSONB,
  result ENUM('approved','rejected'),
  rule_name TEXT,
  reason TEXT,
  created_at
)
```

`ai_analysis_reports`, `backtest_runs`, `decision_logs` 테이블은 2차 목표(AI 분석)에서 추가한다. 단, `trades.ai_analysis_id` 컬럼은 미리 만들어두어 마이그레이션 시 컬럼 추가가 아닌 FK 연결만으로 확장 가능하게 한다.

---

## 6. Paper → Live 전환 시 변경 범위

| 구성요소 | MVP (Paper) | Live 전환 시 |
|---|---|---|
| `BrokerClient` | `KISPaperBrokerClient` (VTS 서버) | `KISRealBrokerClient` (실전 서버) — 동일 인터페이스 구현체 추가 |
| `TradingEngine` | `PaperTradingEngine` | `LiveTradingEngine` — 동일 인터페이스, RiskManager 호출 흐름 동일 |
| `RiskManager` | 동일 룰셋, 보수적 기본값 | 룰셋 강화 + 추가 룰(예: 장중 변동성 기반 포지션 축소) 가능, 인터페이스 변경 없음 |
| `accounts.account_type` | `'paper'` | `'live'` 레코드 추가, 코드 분기는 `account_type` 기준 |
| `trades` 스키마 | 동일 (broker_order_id 등 이미 존재) | 컬럼 추가 불필요 |
| Web/API | 동일 | "Live 모드 활성화"는 명시적 사용자 액션 + 별도 confirm 단계 필요 (구현은 3차 목표에서 설계) |

핵심: **인터페이스(ABC)는 MVP에서 확정하고, 구현체만 추가하는 방식**으로 전환 비용을 최소화한다.
