# 52W Window Basis Audit - 2026-06-29

## Purpose

- Naver validation에서 발생한 **005930/051910 low_52w major_diff** 원인을 조사한다.
- DB 수정이나 CandidateEvent 승인이 아니라, **window basis 차이를 설명하기 위한 read-only audit**이다.
- endpoint: `GET /api/v1/leader-trend/validation/52w-window-basis-audit` (매수 신호 아님 · 외부/KIS 호출 없음 ·
  DB write 없음).

## Compared Bases

- **last_252_trading_rows**: 현재 DB snapshot 방식 — symbol별 최신 252개 1d row.
- **calendar_52_weeks**: 기준일 `last_date`(2026-06-29)에서 `-364 days`(=52주) 이후 row만. (DB 외 데이터 미사용.)

## Why This Matters

- 252 trading rows는 약 1년 거래일 기준이지만, calendar 52주와 **시작일이 다를 수 있다**.
- 본 DB의 252 rows는 **2025-06-18부터** 시작한다. calendar-52주 cutoff(2025-06-30)에서는 2025-06-18~29의
  **오래된 저점이 제외**된다.
- 따라서 DB(252-row) low가 Naver(calendar) low보다 낮게 나올 수 있다 → 이번 major_diff의 유력 원인.

## Audit Results — per basis

| symbol | basis | rows | first_date | last_date | high | high_date | low | low_date | close | bucket |
| ------ | ----- | ---: | ---------- | --------- | ---: | --------- | --: | -------- | ----: | ------ |
| 005930 | last_252_trading_rows | 252 | 20250618 | 20260629 | 380,000 | 20260619 | 57,600 | 20250618 | 323,000 | B |
| 005930 | calendar_52_weeks | 244 | 20250630 | 20260629 | 380,000 | 20260619 | 59,800 | 20250630 | 323,000 | insufficient_data* |
| 000660 | last_252_trading_rows | 252 | 20250618 | 20260629 | 3,002,000 | 20260623 | 242,000 | 20250619 | 2,610,000 | B |
| 000660 | calendar_52_weeks | 244 | 20250630 | 20260629 | 3,002,000 | 20260623 | 244,000 | 20250822 | 2,610,000 | insufficient_data* |
| 035420 | last_252_trading_rows | 252 | 20250618 | 20260629 | 308,500 | 20260609 | 190,300 | 20260626 | 205,500 | none |
| 035420 | calendar_52_weeks | 244 | 20250630 | 20260629 | 308,500 | 20260609 | 190,300 | 20260626 | 205,500 | insufficient_data* |
| 005380 | last_252_trading_rows | 252 | 20250618 | 20260629 | 787,000 | 20260602 | 200,500 | 20250618 | 499,500 | none |
| 005380 | calendar_52_weeks | 244 | 20250630 | 20260629 | 787,000 | 20260602 | 202,000 | 20250708 | 499,500 | insufficient_data* |
| 051910 | last_252_trading_rows | 252 | 20250618 | 20260629 | 437,500 | 20260506 | 200,500 | 20250623 | 308,000 | none |
| 051910 | calendar_52_weeks | 244 | 20250630 | 20260629 | 437,500 | 20260506 | 208,000 | 20250630 | 308,000 | insufficient_data* |

\* calendar_52_weeks는 244 rows(<252)라 `candidate_bucket_if_any="insufficient_data"`로 계산된다(252 미만 규칙).
이는 **계산 artifact**일 뿐이며, 본 audit의 목적은 **low 값 비교**다.

## Audit Results — low basis vs Naver

| symbol | 252-row low | calendar-52w low | Naver low | 252 vs Naver diff % | calendar vs Naver diff % | explainable by window basis |
| ------ | ----------: | ---------------: | --------: | ------------------: | -----------------------: | --------------------------- |
| 005930 | 57,600 | 59,800 | 59,800 | -3.679 | **0.000** | **true** |
| 000660 | 242,000 | 244,000 | 245,000 | -1.224 | -0.408 | true |
| 035420 | 190,300 | 190,300 | 190,300 | 0.000 | 0.000 | true |
| 005380 | 200,500 | 202,000 | 203,500 | -1.474 | -0.737 | true |
| 051910 | 200,500 | 208,000 | 212,000 | -5.425 | **-1.887** | **true** |

→ **005930·051910의 major_diff는 모두 window basis 차이로 설명된다.** calendar-52주 기준 low가 Naver low와 ≤2%로
일치(005930은 59,800 정확 일치, 051910은 -5.43%→-1.89%). 차이의 원인은 DB의 252-row window가 calendar 52주보다
**오래된 저점(2025-06-18/23)을 더 포함**하기 때문이다.

## Decision

- **CandidateEvent allowed: no** (본 audit는 설명일 뿐, 승인 근거가 아니다).
- **DB correction allowed: no** (DB는 정상 — 단지 window 정의가 다름).
- Next step:
  - **calendar_52_weeks가 major_diff를 설명함** → **source-basis difference로 문서화**(DB=trading-day 252-row
    window, Naver=calendar-52주 window). 추가 non-KIS source/수동 차트 점검은 선택.
  - CandidateEvent 진행은 **사람의 별도 승인**이 있어야 한다(이 작업 범위 아님).
