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

---

## D-19. M2.3 challenger 세션 브리지는 마이그레이션 승인 전까지 구현하지 않는다 — challenger를 기존 candidate/experiment 경로에 끼워넣지 않는다

**날짜**: 2026-06-26  
**상태**: 확정 (가드레일 / 갭 분석 단계, 구현 미승인)

**경위**:  
M2.3(준비된 DRAFT challenger → 사람-게이트 PaperSignalSession → baseline 비교) 갭 분석 결과, 기능적
브리지를 무-마이그레이션으로 안전하게 만들 수 없음을 확인했다(코드 검증):

1. 현재 세션 생성은 **CandidateStrategyProposal + Experiment + readiness**에 묶여 있다(시작 API/모델 모두).
2. M2.2 challenger는 **StrategyProposal.created_version_id**만 가진다(Experiment/variant/candidate
   proposal/readiness 없음).
3. `PaperSignalSession.candidate_strategy_proposal_id`는 **NOT NULL**.
4. 시작 경로는 버전을 **ExperimentVariant** 경유로 찾는다.
5. **per-proposal duplicate-active 가드** 때문에 baseline의 candidate proposal을 재사용하면 baseline·
   challenger 세션이 공존할 수 없다(비교 불가).
6. **'준비됨/비실행' 세션 상태가 없다**(active/stopped만).

**결정 내용**:

1. **M2.3 기능적 브리지는 명시적 마이그레이션 승인 전까지 구현하지 않는다.** 위 구조적 불일치 때문에 세션
   모델/시작 경로 변경 없이는 challenger 세션을 만들 수 없다 — 스키마 변경은 사람만 승인한다(작업 규칙 §6/§11).
2. **M2.2 challenger를 기존 CandidateStrategyProposal/Experiment 경로에 억지로 끼워넣지 않는다.** baseline의
   candidate proposal/experiment를 재사용하는 우회는 duplicate-active 가드와 충돌하고 의미를 흐린다(회피).
3. **무위험 대안은 Option B(UI 전용 헬퍼)뿐**이며, 이는 네비게이션만 돕고 기능 갭은 닫지 못함을 명시한다.

**향후 방향(승인 시, Option C/E)**: 사람-게이트 challenger 세션 *준비* 엔드포인트 + `prepared` 비실행 상태 +
nullable `candidate_strategy_proposal_id`/별도 `source_strategy_proposal_id`·`source_challenger_version_id`
링크. 세션 자동시작·잡 활성·SignalLog(prepare 시)·TESTING/ACTIVE·주문/거래 경로는 모두 없음(여전히 사람-게이트).

**이유**:  
- 갭이 데이터 모델 수준이라 UI/서비스 트릭으로는 안전하게 우회 불가 → 정직한 스키마 결정을 사람에게 위임.
- 우회(candidate proposal 재사용)는 baseline+challenger 동시 운용을 막아 비교 목적 자체를 깨뜨린다.

**구현/상세**: `docs/design/M2.3-challenger-session-workflow-gap.md`. 관련: [[followup-bulk-approve-safety]].

---

## D-20. Challenger 세션 스키마는 PaperSignalSession을 최소 확장(Option A)한다 — nullable candidate FK + source 컬럼 + `prepared` 상태

**날짜**: 2026-06-26  
**상태**: 확정 (스키마 방향 결정 / 마이그레이션은 사람 승인 대기)

**경위**:  
M2.4 스키마 설계 중, 런너 경로를 코드로 검증했다: `run_due_sessions`/`PaperSignalSessionRepository.list_active()`는
`status=="active"` + `strategy_version_id` + `symbol_code`만 사용하고 **`candidate_strategy_proposal_id`를 전혀
읽지 않는다.** `PaperSignalOutcomeService`/M2.1 비교도 `candidate_strategy_proposal_id`에 의존하지 않는다.

**결정 내용**:

1. **스키마 방향은 Option A** — `paper_signal_sessions`를 최소 확장한다: `candidate_strategy_proposal_id`를
   **nullable**로 풀고, `source_type`(기본 `candidate_proposal`)·`source_strategy_proposal_id`(nullable FK)·
   `baseline_session_id`(nullable self-FK)를 additive로 추가하며, 기존 `strategy_version_id`를 재사용한다.
   **새 세션 테이블도 Experiment도 만들지 않는다.**
2. **'준비됨/비실행' 상태는 `status="prepared"` 값으로 표현한다.** `list_active()`가 `status=="active"`만
   잡으므로 `prepared` 세션은 **런너에 보이지 않는다**(사람이 명시적으로 start해 active로 올릴 때까지). 상태기계:
   prepared → active → stopped. `status`는 문자열이라 enum 마이그레이션 불필요.
3. **거부**: B(side table — NOT NULL 블로커 미해소), D(병렬 세션 테이블 — 런너/outcome/M2.1이 두 형태 union 필요),
   E(D-19). C(오케스트레이션 테이블)는 A 위 후속 단계로 이연.
4. **마이그레이션 자체는 여전히 사람 승인 대기(D-19).** additive + constraint-relaxing이지만 스키마 변경이므로
   사람만 승인한다(작업 규칙 §6/§11).

**이유**:  
- 런너/outcome/비교가 candidate FK에 무관 → nullable화는 런타임 선택 로직을 바꾸지 않는다(최소 위험).
- `prepared` 상태는 기존 active 필터를 그대로 활용한 **런너 불가시성** 메커니즘 — 별도 started/active 구분 불필요.
- 단일 세션 테이블 유지 → M2.1 비교(한 테이블의 두 id)가 변경 없이 그대로 동작.

**다운그레이드 주의**: nullable→NOT NULL 복원은 challenger 행(NULL candidate FK)이 없을 때만 안전. 다운그레이드는
`source_type='signal_challenger'` 행을 먼저 제거(또는 실패)해야 한다 — 마이그레이션 `downgrade()`에 명시.

**구현/상세**: `docs/design/M2.4-challenger-session-schema-design.md`. 관련: [[D-19]], [[followup-bulk-approve-safety]].

---

## D-21. 세션 활성화(prepared→active)는 런너 활성화·신호 생성과 분리한다

**날짜**: 2026-06-26  
**상태**: 확정 (구현됨 — M2.5 Phase 3)

**경위**:  
M2.5 Phase 3에서 prepared challenger 세션을 active로 전환하는 사람-게이트 단계를 구현했다. "active"는
`PaperSignalSessionRepository.list_active()`가 잡는 상태라, 자칫 "활성화 = 신호 생성/매매"로 오해될 수 있다.

**결정 내용**:

1. **활성화는 세션 `status`만 prepared→active로 바꾼다.** 이는 전용 `paper_signal_session_runner` 잡의
   **대상 자격(eligibility)만** 부여한다. 활성화 자체는 잡을 켜지 않고, `run_due_sessions`를 호출하지 않으며,
   SignalLog/Trade/Order를 만들지 않는다. baseline/proposal/StrategyVersion/Experiment를 바꾸지 않는다.
2. **신호 기록은 별도 조건에서만 발생한다**: (a) `paper_signal_session_runner_enabled=true`(사람이 별도로 켬)
   + (b) 잡이 스케줄 실행될 때 `run_due_sessions`가 active 세션에 대해 SignalLog를 만든다. 주문/체결은 전 구간
   없음(잡이 TradeService를 구성하지 않음).
3. **활성화 응답은 이 분리를 명시한다**: `runner_eligible=true`, `runner_currently_enabled`(현재 플래그) +
   "Activation does not create signals immediately" 등 warnings. 활성화는 잡 설정을 바꾸지 않는다.

**이유**:  
- "준비/활성/실행/매매"를 한 단계씩 분리해 각 단계에 사람 확인을 두는 것이 이 프로젝트의 핵심 안전 패턴
  (D-12 계열). 활성화가 곧 신호/매매가 아니라는 점을 코드·응답·UI에서 반복 고지한다.
- 잡 활성(`*_enabled`)은 기본 OFF 불변식이라 활성화 단계에서 자동으로 켜지 않는다(작업 규칙 §4/§11).

**구현**: `app/services/paper_signal_challenger_session_service.py`(activate_prepared_session),
`app/api/v1/candidates.py`(POST .../activate), `tests/test_paper_signal_challenger_session_activate.py`.
관련: [[D-20]].

---

## D-22. Paper signal 운영은 세션 단위 수동 run-once부터 — 상시 스케줄러 활성보다 먼저

**날짜**: 2026-06-26  
**상태**: 확정 (가드레일 / 설계 단계, 구현 미승인)

**경위**:  
M2.7에서 active 세션의 SignalLog 생성 흐름을 설계하며 런너를 코드 검증했다: `run_due_sessions`는 **SignalLog만**
만들고(주문/Trade/TradeService 없음, broker는 캔들 시세 전용), 세션/버전 status를 바꾸지 않으며, candle dedupe와
장-마감 staleness 가드를 가진다. 또한 기존 `POST /autonomous-jobs/{job_id}/run`(`run_now`)이 **enabled 플래그와
무관하게** 잡을 1회 실행할 수 있는데, 이는 **모든 active 세션**을 한꺼번에 돌린다.

**결정 내용**:

1. **운영은 세션 단위 수동 run-once부터 시작한다(Option B).** 선택한 단일 active 세션에 대해 confirmed 게이트로
   1회만 신호를 평가한다. `paper_signal_session_runner_enabled`는 그대로 OFF, 스케줄러 트리거를 켜지 않는다.
2. **상시 스케줄러 활성(Option C)은 그 다음, 별도 사람 승인**으로만 한다. 범위(모든 active 세션 × 매 interval)와
   무인 백그라운드 쓰기 때문에 더 위험하다.
3. **어떤 운영 단계도 주문/거래 경로를 만들지 않는다.** run-once/잡 모두 TradeService/OrderService/broker 주문
   미구성, `KIS_REAL_TRADING_ENABLED=false`, 버전 DRAFT, auto_trade off.

**이유**:  
- "준비→활성→1회 실행→(나중에) 상시" 한 단계씩 사람 확인을 두는 패턴(D-12/D-21 계열). 세션 단위 1회 실행은
  범위가 작고(한 세션·한 tick·dedupe 한도) 멈춤이 자명하다.
- 기존 generic `run-now`는 전체 active를 돌려 challenger 테스트엔 과하다 → 세션-스코프 엔드포인트가 더 안전·명확.

**구현/상세**: `docs/design/M2.7-paper-signal-runner-operation-gate.md`. 관련: [[D-21]].

---

## D-23. baseline/challenger 신호 누적은 명시적 페어 run-once로 — 상시 스케줄러보다 먼저

**날짜**: 2026-06-26  
**상태**: 확정 (가드레일 / 설계 단계, 구현 미승인)

**경위**:  
M2.9에서 공정한 baseline↔challenger 비교를 위한 신호 누적 흐름을 설계했다. 단일 세션 run-once(M2.8)는 두 세션을
서로 다른 사람-트리거 시점에 평가해 비교 데이터가 불공정해질 수 있다.

**결정 내용**:

1. **페어 신호 누적은 명시적 페어 run-once부터 한다.** 한 사람-게이트 요청에서 **명시한 두 세션(baseline,
   challenger)만** 각각 1회씩 평가한다. 서버가 관계(challenger.baseline_session_id 일치)·동일 symbol·둘 다
   active·둘 다 DRAFT+auto_trade off를 **실행 전** 검증한다(Option B 권장; 검증을 클라이언트에 두는 Option A 회피).
2. **상시 스케줄러 활성(M2.7 Option C)은 그 다음, 별도 사람 승인.** 페어 run-once는 범위가 두 세션·한 tick으로
   한정되고 dedupe로 세션당 0/1을 보장한다(최대 2 SignalLog).
3. **페어 run-once도 주문/거래 경로를 만들지 않는다.** `list_active`/`run_due_sessions`/`run_now` 미사용,
   TradeService/OrderService/broker 주문 미구성, `KIS_REAL_TRADING_ENABLED=false`, 버전 DRAFT, auto_trade off.

**이유**:  
- 같은 요청에서 같은 시장 시점·같은 종목으로 두 세션을 샘플링해야 비교가 공정하다.
- 서버가 관계/심볼/상태를 강제하면 잘못 짝지어진 페어 실행을 막는다(클라이언트 검증보다 안전).

**구현/상세**: `docs/design/M2.9-pair-run-once-operation-design.md`. 관련: [[D-22]], [[D-21]].

---

## D-24. 상시 신호 운영은 pair-scoped·max-run 제한 계획부터 — 전역 런너 활성은 V1 아님

**날짜**: 2026-06-27  
**상태**: 확정 (가드레일 / 설계 단계, 구현 미승인)

**경위**:  
M2.13에서 상시(반복) paper signal 운영을 설계하며 기존 전역 런너를 코드 검증했다. `run_paper_signal_session_job`
→ `run_due_sessions`는 `list_active()`(status=="active" **전체**, candidate_proposal + signal_challenger 모두)를
순회하며 SignalLog만 만든다(주문/Trade 없음, 세션/버전 status 불변). 또한 `SchedulerControlService.run_now`는
**enabled 플래그를 확인하지 않고** `job.func(app)`을 직접 실행한다 → 플래그가 false라도 전체 active 1회 실행 가능.

**결정 내용**:

1. **기존 전역 `paper_signal_session_runner`를 첫 상시 V1으로 켜지 않는다.** 범위(전체 active × 매 interval)와
   run-now 우회 때문에 운영 리스크가 가장 크다.
2. **상시 운영은 pair-scoped, max-run 제한, SignalLog-only 반복 계획부터 한다(Option E).** 명시 baseline+
   challenger 페어만, `confirmed` 게이트, 두 세션 active + 관계/symbol/DRAFT/auto_trade off 검증(M2.8/M2.10
   게이트 재사용), `interval_seconds` + `max_runs`(상한 자동 종료) + 수동 중지 + 상태 노출.
3. **반복 계획도 주문/거래 경로를 만들지 않는다.** `run_due_sessions`/`run_now` 미사용(단일 디스패처가 검증된
   페어 1회 평가를 시간축으로 반복), TradeService/OrderService/broker 주문 미구성, `KIS_REAL_TRADING_ENABLED=false`,
   버전 DRAFT, auto_trade off.
4. **구현은 별도 승인 후에만(M2.14).** 신규 테이블 `paper_signal_recurring_runs` + 마이그레이션은 사람 승인 필요
   (D-20 계열). UI는 "runner 시작"/"잡 활성화" 금지, "페어 반복 신호 기록"으로 한정.

**이유**:  
- pair-scoped + max_runs는 SignalLog량·표면을 유한·예측가능하게 만든다(전역은 무한·불특정).
- "1회 → 반복"으로 가도 통제된 계획 객체가 선행돼야 종료 조건·사람 개입점·범위가 보장된다(D-22/D-23 연장선).

**구현/상세**: `docs/design/M2.13-recurring-runner-operation-design.md`. 관련: [[D-23]], [[D-22]], [[D-21]].

---

## D-25. 반복 계획의 활성화(active)는 실행이 아니다 — 디스패처는 별도 승인

**날짜**: 2026-06-27  
**상태**: 확정 (가드레일)

**경위**:  
M2.14B-1에서 반복 신호 *계획*에 상태 전환(prepared→active, active→stopped)을 추가했다. "active"라는 단어가
"실행 중"으로 오해될 수 있어 경계를 명문화한다.

**결정 내용**:

1. **활성화는 상태 전환일 뿐 실행이 아니다.** `active`는 "미래에 **별도로 승인될** 디스패처의 후보 상태"를
   의미한다. 활성화는 디스패처/잡/스케줄러를 시작하지 않고, SignalLog/주문/거래를 만들지 않으며,
   `SignalService.generate_and_log_signal`/페어 평가/`run_due_sessions`/`run_now`를 호출하지 않는다.
2. **active 계획은 별도 승인된 디스패처 없이는 절대 돌지 않는다.** `next_run_at`은 미래 디스패처용 메타데이터일
   뿐, 이를 읽어 실행하는 코드는 M2.14B-1에 존재하지 않는다(디스패처는 M2.14B-2, 별도 승인).
3. **활성화도 활성화 시점에 재검증한다.** 생성 이후 세션/버전 상태가 바뀌었을 수 있으므로, 활성화 시
   관계/symbol/active/DRAFT/auto_trade off/실거래 OFF/상시 런너 OFF를 다시 검증한다(M2.8/M2.10 코어 재사용).

**이유**:  
- 상태(eligibility)와 실행(mechanism)을 분리해야 "켜두면 자동으로 도는" 자동매매로의 미끄러짐을 막는다.
- 활성화 후 시간이 지나 세션/버전이 변할 수 있으므로 활성화 시점 재검증이 안전하다.

**구현/상세**: M2.14B-1 (`app/services/paper_signal_recurring_run_service.py`). 관련: [[D-24]], [[D-22]], [[D-21]].

---

## D-26. 반복 계획의 수동 tick-once는 디스패처가 아니다 — 선택 계획·SignalLog만

**날짜**: 2026-06-27  
**상태**: 확정 (가드레일)

**경위**:  
M2.14B-2에서 active 반복 계획을 사람이 1회 실행하는 `tick-once` 엔드포인트를 추가했다. 무인 디스패처(M2.14B-3)와
혼동되지 않도록 경계를 명문화한다.

**결정 내용**:

1. **수동 tick-once는 디스패처가 아니다.** 사람이 **하나의 plan_id를 골라 confirm한 한 번만** 실행한다.
   active 계획을 스캔하지 않고(`list_active`/`run_due_sessions`/`run_now` 미사용), 미래 실행을 스케줄하지 않으며,
   루프를 돌지 않는다. 선택한 계획의 baseline/challenger **두 세션만** 각각 1회 평가한다(최대 2 SignalLog).
2. **completed_runs는 페어 tick 시도 횟수를 센다(SignalLog 수가 아님).** 양쪽이 skip(중복/장마감/무신호)이어도
   시도 1회로 +1 한다. 평가 전 검증 실패/예외 시에는 증가하지 않는다(커밋 전 예외 → 롤백). `max_runs` 도달 시
   status=completed + next_run_at=NULL.
3. **tick 실행은 선택-계획-한정 · SignalLog-only로 유지한다.** 주문/거래 경로 없음(TradeService/OrderService/broker
   주문 미구성), `KIS_REAL_TRADING_ENABLED=false`, 버전 DRAFT + auto_trade off, 세션/버전/제안 status 불변(세션
   카운터만). SignalLog 생성은 M2.8 `evaluate_session`(주입된 signal-only SignalService) 경유만 — 재귀 서비스가
   직접 만들지 않는다.
4. **무인 디스패처/전체 active 실행(M2.14B-3)은 별도 명시 승인.** tick-once가 있어도 자동 반복은 금지된다.

**이유**:  
- "사람이 고른 한 계획, 한 번" 단위는 범위가 자명하고(두 세션·한 tick·dedupe 0/1) 멈춤이 명확하다(D-22/D-23 계열).
- 시도 단위 카운트는 무인 디스패처가 나중에 같은 의미로 max_runs 종료 조건을 재사용할 수 있게 한다.

**구현/상세**: M2.14B-2 (`paper_signal_recurring_run_service.tick_plan_once`,
`POST /paper-signal-recurring-runs/{id}/tick-once`). 관련: [[D-25]], [[D-24]], [[D-23]], [[D-22]].

---

## D-27. 반복 디스패처는 recurring_runs만 스캔한다 — 전역 런너 활성은 V1 영구 금지

**경위**:
M2.14B-3 설계(`docs/design/M2.14B-3-recurring-plan-dispatcher-design.md`)에서 무인 디스패처의 범위·금지선을
명문화한다. 기존 전역 `paper_signal_session_runner`는 모든 active PaperSignalSession을 실행하며,
`SchedulerControlService.run_now`가 enabled 플래그를 우회(`await job.func(app)`)하는 위험이 있어 재사용 불가.

**결정 내용**:

1. **디스패처를 구현한다면 `paper_signal_recurring_runs`만 스캔한다.** `PaperSignalSession.active` 직접 스캔,
   `run_due_sessions`(전체 active 세션 실행), 전역 `paper_signal_session_runner` 사용/활성, `run_now`,
   autonomous-jobs run-now, `list_active` 실행 경로는 **영구 금지**. 선택 조건은 `status='active' AND
   next_run_at<=now AND completed_runs<max_runs` + bounded batch.
2. **전역 런너 활성(Option D)은 첫 recurring V1로 영구 거부.** 너무 광범하고 D-24에 위배된다.
3. **디스패처 구현은 별도 비활성 기본 플래그 + 명시 승인이 있어야 한다.** 신규
   `paper_signal_recurring_plan_dispatcher_enabled=false`(기본 OFF, 잡 함수 첫 줄에서 검사 — run_now로
   강제돼도 no-op). 기존 `paper_signal_session_runner_enabled`는 분리·false 유지. 디스패처 tick도
   `KIS_REAL_TRADING_ENABLED=false` 불변 · SignalLog-only · Trade/Order/`broker.place_order` 도달 불가.
4. **디스패처 tick 의미론은 D-26(수동 tick)과 동일.** `tick_plan_once` 코어 재사용 — 새 평가 경로 신설 금지.
   completed_runs=시도 횟수, max_runs→completed, 실행 시점 재검증, row-lock(`FOR UPDATE SKIP LOCKED`)으로
   디스패처↔수동 race 방지(무마이그레이션). `running`/`locked_at`/실패카운트 컬럼은 선택적 후속 마이그레이션
   (별도 승인).

**이유**:
- 파일-스코프 스캔은 범위가 자명하고 멈춤(stop/max_runs)·킬스위치(플래그 OFF)가 명확하다.
- 전역 런너 재사용은 우회 위험·과범위라 안전 모델을 깨뜨린다. 코어 재사용은 검증 드리프트를 막는다.
- 설계 readiness(13/13)는 수동 UX 명확성 기준이며, 디스패처 구현 승인과는 별개다.

**구현/상세**: 설계 문서만(M2.14B-3a). 구현 미착수. 관련: [[D-26]], [[D-25]], [[D-24]].

## D-28. Leader Trend 스캐너 경고는 3계층 — 전략-극단(큰 gain/range)은 비차단

**경위**:
M2.15C-1 스캐너는 `range_ratio>4`·`gain>500%`·`일일점프>50%`를 한 통의 경고로 묶어 모두
`operationally_safe=False`로 차단했다. M2.15C-2(라이브 adjusted=True 프로브)는 5종 모두 high_52w·low_52w가
**raw와 정확히 일치**(수정주가 아티팩트 아님)함을, M2.15C-3는 차단된 005930·000660이 **일일점프 ≤19.1%·저가 다일
연속·OHLCV 완전**(데이터 무결)임을 확인했다. 즉 대형 gain/range는 **데이터 결함이 아니라 강한 주도주의 실제
특성**이며, Candidate B(`gain>=200`)는 본래 큰 gain을 노린다 → 단일 임계로 하드 차단하면 전략 의도와 충돌.

**결정 내용**:
1. **경고를 3계층으로 분리한다.** ① `hard_errors`(nonpositive·high<low·close 범위밖·null·중복일) → `invalid_data`,
   분류 불가. ② `adjustment_warnings`(미설명 일일 종가 점프 >50%) → **운영 차단**, 후보면 `*_raw_needs_adjusted_review`,
   `operationally_safe=False`. ③ `strategy_extreme_warnings`(`range_ratio>4`·`gain>500%`) → **비차단**,
   `is_strategy_extreme=True`만 표시.
2. **`range_ratio`·`gain` 단독으로는 운영 분류를 하드 차단하지 않는다.** 깨끗한 데이터의 강한 주도주(Candidate B)는
   운영 후보로 노출하되 high-extension/high-risk로 표기.
3. **연구/운영 버킷 분리.** `candidate_bucket_research`(경고 무관 A/B)와 `candidate_bucket_operational`(위 규칙 반영).
   `operationally_safe = is_data_valid AND ready_for_52w AND not is_adjustment_suspect`(전략-극단 무관).
4. **여전히 후보일 뿐 매수 신호 아님.** 스캐너는 읽기 전용 · 영속화 0 · SignalLog/Trade/Order 0 · 주문/스케줄러 도달
   불가. 후보 영속화는 별도(M2.15D).

**이유**:
- 데이터 무결성 결함과 전략-극단(강한 추세)은 성격이 다르다 — 한 통에 묶으면 진짜 주도주를 버린다.
- adjusted=True가 경고를 해소하지 못함을 라이브로 증명(M2.15C-2) → 수정주가 채택 실익 없음. 차단 명분은 데이터
   무결성 증거(분할 같은 점프)로 한정해야 한다.

**구현/상세**: `leader_trend_scanner.py`(M2.15C-4) + 테스트(c1 갱신·c4 신규). 5종 read-only 재스캔으로
005930·000660이 운영 `B`(safe=True, strategy_extreme)로, 035420/005380/051910이 `none`으로 확인. DB write 0 ·
마이그레이션 0. 관련: [[D-24]].

## D-29. Leader Trend 후보 API는 read-only 연구용 — 매수 신호 아님 · 영속화/주문 없음

**경위**:
M2.15D-1~3A에서 5종 후보 데이터의 스케일·52주 이력을 KIS 실전 도메인으로 검증(현재가 ≤0.7%·52주 저점 정확 일치·
B 분류 재현). 단 KIS 실전·모의 도메인이 동일 데이터를 반환하고 비-KIS 독립 소스가 환경에 없어 실세계 독립성은
미확증. 이 전제에서 후보를 노출하되 "운영/거래 승인"이 아닌 **연구용**으로만 한정한다.

**결정 내용**:
1. **`GET /api/v1/leader-trend/candidates`는 read-only.** 적재 `market_data` 1d만 읽고 라이브 KIS·일봉 fetch·DB
   write·후보 영속화·CandidateEvent 생성·SignalLog/Trade/Order·broker/주문·스케줄러를 일절 하지 않는다.
2. **후보는 매수 신호가 아니다.** 응답은 `research_only=true`·`not_buy_signal=true`·`safety_warning`·
   `provenance_warning`(비-KIS 독립성 미확증)을 항상 포함하고, buy/order/trade/signal/recommendation을 긍정 라벨로
   쓰지 않는다.
3. **기본 범위는 검증된 pilot_5만.** 명시 심볼은 최대 5, wildcard/all/universe 거부. 20/110/전체 확장은 별도 승인.
4. **후보 영속화·자동 제안·실배치는 별도 승인 단계**(M2.15E 이후). 본 API는 표면 노출까지만.

**이유**:
- 검증은 KIS 생태계 내부 정합성까지 — 실세계 독립성 미확증이므로 "연구용+출처 경고"가 정직한 노출 수준이다.
- read-only·무영속·무부작용으로 안전 모델(주문/신호/스케줄러 도달 불가)을 유지하면서 후보를 사람이 검토 가능.

**구현/상세**: `app/api/v1/leader_trend.py` + `main.py` 등록 + 테스트(M2.15D-3B, 6) + 전체 1790 passed. DB write 0 ·
마이그레이션 0 · 프론트 0. 관련: [[D-28]], [[D-24]].

---

## D-30. 매매 타임프레임은 일봉이 기본 — 분봉 매매는 수수료 드래그로 폐기 방향

**날짜**: 2026-07-03
**상태**: 확정 (근거: docs/strategy/strategy-effectiveness-analysis.md)

**결정 내용**: 분봉(1m/5m) 고빈도 매매는 KR 수수료+거래세 구조에서 백테스트 전 구간
마이너스. 신규 전략은 일봉 기본, 기존 분봉 전략은 신호 관찰용으로 강등 후 일몰.

**이유**: 14일 130거래에 원금 ~20%가 비용으로 소진. C-6.18 데이터 오염 수정 후에도
분봉 신호의 구조적 열위는 동일.

**영향**: 제안·백테스트·러너가 timeframe=1d 지원 (C-6.18/6.20). v334/v335가 일봉 파일럿.

---

## D-31. 만능 전략은 없다 — 국면·종목 특성 조건부 조합이 방침

**날짜**: 2026-07-03
**상태**: 확정

**결정 내용**: breakout=추세 국면 전용(횡보 종목 1년 -43%), rsi_reversion(oversold 40)=
횡보·하락 방어 전용. 단일 전략 최적화가 아니라 레짐/종목 특성에 따른 조건부 가동을 지향.
자동매매의 성과 목표는 "시장 이기기"가 아니라 "MDD 줄이면서 벌기".

**영향**: 다음 대형 과제 = 종목-전략 적합성 매칭. 매크로 레짐(C-2.49)·변동성
밴드(C-6.4)·soft kill(C-6.5)이 이 방침의 실행 인프라.

---

## D-32. 제안 생성 시 백테스트 자동 첨부 — 단 verdict는 참고, 승인은 사람

**날짜**: 2026-07-03
**상태**: 확정

**결정 내용**: 모든 전략 제안에 base vs proposed 백테스트 비교를 자동 첨부한다
(suggested_parameters **원문**을 검증 — 승인이 만드는 버전과 동일해야 함).
verdict(proposed_better 등)는 라벨일 뿐 승인 흐름을 자동으로 바꾸지 않는다.

**영향**: paper 검증 며칠 → 초 단위 1차 검증. 백테스트 예측력 자체를 회고와 대조하는
메타 지표(backtest-accuracy)로 신뢰도를 계량한다.
