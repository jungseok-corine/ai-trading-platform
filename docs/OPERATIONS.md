# 운영 콘솔 가이드 (C-3)

> 연구 루프(C-2)가 "후보→실험→제안→승인→회고"를 돈다면, **C-3 운영 콘솔**은 그 위에서
> "지금 안전한가 · 비용은 얼마인가 · 무엇을 검토해야 하나 · 잘 돌고 있나"를 한눈에 본다.
> **전부 read-only**다. 주문을 내지 않고, 어떤 안전 불변식도 자동으로 바꾸지 않는다.
> 외부 전송(알림)과 새 스케줄러 잡은 **기본 비활성**이며, 사람이 명시적으로 켤 때만 동작한다.

프론트는 **AI 전략 연구소** 페이지의 상단 탭들(운영 종합/운영 추세/… 안전 점검)에서 본다.

## 한눈에 — 화면(탭)과 API

| 화면(탭) | API | 무엇을 보나 |
|----------|-----|-------------|
| 운영 종합 | `GET /operations-overview` | 안전·검토대기·승격후보·비용·거래/리스크 헤드라인 + 다이제스트 |
| 운영 추세 | `GET /operations-snapshot/trend` | 일자별 헤드라인 추세(비용·실현손익·검토대기·승격후보) |
| 제안 퍼널 | `GET /proposal-funnel` | 제안 생성→승인/거절→버전생성 + 회고 |
| AI 비용 | `GET /ai-cost/summary` | provider/model·일자별 토큰·추정비용 + 예산 신호등 |
| 분석 감사 | `GET /analysis-audit` | 최근 AI 분석 run의 토큰/비용/생성 제안 |
| 포트폴리오 | `GET /portfolio-summary` | 보유 포지션 시가평가·미실현손익·노출 |
| 거래 활동 | `GET /trade-activity` | 건수·승패·승률·손익(전체/전략별) |
| 리스크 이벤트 | `GET /risk-events/summary` | 리스크 승인/차단 룰별·최근 차단 |
| 승격 준비 | `GET /promotion-readiness` | 활성/테스트 버전의 승격 기준 근접도 |
| 데이터 신선도 | `GET /data-freshness` | 시세/미국장/뉴스/DART 최신성 |
| 안전 점검 | `GET /safety-status`, `GET /scheduler-health` | 핵심 불변식 + 자율 잡 건강 |
| (전송) | `GET /operations-digest`, `POST /operations-digest/notify` | 조치 필요 다이제스트 + 알림 |

## 운영 다이제스트 — '봐야 할 것'만

`OperationsDigestService`가 운영 종합을 받아 **조치가 필요한 항목만** 추려 다이제스트로 만든다.
심각도는 `ok < attention < alert`. 현재 수집되는 경보:

- **alert**: 안전 불변식 드리프트(실거래 ON/auto_trade ON), AI 비용 예산 초과, 자율 잡 이상(미실행/실패)
- **attention**: 비용 예산 임계 도달, 검토 대기 제안, 승격 기준 통과 전략, 공시 알림, 회고 악화>개선,
  기간 실현손익 마이너스, 리스크 차단률 높음(표본 5↑·50%↑), 데이터 신선도 stale

다이제스트는 운영 종합 탭 상단에 항상 노출된다. 알림 전송은 아래 참고.

## 안전 자세 (기본값)

- **실거래/자동매매**: `KIS_REAL_TRADING_ENABLED=false`, 활성/테스트 버전 `auto_trade_enabled=false`.
  안전 점검 탭의 `invariants_ok`가 이를 감시하며, 드리프트는 경보로만 알린다(해제는 사람만).
- **승격 통과 = 판단일 뿐**: 승격 준비 보드에서 통과해도 실거래가 켜지지 않는다. 실전 활성화는
  항상 사람의 명시적 확인이 필요하다.
- **알림 채널**: 기본 `none`(외부 전송 없음). `log`는 로거에만. `telegram`은 토큰/chat_id가 모두
  있을 때만 전송(없으면 no-op).
- **새 스케줄러 잡**: `operations_digest` 잡은 기본 비활성. 켜도 채널이 none이면 외부 전송은 없다.

## 선택 기능 켜기 (`.env`)

```bash
# AI 비용 예산 가드(0이면 비활성). 윈도 추정비용이 예산의 threshold%↑면 경보.
AI_COST_MONTHLY_BUDGET_USD=50
AI_COST_ALERT_THRESHOLD_PCT=80

# 운영 다이제스트 잡(기본 off). 켜면 매일 다이제스트를 만들고 스냅샷을 적재한다.
OPERATIONS_DIGEST_SCHEDULER_ENABLED=true
OPERATIONS_DIGEST_SCHEDULER_HOUR=16
OPERATIONS_DIGEST_SCHEDULER_MINUTE=30

# 알림 채널(기본 none). telegram을 쓰려면 provider + 토큰/chat_id 모두 필요.
NOTIFICATION_PROVIDER=telegram   # none | log | telegram
TELEGRAM_BOT_TOKEN=123456:abcdef
TELEGRAM_CHAT_ID=123456789
```

> 단가표(`app/trading/analysis/model_pricing.py`)는 **추정치**다. 비용 숫자는 가늠자로 보고,
> 토큰 사용량(항상 정확) 추세로 이상 급증을 함께 판단한다. 표에 없는 모델은 비용 0 + `unpriced`로
> 드러낸다(과소계상을 숨기지 않음).

## 추세 적재

운영 추세는 `operations_snapshots`(일자별 1행, 멱등)에서 온다. 채우는 방법 두 가지:
- 다이제스트 잡이 매일 자동 적재(위 `.env`로 잡을 켠 경우)
- 운영 추세 탭의 "지금 스냅샷 적재" 버튼 또는 `POST /operations-snapshot/record`
