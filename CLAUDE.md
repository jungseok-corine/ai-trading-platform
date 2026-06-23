# CLAUDE.md — Claude 작업 규칙서

> 이 파일은 매 세션 자동으로 읽힌다. **작업 시작 전 반드시 이 파일 전체를 읽어라.**
> 길을 잃으면 이 파일로 돌아온다.

---

## 1. 이 프로젝트는 무엇인가

**AI 시장지능 전략 연구소** (KIS OpenAPI, 한국·미국 시장).
단순 자동매매 봇이 아니다. 핵심 철학:

> **"AI가 시장을 분석하고 전략을 실험한다. 사람은 실전 배치를 승인한다."**
>
> 뉴스·공시·수급·가격·거시 데이터 수집 → AI가 후보 종목 발견 →
> 스캐너·전략 자동 생성/수정 → paper에서 자동 실험 → AI가 분석·제안 →
> 사람이 승인 → 실전 배치

자세한 철학·방향은 → **`docs/PROJECT-VISION.md`**

---

## 2. 작업 시작 전 반드시 읽을 문서 목록

```
1. CLAUDE.md              ← 지금 읽는 이 파일 (규칙)
2. docs/NEXT-TASK.md      ← 다음에 무엇을 할지 (최우선)
3. docs/ROADMAP.md        ← 전체 로드맵과 상태
4. docs/PROJECT-VISION.md ← 방향성과 철학 (방향 판단 필요 시)
5. docs/DECISIONS.md      ← 중요 의사결정 기록 (충돌 발생 시)
```

---

## 3. 다음 작업 선택 프로토콜

```
Step 1. docs/NEXT-TASK.md를 읽는다.
         - Status = READY  → 해당 작업을 수행한다.
         - Status = IN_PROGRESS → 중단점부터 이어서 수행한다.
         - Status = DONE / BLOCKED → Step 2로 간다.

Step 2. docs/ROADMAP.md에서 Status = READY인 작업 중
         우선순위가 가장 높은 것을 선택한다.

Step 3. 선택한 작업을 docs/NEXT-TASK.md에 업데이트하고 시작한다.

⛔ 임의로 큰 기능을 만들지 않는다.
⛔ 로드맵에 없는 기능을 추가하지 않는다.
⛔ "이게 더 좋을 것 같아서" 리팩토링을 하지 않는다.
```

---

## 4. 🔒 안전 불변식 (절대 깨지 말 것)

이 값들은 코드·테스트·제안 어디서도 자동으로 바뀌면 안 된다. **사람만 바꾼다.**

| 불변식 | 설명 |
|--------|------|
| `KIS_REAL_TRADING_ENABLED=false` | 실거래 비활성. 코드에서 이 값을 true로 바꾸거나 우회하지 않는다. |
| `TradingGuardState = paused` | 전역 매매 일시정지. 자동 해제 금지. |
| `RiskConfig.emergency_stop = True` | 실계좌 등록 시 강제 설정. 코드에서 false로 바꾸지 않는다. |
| `auto_trade_enabled = False` | AI 제안 승인 시 항상 강제. 코드에서 자동으로 true 설정 금지. |
| 실주문 API 호출 금지 | `TTTC0012U`, `TTTC0011U`, `VTTC0012U`, `VTTC0011U`, `broker.place_order` 호출 금지 |
| 새 스케줄러 잡 기본 비활성 | `*_scheduler_enabled=False`가 기본값. |
| AI 제안 자동 적용 금지 | 제안은 항상 `pending`. 승인해도 항상 `DRAFT + auto_trade=False`. |
| 버전 덮어쓰기 금지 | 개선은 항상 새 버전으로 생성. 기존 버전 수정 금지. |

**유일한 예외**: 모의계좌(PAPER) 자동매매는 사람이 명시 옵트인(`universe_auto_trade=true`)할 때만,
모의계좌 전용 + 회당 주문 상한의 안전장치와 함께만 허용.

---

## 5. Secret / .env 보호 규칙

- `.env`, `token`, `app_key`, `app_secret`, 계좌번호 전체값을 **절대 출력하지 않는다**.
- 환경변수는 값 없이 이름만 언급한다. 예: `FRED_API_KEY=<your_key>`
- `.env` 파일을 커밋하지 않는다. `.env.example`에 키 이름만 명시한다.
- KIS API 키·시크릿이 코드에 하드코딩되지 않는지 확인한다.

---

## 6. 실전 관련 변경 시 반드시 중단하고 확인 요청

아래 항목은 **작업 도중 발견하더라도 즉시 중단하고 사용자에게 확인**을 받아야 한다.

- 실주문 API 호출 로직 추가/변경
- 실계좌 RiskConfig 한도 수정
- `KIS_REAL_TRADING_ENABLED` 관련 코드 변경
- `emergency_stop`, `auto_trade_enabled` 기본값 변경
- 배포 스크립트·CI/CD 파이프라인 변경
- 기존 실거래 관련 마이그레이션 수정

---

## 7. 테스트 규칙

- **모든 코드 변경은 백엔드 전체 테스트 통과 후 커밋한다.**
- 새 기능에는 반드시 테스트를 작성한다.
- 외부 API 테스트는 `httpx.MockTransport`로 격리한다 (네트워크 차단 환경 가정).
- 테스트 DB: 실제 PostgreSQL 사용 (`trading_platform_test`).
- 프론트 변경 시 `npm run build` 통과 확인.

```bash
# Postgres 시작 + 테스트 DB 재생성
pg_ctlcluster 16 main start
su postgres -c "psql -c \"DROP DATABASE IF EXISTS trading_platform_test;\" -c \"CREATE DATABASE trading_platform_test OWNER trading;\""
# 백엔드 테스트
cd backend && source .venv/bin/activate && python -m pytest -q
# 프론트 빌드
cd frontend && npm run build
```

---

## 8. 커밋 규칙

- 커밋 메시지 형식: `type(scope): 설명` (영어)
  - `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- 모델 식별자·내부 지침·세션 정보를 커밋 메시지에 넣지 않는다.
- 커밋 전: 테스트 통과 + 프론트 빌드 통과 확인.
- `.env`, 시크릿, 토큰 파일을 커밋하지 않는다.
- 브랜치: main에서 `feat/c-X.NN-short-description` 형태로 분기.

---

## 9. 완료 보고 형식

작업 완료 시 다음 형식으로 보고한다:

```
## 완료 보고: [작업 ID] [작업명]

### 작업 결과
- 변경된 파일 목록
- 핵심 구현 내용 (2~3줄)

### 테스트
- 실행 결과: N passed / M failed
- 실패 항목: (있으면 설명)

### 안전 검증
- 실거래 코드 변경 없음: ✅ / ⚠️
- 새 스케줄러 잡 기본 비활성: ✅ / 해당 없음

### 다음 단계
- docs/NEXT-TASK.md 업데이트 필요 여부
- 다음 작업 후보
```

---

## 10. 애매할 때 질문해야 하는 조건

다음 상황에서는 **추측해서 진행하지 말고 사용자에게 질문**한다:

- 요구사항이 안전 불변식과 충돌할 때
- 로드맵에 없는 기능 추가가 필요해 보일 때
- DB 스키마 변경이 기존 운영 데이터에 영향을 줄 때
- 외부 서비스(KIS API, DART, EDGAR) 연동 방식이 불명확할 때
- 실계좌·실거래 관련 코드를 건드려야 할 상황이 보일 때

---

## 11. 절대 하면 안 되는 행동

```
❌ 실주문 API(TTTC0012U/0011U, VTTC0012U/0011U) 호출
❌ broker.place_order() 직접 호출
❌ KIS_REAL_TRADING_ENABLED=true 코드/테스트에 설정
❌ AI 제안 자동 적용 (pending → approved 자동 전환)
❌ 기존 StrategyVersion 파라미터 덮어쓰기
❌ .env / 토큰 / 시크릿 값 출력
❌ 로드맵에 없는 대형 기능 임의 추가
❌ 테스트 없이 커밋
❌ 기존 문서 무조건 삭제 (새 문서로 대체하거나 링크 추가)
❌ C-4.1 관련 스크립트 실행 (reset_toy_strategies.py, purge_archived_strategies.py — 실데이터 손실 위험)
```

---

## 12. 기술 스택 요약

- **백엔드**: FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, Pydantic v2, APScheduler, httpx
- **프론트**: React 18 + TypeScript + Vite + TanStack Query + axios
- **DB**: PostgreSQL (JSONB 다용, enum은 `app/domain/models/_types.py`의 `pg_enum`)
- **테스트**: pytest + pytest-asyncio, 실제 Postgres 테스트 DB
- **AI**: Gemini / OpenAI (provider 패턴, `app/services/ai_analysis/`)
- **브로커**: KIS OpenAPI — 국내 모의(`KISPaperBrokerClient`) / 해외 모의(`KISOverseasPaperBrokerClient`) / 국내 실전(`KISRealBrokerClient`, 기본 비활성)

---

## 13. 현재 상태 / 다음 할 일

→ **`docs/NEXT-TASK.md`** 를 먼저 읽는다.
→ 전체 로드맵은 **`docs/ROADMAP.md`**.
→ 방향 판단이 필요하면 **`docs/PROJECT-VISION.md`**.
