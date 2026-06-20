# ROADMAP — AI 전략 연구·실험·운영 시스템

> CLAUDE.md의 상세판. **비전 / 연구 루프 매핑 / 페이즈 로그 / 다음 할 일 / 보류 항목**.
> 목표가 바뀌면 여기를 갱신한다. (마지막 갱신: 2026-06-20, C-2.48까지 반영)

## 1. 비전

자동매매 봇이 아니라 **자동 *실험* 시스템**을 먼저 만든다. 시장을 매일 스캔하고,
후보를 시장/테마/시간 맥락과 함께 포착하고, 전략을 배정·실험해 버전끼리 비교하고,
AI가 개선을 *제안*하면 사람이 승인해 새 버전을 만들고, 그 버전이 실제로 나아졌는지
*회고*해 학습을 닫는다. 한국장뿐 아니라 미국장 흐름(전일 지수/금리/VIX)을 맥락으로 쓴다.

핵심 원칙:
- **AI = 제안자**. 자동 적용/활성화/실거래 없음. 승인은 사람.
- **버전 비교**. 개선은 새 버전으로. 덮어쓰기 금지.
- **맥락 보존**. "왜 후보가 됐는지"(facts/matched_conditions), 시장·시간 맥락을 남긴다.
- **데이터 부족 시 자제**. 표본이 적으면 제안/판정하지 않는다(inconclusive).

## 2. 연구 루프 → 코드 매핑

| 단계 | 서비스 | API(prefix `/api/v1`) | 핵심 모델 |
|------|--------|------------------------|-----------|
| 데이터 수집 | `data_refresh_service`, `investor_flow_service` | `/data-refresh` | `market_data`, `investor_flows` |
| 미국장 수집 | `us_market_refresh_service` + `us_market/`(FRED·TD) | `/us-market-snapshots/refresh` | `us_market_snapshots` |
| 시장 맥락 | `market_context_service`, `market_context_capture_service` | `/market-context` | `market_context_snapshots`, `themes` |
| 스캔 | `scanner_service`, `scanner_scan_service`, `trading/scanner/` | `/scanner-rules` | `scanner_rules`, `scanner_rule_versions` |
| 후보 | `candidate_service` | `/candidates` | `candidate_events` |
| 후보 성과 | `candidate_outcome_service` | `/candidates/analysis` | (집계) |
| 배정 | `assignment_service` | `/assignment-rules`, `/assignment-logs` | `strategy_assignment_*` |
| 실험 | `experiment_service`, `trading/experiment/metrics` | `/experiments` | `experiments`, `experiment_variants/results` |
| AI 제안(전략) | `proposal_generator`, `proposal_service` | `/strategy-proposals` | `strategy_proposals` |
| AI 제안(스캐너) | `scanner_proposal_generator`, `scanner_proposal_service` | `/scanner-proposals` | `scanner_rule_proposals` |
| 자동 점검 잡 | `scanner_review_service`, `strategy_review_service` | `/scanner-review`, `/strategy-review` | (scheduler_runs) |
| 일괄 검토 | `*_proposal_service.bulk_review` | `.../bulk-review` | — |
| 일일 리포트 | `daily_report_service` | `/daily-reports` | `daily_research_reports` |
| 승격 게이트 | `promotion_service` | `/promotion-criteria`, `/strategy-versions/{id}/promotion-evaluation` | `promotion_*` |
| 회고 | `proposal_retrospective_service` | `/proposal-retrospective` | (집계) |
| 자율 파이프라인 | `research_pipeline_service` | `/research-pipeline` | (scheduler_runs) |
| 관제탑 | `research_status_service` | `/research-status` | (집계) |

자율 스케줄러 잡(모두 기본 비활성, `app/scheduler/`): `strategy_runner`, `order_sync`,
`trading_state_sync`, `daily_report`, `data_refresh`, `research_pipeline`,
`scanner_review`(16:10), `strategy_review`(16:20), `us_market_refresh`(07:00).

## 3. 페이즈 로그

**C-1.x ~ C-2.20 (기반)**: KIS 연동, 전략/신호/주문/체결/포지션 파이프라인,
리스크 레이어, 모의투자 자동매매, AI 분석 run, 실계좌 read-only 검증, 시세/수급 수집.

**C-2.21 ~ C-2.30 (연구 랩 1차)**: 스캐너 룰/조건/버전, 후보 이벤트, 전략 배정,
실험·비교 지표, AI 전략 제안(C-2.27) + 생성기(C-2.32), 일일 리포트(C-2.29),
승격 기준/평가, 뉴스·미국장 스냅샷(C-2.28), 시장 맥락/테마.

**C-2.31~2.37**: 스캐너 facts 계산 + 시장데이터 스캔, 자율 파이프라인(스캔→후보→배정),
scheduler_runs 기록, 시장맥락 캡처(후보에 맥락 연결).

**C-2.38**: 후보 성과 분석(조건·시간대별 forward 수익률). *주의: AND 시맨틱이라 한 버전
내 조건별 성과(by_condition)는 동일.*

**C-2.39**: 스캐너 룰 개선 제안 — overall 승률 낮으면 조건 강화(volume_spike ×1.3,
price_change_pct ×1.3, turnover_rank ×0.7). 승인 시 DRAFT 룰 버전 생성.

**C-2.40**: 스캐너 자동 점검 잡 — active/testing 버전을 주기 점검, pending 중복 방지.

**C-2.41**: 일일 리포트에 AI 제안 활동(당일 생성 + 검토 대기 pending) 추가.

**C-2.42**: 전략 자동 점검 잡 — 기대값 음수 버전에 파라미터 조정 제안(C-2.32 재사용).

**C-2.43**: 관제탑 `/research-status` — 자율 잡 최근 실행 + 검토 대기 + 활성 버전.

**C-2.44**: 미국장 provider 추상화(AI provider 패턴). 기본 `manual`(키 없이 no-op).

**C-2.45**: 제안 일괄 승인/거절(bulk_review). 실패 격리, 승인해도 DRAFT만.

**C-2.46/2.47**: 제안 회고 — 새 버전 vs base 비교(전략=기대값, 스캐너=승률), 표본
부족 시 inconclusive. 관제탑에 개선/악화/판단보류 요약.

**C-2.48**: FRED + Twelve Data 어댑터. FRED=VIX/금리/S&P500/나스닥, TD=SOX(SOXX proxy).
권장 provider `fred_twelvedata`. `.env`: `FRED_API_KEY`, `TWELVEDATA_API_KEY`.

**C-2.49**: 매크로 레짐 분류(`classify_macro_regime`) — 전일 미국장으로 risk_on/neutral/
risk_off 결정. 맥락 캡처에 주입(`data.macro`), `/market-context/macro-regime`, 관제탑 노출.

**C-2.50**: 매크로를 스캐너 제안에 반영 — `tighten_conditions(aggressive=)`. risk_off면
강화 폭 확대(×1.45, rank ×0.6), 근거에 레짐 명시. (전일 미국장 → 한국장 제안 연계 1차)

**C-2.51**: 매크로를 전략 제안(C-2.32)에도 반영 — risk_off면 volume_multiplier ×1.45,
long_window +8로 강화, 근거에 레짐 명시. (스캐너+전략 양쪽 제안에 매크로 반영 완료)

## 4. 다음 후보 (우선순위)

1. **매크로 반영 확장** — 전략 제안(C-2.42)에도 레짐 반영, SOX 강세 시 반도체 테마 후보
   가중, risk_off 시 신규 후보 점수 하향 등. (C-2.49/2.50에서 스캐너 제안까지는 완료)
2. **major_news 자동 채우기** — 무료 뉴스 소스 필요(현재 `null`). provider 패턴 재사용.
3. 회고 UI 보강(제안별 회고 테이블), 회고 결과를 제안 생성에 피드백.

## 5. 보류 항목

- **US 실시간(분봉/틱)**: KIS 해외 실시간 승인 또는 Polygon 유료. 현재는 일별 EOD로 충분.
- **Mac mini 배포**: `.github/workflows/deploy.yml` + launchd + self-hosted runner
  (테스트 게이트). 사용자가 Mac mini 구매 후 진행.
- **SOX 지수 직접**: 라이선스 제약 → 현재 SOXX ETF proxy. 필요 시 `US_MARKET_SOX_SYMBOL` 변경.

## 6. 환경 메모

- `.env`는 `backend/.env`. 키 예시는 `backend/.env.example`. **실제 키는 커밋 금지.**
- 미국장 자동 수집: `US_MARKET_PROVIDER=fred_twelvedata` + 두 키, `US_MARKET_REFRESH_SCHEDULER_ENABLED=true`.
- 테스트는 외부 네트워크 없이 — httpx `MockTransport`로 provider 검증.
