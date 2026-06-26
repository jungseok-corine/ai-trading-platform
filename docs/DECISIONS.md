# DECISIONS.md — 중요 방향 전환과 의사결정 기록

> 이 파일은 "왜 이렇게 만들었는가"를 기록한다.  
> 충돌이 발생하거나 방향이 애매할 때 이 파일을 참조한다.  
> 결정이 번복될 때도 이 파일에 기록한다.

---

## D-1. 프로젝트 방향: 단순 자동매매 봇이 아니라 AI 시장지능 전략 연구소

**날짜**: 2026-06-23  
**상태**: 확정

**결정 내용**:  
이 프로젝트는 단순히 매수·매도 주문을 자동화하는 봇이 아니다.  
AI가 시장 데이터를 수집·분석하고, 전략을 실험·개선하며, 검증된 것만 실전에 배치하는  
**AI 시장지능 전략 연구소**로 방향을 정의한다.

**이유**:  
- 단순 자동매매 봇은 전략 품질을 올리는 피드백 루프가 없다.
- 시장은 계속 변한다. 자동 실험·회고 없이는 전략이 노후화된다.
- 사람이 직접 모든 파라미터를 튜닝하는 것은 확장성이 없다.

**영향**:  
- AI는 항상 제안자(proposer), 사람은 실전 배치 최종 승인자.
- Paper 영역은 최대한 자동화, 실전 영역은 사람 승인 게이트.
- 모든 구현 결정은 "이것이 연구소를 더 똑똑하게 만드는가?"를 기준으로 판단.

---

## D-2. 매매의 시작은 전략이 아니라 시장 분석이다

**날짜**: 2026-06-23  
**상태**: 확정

**결정 내용**:  
"어떤 전략을 쓸까?"가 아니라 "시장에서 무슨 일이 일어나고 있나?"가 먼저다.  
시장 맥락(뉴스·공시·수급·매크로·테마) 분석이 선행되어야  
어떤 종목이 후보인지, 어떤 전략이 맞는지를 판단할 수 있다.

**이유**:  
- 전략 중심 접근은 "이 전략으로 어떤 종목을 돌릴까"를 묻는다 → 맥락 없는 기계적 실행.
- 시장 중심 접근은 "지금 시장에서 무엇이 의미 있나?"를 묻는다 → 맥락 있는 판단.

**영향**:  
- 연구 루프의 시작은 **데이터 수집 + 시장 분석**이다.
- 후보 종목은 전략이 결정하는 것이 아니라 **시장 인텔리전스가 먼저 발굴**한다.
- Market Intelligence Core(C-2.21.1)가 모든 후속 기능의 기반이 된다.

---

## D-3. Paper 영역은 최대한 자동화, 실전 영역은 사람 승인 게이트

**날짜**: 2026-06-23  
**상태**: 확정

**결정 내용**:  
Paper(모의투자) 영역의 연구 루프(수집→스캔→배정→실험→제안→회고)는 자동화한다.  
실전 배치(ACTIVE + auto_trade=True)는 반드시 사람이 승인해야 한다.

**자동화 범위**:
- 데이터 수집, 시장 분석, 후보 발굴 → 완전 자동
- 전략 배정, 실험 실행, AI 분석·제안 생성 → 완전 자동
- 실전 배치 승인 → **사람 필수**

**구현**:  
- AI 제안 승인 → 항상 `DRAFT + auto_trade_enabled=False` 강제
- `ACTIVE + auto_trade_enabled=True` → 사람이 직접 설정
- `KIS_REAL_TRADING_ENABLED=true` → 사람이 직접 환경변수 설정

---

## D-4. 전략과 스캐너는 수정하지 않고 새 버전으로 생성 후 비교

**날짜**: 2026-06-23  
**상태**: 확정

**결정 내용**:  
기존 `StrategyVersion`이나 `ScannerRuleVersion`을 직접 수정하지 않는다.  
개선은 항상 새 버전으로 생성하고, 구버전과 신버전을 나란히 실험해 비교한다.

**이유**:  
- 덮어쓰면 "이전이 더 좋았는지" 알 수 없다.
- 실험 도중 버전이 바뀌면 결과가 혼탁해진다.
- 버전 히스토리가 곧 전략의 학습 기록이다.

**구현**:  
- `StrategyProposal` 승인 → 새 `StrategyVersion(status=DRAFT)` 생성
- `ScannerRuleProposal` 승인 → 새 `ScannerRuleVersion(status=DRAFT)` 생성
- 기존 버전은 성과 비교 완료 전까지 유지

---

## D-5. 한국장뿐 아니라 미국장 및 글로벌 데이터를 포함하는 멀티마켓 방향

**날짜**: 2026-06-23  
**상태**: 확정

**결정 내용**:  
한국 주식 자동매매만이 아니라, 미국장과 글로벌 매크로 데이터를 함께 활용하는  
멀티마켓 인텔리전스 시스템으로 방향을 유지한다.

**구현 현황**:  
- `MarketCode.KR` / `MarketCode.US` 분리 완료
- KIS 해외 모의 브로커 (`KISOverseasPaperBrokerClient`) 구현 완료
- EDGAR(미국 공시) 수집 완료
- FRED + Twelve Data 매크로 어댑터 완료
- 미장 매크로가 한국장 전략 제안에 반영됨

**다음 방향**:  
글로벌 뉴스 RSS, 섹터/테마 데이터(한국·미국), 더 풍부한 US 데이터 소스 통합.

---

## D-6. DartLab을 Market Intelligence 데이터 어댑터 후보로 검증한다

**날짜**: 2026-06-23  
**상태**: ✅ 검증 완료 (C-2.21.0)

**검증 결론**: **부분 사용** — 메인 백엔드 의존성으로는 비권장.

**이유**:
- DartLab은 분석가/연구자용 노트북 도구. 서버 앱 설계가 아님.
- 핵심 의존성 충돌: DuckDB + HuggingFace 패턴이 PostgreSQL + httpx 패턴과 근본적으로 다름.
- 패키지 무게: wheel 22.5 MB, 의존성 포함 시 200~500 MB.
- 비동기 미지원: FastAPI 앱에서 `asyncio.to_thread` 래핑 필요.

**유일한 가치**: DART XBRL 재무제표 (손익계산서, 재무상태표, 현금흐름표) — 우리에게 없음.

**결정**: DartLab 없이 DART 재무제표 API(`/api/fnlttSinglAcnt.json`)를 직접 호출하는  
경량 `DartFinanceProvider`를 기존 패턴으로 구현한다 (C-2.21.1에서).

상세 분석 → `docs/design/C-2.21.0-dartlab-spike.md`

---

## D-9. DART 재무제표는 DartLab 없이 직접 구현한다

**날짜**: 2026-06-23  
**상태**: 확정

**결정 내용**:  
DART XBRL 재무제표(손익계산서·재무상태표·현금흐름표)를  
DartLab 없이 DART OpenAPI를 직접 호출하는 경량 구현으로 수집한다.

**구현 패턴**: 기존 `DartProvider` / `EdgarProvider`와 동일한 패턴:
- `httpx.AsyncClient` 기반 비동기 API 호출
- `MockTransport` 테스트 격리
- 결과를 PostgreSQL에 저장
- 새 스케줄러 잡 기본 비활성

**사용 DART API**: `/api/fnlttSinglAcnt.json` (단일 재무제표 항목별 조회)  
**필요 설정**: `DART_API_KEY` (기존 공시 수집에서 이미 사용 중)

---

## D-7. AI는 절대로 실전 주문을 직접 실행하지 않는다

**날짜**: 2026-06-23  
**상태**: 확정 (코드 레벨 불변식으로 구현됨)

**결정 내용**:  
AI(LLM 또는 알고리즘)가 생성한 어떤 출력도 사람의 명시적 승인 없이  
실전 주문으로 이어지지 않는다.

**구현된 안전장치 (4계층)**:
1. `config.kis_real_trading_enabled = False` (기본값, 코드 레벨)
2. `KisRealBroker.place_order()` → `real_trading_enabled=False`이면 `RealTradingDisabledError`
3. AI 제안 승인 → `auto_trade_enabled = False` 강제
4. 유니버스 자동매매 → PAPER 계좌 전용 + `universe_auto_trade=True` 옵트인

**이 결정은 번복하지 않는다.**  
실전 주문 활성화가 필요한 경우, 사람이 환경변수와 DB를 직접 변경해야 한다.

---

## D-8. 새 스케줄러 잡은 항상 기본 비활성으로 추가한다

**날짜**: 2026-06-23  
**상태**: 확정

**결정 내용**:  
새 스케줄러 잡을 추가할 때 `*_scheduler_enabled = False`를 기본값으로 설정한다.

**이유**:  
- 새 기능이 예기치 않게 자동 실행되는 것을 방지.
- 사람이 준비됐을 때 명시적으로 활성화하는 방식이 안전하다.
- 운영 환경에서 새 잡이 갑자기 실행돼 API 레이트리밋이나 비용이 발생하는 것을 방지.

**예외**:  
`strategy_scheduler`(매분 신호 생성)와 `order_sync_scheduler`(체결 동기화)는  
핵심 운영 기능으로 기본 활성. 새 잡은 모두 기본 비활성.

---

## D-10. C-2.21.1 범위 드리프트 인식 — 어댑터 기반 우선, DART finance는 첫 번째 구체 소스

**날짜**: 2026-06-24  
**상태**: 확정

**경위**:  
C-2.21.1 구현 세션에서 ROADMAP 원래 범위(`IntelligenceSource` / `IntelligenceEvent` 모델,  
어댑터 base 클래스)를 건너뛰고 DART XBRL 재무제표 수집기를 바로 구현했다.  
DART finance 구현(financial_statements, DartFinanceProvider, DartFinanceIngestService)은  
유용하고 유지된다. 그러나 그것만으로는 C-2.21.1 원래 범위를 충족하지 않는다.

**결정 내용**:

1. **DART finance 구현은 보존한다.** `financial_statements` 테이블, `DartFinanceProvider`,  
   `DartFinanceIngestService`, `AnalysisBundleService.financials` 키는 모두 유지된다.

2. **어댑터 기반을 추가 구현한다 (C-2.21.1b).** `IntelligenceSource` / `IntelligenceEvent`  
   모델과 `IntelligenceAdapter` 추상 클래스를 C-2.21.1b에서 구현한다.

3. **DART finance는 첫 번째 구체 소스다.** `DartFinanceAdapter` 스켈레톤을 추가해  
   기존 수집기가 나중에 어댑터 패턴으로 연결될 방향을 명시한다.  
   실제 연결(fetch 구현)은 C-2.22+에서 점진적으로 진행한다.

4. **새 소스는 반드시 어댑터 패턴을 따른다.** C-2.22부터 추가하는 모든 수집기는  
   `IntelligenceAdapter`를 상속하고 `IntelligenceSource`에 등록해야 한다.  
   소스별 독립 로직을 직접 스케줄러 잡에 넣는 방식은 금지한다.

**영향**:  
- C-2.22(Intelligence Ingestion Pipeline)는 C-2.21.1b 완료 후 시작한다.
- C-2.22에서 구현하는 모든 수집기(뉴스 RSS 등)는 `IntelligenceAdapter` 상속.
- 기존 `DartProvider` / `DartIngestService` / `EdgarProvider`는 건드리지 않는다  
  (이들은 공시 수집 전용이며, 재무제표/인텔리전스 계층과 분리 유지).

---

## D-11. C-2.30 알림 통합 보류, 일괄 승인 안전 게이트 우선, C-2.30 이후 방향은 사용자 결정

**날짜**: 2026-06-24  
**상태**: 확정

**경위**:  
C-2.30(Mobile Approval Report UX)의 원래 범위에는 "Telegram/모바일 알림 통합"이 포함되어  
있었다. 그러나 알림 통합은 백엔드 + 시크릿(토큰)이 필요해, 최근 작업들에서 지켜온  
frontend-only 범위를 벗어난다. C-2.30은 승인 리포트 카드 UX를 frontend-only로 완성하고,  
알림 통합은 의도적으로 보류했다. 또한 일괄 승인이 단일 승인의 안전 UX를 우회하던 문제를  
C-2.30.1(Bulk Approval Safety Guard)에서 먼저 처리했다.

**결정 내용**:

1. **C-2.30 알림 통합은 보류한다.** Telegram/모바일 푸시 알림은 별도 작업으로 분리하고,  
   사용자의 명시적 승인 후에만 착수한다. C-2.30의 알림 부분은 `DONE`으로 표시하지 않는다.

2. **일괄 승인 안전 게이트를 먼저 추가했다 (C-2.30.1).** 일괄 승인은 이제 확인 게이트  
   (선택 개수 + 정적 안전 문구 + 확인 체크박스)를 거쳐야 실행된다.

3. **C-2.30 이후 로드맵 방향은 사용자가 명시적으로 선택해야 한다.** 신규 Phase 로드맵이  
   C-2.30까지 소진되어 명확한 다음 작업이 없다. 후보(A 알림 통합 / B 안정화 / C 파이프라인  
   프로덕션화 / D UI 폴리시)는 `NEXT-TASK.md`에 기록한다. 사용자 선택 전 새 기능 착수 금지.

**영향**:  
- `NEXT-TASK.md`는 "활성 구현 작업 없음" 상태로 두고 후보 방향만 제시한다.
- 알림 통합 착수 시 백엔드/시크릿을 다루므로 안전 검토 + 사용자 승인이 선행되어야 한다.
- 실전 매매/주문/브로커/실계좌 코드는 어느 후보에서도 건드리지 않는다.

---

## D-12. Paper 신호 기록은 TESTING 전환이 아니라 전용 PaperSignalSession + signal-only 잡으로 한다

**날짜**: 2026-06-26  
**상태**: 확정

**경위**:  
후보 → 제안 → 준비 → 준비승인 파이프라인 다음의 첫 "실행" 단계로 paper 신호 기록을 추가하려 했다.
초기 시도는 StrategyVersion을 TESTING으로 올리는 방식이었으나, runner의 `list_active()`가
ACTIVE/**TESTING**을 잡으므로 기본 활성인 `strategy_scheduler`(60초)가 즉시 대상화해 매 tick
SignalLog를 만드는 백그라운드 실행 효과가 생겼다(주문은 auto_trade=false로 막히지만). 이 결합을
의도적으로 롤백했다(준비승인은 상태를 바꾸지 않는 readiness-only로 확정).

**결정 내용**:

1. **버전은 DRAFT로 유지한다.** paper 신호 기록을 위해 StrategyVersion 상태를 바꾸지 않는다.
   DRAFT는 trade-capable runner(`list_active`)의 비대상이라 기존 매매 경로와 완전히 분리된다.

2. **전용 PaperSignalSession 테이블 + signal-only 잡으로 분리한다.** suggested_parameters에
   세션 상태를 욱여넣지 않고(first-class 레코드로 관리), 전용 잡 `paper_signal_session_runner`가
   active 세션의 DRAFT 버전으로 `SignalService.generate_and_log_signal`만 호출한다.

3. **잡은 TradeService/주문 클라이언트를 구성하지 않는다.** 구조적으로 주문 경로가 없다.
   broker_client는 시세(캔들) 조회에만 쓰인다. 잡은 기본 비활성(D-8)이며 사람이 명시 시작/중지한다.

**이유**:  
- TESTING 전환은 "준비"와 "실행"을 분리하지 못하고, 매매 가능한 runner에 결합된다.
- 전용 세션 + 전용 signal-only 잡은 주문 불가능성을 *구조적으로* 보장한다(코드에 주문 경로 부재).
- 세션을 stop하면 신호 기록이 즉시 멈춘다(명시적 수명주기).

**구현**: `paper_signal_sessions`(m1n2o3p4q5r6), `paper_signal_service.py`,
`run_paper_signal_session_job`(기본 OFF), `POST .../paper-signal-sessions` 외.

**이연**: 전략 버전 ACTIVE 승격, 실주문/자동매매, 실험 compare 자동화, 실전 승격은 별도 후속 작업.

---

## D-13. SignalLog에 paper_signal_session_id를 추가해 세션별 outcome을 정확 귀속한다

**날짜**: 2026-06-26  
**상태**: 확정

**경위**:  
Paper Signal Session의 신호 성과(outcome)를 세션 단위로 보려면 SignalLog를 세션에 귀속해야 한다.
SignalLog에는 `strategy_version_id`만 있고 세션 id가 없었다. 후보:
(A) SignalLog에 `paper_signal_session_id` 추가, (B) `strategy_version_id` + 시간창으로 추정,
(C) 세션 메타에 신호 id 목록 저장.

**결정 내용**:  
**Option A 채택** — SignalLog에 `paper_signal_session_id`(nullable FK, ON DELETE SET NULL)를 추가하고
(`n1o2p3q4r5s6`), `run_due_sessions`가 생성한 신호에 세션 id를 남긴다.

**이유**:  
- Option B는 **세션 재시작** 시 같은 제안의 동일 DRAFT 버전을 재사용하므로 version_id로는 세션 #1/#2를
  구분할 수 없다(오귀속). 정확 귀속에는 컬럼이 필요하다.
- additive nullable 컬럼이라 기존 데이터/경로에 영향 없음(일반 strategy_runner 신호는 NULL 유지).
- 프로젝트의 "왜 이렇게 됐는가" 추적 가치와 일치.

**영향**:  
- 세션 outcome 보드는 `paper_signal_session_id`로 정확히 필터링한다.
- outcome 계산은 기존 `SignalOutcomeService`(market_data forward 수익률)를 읽기 전용으로 재사용한다.
- 주문/체결/상태 전환과 무관하다.

---

## D-14. Paper Signal Session AI 분석 입력은 세션 중심 전용 서비스로 만든다(전략 입력 재사용 X)

**날짜**: 2026-06-26  
**상태**: 확정

**경위**:  
세션 성과를 AI에 넘길 분석 입력(payload)이 필요했다. 기존 `StrategyAnalysisInputService`(C-2.0)는
strategy_version 중심이고 성과를 **trades** 기반(`StrategyPerformanceService`)으로 계산한다. Paper Signal
Session은 **신호 전용(주문/거래 없음)**이고 후보→제안→준비→세션의 추적 정보가 핵심이라 형태가 다르다.

**결정 내용**:  
전용 `PaperSignalAnalysisInputService`를 만든다. 기존 read-only 패턴(payload + generated_at +
limitations, **AI 호출/DB 쓰기 없음**)을 따르되, outcome 요약은 `PaperSignalOutcomeService`를 재사용하고,
session/candidate_proposal/experiment_version/outcome_summary/safety 5개 섹션으로 세션 중심 구성한다.
recent_signals는 상한(10)으로 bounded.

**이유**:  
- 전략 입력은 trades 기반이라 신호 전용 세션에 안 맞는다(거래 0 → 의미 없는 성과).
- 세션 입력은 "왜 이 후보/제안인가 + 신호가 실제로 어땠나 + 안전 상태"가 핵심 — 추적 중심.
- 기존 read-only·no-AI 패턴은 그대로 따라 일관성 유지.

**이연**: 실제 AI provider 호출, AiAnalysisRun 생성, AI 제안 생성은 별도 후속 작업(승인 게이트 필요).

---

## D-15. PaperSignalSession AI 분석 run은 기존 AiAnalysisRun을 재사용한다(전용 테이블 X), V1은 markdown 리포트

**날짜**: 2026-06-26  
**상태**: 확정

**경위**:  
세션 분석 입력 다음 단계로 "AI 분석 리포트 생성"이 필요했다. 기존 `AiAnalysisRun`/`AiModelResponse`는
`target_type`(enum)+`target_id`(FK 없는 Integer)로 일반화돼 있어 strategy_version 외 대상도 담을 수 있다.

**결정 내용**:

1. **기존 `AiAnalysisRun` 재사용.** `target_type='paper_signal_session'`, `target_id=session_id`,
   `strategy_version_id`는 세션 연결 버전(추적용). 분석 입력은 `input_payload`(JSONB)에 보존.
   enum 두 값(`analysis_target_type`/`analysis_run_type`)만 additive로 추가(`o1p2q3r4s5t6`).

2. **전용 테이블을 만들지 않는다.** 새 테이블은 run/response 스키마와 기존 run 조회 UI/repo를 중복시킨다.
   `target_id`가 FK가 아니라 세션 id를 그대로 담을 수 있어 모델 변경도 불필요(인덱스만 추가).

3. **V1 출력은 markdown 리포트.** 모델 출력은 free-text `content`에 저장하고, 구조화 입력은
   `input_payload`에 둔다. JSON 스키마 강제 출력은 brittle하므로 보류(향후 제안 생성 단계에서 도입 가능).

4. **provider 기본은 fake(오프라인).** 실 provider(openai/anthropic)는 명시 요청 + API 키가 있을 때만
   factory를 통해 동작. 테스트는 fake/stub만 사용. 기본값에 실 provider를 넣지 않는다.

**이유**:  
- `target_id` FK 부재 + JSONB input_payload 덕에 모델이 이미 범용 → 재사용이 가장 작고 정직한 길.
- 기존 run 조회 API(`GET /analysis-runs/{id}`)·read 스키마를 그대로 재사용.
- enum downgrade는 PG가 값 제거를 지원하지 않아 index만 되돌린다(값은 미사용 시 무해).

**이연**: AI 제안 생성(CandidateStrategyProposal/ScannerRuleProposal), 전략 승격, 실거래는 별도 승인 게이트.

---

## D-16. Paper Signal AI 개선 제안은 기존 StrategyProposal을 재사용한다(전용 테이블·세션 컬럼 없음)

**날짜**: 2026-06-26  
**상태**: 확정

**경위**:  
세션 AI 분석 리포트에서 "개선 제안 초안"을 만드는 M1이 필요했다. `StrategyProposal`은 이미
`ai_analysis_run_id`(FK), `base_version_id`(FK), 자유 `source`, `suggested_parameters`, `status`(PENDING)와
승인 시 버전 생성 플로우(`proposal_service.approve`)를 갖춰 "AI 분석 run → 개선 제안" 용도로 설계돼 있다.
또한 `AnalysisProposalService.create_from_text`가 JSON 분석 출력을 검증해 PENDING 제안을 만든다.

**결정 내용**:

1. **기존 `StrategyProposal` 재사용.** 전용 `PaperSignalImprovementProposal` 테이블을 만들지 않는다.
   세션 추적은 `StrategyProposal.ai_analysis_run_id` → `AiAnalysisRun.target_id`(=세션 id)로 한다 →
   **세션 id 컬럼/마이그레이션 불필요.** base 버전은 `base_version_id`.

2. **CandidateStrategyProposal 미사용(V1).** 후보 중심이고 AI-run 링크/base 버전이 없어 부적합.

3. **구조화 우선 + 보수적 폴백.** 리포트가 검증 가능한 JSON 가설이면 `AnalysisProposalService`로 검증된
   param 변경 제안(source="ai_llm"). 아니면(마크다운/근거 부족) 현재 버전 파라미터 그대로의 **무변경**
   초안(source="paper_signal_analysis") + "insufficient evidence — no parameter change recommended".
   **파라미터를 지어내지 않는다.**

4. **V1은 PENDING까지만.** `proposal_service.approve`를 호출하지 않는다. 승인/버전 생성/머티리얼라이즈는
   기존 `ProposalsSection`에서 사람이 별도로.

**이유**:  
- `StrategyProposal`이 이미 범용(ai_analysis_run_id·base_version·free source) → 재사용이 가장 작고 정직.
- 기존 제안 검토 UI/승인 플로우 그대로 활용 → 중복 시스템 방지.

**주의(후속)**: `proposal_service.approve`는 status=TESTING 버전을 만든다(TESTING은 runner 대상, 단
auto_trade=false라 주문은 없음). paper-signal 제안 *승인/머티리얼라이즈* 단계에서 DRAFT 유지 vs TESTING을
의도적으로 결정해야 한다(readiness/activation 마일스톤과 동일한 고려).

**이연**: 제안 승인·버전 생성·compare·승격·실거래는 별도 승인 게이트.

---

## D-17. 신호 트랙 challenger는 DRAFT 전용 — 공유 approve(TESTING) 경로를 재사용하지 않는다 (가드레일)

**날짜**: 2026-06-26  
**상태**: 확정 (가드레일 / 설계 단계, 구현 미승인)

**경위**:  
M2(Paper Signal Version Comparison) 설계 중, 기존 `ProposalService.approve`가 새 `StrategyVersion`을
**TESTING**으로 만들고 runner의 `list_active()`가 ACTIVE/**TESTING**을 실행 대상으로 잡는다는 것을
확인했다. 즉 신호 전용 제안을 기존 approve로 머티리얼라이즈하면 버전이 **런너-대상**이 되어 신호가
자동 생성된다(배경 실행 효과; D-12와 동일한 결합 위험).

**결정 내용**:

1. **신호 트랙 challenger는 항상 DRAFT로 만든다.** `create_version(status=DRAFT)`(+ auto_trade=false)로
   생성하고, TESTING/ACTIVE로 올리지 않는다. DRAFT는 `list_active()` 비대상 → 런너가 보지 못한다.

2. **공유 `ProposalService.approve`를 신호 트랙용으로 수정하지 않는다.** approve는 strategy/intelligence
   트랙과 공유되는 매매-인접 경로다. 신호 challenger는 approve를 **호출하지 않는** 별도 경로로 만든다.

3. **비교(M2.1)는 읽기 전용 우선.** 버전/세션/실험 생성 없이 기존 두 세션의 신호 outcome을 비교한다.
   challenger 버전 생성(M2.2)은 별도 사람 승인 단계로 분리.

**이유**:  
- TESTING은 런너-대상 → "준비"와 "실행" 분리 실패. DRAFT 전용이 신호 전용 트랙의 핵심 안전 속성.
- 공유 approve를 조건부로 분기하면 매매-인접 임계 경로가 복잡해진다(회피).

**구현/상세**: `docs/design/M2-paper-signal-challenger-comparison.md`.

**이연**: M2 구현 자체(읽기 전용 비교·DRAFT challenger 준비)는 각각 별도 사람 승인 후 진행.

---

## D-18. Signal challenger 추적은 PENDING 제안의 created_version_id 링크로 하고, 공유 approve는 엔드포인트 가드로 막는다

**날짜**: 2026-06-26  
**상태**: 확정 (구현됨 — M2.2)

**경위**:  
M2.2(DRAFT-only Signal Challenger Preparation) 구현 시 두 가지 비자명한 선택이 필요했다:
(1) 준비된 DRAFT challenger 버전을 어떤 필드로 제안에 연결할지, (2) 공유 `ProposalService.approve`
(TESTING=runner-eligible 생성)가 signal 트랙 제안에 쓰이는 것을 어떻게 막을지.

**결정 내용**:

1. **추적 링크는 `StrategyProposal.created_version_id`를 재사용하되, 제안 상태는 PENDING으로 유지한다.**
   기존엔 approve만 이 필드를 채웠고 동시에 status를 APPROVED로 바꿨다. M2.2는 **승인이 아니므로**
   created_version_id만 채우고 **status는 PENDING 그대로** 둔다(review 필드 미설정). 새 컬럼/마이그레이션
   없이 idempotency(중복 준비 409)와 추적을 동시에 얻는다. 즉 "created_version_id != null"은 더 이상
   "승인됨"을 의미하지 않으며, signal 트랙에선 "DRAFT challenger 준비됨"을 뜻한다.

2. **공유 approve 차단은 엔드포인트 레벨 가드로 한다(서비스 내부 미변경).** `POST /strategy-proposals/{id}/approve`
   와 bulk-review의 approve 액션은 호출 전 `source=="paper_signal_analysis"`를 확인해 422(단건)/`failed` 격리
   (bulk)로 막는다. `ProposalService.approve` 내부는 건드리지 않아 strategy/intelligence 트랙 동작에 영향이 없다.

**이유**:  
- 전용 challenger 테이블(Option D)은 마이그레이션·UI 비용이 큼 → V1은 기존 필드 재사용이 최소·안전.
- 가드를 서비스 내부가 아닌 엔드포인트에 두면 공유 임계 경로 수정 없이 signal 트랙만 정확히 차단한다(D-17 §2 준수).

**주의**: created_version_id 의미가 트랙에 따라 다르므로, 향후 이 필드로 "승인 여부"를 추론하지 말 것
(status로 판단). bulk approve 격리는 [[followup-bulk-approve-safety]] 후속 과제와도 정합적이다.

**구현**: `app/services/paper_signal_challenger_service.py`, `app/api/v1/strategy_proposals.py`(가드),
`tests/test_paper_signal_challenger.py`.
