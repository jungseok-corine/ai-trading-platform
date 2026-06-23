# GAP-AND-PLAN.md — 갭 분석 + 개선 계획 + 다음 구현 순서

> 마지막 갱신: 2026-06-23  
> "갭"은 시스템이 의도한 기능과 현재 구현 사이의 차이다.  
> 항목은 실현 가능성·임팩트·리스크 기준으로 우선순위를 매겼다.

---

## 1. 갭 분석 요약

### A. 즉시 보완 가능한 갭 (코드 수정 10~30줄 수준)

| # | 갭 | 현재 상태 | 임팩트 |
|---|----|-----------|----|
| A-1 | 손절/익절 파라미터 AI 제안 포함 안 됨 | `stop_loss_pct`/`take_profit_pct` 구현됐지만 LLM 프롬프트에 명시 안 됨 | 중 |
| A-2 | 미체결 주문 조회 API 미연동 | `OrderSyncService`에 TODO 주석, 실행일 체결 내역으로만 상태 갱신 | 중 |
| A-3 | 연구소 섹션 그룹핑 없음 | 24개 버튼 나열 — UX 혼잡 | 낮 |
| A-4 | `stop_loss_pct`/`take_profit_pct` AI 분석 bundle에 포함 안 됨 | LLM이 현재 손절/익절 기준을 모름 | 중 |

### B. 1~2일 작업 갭

| # | 갭 | 현재 상태 | 임팩트 |
|---|----|-----------|----|
| B-1 | 알림 시스템 미사용 | Telegram 채널 구현됐지만 `notification_provider=none` 기본값 | 높 |
| B-2 | RSS/뉴스 피드 없음 | NewsCuratorService가 DART/EDGAR 공시만 취급 | 높 |
| B-3 | 유니버스 전략의 종목별 손절/익절 미지원 | 단일 symbol 전략만 SL/TP 동작 | 중 |
| B-4 | 포트폴리오 실시간 평가 미지원 | DB 기반 집계만, 브로커 실시간 호출 없음 | 중 |

### C. 구조적 개선 갭 (더 큰 작업)

| # | 갭 | 현재 상태 | 임팩트 |
|---|----|-----------|----|
| C-1 | 백테스트 없음 | 전략 검증이 모의투자 실시간 실험으로만 가능 | 높 |
| C-2 | 전략 파라미터 최적화 없음 | AI 제안이 LLM 판단에만 의존, 수치 최적화 없음 | 높 |
| C-3 | 알림 트리거 없음 | 공시 이벤트 감지 구현됐지만 알림과 미연결 | 중 |
| C-4 | 다계좌 전략 분리 없음 | 계좌 간 전략 격리 없음 | 중 |

---

## 2. 단기 개선 계획 (우선순위 순)

### P-1. 손절/익절 파라미터 → AI 분석 bundle에 포함  
**작업**: `AnalysisBundleService`가 전략 버전의 `stop_loss_pct`/`take_profit_pct`를 bundle에 넣고,  
LLM 프롬프트가 이 값을 참조해 개선 제안을 할 수 있도록 수정.  
**파일**: `backend/app/services/analysis_bundle_service.py`, `app/trading/strategy/schemas.py`  
**예상 작업**: ~1시간  
**테스트**: `test_c5_us_analysis_news.py` 패턴으로 추가

### P-2. Telegram 알림 연동 — 일일 리포트/운영 다이제스트 발송  
**작업**: `NOTIFICATION_PROVIDER=telegram`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 환경변수 설정 후  
`daily_report_scheduler`와 `operations_digest_scheduler`가 생성한 리포트를 Telegram으로 전송.  
**파일**: `backend/app/scheduler/jobs.py` (이미 `get_notification_channel` 호출 있음)  
**예상 작업**: 설정 + 테스트 ~2시간  
**주의**: 알림은 단방향 전송만. 봇이 명령을 받아 실행하는 구조 금지.

### P-3. 연구소 UI — 섹션 그룹핑 + 기본 섹션 정리  
**작업**: 24개 버튼을 5~6개 그룹("운영", "연구", "제안", "데이터", "시스템")으로  
접혀있는 형태로 재구성.  
**파일**: `frontend/src/pages/ResearchPage.tsx`  
**예상 작업**: ~1~2시간 (로직 변경 없음, UI 구조만)

### P-4. 유니버스 전략 SL/TP — 보유 종목 전체에 적용  
**작업**: 유니버스 전략은 `symbol_code`가 없으므로 `holdings` 전체를 순회해  
개별 종목에 SL/TP를 적용하는 로직 추가.  
**파일**: `backend/app/services/strategy_runner_service.py`  
**예상 작업**: ~2~3시간  
**테스트**: `test_stop_loss_take_profit.py` 패턴으로 추가

### P-5. 미체결 주문 조회 API 연동 (TTTC8036R/VTTC8036R)  
**작업**: `OrderSyncService.sync_pending_orders()`에서 KIS 미체결조회 API를 호출해  
더 정확한 주문 상태 갱신.  
**파일**: `backend/app/services/order_sync_service.py`  
**예상 작업**: ~3~4시간  
**주의**: 실계좌 API 호출 — 테스트는 MockTransport로 격리

---

## 3. 다음 구현 순서 체크리스트

아래 항목은 현재 상태 기준으로 작성됐으며, 순서는 의존성과 리스크를 고려했다.

```
[ ] P-1. SL/TP → AI bundle 포함
    - [ ] StrategyVersionParameters의 sl/tp 값이 bundle meta에 포함되도록 수정
    - [ ] LLM 프롬프트 템플릿에 sl/tp 컨텍스트 추가
    - [ ] 테스트 추가

[ ] P-2. Telegram 알림 설정
    - [ ] 환경변수 문서화 (.env.example 추가)
    - [ ] daily_report_scheduler 활성화 검증
    - [ ] operations_digest_scheduler 활성화 검증
    - [ ] 알림 형식 검토 (너무 길지 않게)

[ ] P-3. 연구소 UI 섹션 그룹핑
    - [ ] 5~6개 카테고리로 분류
    - [ ] 각 카테고리 토글 가능한 서브네비 구현
    - [ ] 기본 선택 섹션 "운영 종합" 유지

[ ] P-4. 유니버스 전략 SL/TP
    - [ ] _run_version에서 universe 전략의 holdings 전체 순회 로직
    - [ ] 종목별 force_sell 신호 생성 (멀티 심볼 처리)
    - [ ] 테스트 추가

[ ] P-5. 미체결 주문 조회 API
    - [ ] KIS TTTC8036R/VTTC8036R API 클라이언트 구현
    - [ ] OrderSyncService에 연동
    - [ ] MockTransport 테스트 추가
```

---

## 4. 다음 세션 진입점

현재 시스템은 C-5.21까지 완성됐고, 손절/익절(SL/TP) 기능이 방금 추가됐다.  
다음 작업으로 권장하는 순서:

1. **P-1** (SL/TP → AI bundle): 이미 구현된 기능을 AI가 인식하도록 연결. 작은 작업, 높은 가치.
2. **P-3** (연구소 UI 그룹핑): 섹션이 24개로 늘어 UX가 혼잡. 코드 수정 없이 UI만 정리.
3. **P-2** (Telegram): 알림이 없으면 시스템을 항상 열어봐야 함. 설정 레벨 작업.
4. **P-4 / P-5**: 선택적. 유니버스 전략 사용 빈도와 미체결 주문 발생 빈도에 따라 결정.
