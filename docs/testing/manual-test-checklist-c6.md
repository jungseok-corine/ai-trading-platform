# C-6.x 수동 테스트 체크리스트

> 자동 테스트(pytest 2036개, npm build)로 검증 못 하는 **사람/보조 모델의 노가다 테스트** 목록.
> 각 항목은 실행 명령/절차와 기대 결과를 포함한다. 완료하면 체크한다.
> 서버: `http://localhost:8000`, 프론트: Vite dev 또는 빌드본.

## 검증 결과 (2026-07-03)

**API/데이터 계층 전부 통과** + 사용자 UI 확인분:
- ✅ A-1/I 레짐(5m 병용, regime=normal·19심볼) · A-5 Telegram(폰 수신)
- ✅ B-1 제안 백테스트 첨부(#16 verdict=base_better) · B-2 카드 블록(사용자 확인)
- ✅ C-1 AI 피드 · D/H 백테스트+에쿼티곡선(200pt) · E 체결품질(37쌍) · F 안전스트립 · G 적중률(comparable=0 예상대로)

**옵트인 필요 — 라이브 관찰은 기능을 켜야 가능 (로직은 pytest로 검증 완료)**:
- ⏸️ A-2 밴드 마커: `volatility_overrides` 든 전략 버전 + elevated/extreme 레짐 필요
- ⏸️ A-3 soft kill: `VOLATILITY_SOFT_KILL_ENABLED=true` + 재시작 필요

→ A-2/A-3은 C-6.4/6.5 기능을 실제로 켤 때 함께 확인. 그 외 항목은 클리어.

---

## A. C-6.1~6.5 (2026-07-03 오전 머지분)

### A-1. 인트라데이 레짐 — 장중 실데이터 분류
- [ ] **장중(09:00~15:30 KST)에** `curl http://localhost:8000/api/v1/intraday-regime`
- 기대: `regime`이 `unknown`이 아닌 값(calm/normal/elevated/extreme), `symbols_used >= 3`,
  `detail.per_symbol_ratio`에 심볼별 비율.
- 심야/주말엔 unknown이 정상 (최근 2일 1분봉 부족).

### A-2. 파라미터 밴드 — 실전략에서 오버라이드 발동
- [ ] 전략 버전 파라미터에 `"volatility_overrides": {"elevated": {"stop_loss_pct": 1.0}}` 넣은
  새 버전 생성(UI 또는 API) → 장중 elevated/extreme 레짐일 때 러너 실행 후
  `signal_logs.reason`에 `[변동성 레짐 ...]` 마커가 찍히는지 확인.
- SQL: `SELECT reason FROM signal_logs WHERE reason LIKE '%변동성 레짐%' ORDER BY id DESC LIMIT 5;`

### A-3. soft kill — 게이트 켜고 동작 확인 (모의)
- [ ] `.env`에 `VOLATILITY_SOFT_KILL_ENABLED=true` + 백엔드 재시작.
- [ ] extreme 레짐 상황(또는 임계 낮춰 강제: `INTRADAY_REGIME_EXTREME_RATIO=0.1`)에서
  자동매매 전략의 BUY가 risk_events에 `volatility_soft_kill` reject로 기록되는지.
- [ ] SELL은 차단되지 않는지.
- 확인 후 **게이트 원복**(false) + 재시작.

### A-4. UI 4뷰 재편
- [ ] 연구 탭: 4그룹(홈/승인함/전략 성적표/운영(고급)) 표시, 그룹 클릭 시 첫 섹션 자동 선택.
- [ ] 홈 그룹: 오늘 요약/안전 점검/포트폴리오 전환 정상.
- [ ] 액션 인박스에서 항목 클릭 시 해당 섹션+그룹으로 함께 이동하는지.
- [ ] 모바일 폭에서 2단 내비 줄바꿈 깨짐 없는지.

### A-5. Telegram (사용자가 키 연결 후)
- [ ] `.env`: `NOTIFICATION_PROVIDER=telegram`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
  `NOTIFICATION_EVENTS_ENABLED=true` + 재시작.
- [ ] `POST /api/v1/operations-digest/notify?only_if_alerts=false` (다이제스트 강제 전송)로
  채널 연결 확인 — 응답 `notification.sent=true` + 폰 수신.
- [ ] daily_analysis run-now로 제안이 생성되면 "AI 제안 검토 요청" 메시지가 폰에 오는지.

## B. C-6.1b 제안-백테스트 자동 연결

### B-1. 실제 제안 생성 시 자동 첨부
- [ ] `curl -X POST http://localhost:8000/api/v1/autonomous-jobs/daily_analysis/run` (LLM 비용 발생 주의)
  또는 전략 자동 점검: `.../strategy_review/run`
- [ ] 새 pending 제안 조회: `GET /api/v1/strategy-proposals?status=pending` →
  `backtest_summary`에 base/proposed 지표 + verdict 존재 (단일 종목 전략 대상일 때).
- [ ] 유니버스 전략 제안이면 `skipped: "유니버스/무심볼..."`이 정상.

### B-2. 제안 카드 UI
- [ ] 승인함 → AI 전략 제안 → 제안 카드에 "백테스트 비교" 블록:
  verdict 배지 색상(우세=초록/열세=빨강/보류=노랑/표본부족=회색), base vs proposed 표.
- [ ] "참고용, 판정과 승인은 사람" 문구 확인.
- [ ] backtest_summary가 NULL인 옛 제안에서 블록이 아예 안 보이는지 (에러 없이).

### B-3. 성능 체감
- [ ] 제안 생성 API 응답이 백테스트 첨부로 심하게 느려지지 않았는지 (수 초 이내).
  느리면 `.env`에 `PROPOSAL_BACKTEST_DAYS`를 7로 낮춰 재확인.

## C. C-6.7 AI 의사결정 피드

### C-1. 피드 데이터 정합
- [ ] `curl "http://localhost:8000/api/v1/ai-activity-feed?days=3"` →
  최근 분석 실행·제안 생성·승인/거절 이벤트가 시간 역순으로 나오는지.
- [ ] 어제 승인한 제안 #13~15가 `proposal_approved` 이벤트로 보이는지 (days=3 이상).

### C-2. 피드 UI
- [ ] 연구 탭 → 홈 그룹 → "AI 피드" 섹션: 배지 색상(분석=파랑/제안=보라/승인=초록/거절=빨강),
  1일/3일/7일 전환 동작.
- [ ] 이벤트 없을 때 "기록된 AI 활동이 없습니다" 표시.

## D. C-6.8 백테스트 콘솔 UI

- [ ] 전략 성적표 그룹 → "백테스트" 섹션: 기본값(005930, MA cross, 1m, 14일)으로 실행 →
  결과 지표 표 + 최근 실행 목록 갱신.
- [ ] 잘못된 JSON 파라미터 입력 시 에러 문구, 실행 안 됨.
- [ ] 데이터 없는 종목(예: 999999) 실행 → "실패: 캔들 부족" 표시 (앱 크래시 없음).
- [ ] 5m/1d 분봉 실행 정상.

## E. C-6.9 체결 품질 (슬리피지)

- [ ] `curl "http://localhost:8000/api/v1/execution-quality?days=30"` →
  기존 자동매매 체결 쌍이 집계되는지 (pair_count > 0이면 aggregate 값 확인).
- [ ] 전략 성적표 그룹 → "체결 품질" 섹션: 전체/매수/매도 표 + 가장 불리했던 체결 목록.
- [ ] 체결 쌍이 없으면 "신호-체결 쌍이 없습니다" 안내 (에러 없음).
- [ ] 슬리피지 부호 검증: 아무 체결 하나 골라 신호가·체결가로 수동 계산해 표 값과 대조.

## F. C-6.12 전역 안전 스트립

- [ ] 모든 탭 상단 내비 우측에 🟢 스트립: "실거래 OFF · 자동매매 버전 N · 매매가드 일시정지/가동".
- [ ] 안전 점검 섹션과 값 일치 확인.
- [ ] (선택) `.env`로 위반 상황을 만들지 말 것 — 대신 warnings가 있을 때 "경고 N건" 노출만 확인.
- [ ] 모바일 폭에서 아이콘만 남는지.

## G. C-6.13 백테스트 예측 적중률

- [ ] `curl "http://localhost:8000/api/v1/proposal-retrospective/backtest-accuracy"` →
  현재는 comparable=0이 정상 (백테스트 첨부 제안이 승인·회고까지 가려면 며칠 필요).
- [ ] 며칠 뒤 재확인: comparable > 0이면 hit_rate로 백테스트 엔진 신뢰도 판단 시작.

## H. C-6.14 백테스트 에쿼티 곡선

- [ ] 백테스트 콘솔에서 실행 → 결과 아래 에쿼티 곡선 SVG (상승=초록/하락=빨강, 점선=초기 자본).
- [ ] 긴 기간(90일 5m)에서도 곡선이 200포인트로 다운샘플되어 즉시 렌더링.

## I. C-6.15 레짐 5m 병용

- [ ] 백엔드 재시작 후 **장중에** `curl http://localhost:8000/api/v1/intraday-regime` →
  `regime`이 unknown이 아니고 `symbols_used >= 3`, `detail.per_symbol_timeframe`에 5m 심볼 포함.
- [ ] A-1 항목 재검증 (이전에 unknown이었다면 이 수정으로 해소됐는지).

## J. C-6.16 Paper 승인 게이트 통합

- [ ] 운영(고급) → 후보 종목 → 전략 제안 패널: PENDING 제안에 "승인 + 실험 준비"(파랑) /
  "승인만" / "제안 거절" 3버튼 확인.
- [ ] "승인 + 실험 준비" 클릭 → 한 번에 준비된 실험 카드(DRAFT + 실행 전) 표시.
- [ ] DB 검증: 해당 제안 experiment_id NOT NULL + suggested_parameters._paper_testing_ready_at 존재
  + 연결 버전 status='draft' + auto_trade_enabled=false.
- [ ] "승인만" 클릭 → 기존처럼 "Paper 실험 준비" 개별 버튼 경로 유지 (하위호환).

## K. C-6.19 전략 분류 요약

- [ ] 전략 관리 탭 상단 "전략 분류 요약" 표: 살아있는 전략 6개만 기본 표시,
  "아카이브 전략 7개 보기" 토글 동작.
- [ ] 배지: 🟢 신호 발생 중 / 💤 휴면 / 📦 아카이브 / 🤖 자동매매 구분.
- [ ] 행 클릭 시 아래 버전 목록이 해당 전략으로 전환.
