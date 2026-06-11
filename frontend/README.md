# AI Trading Platform — Web Dashboard (MVP)

자동매매 시스템의 현재 상태(엔진 상태, Signal/Trade/Position, Risk Config)를 한눈에 확인하고
주요 작업(Run Once, Sync Orders, Emergency Stop)을 수동으로 실행할 수 있는 최소 기능 대시보드.

자동매매 로직은 포함하지 않으며, 백엔드 API를 호출/표시하는 클라이언트 역할만 한다.

## 기술 스택

- React + TypeScript + Vite
- TanStack Query (서버 상태 조회/캐싱/뮤테이션)
- 별도 UI 라이브러리/차트 라이브러리 없음 (기본 CSS)

## 사전 준비

- Node.js 18+ (개발 환경: Node 24, npm 11)
- 백엔드 서버가 `http://127.0.0.1:8000`에서 실행 중이어야 한다 (`backend/README.md` 참고)
  - PostgreSQL 실행: `cd backend && docker compose up -d`
  - 마이그레이션: `.venv/bin/alembic upgrade head`
  - 서버 실행: `.venv/bin/uvicorn app.main:app --reload`

## 실행 방법

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 http://localhost:5173 접속.

기본적으로 백엔드 API는 `http://127.0.0.1:8000/api/v1`을 호출한다. 다른 주소를 사용하려면
`frontend/.env`에 다음을 설정한다.

```
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

## 화면 구성

- **Engine Status**: scheduler 실행 여부, 등록된 작업, 마지막 실행/에러 시각, 활성 전략 수
- **Actions**: `Run Once`(전략 1회 실행), `Sync Orders`(주문 체결 동기화), 새로고침
- **Positions**: 계좌-종목별 보유 수량/평단가/실현·미실현 손익/현재가
- **Trades**: 거래 내역 (체결 상태, 브로커 주문번호, 포지션 반영 수량 포함)
- **Signals**: 생성된 매매 시그널 (이동평균 교차 등)
- **Risk Controls**: 계좌별 Risk Config 조회 + Emergency Stop On/Off

## 빌드

```bash
npm run build
```

`dist/`에 정적 파일이 생성된다 (Docker Compose 통합은 이후 단계에서 진행).

## 백엔드 CORS

`backend/app/main.py`에 `http://localhost:5173` origin을 허용하는 CORS 미들웨어가 설정되어 있다.
다른 포트/도메인에서 프론트엔드를 실행하려면 백엔드의 `allow_origins` 설정을 함께 수정해야 한다.
