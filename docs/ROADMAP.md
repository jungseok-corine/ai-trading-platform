# ROADMAP — AI 전략 연구·실험·운영 시스템

> CLAUDE.md의 상세판. **비전 / 연구 루프 매핑 / 페이즈 로그 / 다음 할 일 / 보류 항목**.
> 목표가 바뀌면 여기를 갱신한다. (마지막 갱신: 2026-06-20, C-3.25까지 반영)
> **운영 콘솔(C-3) 사용법은 → `docs/OPERATIONS.md`.**

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

> 완료: **AI 분석 파이프라인**(§7, C-2.52~2.65) + **운영 콘솔**(§8, C-3.1~3.25).
> C-2/C-3의 buildable 항목은 전부 완료. 남은 건 외부 의존(아래 §5 보류) 또는 실데이터 축적 후 튜닝.

다음 후보(데이터가 쌓이면):
1. **실데이터 기반 튜닝** — 며칠 운영해 후보/거래/제안이 쌓이면, 운영 추세·퍼널·회고를 보고
   스캐너/전략 제안 파라미터(매크로 계수, 큐레이터 임계 등)를 재조정.
2. **운영 콘솔 심화** — 알림 외부 채널(Slack 등) 추가, 임계값 설정화(집중도/예산/신선도),
   실험 비교 자동 다이제스트.
3. **보류 항목(§5)** — 외부 자원이 준비되면 진행.

- **C-4.1** ✅: **전략 엔진 확장 — 실전 전략 타입 4종 + 유니버스 신호 스캔**
  (설계: `docs/design/C-4-strategy-engine.md`). 엔진이 이동평균 교차 변형만 돌던 한계를 깨고
  `rsi_reversion`(RSI 평균회귀)·`macd_trend`(MACD 추세)·`breakout_high`(전고점 돌파)·
  `pullback_trend`(눌림목)를 상태 없는 신호 생성기로 추가(기존 지표 재사용, 청산은 SELL 신호).
  + **유니버스 모드**: 전략 파라미터 `universe`(scanner_candidates/watchlist) 설정 시 종목을
  하나씩 지정하지 않아도 유니버스 전체에 전략을 돌려 신호 기록(`UniverseResolver`, 러너 확장).
  안전: universe는 신호 생성 전용 — auto_trade 강제 off(검증으로 차단). 프론트 전략 폼에 타입·
  유니버스·타입별 파라미터 노출. read-only. (남은 것: 토이 전략 아카이브 + 로그 리셋)

- **C-2.63** ✅: 매크로를 **스캔 단계 후보 점수**에 반영 — `macro_score_adjustment`
  (risk_off ×0.85, risk_on ×1.05, 반도체테마×SOX강세 ×1.15/약세 ×0.9). 스캔 시 regime_as_of +
  반도체 테마 종목 집합 조회해 후보 score 조정(원점수는 facts에 보존).

- **C-2.64** ✅: 회고 UI(제안별 회고 테이블, '제안 회고' 탭) + **회고→AI 피드백**
  (분석 번들에 retrospective 요약 주입 → 프롬프트에 '악화 많으면 신중' 노출).

- **C-2.65** ✅: 뉴스 큐레이터 **LLM 정밀화**(옵션, 기본 off) — 룰이 놓친 중요 뉴스를
  싼 모델이 0~1 점수로 보강. `final=max(rule, llm)`. `news_llm_score`(프롬프트/파서) +
  `NewsCuratorService(llm_provider=)`. 실패 시 룰로 폴백. config `news_curator_llm_*`.

## 5. 보류 항목

- **US 실시간(분봉/틱)**: KIS 해외 실시간 승인 또는 Polygon 유료. 현재는 일별 EOD로 충분.
- **Mac mini 배포**: `.github/workflows/deploy.yml` + launchd + self-hosted runner
  (테스트 게이트). 사용자가 Mac mini 구매 후 진행.
- **SOX 지수 직접**: 라이선스 제약 → 현재 SOXX ETF proxy. 필요 시 `US_MARKET_SOX_SYMBOL` 변경.

## 6. 환경 메모

- `.env`는 `backend/.env`. 키 예시는 `backend/.env.example`. **실제 키는 커밋 금지.**
- 미국장 자동 수집: `US_MARKET_PROVIDER=fred_twelvedata` + 두 키, `US_MARKET_REFRESH_SCHEDULER_ENABLED=true`.
- 테스트는 외부 네트워크 없이 — httpx `MockTransport`로 provider 검증.

## 7. AI 분석 파이프라인 설계 (확정 — 사용자 합의)

> "AI가 그날 매매를 분석하고 개선을 제안한다"의 구체 설계. 점진 구축(C-2.52~).

**현재 상태 구분**: "AI 제안"(proposal generators C-2.32/2.39/…)은 **결정적 휴리스틱**.
별도로 LLM `ai_analysis`(C-2.0~2.7, single/dual/debate)는 **수동 트리거만**, 입력은
전략메타+성과지표+신호요약뿐(캔들/뉴스/매크로 미포함). 아래는 그 격차를 메우는 계획.

**확정 결정**:
1. **분봉은 AI엔 텍스트(매매 테이프), 사람엔 마킹된 차트 이미지(UI)**. 정확도·토큰 모두 텍스트 우위
   (이미지는 눈대중 오독). 핵심은 "날것 전체 vs 정제" — 매매±구간 1분 상세 + 나머지 집계 +
   **사전계산 지표**(VWAP대비/레인지위치/거래량 z-score/MFE·MAE)를 우리가 계산해 넘김.
2. **빈도: 장별 하루 1회**. 국장 마감 후 KR 분석, 미장 마감 후 US 분석(→다음 국장 맥락). 기본 비활성 잡.
3. **뉴스/인터넷: 2-티어**. 싼 모델(큐레이터)이 홍수를 필터·요약·고정구조화 → 비싼 모델(분석)이
   정제본만. 원료 직결 금지. **사용자 수동 데이터 주입**(news source=manual + 애널리스트 노트)도 합류.
4. **모델/비용**: OpenAI+Claude 키 연결됨. dual/debate로 교차검증. 비용은 2-티어로 통제.
5. **최종 방아쇠는 사람**: 승격 기준(promotion_criteria) 자동 평가 → 통과 전략만 후보 →
   **실거래 ON은 사람이 단 한 번** 승인. 나머지(수집·분석·제안·승인→DRAFT·paper검증·승격)는 자동.
6. **압축 손실 가드**: 원본은 DB 보존(파괴 없음). 매매 구간 밖이라도 큰 변동/거래량 급증은
   notable로 항상 포함 + audit에 무엇을 넣고 뺐는지 기록. 온디맨드 상세 조회 별도.

**구축 순서**:
- **C-2.52** ✅: 매매 테이프 빌더(압축+사전계산+notable 가드) + 온디맨드 `/analysis-bundle/trade-tape`
- **C-2.53** ✅: 전체 분석 번들 합본 `AnalysisBundleService` (전략입력+테이프+매크로+뉴스+노트),
  온디맨드 `GET /analysis-bundle/full`. 기존 스키마 변경 없이 재사용·추가만.
- **C-2.53.1** ✅(실데이터 점검 보정): ①매크로 룩어헤드 차단(`regime_as_of`=trading_day 직전
  미국 세션) ②미청산 단건 주문 라벨(`status`/`excursion_basis`) ③장중(09:00~15:30 KST) 필터.
- **C-2.54** ✅: **일일 분석 잡**(기본 비활성) + **활동량 게이트**(없음/적음/적정/과다 ×
  시장활발도 — 적음+활발이면 '조건 과빡' 분석). provider/model/mode 설정화(A/B용 dual).
  `DailyAnalysisService` + `/daily-analysis`. 실제 LLM은 AnalysisRunService(single/dual).
- **C-2.55** ✅: 분석 번들(C-2.53)을 LLM 프롬프트에 **추가 컨텍스트 블록**으로 결합 +
  활동밴드 주입. `format_bundle_for_prompt`(원시 캔들 대신 사전계산 지표만), create_run/
  get_prompt에 `extra_context` 패스스루(감사용 input_payload 보존). 기존 스키마 무변경.
- **C-2.56** ✅: LLM 출력(JSON: verdict/observations/mistakes/hypotheses+param_change/
  confidence) → 파싱·검증 → **pending 제안 연결**(`AnalysisProposalService`). confidence<임계
  /param_change 없음/미등록 strategy_type이면 제안 안 만듦. 일일 잡이 proposals 수까지 기록.
- **C-2.57** ✅(룰 기반): 뉴스 **중요도 큐레이터** — `score_materiality`(KR 공시/뉴스 키워드로
  high/medium/noise 분류) + `NewsCuratorService`(임계 미달 노이즈 제외, 중요도순). 번들이
  큐레이트된 중요 뉴스만 사용. 싼 모델 정밀 점수·실제 소스(DART)는 후속.
- **C-2.58** ✅(유틸): **시드 헬퍼** — 예시 스캐너 룰 3 + 전략 3 + 배정 룰 2를 멱등 생성
  (`SeedService`, `POST /api/v1/seed/examples`). 전부 auto_trade=False·TESTING(안전).
  연구 루프가 바로 씹을 재료를 채운다. ("전략·조건이 얇다" 해소용)
- **C-2.59** ✅: **DART 공시 수집** — `DartProvider`(list.json, stock_code 포함→종목 매핑 불요) +
  `DartIngestService`(모니터 종목·중요도 필터, url 중복 방지) → news_events(source=dart) →
  큐레이터(C-2.57)→번들에 자동 합류. API `/dart/ingest`, 폴링 잡(기본 비활성, 10분).
  `.env`: `DART_API_KEY`. **인트라데이 감시(§7.1)의 1차 기반 완성.**
- **C-2.60** ✅: 매매 마킹 분봉 차트(사람 UI 전용) — 백엔드 `/analysis-bundle/chart-data`
  (전체 캔들+마커, 비압축) + 의존성 없는 SVG 캔들차트(▲매수/▼매도, 진입/청산). '매매 차트' 탭.
- **C-2.61** ✅: 공시 알림 — `DisclosureAlertService`(수집된 DART 중요 공시 최신순) +
  `GET /dart/alerts` + 관제탑에 `disclosure_alerts` 수·목록 노출. (감지·표시만, 대응은 사람)
- **C-2.62** ✅: 공시 온디맨드 AI 평가 — `DisclosureAssessmentService`(공시→LLM→JSON:
  impact/severity/action_hint/rationale, enum 보정). API `POST /dart/assess`. AI는 평가만, 대응은 사람.

### 7.1 인트라데이 이벤트 감시 (보유 종목 실시간 공시/뉴스) — 계획
> 일일 분석과 별개로, **전략이 매매 중인 종목**에 한해 장중 중요 이벤트를 감시.
- **1차 소스 = DART 공시**(전자공시, 무료 OpenAPI, 구조화·고신호). 일반 뉴스보다 신호/노이즈 우수.
- **중요만 필터**: ①룰(공시유형 화이트리스트: 실적/공급계약/유증·무증/합병/자기주식/횡령배임/
  거래정지 등, 정정·IR일정 등 제외) ②뉴스는 싼 모델(큐레이터)로 materiality 점수.
- **범위 한정**: 현재 보유 포지션(또는 활성 전략) 종목만 → 비용·노이즈 최소.
- **실시간**: 무료 푸시는 없음 → 장중 N분 폴링(DART near-real-time).
- **동작**: 감지→고우선 이벤트 저장→관제탑 알림(+선택적 온디맨드 AI 평가). **자동매매 없음**(안전).
- 필요: `DART_API_KEY`(무료), positions 연동, 큐레이터 티어(C-2.57). 페이즈는 C-2.59+로.

**모델 운영(합의)**: 매일=Sonnet 4.6 (또는 GPT, 일주일 A/B로 확정) / debate=Claude×현세대
GPT(gpt-5.4↑) / 승격 딥다이브=Opus 4.8+gpt-5.5 / 큐레이터=Haiku 4.5·gpt-5.4-mini.
기본 provider는 `fake`(실수 유료호출 방지), 사람이 명시적으로 켠다.

## 8. C-3 — 연구 → 실전 운영 (operator 관제)

> C-2의 buildable 항목 완료 후 시작. **실거래는 여전히 사람만**(안전 불변식 유지).
> 우선 read-only 관제·가시성부터: "지금 뭐가 돌고, 비용은 얼마고, 무엇을 봐야 하나".

- **C-3.1** ✅: **AI 비용·사용량 대시보드**(비용 가드) — `ai_model_responses`의 토큰을
  provider/model별·일자별 집계 + 추정 단가(`model_pricing`, USD/1M). 단가 미상 모델은
  비용 0 + `unpriced` 표기(과소계상 숨기지 않음). `AiCostService` +
  `GET /ai-cost/summary?days=N` + 'AI 비용' 탭. read-only, 외부 호출 없음.

- **C-3.2** ✅: **제안 퍼널**(연구 루프 ROI) — 전략·스캐너 제안의 생성→승인/거절→버전생성
  흐름 + 끝단 회고(개선/악화)를 한 화면에. 승인률=승인/(승인+거절), 검토 없으면 None.
  `ProposalFunnelService.funnel(days)` + `GET /proposal-funnel?days=N` + '제안 퍼널' 탭.
  승인/거절은 여전히 사람만(여긴 집계만). read-only.

- **C-3.3** ✅: **안전 점검 패널** — 핵심 불변식(실거래 off, 활성/테스트 버전 auto_trade off)이
  드리프트했는지 한 화면에서 확인 + 가드 pause/비상정지/거래 스케줄러 on/off 표시.
  `SafetyStatusService.status()`(invariants_ok + warnings) + `GET /safety-status` + '안전 점검' 탭.
  read-only 점검 — 아무것도 바꾸지 않고 드리프트는 경고로만(해제·변경은 사람이 직접).

- **C-3.4** ✅: **AI 분석 실행 감사** — 최근 `ai_analysis_runs`를 실행 메타 + 토큰/추정비용 +
  이 run이 만든 제안 수와 함께 나열(N+1 회피, created_at desc·id desc 정렬). `AnalysisAuditService`
  + `GET /analysis-audit?limit=N` + '분석 감사' 탭. read-only.

- **C-3.5** ✅: **운영 종합 관제**(랜딩) — 안전(C-3.3)·연구 루프(C-2.43)·퍼널(C-3.2)·비용(C-3.1)의
  핵심 헤드라인만 한 화면에. `OperationsOverviewService`(기존 read-only 서비스 조합) +
  `GET /operations-overview?days=N` + '운영 종합' 탭(연구소 기본 랜딩). read-only 합본.

- **C-3.6** ✅: **포트폴리오·노출 집계** — 보유 포지션(수량≠0)을 시가평가·미실현손익·종목별
  노출 비중으로. 현재가 미수신이면 평단으로 평가(has_price 표시). `PortfolioSummaryService` +
  `GET /portfolio-summary?account_id=` + '포트폴리오' 탭. read-only(시세 갱신은 동기화 잡 몫).

- **C-3.7** ✅: **AI 비용 예산 가드** — config `ai_cost_monthly_budget_usd`/`alert_threshold_pct`.
  비용 요약에 윈도 추정비용 대비 ok/warn/over/disabled 판정(`budget` 블록) 추가, 운영 종합·AI
  비용 탭에 신호등 노출. 예산 0이면 disabled. 단가 추정이므로 경보는 가늠자(사람 최종 판단).

- **C-3.8** ✅: **운영 다이제스트 + 알림 채널** — 운영 종합에서 '조치 필요'만 추려 다이제스트로
  (안전 드리프트/예산 초과/검토 대기/공시/회고 악화). `OperationsDigestService` +
  `GET /operations-digest`(미리보기) + `POST /notify`(설정 채널 전송). 알림 채널 추상화
  (`notifications/`: none/log, 기본 none=no-op) — 외부 채널은 토큰 준비 시 추가. 운영 종합 상단 노출.

- **C-3.9** ✅: **운영 다이제스트 스케줄러 잡**(기본 비활성) — 매일 다이제스트를 만들어 조치 항목이
  있으면 설정 채널로 전송. `run_operations_digest_job` + config `operations_digest_scheduler_*`.
  채널 기본 none이라 켜도 외부 전송 없음(채널 함께 설정해야 발송). 새 잡은 기본 off 규칙 준수.

- **C-3.10** ✅: **데이터 신선도 점검** — 시세/미국장/뉴스/DART의 최신 타임스탬프·경과 시간·stale
  여부. 데이터 없는 소스(미사용 가능)는 stale로 안 봄(거짓 경보 방지). `DataFreshnessService` +
  `GET /data-freshness` + '데이터 신선도' 탭 + 다이제스트에 stale 경보 통합. read-only.

- **C-3.11** ✅: **거래 활동 요약** — 최근 거래 건수·승패·승률·손익을 전체/전략버전별로(청산 손익
  있는 거래만 승패·손익 집계, 미청산은 건수만). `TradeActivityService` + `GET /trade-activity?days=N`
  + '거래 활동' 탭. read-only.

- **C-3.12** ✅: **리스크 이벤트 요약** — 리스크 레이어 승인/차단 기록을 룰별·최근 차단 목록으로.
  차단률·룰별 집중도로 전략/리스크 설정 점검 신호. `RiskEventSummaryService` +
  `GET /risk-events/summary?days=N` + '리스크 이벤트' 탭. read-only.

- **C-3.13** ✅: **승격 준비 보드** — 활성/테스트 전략 버전을 승격 기준에 평가(persist=False)해
  근접도(통과/충족 체크 수)를 표로. ⚠️ 통과는 판단일 뿐, 실거래 활성화는 사람만(안전 불변식).
  `PromotionReadinessService`(PromotionService 재사용) + `GET /promotion-readiness` + '승격 준비' 탭.

- **C-3.14** ✅: **운영 종합/다이제스트에 거래·리스크 통합** — 운영 종합에 trading 블록(청산·승률·
  실현손익·리스크 차단률) 추가, 다이제스트에 '실현손익 마이너스'·'차단률 50%↑(표본 5↑)' 경보 추가.

- **C-3.15** ✅: **Telegram 알림 채널** — `TelegramChannel`(bot token+chat_id 모두 있을 때만 전송,
  없으면 no-op). factory에 telegram 등록, config `telegram_bot_token`/`telegram_chat_id`.
  테스트는 httpx MockTransport(외부 네트워크 없음). 기본 provider는 여전히 none — 사람이 명시적으로 켠다.

- **C-3.16** ✅: **승격 후보 알림** — 운영 종합 research에 `promotion_ready`(승격 기준 통과 버전 수),
  다이제스트에 '승격 기준 통과 N개 — 검토하세요(실거래는 사람만)' 경보. 연구→승격→사람검토 루프를
  운영 화면에서 닫는다. `PromotionReadinessService.ready_count()`. read-only.

- **C-3.17** ✅: **운영 종합 스냅샷 + 추세** — 일자별 헤드라인(비용·실현손익·검토대기·승격후보)을
  `operations_snapshots` 테이블에 멱등 적재(마이그레이션 b1c2d3e4f5a6, enum 없음). `OperationsSnapshotService`
  (record/trend) + `POST /operations-snapshot/record`·`GET /trend` + 다이제스트 잡이 매일 함께 적재
  + '운영 추세' 탭. read-only 집계의 적재.

- **C-3.18** ✅: **스케줄러 잡 건강 점검** — 설정상 활성인 자율 잡이 제때 돌았는지/마지막이 실패했는지
  점검(비활성 잡은 대상 아님). `SchedulerHealthService` + `GET /scheduler-health` + '안전 점검' 탭에
  '자율 잡 건강' 섹션. read-only.

- **C-3.19** ✅: **스케줄러 이상 → 다이제스트 경보** — 활성 잡이 미실행/실패면 다이제스트에 alert
  레벨 경보('자율 잡 이상: … — 스케줄러 점검'). 운영 종합 상단 다이제스트에 자동 노출.

- **C-3.20** ✅: **운영 콘솔 가이드 문서** — `docs/OPERATIONS.md`. C-3 화면/엔드포인트 표, 다이제스트
  경보 목록, 안전 자세(기본값), 선택 기능(`.env`로 예산·다이제스트 잡·Telegram 켜기), 추세 적재 안내.

- **C-3.21** ✅: **연구 루프 전반부 퍼널** — 후보 포착→전략 배정→실험 흐름과 전환율(배정/후보).
  제안 퍼널(C-3.2, 후반부)의 짝. `ResearchFunnelService` + `GET /research-funnel?days=N` +
  '제안 퍼널' 탭을 '연구 루프 퍼널'로 확장(전반부+후반부 한 화면). read-only.

- **C-3.22** ✅: **에쿼티 곡선** — 일자별 실현손익·누적손익. `TradeActivityService.equity_curve(days)`
  + `GET /trade-activity/equity-curve` + '거래 활동' 탭에 의존성 없는 SVG 누적손익 곡선. read-only.

- **C-3.23** ✅: **포지션 집중 위험 경보** — 단일 종목 노출이 40%↑면 다이제스트에 '포지션 집중: …
  — 분산 검토' 경보(포트폴리오 요약 재사용). read-only.

- **C-3.24** ✅: **운영 콘솔 HTTP 스모크 테스트** — 모든 C-3 엔드포인트를 ASGI 레벨에서 200 + 고정
  구조로 검증(라우터 결선/직렬화 회귀 방지). 빈 DB에서도 통과.

- **C-3.26** ✅: **안전 불변식 회귀 가드** — CLAUDE.md의 🔒 안전 불변식을 코드로 못박는 테스트.
  실거래 off / provider 기본 fake / 알림 none / 새 잡 기본 off / 예산 0을 코드 기본값(`_env_file=None`)
  으로 검증. 누가 기본값을 슬그머니 바꾸면 CI가 실패해 알린다.
