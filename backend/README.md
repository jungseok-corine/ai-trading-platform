# AI Trading Platform — Backend

KIS Open API 기반 AI 주식 자동매매 연구 플랫폼의 백엔드. 현재는 **Phase 0 (프로젝트 기반)** 단계로, 실행 가능한 FastAPI 서버 + PostgreSQL 연결 + Alembic 마이그레이션 환경만 구성되어 있다.

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

필요 시 `.env` 값을 수정한다 (기본값은 docker-compose 설정과 일치).

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
│   ├── main.py          # FastAPI 앱 진입점
│   ├── core/
│   │   ├── config.py     # 환경설정 (pydantic-settings)
│   │   └── logging.py    # 로깅 설정
│   └── db/
│       └── session.py    # SQLAlchemy async engine/session, Base
├── alembic/               # DB 마이그레이션
├── docker-compose.yml     # PostgreSQL
├── .env.example
└── pyproject.toml
```

## 현재 범위 (Phase 0)

- FastAPI 스켈레톤 + health check
- PostgreSQL 연결 (async SQLAlchemy)
- Alembic 마이그레이션 환경 (모델은 아직 없음)

KIS API 연동, 주문 실행, RiskManager, Strategy 등은 이후 Phase에서 추가된다. 자세한 내용은 `../docs/mvp-plan.md` 참고.
