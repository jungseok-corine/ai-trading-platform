# AI Analysis Workflow — Dual-Model Debate Architecture (C-2.2)

작성일: 2026-06-17  
상태: **설계 문서** — 구현 전 참고용. 이 문서 자체는 코드가 아니다.

---

## 1. 목표

### 1.1 핵심 목표

GPT(OpenAI)와 Claude(Anthropic) 두 LLM이 동일한 분석 주제를 독립적으로 평가하고,  
서로의 분석을 보완/비판한 뒤, 최종 종합 리포트를 생성하는 **dual-model debate workflow** 구현.

### 1.2 분석 목적 제한

> **이 시스템은 투자 조언 도구가 아니다.**

- 목적: 자동매매 **전략 및 시스템의 품질 개선** 분석
- 분석 결과는 사람이 검토한 뒤 직접 적용 여부를 결정
- LLM 출력은 언제나 "제안" 수준이며, 사실로 간주하지 않음
- AI가 실거래 주문을 실행하거나 기존 전략을 자동 수정하는 것은 명시적으로 금지

### 1.3 분석 가치 사슬

```
raw data → analysis input payload → prompt → LLM analysis
→ critique → synthesis → report → human review → optional action
```

---

## 2. 분석 타입

| analysis_type         | 설명                               | 트리거      | 주요 데이터 소스                            |
|-----------------------|------------------------------------|-------------|---------------------------------------------|
| `daily_market`        | 시장 데이터 일별 요약 분석         | 스케줄(장마감) | market_data, 전일 대비 가격 변동              |
| `daily_trading`       | 당일 신호/체결 품질 분석           | 스케줄(장마감) | signal_logs, trades, signal outcome         |
| `strategy_performance`| 특정 전략 버전의 성과 심층 분석    | 사용자 요청  | StrategyAnalysisInputRead (C-2.0 산출물)     |
| `user_question`       | 사용자가 입력한 임의 질문 분석     | 사용자 요청  | 질문 + 관련 데이터 동적 수집                  |

---

## 3. Full Debate Workflow

```
                        ┌─────────────────────┐
                        │  Input Payload 생성   │
                        │  (AnalysisInputSvc)   │
                        └──────────┬──────────┘
                                   │
               ┌───────────────────┴───────────────────┐
               ▼                                       ▼
  ┌─────────────────────┐               ┌─────────────────────┐
  │  GPT Independent    │               │ Claude Independent   │
  │     Analysis        │               │     Analysis         │
  │  (model_a_response) │               │  (model_b_response)  │
  └──────────┬──────────┘               └──────────┬──────────┘
             │                                     │
             ▼                                     ▼
  ┌─────────────────────┐               ┌─────────────────────┐
  │  Claude critiques   │               │  GPT critiques       │
  │  GPT's analysis     │               │  Claude's analysis   │
  │  (critique_b_of_a)  │               │  (critique_a_of_b)   │
  └──────────┬──────────┘               └──────────┬──────────┘
             │                                     │
             └─────────────────┬───────────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │   Synthesis / Final      │
                  │   Report 생성            │
                  │  (GPT or Claude 중 택1)  │
                  └──────────┬──────────────┘
                             │
                  ┌──────────▼──────────────┐
                  │  ai_analysis_reports에   │
                  │  저장                    │
                  └──────────┬──────────────┘
                             │
                  ┌──────────▼──────────────┐
                  │  UI 표시 + 사람 검토     │
                  └─────────────────────────┘
```

### 3.1 단계별 설명

| 단계 | 이름 | 설명 |
|------|------|------|
| 0 | Input Payload | 분석 대상 데이터를 구조화된 payload로 변환 (C-2.0 재사용) |
| 1a | GPT Independent | GPT가 payload를 독립적으로 분석, system prompt에 투자 조언 금지 명시 |
| 1b | Claude Independent | Claude가 동일 payload를 독립적으로 분석 |
| 2a | Claude critiques GPT | Claude가 GPT 분석의 논리적 허점·누락 지적 |
| 2b | GPT critiques Claude | GPT가 Claude 분석의 논리적 허점·누락 지적 |
| 3 | Synthesis | 양측 분석과 critique를 종합한 최종 리포트 생성 (synthesizer 모델 지정) |
| 4 | Persist | `ai_analysis_reports`에 최종 리포트 저장, 각 응답은 `ai_model_responses`에 보존 |
| 5 | UI | 프론트엔드에서 debate 흐름 및 최종 리포트 표시 |

---

## 4. MVP Workflow — 단계별 구현

처음부터 full debate를 구현하지 않는다.  
각 Phase는 독립적으로 동작 가능하며, 이전 Phase 결과를 그대로 사용한다.

### Phase 1 — Single-Model Report

```
input payload → [GPT or Claude] → report 저장 → UI
```

- 모델 한 개만 사용
- debate 없음, critique 없음
- 빠른 검증: API 연결, 비용, 응답 품질 확인
- 산출물: `ai_analysis_runs`, `ai_model_responses` 테이블

### Phase 2 — Dual Independent Analysis

```
input payload → GPT analysis
             → Claude analysis
             → 두 결과를 side-by-side로 저장/표시
```

- critique 없음
- 두 모델의 관점 차이 관찰
- 산출물: `ai_analysis_runs`에 `model_a_response_id`, `model_b_response_id` 추가

### Phase 3 — Critique Round

```
input payload → dual analysis → GPT critiques Claude → Claude critiques GPT → 저장
```

- `ai_debate_rounds` 테이블 도입
- critique prompt 설계가 핵심 (단순 반박 금지, 구체적 개선 제안 요구)

### Phase 4 — Final Synthesis

```
Phase 3 결과 → synthesis prompt → final report → ai_analysis_reports 저장
```

- synthesizer 모델은 설정 가능 (기본: Claude)
- synthesis는 양쪽 critique를 모두 받아 작성

### Phase 5 — Scheduled Daily Analysis

```
APScheduler (장마감 후) → daily_market / daily_trading → Phase 4 workflow → 저장
```

- 스케줄러 job 추가 (기존 APScheduler 확장)
- 실패 시 재시도 로직, 알림 없음 (단순 로그)

### Phase 6 — User Question Analysis

```
사용자 질문 입력 → 관련 데이터 수집 → analysis input 생성 → Phase 4 workflow → 즉시 반환
```

- REST API: `POST /api/v1/analysis/question`
- 응답 시간이 길어질 수 있으므로 async job + polling 패턴 고려

---

## 5. 권장 DB 모델

> DB 스키마 변경은 각 구현 Phase에서 마이그레이션으로 진행.  
> 아래는 필드 제안이며, 구현 시 조정될 수 있다.

### 5.1 `ai_analysis_runs` — 분석 실행 단위

```sql
CREATE TABLE ai_analysis_runs (
    id                SERIAL PRIMARY KEY,
    analysis_type     VARCHAR(50) NOT NULL,   -- daily_market / daily_trading / strategy_performance / user_question
    workflow_phase    VARCHAR(20) NOT NULL,   -- single / dual / debate / synthesis
    status            VARCHAR(20) NOT NULL,   -- pending / running / completed / failed
    strategy_version_id INT REFERENCES strategy_versions(id),  -- nullable (strategy_performance 타입만)
    user_question     TEXT,                   -- nullable (user_question 타입만)
    input_payload     JSONB,                  -- StrategyAnalysisInputRead 또는 커스텀 payload
    final_report_id   INT,                    -- ai_analysis_reports.id (완료 시)
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ,
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5.2 `ai_model_responses` — 각 모델의 개별 응답

```sql
CREATE TABLE ai_model_responses (
    id              SERIAL PRIMARY KEY,
    run_id          INT NOT NULL REFERENCES ai_analysis_runs(id),
    round           VARCHAR(30) NOT NULL,  -- independent_a / independent_b / critique_a_of_b / critique_b_of_a / synthesis
    model_provider  VARCHAR(20) NOT NULL,  -- openai / anthropic
    model_name      VARCHAR(50) NOT NULL,  -- gpt-4o / claude-sonnet-4-6 등
    prompt_type     VARCHAR(30),           -- overview / risk / improvement / critique / synthesis
    system_prompt   TEXT,
    user_prompt     TEXT,
    response_text   TEXT,
    input_tokens    INT,
    output_tokens   INT,
    latency_ms      INT,
    finish_reason   VARCHAR(30),           -- stop / length / error
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5.3 `ai_analysis_reports` — 최종 리포트

```sql
CREATE TABLE ai_analysis_reports (
    id                     SERIAL PRIMARY KEY,
    run_id                 INT NOT NULL REFERENCES ai_analysis_runs(id),
    analysis_type          VARCHAR(50) NOT NULL,
    strategy_version_id    INT REFERENCES strategy_versions(id),
    report_date            DATE NOT NULL,  -- 분석 기준일
    summary                TEXT,
    full_report            TEXT,           -- markdown 형식 최종 리포트
    suggested_parameters   JSONB,          -- AI가 제안한 파라미터 후보 (사람 승인 전까지 미적용)
    model_a_response_id    INT REFERENCES ai_model_responses(id),
    model_b_response_id    INT REFERENCES ai_model_responses(id),
    synthesis_response_id  INT REFERENCES ai_model_responses(id),
    human_reviewed         BOOLEAN NOT NULL DEFAULT FALSE,
    human_review_note      TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5.4 `ai_debate_rounds` — Critique 라운드 (Phase 3+)

```sql
CREATE TABLE ai_debate_rounds (
    id              SERIAL PRIMARY KEY,
    run_id          INT NOT NULL REFERENCES ai_analysis_runs(id),
    round_no        SMALLINT NOT NULL,        -- 1, 2, ... (향후 multi-round debate 지원)
    critic_model    VARCHAR(20) NOT NULL,     -- openai / anthropic
    target_response_id INT REFERENCES ai_model_responses(id),
    critique_response_id INT REFERENCES ai_model_responses(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5.5 테이블 관계도

```
ai_analysis_runs
  ├── ai_model_responses (run_id, 다수)
  │     └── [independent_a, independent_b, critique_a_of_b, critique_b_of_a, synthesis]
  ├── ai_debate_rounds (run_id, 다수)
  └── ai_analysis_reports (run_id, 1:1)
        ├── model_a_response_id → ai_model_responses
        ├── model_b_response_id → ai_model_responses
        └── synthesis_response_id → ai_model_responses
```

---

## 6. Provider Abstraction 설계

### 6.1 공통 인터페이스

```python
# app/services/ai/base.py (구현 Phase에서 확정)

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class AnalysisRequest:
    system_prompt: str
    user_prompt: str
    max_tokens: int = 4096
    temperature: float = 0.3

@dataclass
class AnalysisResponse:
    response_text: str
    input_tokens: int
    output_tokens: int
    model_name: str
    finish_reason: str
    latency_ms: int

class AnalysisClientBase(ABC):
    @abstractmethod
    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse: ...

    @abstractmethod
    def provider_name(self) -> str: ...
```

### 6.2 OpenAI 클라이언트

```python
# app/services/ai/openai_client.py

class OpenAIAnalysisClient(AnalysisClientBase):
    """OpenAI API를 통한 분석 클라이언트.

    - 기본 모델: gpt-4o
    - timeout: 60s per request
    - retry: 최대 3회 (exponential backoff, 5xx/429만)
    - API key: 환경 변수 OPENAI_API_KEY
    """

    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse: ...
    def provider_name(self) -> str: return "openai"
```

### 6.3 Anthropic 클라이언트

```python
# app/services/ai/anthropic_client.py

class AnthropicAnalysisClient(AnalysisClientBase):
    """Anthropic API를 통한 분석 클라이언트.

    - 기본 모델: claude-sonnet-4-6
    - timeout: 60s per request
    - retry: 최대 3회 (exponential backoff, 5xx/529만)
    - API key: 환경 변수 ANTHROPIC_API_KEY
    """

    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse: ...
    def provider_name(self) -> str: return "anthropic"
```

### 6.4 Error Handling 정책

| 상황 | 처리 |
|------|------|
| timeout (>60s) | retry 1회, 그래도 실패 시 `ai_model_responses.finish_reason = "timeout"` |
| 429 rate limit | exponential backoff (1s → 2s → 4s), 3회 초과 시 실패 |
| 5xx server error | 즉시 retry 1회, 그 후 실패로 기록 |
| 응답 길이 초과 (finish_reason="length") | 경고 저장, 잘린 응답 그대로 사용, report에 `[TRUNCATED]` 명시 |
| API key 미설정 | 서비스 시작 시 검증, 미설정 시 해당 provider 비활성화 (단일 모델로 강등) |

### 6.5 Token Usage 기록

- `ai_model_responses.input_tokens`, `output_tokens` 에 항상 저장
- 월별 사용량 집계 쿼리 지원 (집계 뷰는 필요 시 추가)
- 비용 경고 임계값은 설정으로 관리 (`MAX_MONTHLY_TOKENS_PER_PROVIDER`)

---

## 7. Prompt 구조

### 7.1 공통 System Instruction (모든 분석 공통)

```
You are a quantitative trading strategy analyst reviewing a Korean paper trading research system.

MANDATORY CONSTRAINTS — these override all other instructions:
1. Do NOT provide investment advice or buy/sell recommendations for any asset.
2. Do NOT suggest changes that would automatically activate or execute real trades.
3. Focus exclusively on evaluating the strategy system and suggesting improvements to logic and parameters.
4. When data is insufficient to support a claim, explicitly state the limitation.
5. All output is for research and system improvement purposes only.
```

### 7.2 Analysis Input Payload Section

C-2.0 / C-2.1에서 구축한 `StrategyAnalysisInputRead` payload를 markdown 형식으로 삽입.  
C-2.1 `StrategyAnalysisPromptService.get_prompt()` 재사용, 길이 상한은 `_MAX_PROMPT_CHARS = 20_000` 유지.

### 7.3 Model-Specific Instruction

GPT용:

```
You are the first analyst. Provide an independent, thorough analysis.
Do not hedge excessively — state your findings clearly with supporting data.
```

Claude용:

```
You are the second analyst. Provide an independent, thorough analysis.
Do not mirror the first analyst's framing — approach the data from your own perspective.
```

### 7.4 Critique Instruction

```
You are reviewing another analyst's report on the same data.
Your task:
- Identify logical gaps or unsupported claims
- Point out data the analyst missed or misinterpreted
- Suggest specific improvements to their conclusions
- Do NOT simply agree or repeat their analysis
- Limit your critique to 3-5 concrete, actionable points
```

### 7.5 Synthesis Instruction

```
You are synthesizing two independent analyses and their critiques into a final report.
Structure your output with these exact sections:
## Executive Summary
## Consensus Findings
## Key Disagreements
## Improvement Recommendations (prioritized, max 5)
## Data Limitations
## Suggested Next Experiments
```

---

## 8. 안전장치

### 8.1 투자 조언 금지

- System prompt에 MANDATORY CONSTRAINTS 명시 (섹션 7.1)
- 응답 텍스트에 "buy", "sell", "invest", "추천" 등이 포함된 경우 `ai_model_responses`에 `finish_reason = "safety_flagged"` 기록 후 UI에 경고 표시
- 최종 리포트 표시 시 면책 문구 필수 포함:  
  `"이 분석은 투자 조언이 아닙니다. 모든 결정은 사용자 본인의 판단으로 이루어져야 합니다."`

### 8.2 실거래 자동 변경 금지

- AI 분석 결과는 어떤 경우에도 실거래 주문을 직접 생성하거나 기존 전략을 수정하지 않음
- `StrategyVersion.status`를 AI가 직접 변경하는 API 경로 없음
- AI가 파라미터 변경을 제안하는 경우 `ai_analysis_reports.suggested_parameters` (JSONB)에만 저장

### 8.3 사람 승인 워크플로우

```
AI 파라미터 제안
  → ai_analysis_reports.suggested_parameters 에 저장
  → human_reviewed = FALSE
  → 사용자가 UI에서 "이 제안으로 새 버전 생성" 버튼 클릭
  → 새 strategy_version 생성 (status=DRAFT)
  → 사용자가 직접 TESTING → ACTIVE 전환
```

- AI가 `ACTIVE` 상태의 전략을 직접 생성하거나 전환하는 경로 없음

### 8.4 데이터 부족 명시

- 분석 신호 < 10개, market_data row_count < 50 인 경우 system prompt에 명시적 경고 삽입
- LLM에게 "데이터가 충분하지 않으면 분석 불가 판정을 내리라"고 지시
- 분석 불가 판정도 `ai_model_responses`에 저장 (리포트 생성 중단)

---

## 9. Daily Scheduled Analysis 설계

### 9.1 실행 시점

- 한국 주식시장 장마감: 15:30 KST
- 스케줄: 매 평일 15:45 KST (마감 후 15분 여유)
- APScheduler cron job으로 추가 (기존 `scheduler/jobs.py` 확장)

### 9.2 Daily Workflow

```
1. market_data 최신 여부 확인
   → 당일 데이터 없으면 skip (공휴일/주말 자동 처리)

2. daily_market 분석
   → MarketDataRepository.get_global_summary() 로 전일 대비 가격 변동 수집
   → analysis input 생성
   → dual-model analysis (Phase 4 workflow)
   → ai_analysis_reports 저장

3. daily_trading 분석
   → 당일 signal_logs + trades 수집
   → signal outcome summary (5m/15m/30m/60m)
   → dual-model analysis
   → ai_analysis_reports 저장

4. strategy_performance 분석 (ACTIVE 전략만)
   → ACTIVE strategy_version 목록 조회
   → 전략 수가 많으면 최근 신호 기준 상위 N개만 처리
   → 각 전략마다 StrategyAnalysisInputService.get_analysis_input() 호출
   → 순차 처리 (병렬 처리는 rate limit 위험 — Phase 5에서 보수적으로 시작)

5. 실행 결과 기록
   → ai_analysis_runs.status = completed / failed
   → 실패해도 다음 분석은 계속 진행 (독립 실행)
```

### 9.3 비용 제어

- 하루 최대 API 호출 수: 설정 파라미터로 관리 (`MAX_DAILY_ANALYSIS_RUNS`)
- ACTIVE 전략이 많을 경우 신호 수 기준 상위 `MAX_STRATEGY_ANALYSIS_PER_DAY` 개만 처리
- 초과 시 나머지는 다음 날 처리 또는 skip

---

## 10. User Question Analysis 설계

### 10.1 API

```
POST /api/v1/analysis/question
{
  "question": "삼성전자 전략의 최근 성과가 왜 나빠졌는지 분석해줘",
  "strategy_version_id": 42,    // optional
  "include_market_data": true    // optional
}

→ 202 Accepted
{
  "run_id": 123,
  "status": "pending"
}

GET /api/v1/analysis/runs/{run_id}
→ 200 OK (status: pending / running / completed / failed)
→ 완료 시 final_report_id 포함
```

### 10.2 질문 처리 흐름

```
1. 질문 파싱
   → 관련 strategy_version_id가 명시된 경우 → StrategyAnalysisInputService 재사용
   → 미명시 경우 → 질문 텍스트 기반 최근 ACTIVE 전략 자동 선택 (단순 매칭)

2. Analysis Input 생성
   → strategy_performance 타입 payload 또는 범용 market summary

3. Dual-Model Analysis (Phase 4 workflow 재사용)
   → user_question을 추가 context로 삽입

4. 결과 반환
   → ai_analysis_reports.full_report 반환
   → 소요 시간 예상: 30~120초 (모델·데이터 크기 따라)
```

### 10.3 비동기 패턴

- `POST /question` → 즉시 `run_id` 반환 (202)
- 백그라운드 task로 analysis 실행
- `GET /runs/{run_id}` 로 폴링 (프론트엔드 30s 간격 권장)
- SSE(Server-Sent Events) 스트리밍은 Phase 6 이후 고려

---

## 11. 구현 순서

| Phase | 코드명 | 내용 | 선행 조건 |
|-------|--------|------|-----------|
| C-2.2 | **이 문서** | 설계 문서 작성 | — |
| C-2.3 | Provider Abstraction | `AnalysisClientBase`, `OpenAIAnalysisClient`, `AnthropicAnalysisClient`, retry/timeout/token 기록 | C-2.2 |
| C-2.4 | Single-Model Run | `ai_analysis_runs`, `ai_model_responses` 테이블 마이그레이션, `AnalysisRunService.run_single()`, API endpoint | C-2.3 |
| C-2.5 | Dual Independent | `run_dual()`, 두 모델 독립 분석, side-by-side 저장 | C-2.4 |
| C-2.6 | Critique + Synthesis | `ai_debate_rounds` 테이블, `run_debate()`, `ai_analysis_reports` 생성 | C-2.5 |
| C-2.7 | Scheduled Daily | APScheduler job 추가, daily_market / daily_trading / strategy_performance 자동 실행 | C-2.6 |
| C-2.8 | UI | 분석 실행 요청, 진행 상태 표시, report viewer, user question 입력창 | C-2.6 |

---

## 12. 명시적으로 하지 않을 것

다음 기능은 이 workflow에 포함되지 않는다.

| 항목 | 이유 |
|------|------|
| AI가 직접 실거래 주문 실행 | 안전장치 (섹션 8.2) — 사람 승인 없이 실거래 금지 |
| AI가 기존 전략을 자동 수정/활성화 | 동일. AI 제안은 `suggested_parameters` 에만 저장 |
| 외부 뉴스/시장 데이터 수집기 | 별도 모듈로 분리 — 이 workflow의 scope 외 |
| LLM 응답의 사실 검증 | LLM 출력은 언제나 "제안" 수준으로 취급 |
| 실시간 스트리밍 분석 | Phase 6 이후 검토 (SSE/WebSocket) |
| 멀티-라운드 debate (3회 이상) | `ai_debate_rounds.round_no`로 확장 가능 설계이나 초기 구현은 1라운드 |
| 분석 결과 기반 자동 backtesting | backtesting 엔진이 별도 필요 — 현재 scope 외 |

---

## 13. 설계 리스크 및 미결 사항

| 리스크 | 설명 | 완화 방안 |
|--------|------|-----------|
| LLM 응답 품질 편차 | GPT/Claude 응답 품질이 일정하지 않을 수 있음 | Phase 1에서 prompt 품질 집중 검증 후 Phase 2 진행 |
| API 비용 | Daily debate = 하루 6+ API 호출 × 전략 수 | `MAX_DAILY_ANALYSIS_RUNS` 설정으로 제한, Phase 5에서 실측 후 조정 |
| 응답 지연 | Synthesis까지 최대 2~3분 소요 가능 | 비동기 job + polling 패턴으로 UI 블로킹 없음 |
| critique 의미 없는 동의 | 두 모델이 서로 동의만 할 경우 debate 무의미 | critique prompt에 "동의 금지, 반드시 3개 이상 구체적 이견 제시" 명시 |
| 데이터 부족 시 할루시네이션 | 신호가 적을 때 LLM이 없는 패턴을 만들어낼 위험 | 데이터 임계값 미달 시 분석 거부 (섹션 8.4) |
| DB 스키마 확장 부담 | 4개 신규 테이블 | Phase별로 마이그레이션 분리 — 한 번에 다 만들지 않음 |
| 동시 실행 충돌 | 스케줄 실행 중 사용자 요청이 겹칠 경우 | `ai_analysis_runs.status` 로 중복 실행 방지 |

---

## Appendix A — 환경 변수 목록 (구현 시 추가 예정)

```
OPENAI_API_KEY
ANTHROPIC_API_KEY
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-sonnet-4-6
AI_ANALYSIS_TIMEOUT_SECONDS=60
AI_ANALYSIS_MAX_RETRIES=3
MAX_DAILY_ANALYSIS_RUNS=10
MAX_STRATEGY_ANALYSIS_PER_DAY=5
MAX_PROMPT_CHARS=20000
DAILY_ANALYSIS_SCHEDULE_KST=15:45
```

## Appendix B — 참조 문서

- `docs/revised-architecture.md` — 전체 시스템 아키텍처
- `docs/risk-management.md` — Risk Manager 설계
- `app/services/strategy_analysis_input_service.py` — C-2.0 input payload
- `app/services/strategy_analysis_prompt_service.py` — C-2.1 prompt builder
- `app/trading/strategy/schemas.py` — StrategyAnalysisInputRead, StrategyAnalysisPromptRead
