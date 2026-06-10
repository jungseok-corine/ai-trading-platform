# AI Trading Platform — Backend

KIS Open API 기반 AI 주식 자동매매 연구 플랫폼의 백엔드. 현재까지 진행 상태:

- **Phase 0 (프로젝트 기반)**: FastAPI 서버 + PostgreSQL 연결 + Alembic 마이그레이션 환경
- **Phase 1 (KIS 모의투자 연동)**: KISPaperBrokerClient — 접근토큰 발급/캐싱/자동갱신, 현재가/분봉/계좌 조회 API

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
│   ├── main.py            # FastAPI 앱 진입점, BrokerClient 라이프사이클
│   ├── core/
│   │   ├── config.py       # 환경설정 (pydantic-settings, KIS 설정 포함)
│   │   └── logging.py      # 로깅 설정
│   ├── db/
│   │   └── session.py      # SQLAlchemy async engine/session, Base
│   ├── api/
│   │   ├── deps.py          # BrokerClient 의존성 주입
│   │   └── v1/
│   │       ├── market.py    # 현재가/분봉 조회 API
│   │       └── account.py   # 계좌 조회 API
│   └── trading/
│       └── broker/
│           ├── base.py       # BrokerClient 추상 인터페이스
│           ├── kis_client.py # KIS 공통 클라이언트 (토큰 발급/캐싱/갱신)
│           ├── kis_paper.py  # KISPaperBrokerClient (VTS)
│           ├── schemas.py    # 응답 스키마 (PriceQuote, MinuteCandle, AccountBalance...)
│           └── exceptions.py # KISAPIError
├── alembic/               # DB 마이그레이션
├── docker-compose.yml     # PostgreSQL
├── .env.example
└── pyproject.toml
```

## 현재 범위

- **Phase 0**: FastAPI 스켈레톤 + health check, PostgreSQL 연결 (async SQLAlchemy), Alembic 마이그레이션 환경
- **Phase 1**: `KISPaperBrokerClient` (모의투자 VTS) — 접근토큰 발급/파일 캐싱/자동 갱신, 현재가·분봉·계좌 조회. DB 저장은 아직 하지 않음 (조회 전용)

주문 실행, RiskManager, Strategy, DB 저장 등은 이후 Phase에서 추가된다. 자세한 내용은 `../docs/mvp-plan.md` 참고.

## KIS 계정 연결 전 준비사항

1. [KIS Developers 포털](https://apiportal.koreainvestment.com)에서 회원가입 후 **모의투자(VTS) 앱키/앱시크리트** 발급
   - 실전투자 앱키와 모의투자 앱키는 별개이므로 반드시 모의투자용으로 발급
2. 한국투자증권 HTS/MTS에서 **모의투자 계좌 개설** (계좌번호 형식: `12345678-01`)
3. 발급받은 정보를 `.env`에 입력
   - `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`
4. 접근토큰 발급은 빈번하게 호출 시 KIS 측에서 제한될 수 있으므로, 앱을 재시작해도 `backend/.cache/kis_token.json`에 캐싱된 토큰이 재사용됨을 확인
5. 모의투자는 실제 장 운영시간(평일 09:00~15:30)에만 시세/체결 데이터가 정상적으로 채워짐 — 장 마감 후에는 분봉 조회 결과가 비어있을 수 있음
