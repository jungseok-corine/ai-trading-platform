# C-6.x 수동 테스트 체크리스트

> 자동 테스트(pytest 2013개, npm build)로 검증 못 하는 **사람/보조 모델의 노가다 테스트** 목록.
> 각 항목은 실행 명령/절차와 기대 결과를 포함한다. 완료하면 체크한다.
> 서버: `http://localhost:8000`, 프론트: Vite dev 또는 빌드본.

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
- [ ] `POST /api/v1/notify` (다이제스트 수동 전송)로 채널 연결 확인.
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
