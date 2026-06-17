# AI Trading Platform

KIS 모의투자(VTS) 기반 자동매매 연구 플랫폼. 전략 신호 생성부터 리스크 검증, 주문 실행, 포지션 추적, 시세 데이터 누적까지 전 흐름을 단일 서버에서 운영한다.

> **주의**: 현재는 KIS 모의투자(VTS/Paper Trading) 환경 전용입니다.
> 실거래(Live Trading) 연동은 구현되어 있지 않으며, 투자 판단 목적으로 사용해서는 안 됩니다.

---

## 목적

- KIS 모의투자 환경에서 이동평균 교차 등 전략을 자동으로 실행하고 그 결과(신호, 주문, 체결, 포지션, 리스크 이벤트)를 DB에 축적한다.
- 데이터 파이프라인이 정상 작동하는지 확인하고, 향후 AI 분석 및 백테스트 기반을 마련한다.
- 전략 성능 자체보다 **파이프라인 전체의 정합성 검증**이 현재 단계의 목표다.

---

## 현재 구현 완료 기능

| 영역 | 상태 |
|------|------|
| KIS OAuth 토큰 발급/캐싱/자동 갱신 | ✅ |
| 현재가 / 분봉 / 계좌 조회 (VTS) | ✅ |
| 전략(Strategy) / 버전(StrategyVersion) 관리 API | ✅ |
| 이동평균 교차 전략 (MovingAverageCrossStrategy) | ✅ |
| Risk Manager (6개 규칙) + risk_events 기록 | ✅ |
| 매매 신호 생성 및 signal_logs 저장 | ✅ |
| 수동 주문 실행 (VTS, 지정가) | ✅ |
| APScheduler 기반 전략 자동 실행 + 주문 체결 동기화 | ✅ |
| auto_trade_enabled 전략 → 자동 주문 실행 | ✅ |
| 포지션 / P&L 추적 (평단가, 실현·미실현 손익) | ✅ |
| Watchlist 종목 관리 + 전략 일괄 생성 | ✅ |
| 스케줄러 실행 이력 (scheduler_runs) | ✅ |
| DB 운영 점검 도구 (maintenance CLI) | ✅ |
| 분봉 데이터 DB 저장 (market_data 테이블 upsert) | ✅ |
| market_data 조회 / summary API | ✅ |
| React 대시보드 (엔진 상태, 신호, 거래, 포지션, 리스크) | ✅ |

## 미구현 / 로드맵

| 항목 | 비고 |
|------|------|
| 실거래(Live Trading) — KIS Real API 연동 | 인터페이스만 정의됨 |
| 신호 성과 분석 (Signal Outcome Analysis) | 다음 Phase |
| 전략 성과 지표 (Win Rate, MDD 등) | 다음 Phase |
| AI 분석 리포트 생성 | 2차 목표 |
| 백테스트 엔진 | 2차 목표 |
| 실시간 차트 / WebSocket 대시보드 | 3차 목표 |
| TimescaleDB 전환 | 데이터 규모 확대 시 |
| iOS 앱 | 장기 목표 |

---

## 아키텍처

```
┌─────────────────────────────────────────────────────┐
│  Frontend (React + TypeScript + Vite)                │
│  └─ TanStack Query → REST API 호출                   │
└────────────────────────┬────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────┐
│  Backend (FastAPI + Python 3.12)                     │
│  ├─ API Layer (v1): market, signals, strategies,     │
│  │   orders, positions, risk_config, engine,         │
│  │   watchlists, market_data                         │
│  ├─ Services: SignalService, TradeService,            │
│  │   RiskService, MarketDataService, …               │
│  ├─ APScheduler: 전략 실행 + 주문 체결 동기화 Job    │
│  └─ Repositories (SQLAlchemy 2.0 async)             │
└──────────┬───────────────────────┬──────────────────┘
           │                       │
┌──────────▼──────────┐  ┌────────▼─────────────────┐
│  PostgreSQL          │  │  KIS Open API (VTS)       │
│  (asyncpg + Alembic) │  │  (모의투자 전용)           │
└─────────────────────┘  └──────────────────────────┘
```

**핵심 기술 스택**

| 계층 | 기술 |
|------|------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), asyncpg |
| DB | PostgreSQL, Alembic (마이그레이션) |
| 스케줄러 | APScheduler 3.x (AsyncIOScheduler) |
| Frontend | React, TypeScript, Vite, TanStack Query |
| 브로커 | KIS Open API (모의투자 VTS) |

---

## 디렉토리 구조

```
ai-trading-platform/
├── backend/                  # FastAPI 서버
│   ├── app/
│   │   ├── main.py           # 앱 진입점, lifespan (Scheduler + BrokerClient)
│   │   ├── api/v1/           # REST API 라우터
│   │   ├── domain/
│   │   │   ├── models/       # SQLAlchemy 모델 (12개 테이블)
│   │   │   └── repositories/ # DB 접근 계층
│   │   ├── services/         # 비즈니스 로직
│   │   ├── scheduler/        # APScheduler 작업
│   │   ├── maintenance/      # 운영 점검 도구
│   │   └── trading/
│   │       ├── broker/       # KIS VTS 클라이언트
│   │       ├── strategy/     # 전략 인터페이스 + MA Cross
│   │       └── risk/         # RiskManager + 6개 규칙
│   ├── alembic/              # DB 마이그레이션
│   ├── tests/                # pytest (210+ 테스트)
│   └── scripts/              # 운영 스크립트
├── frontend/                 # React 대시보드
│   └── src/
│       ├── components/       # 카드형 UI 컴포넌트
│       ├── pages/            # 대시보드 페이지
│       └── api/              # API 클라이언트 함수
├── docs/
│   ├── mvp-plan.md
│   ├── revised-architecture.md
│   └── risk-management.md
└── iOS/                      # iOS 앱 (미구현 예정)
```

---

## 로컬 실행

### 사전 조건

- Python 3.12
- Node.js 18+
- Docker (PostgreSQL 실행용)
- KIS 모의투자 앱키/앱시크리트 ([KIS Developers](https://apiportal.koreainvestment.com)에서 발급)

### Backend

```bash
cd backend

# 1. 가상환경 및 의존성
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .

# 2. 환경 변수
cp .env.example .env
# .env에 KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO 입력

# 3. PostgreSQL 실행
docker compose up -d

# 4. DB 마이그레이션
alembic upgrade head

# 5. 서버 실행
uvicorn app.main:app --reload
# → http://127.0.0.1:8000
# → Swagger: http://127.0.0.1:8000/docs
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

백엔드가 `http://127.0.0.1:8000`에서 실행 중이어야 한다. 주소가 다르면 `frontend/.env`에 `VITE_API_BASE_URL`을 설정한다.

---

## 테스트 실행

```bash
cd backend
source .venv/bin/activate

# 의존성 (dev 포함)
pip install -e ".[dev]"

# PostgreSQL 실행 (test DB는 conftest.py가 자동 생성)
docker compose up -d

# 전체 테스트 실행
pytest

# 특정 파일만
pytest tests/test_market_data_api.py -v
```

- test DB(`trading_platform_test`)는 dev DB(`trading_platform`)와 완전 분리된다.
- 각 테스트는 savepoint 기반 트랜잭션 롤백으로 격리되어 DB에 잔류 데이터를 남기지 않는다.

**Frontend 타입 검사**

```bash
cd frontend
npm run build   # 타입 오류 시 빌드 실패
```

---

## 주요 API 영역

| 경로 | 설명 |
|------|------|
| `GET /api/v1/market/price/{symbol_code}` | 현재가 조회 |
| `GET /api/v1/market/candles/{symbol_code}` | 분봉 조회 |
| `GET /api/v1/account` | 모의투자 계좌 잔고/보유종목 |
| `GET/POST /api/v1/strategies` | 전략 목록/생성 |
| `GET/POST/PATCH /api/v1/strategies/{id}/versions` | 전략 버전 관리 |
| `GET/PATCH /api/v1/risk-config/{account_id}` | Risk Config 조회/수정 |
| `POST /api/v1/risk-config/{account_id}/emergency-stop` | 비상 정지 |
| `POST /api/v1/orders` | 수동 주문 (RiskManager 통과 시 VTS 주문) |
| `GET /api/v1/signals` | 매매 신호 로그 조회 |
| `GET /api/v1/engine/status` | 스케줄러 상태 |
| `POST /api/v1/engine/run-once` | 전략 즉시 1회 실행 |
| `POST /api/v1/engine/sync-orders` | 주문 체결 수동 동기화 |
| `GET /api/v1/positions` | 포지션 / 손익 조회 |
| `GET/POST /api/v1/watchlists` | 종목 관리 |
| `GET /api/v1/market-data/{symbol_code}` | 저장된 캔들 조회 |
| `GET /api/v1/market-data/{symbol_code}/summary` | 종목별 저장 현황 |
| `GET /api/v1/market-data/summary` | 전체 시세 데이터 현황 |

전체 API 명세는 서버 실행 후 `/docs` (Swagger UI) 참고.

---

## 개발 Phase 현황

| Phase | 내용 | 상태 |
|-------|------|------|
| 0 | 프로젝트 기반 (FastAPI + PostgreSQL + Alembic) | ✅ |
| 1 | KIS VTS 연동 (토큰, 시세, 계좌 조회) | ✅ |
| 2 | 핵심 도메인 모델 + 마이그레이션 | ✅ |
| 3 | Risk Management Layer | ✅ |
| 4 | 수동 주문 실행 (VTS) | ✅ |
| 5A | 전략 엔진 MVP (MA Cross + SignalService) | ✅ |
| 5B | APScheduler 기반 자동 신호 생성 | ✅ |
| 5C | Signal → 자동 주문 연결 | ✅ |
| 5D | 주문 체결 동기화 (OrderSyncService) | ✅ |
| 6 | 포지션 / P&L 추적 | ✅ |
| 7 | Web Dashboard MVP | ✅ |
| Alpha | Watchlist, 스케줄러 이력, 운영 도구, 신호 표시 개선 | ✅ |
| B-1 | Market Data DB 저장 (전략 실행 중 분봉 upsert) | ✅ |
| B-2 | Market Data 조회 / summary API | ✅ |
| **다음** | Signal Outcome Analysis, 성과 지표 | 🔜 |
| — | AI 분석 리포트 | 🗓 로드맵 |
| — | 백테스트 엔진 | 🗓 로드맵 |
| — | 실거래(Live Trading) | 🗓 로드맵 |

---

## 운영 주의사항

- 현재 브로커 연동은 **KIS 모의투자(VTS)** 전용입니다. 실계좌로 연결되지 않습니다.
- `auto_trade_enabled=true` 전략은 스케줄러가 골든/데드크로스 신호를 감지하면 자동으로 VTS 주문을 전송합니다. 운영 전 Risk Config(1회 최대 수량, 일일 손실 한도 등)를 반드시 확인하세요.
- 분봉 시세는 **평일 장 운영시간(09:00~15:30 KST)** 에만 정상 수신됩니다. 장 마감 후에는 분봉 응답이 비어 있을 수 있습니다.
- KIS 접근토큰은 `backend/.cache/kis_token.json`에 캐싱되며, 만료 5분 전 자동 갱신됩니다.

---

## 관련 문서

- [Backend 상세 가이드](backend/README.md) — 서버 실행, DB 마이그레이션, KIS 계정 연결 방법
- [Frontend 상세 가이드](frontend/README.md) — 대시보드 실행, 빌드, CORS 설정
- [MVP Plan](docs/mvp-plan.md) — 개발 목표 및 Phase별 Task
- [Architecture](docs/revised-architecture.md) — 아키텍처 설계 결정 사항
- [Risk Management](docs/risk-management.md) — Risk Rule 설계 근거
