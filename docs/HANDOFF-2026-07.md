# HANDOFF — 2026-07-04 (C-6 시대 인수인계)

> **대상**: 2026-07-07 이후 이 프로젝트를 이어받는 AI 모델.
> 2026-07-02~04 사흘간 시스템이 크게 바뀌었다. CLAUDE.md·ROADMAP만으로는 부족한
> 최신 맥락을 이 문서가 채운다. **작업 시작 전 CLAUDE.md → 이 문서 → NEXT-TASK.md 순서로 읽어라.**

---

## 1. 사흘간 무엇이 바뀌었나 (C-6.1~6.21)

목표 재정의: "당일 시장 변동성에 맞춰 자동으로 전략을 조정하는 자동매매" (갭 분석:
`docs/roadmap/C-6-adaptive-trading-plan.md`). 구현된 것:

| 시스템 | 핵심 파일 | 상태 |
|---|---|---|
| 백테스트 엔진 (히스토리컬 리플레이) | `services/backtest_service.py`, `POST /backtests` | 가동 |
| 제안-백테스트 자동 첨부 | `services/proposal_backtest_service.py` → `strategy_proposals.backtest_summary` | 가동 (verdict는 참고용 — 승인은 사람) |
| 인트라데이 변동성 레짐 (1m+5m) | `services/intraday_regime_service.py`, `GET /intraday-regime` | 가동 (60초 캐시, 잡 없음 — 온디맨드) |
| 변동성 파라미터 밴드 | `trading/strategy/volatility_overrides.py` + 러너 | **v333에 실배치** (elevated/extreme 밴드) |
| vol_scaled 사이징 / soft kill 룰 | `trading/pricing/sizing.py`, `trading/risk/rules.py` | 코드 완성, **게이트 off** |
| Telegram 알림 | `services/notifications/events.py` | **가동** (제안 생성·다이제스트 경보 → 폰) |
| 체결 품질(슬리피지) + 다이제스트 경보 | `services/execution_quality_service.py` | 가동 |
| 백테스트 적중률 메타 | `proposal_retrospective_service.backtest_accuracy()` | 데이터 대기 |
| UI 4뷰 재편 + 전략 분류 요약 + 전역 안전 스트립 | `ResearchPage.tsx`, `StrategyOverviewTable.tsx`, `GlobalSafetyStrip.tsx` | 가동 |
| KIS 실시간 웹소켓 (틱→1분봉) | `trading/broker/kis_websocket.py` | 코드 완성, **게이트 off, 라이브 미검증** |
| 스캐너 기근→완화 제안 | `scanner_proposal_generator.loosen_conditions` | 가동 (완화 3벌 배포됨) |

## 2. 🚨 반드시 알아야 할 대형 버그 수정 이력 (재발 감시)

1. **C-6.18 (커밋 43e8a0e)**: KR 시세 경로가 timeframe을 무시하고 항상 1분봉 반환 —
   모든 '5m' 전략이 1분봉 위에서 돌았고 market_data '5m'도 오염됐었다.
   수정: 1m→Nm 리샘플(DB 이력 병합) + timeframe=1d 지원 + 캔들 캐시 키 (symbol, timeframe).
   오염 데이터는 정리됨(25만 행 1m 리라벨, 7만 삭제, US 5m은 원래 정상이라 보존).
2. **C-6.20 (c61fbc2)**: 신선도 가드가 '1d'를 1분으로 취급해 일봉 신호 영구 차단 — 1440분으로 수정.
3. **캔들 계열 버그 패턴**: timeframe 관련 변경 시 항상 "실제 저장된 ts 간격"을 SQL로 확인하라.

## 3. 전략 유효성 결론 (docs/strategy/strategy-effectiveness-analysis.md)

- **분봉 매매는 수수료 드래그로 구조적 마이너스** → 일봉 전환이 방침
- **만능 전략 없음**: breakout=추세 국면 전용(횡보에서 -43%), rsi_reversion(oversold 40)=횡보·하락 방어
  → 다음 큰 과제 = **종목-전략 적합성 매칭 / 레짐 조건부 가동**
- 목표는 "시장 이기기"가 아니라 **"MDD 줄이면서 벌기"**
- 현재 실험 중: v333(MA+밴드), v334(breakout 일봉), v335(rsi 일봉) — 전부 TESTING·신호 전용

## 4. 게이트 현황 (전부 사람이 켠다 — 임의로 켜지 마라)

| 게이트 | 기본 | 현재 |
|---|---|---|
| `KIS_REAL_TRADING_ENABLED` | false | **false (불변식)** |
| `NOTIFICATION_EVENTS_ENABLED` + telegram | false | **true (가동 중)** |
| `VOLATILITY_SOFT_KILL_ENABLED` | false | false |
| `KIS_WS_ENABLED` | false | false (라이브 검증 전) |
| `proposal_backtest_enabled` | true | true (read-only 계산이라 예외적 기본 on) |

## 5. 작업 함정 (선임이 밟은 것들)

- **pytest를 `| tail`로 파이프하면 exit code가 가려져 실패 채로 커밋된다** — 두 번 당했다.
  `pytest -q > /tmp/out.txt 2>&1; tail -1 /tmp/out.txt` 후 결과 확인하고 커밋하라.
- pytest는 `PYTHONPATH=$PWD`(backend에서) 필수. 프론트는 `npm --prefix frontend run build`.
- `docker exec`에 stdin 파이프할 땐 **`-i` 필수** (없으면 조용히 no-op — DB 트랜잭션이 안 들어감).
- zsh는 `set -- $var` 워드 스플리팅이 안 됨 — 루프는 `while read`로.
- DB는 `docker exec backend-db-1 psql -U trading -d trading_platform`. 서버는 사용자가
  `uvicorn --reload`로 직접 띄움 — **.py는 자동 반영, .env는 사용자 재시작 필요. 서버를 임의 재시작하지 마라.**
- 제안 승인(`approve`)은 suggested_parameters를 **그대로** 새 버전으로 만든다 — 부분 제안이 아니라
  완전한 파라미터를 넣어라 (base의 universe 등이 상속되지 않음).
- 사용자와 합의된 위임 수준: paper 영역 실행·수정은 브리핑 후 지시받으면 대행 가능,
  **실전 배치·게이트 켜기는 항상 사용자**.

## 6. 미결 사항 (우선순위순 — NEXT-TASK.md와 동기화)

1. **월요일(7/6) 장 시작 점검** — 상세 절차: `docs/runbooks/monday-market-check.md`
2. **C-6.21 웹소켓 라이브 검증** — 장중 + 사용자가 게이트 켠 후. H0STCNT0 필드 인덱스(_F_*)는
   문서 기준 구현이라 실데이터로 확인·조정 필요 (체크리스트 L절)
3. **종목-전략 적합성 매칭** (§3 결론의 후속) — 추세성 분류 → breakout/rsi 자동 배정
4. **백테스트 적중률 확인** — `/proposal-retrospective/backtest-accuracy` comparable>0 되면
5. v335(rsi·005930)는 종목 부적합 가능성 — paper 신호 보고 NAVER류 횡보 종목 재배정 검토
6. 수동 테스트 잔여: `docs/testing/manual-test-checklist-c6.md` A-2/A-3(옵트인 시), L(웹소켓)

## 7. 판단 원칙 (사흘간 사용자와 형성된 것)

- 매 단계 후 "이 단계가 완벽성에 기여했나 + 다음 단계가 여전히 최선인가"를 재평가하고 계획을 수정하라
  (실례: 유니버스 백테스트를 발견 즉시 우선순위로 끌어올림)
- 수동으로 검증한 것은 자동화하라 (실례: 수동 백테스트 → 제안 자동 첨부)
- 노가다 테스트는 체크리스트 문서로 남겨 위임하라
- 큰 변경마다 커밋 분리, 5커밋 이상이면 main 머지
- 토큰/비용을 아껴라 — 아는 구조 재탐색 금지, LLM 잡 실행은 비용 인지 후
