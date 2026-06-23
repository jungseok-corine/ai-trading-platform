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
