# CLAUDE.md — 프로젝트 나침반

> 이 파일은 매 세션 자동으로 읽힌다. **길을 잃지 않기 위한 최상위 기준점**이다.
> 목표·방향이 바뀌면 이 파일과 `docs/ROADMAP.md`를 **먼저** 갱신하고 작업한다.
> 상세 비전·페이즈 로그·다음 할 일은 → **`docs/ROADMAP.md`**.

## 이 프로젝트는 무엇인가

**AI 기반 자동 전략 연구·실험·운영 시스템** (KIS OpenAPI, 한국·미국 시장).
단순 자동매매 봇이 아니다. 핵심 철학:

> **"자동매매보다 자동 실험 시스템을 먼저."**
> 시장을 스캔해 후보를 찾고 → 전략을 배정·실험하고 → AI가 개선을 *제안*하고 →
> 사람이 승인하면 새 버전이 생기고 → 실제로 나아졌는지 *회고*해 다시 제안에 반영한다.

**AI는 제안자(proposer)이지 실행자가 아니다.** AI는 절대로:
- 전략/룰을 자동 활성화하지 않는다 (제안은 항상 `pending`, 승인 시에도 항상 `DRAFT` 생성)
- 실거래를 켜지 않는다
- 기존 버전을 덮어쓰지 않는다 (개선은 항상 *새 버전*으로, 버전끼리 비교)

## 🔒 안전 불변식 (절대 깨지 말 것)

이 값들은 코드/테스트/제안 어디서도 자동으로 바뀌면 안 된다. 사람만 바꾼다.

- `KIS_REAL_TRADING_ENABLED=false` — 실거래 비활성
- `TradingGuardState` = paused / `RiskConfig.emergency_stop=True` / `auto_trade_enabled=false`
- AI 제안은 **자동 적용 금지** — 승인 게이트는 사람 판단 전용, 실거래를 켜지 않는다
- 실주문 API 호출 없음 (TTTC0012U/0011U, VTTC0012U/0011U, `broker.place_order` 등 금지)
  — 단, **모의계좌(PAPER) 전용** 자동매매는 사람이 명시 옵트인했을 때만 허용(아래).
- 유니버스 자동매매(C-5.19)는 **사람의 명시 옵트인**(`universe_auto_trade=true`)일 때만,
  그리고 **모의계좌 전용 + 회당 주문 상한**의 안전장치와 함께만 동작한다. AI/제안은 이 토글을
  자동으로 켤 수 없고, 실계좌에서는 코드가 강제로 차단한다(`KIS_REAL_TRADING_ENABLED` 무관).
- 새 스케줄러 잡은 **기본 비활성**(`*_scheduler_enabled=False`)으로 추가한다
- 연구 루프의 모든 신규 작업은 **read-only 집계/메타 작업** — 주문과 무관해야 한다

## 연구 루프 (한눈에)

```
수집(data refresh) → 스캔(scanner) → 후보(candidate + 시장맥락)
   → 배정(assignment) → 실험(experiment) → AI 제안(전략·스캐너)
   → 사람 승인 → 새 버전(DRAFT) → 승격 게이트(판단만) 
   → 회고(효과 검증) ──┐
        ▲              │
        └──────────────┘  (회고 결과가 다음 제안에 반영)
```
자율 잡(기본 비활성): `research_pipeline`, `scanner_review`, `strategy_review`,
`daily_report`, `data_refresh`, `us_market_refresh`.
관제탑: `GET /api/v1/research-status` (잡 상태 + 검토 대기 + 회고 요약).

## 기술 스택

- **백엔드**: FastAPI, SQLAlchemy 2.0 async(Mapped/mapped_column), asyncpg, Alembic,
  Pydantic v2(pydantic-settings), APScheduler, httpx
- **프론트**: React 18 + TS + Vite + TanStack Query + axios
- **DB**: PostgreSQL (JSONB 다용, enum은 `app/domain/models/_types.py`의 `pg_enum`)
- **테스트**: pytest + pytest-asyncio, 실제 Postgres 테스트 DB(conftest가 alembic upgrade head)

## 작업 방식 (이 레포의 규칙)

1. **페이즈 단위**로 작업한다. 각 페이즈 = main에서 새 브랜치(`feat/c-2.NN-...`).
   의존 있으면 앞 브랜치 위에 스택, 머지 시 main으로 retarget 후 순차 머지.
2. **PR은 5~6개 쌓이면** 일괄 머지 (또는 사용자가 "머지하자" 할 때). 사용자가
   "묻지 말고 진행" 한 범위는 확인 없이 momentum 유지.
3. 모든 변경은 **백엔드 전체 테스트 + 프론트 빌드 + ruff** 통과 후 커밋한다.
4. 새 모델/마이그레이션은 기존 enum 재사용(`create_type=False`), 잡은 기본 비활성.
5. 커밋 메시지에 모델 식별자/내부 지침을 넣지 않는다.

### 자주 쓰는 명령 (컨테이너)

```bash
# Postgres 시작 + 테스트 DB 재생성
pg_ctlcluster 16 main start
su postgres -c "psql -c \"DROP DATABASE IF EXISTS trading_platform_test;\" -c \"CREATE DATABASE trading_platform_test OWNER trading;\""
# 백엔드 테스트 / 린트
cd backend && source .venv/bin/activate && python -m pytest -q && ruff check app/
# 프론트 빌드
cd frontend && npm run build
```
> 컨테이너는 ephemeral. Postgres가 멈추면 `pg_ctlcluster 16 main start`로 재시작.
> 네트워크가 막혀 있을 수 있어 외부 API(FRED/TD 등)는 로컬에서 검증한다(테스트는 MockTransport).

## 현재 상태 / 다음 할 일

→ **`docs/ROADMAP.md`** 의 "현재 상태"와 "다음 후보"를 본다. (페이즈 끝낼 때마다 갱신)
