# Non-KIS 52W Validation Report - 2026-06-29 Naver

> 데이터 품질 검증 기록. **매수 신호 아님 · CandidateEvent 진행 아님.**

## Snapshot

- validation date: 2026-06-30 KST
- DB market_data timeframe: 1d
- DB row count: 1,260
- reference file: `backend/app/data/reference/non_kis_52w_reference_pilot5.manual.json`
- reference source: 네이버증권 (non-KIS)
- as_of_date / reference_close_date: 2026-06-29
- checked_at: 2026-06-30 KST
- collected by: user

## Safety

- research_only: true
- not_buy_signal: true
- KIS call used: false
- external auto-fetch used: false
- DB write performed: false
- trading path touched: false
- CandidateEvent allowed: **false**

## Basis Match Check

- DB last_date: 2026-06-29
- reference_close_date: 2026-06-29
- close basis matched: **yes** (둘 다 daily close, 동일 일자)
- 52w window basis matched: **partial/uncertain** (네이버 "52주 최고/최저"의 기준 기간이 DB의 정확한 252거래일과
  동일한지 미확인)
- adjusted/raw basis known: **yes** (user: 수정주가)
- proceed to validation: yes
- proceed to CandidateEvent: **no**

## Per-symbol Results

| symbol | db close | ref close | close diff % | db high 52w | ref high 52w | high diff % | db low 52w | ref low 52w | low diff % | status | note |
| ------ | -------: | --------: | -----------: | ----------: | -----------: | ----------: | ---------: | ----------: | ---------: | ------ | ---- |
| 005930 | 323,000 | 323,000 | 0.000 | 380,000 | 374,500 | +1.469 | 57,600 | 59,800 | **-3.679** | **major_diff** | low_52w 차이 — 원인 분석 필요 |
| 000660 | 2,610,000 | 2,628,000 | -0.685 | 3,002,000 | 2,987,000 | +0.502 | 242,000 | 245,000 | -1.224 | minor_diff | low minor |
| 035420 | 205,500 | 204,000 | +0.735 | 308,500 | 304,000 | +1.480 | 190,300 | 190,300 | 0.000 | minor_diff | low matched |
| 005380 | 499,500 | 497,000 | +0.503 | 787,000 | 783,000 | +0.511 | 200,500 | 203,500 | -1.474 | minor_diff | low minor |
| 051910 | 308,000 | 308,000 | 0.000 | 437,500 | 437,500 | 0.000 | 200,500 | 212,000 | **-5.425** | **major_diff** | low_52w 차이 — 원인 분석 필요 |

Summary: matched 0 · minor_diff 3 · major_diff 2 · missing_db_data 0 · missing_reference_data 0 · placeholder_reference 0.

## Expected Difference Notes

- **005930**: close 정확 일치, high_52w 근접(minor). **low_52w가 major_diff**(DB 57,600 vs 네이버 59,800, -3.68%).
  원인 후보: 52주 window 차이, 장중 저가/종가 기준 차이, 수정주가/비수정주가 차이, source 산식 차이.
- **000660**: close/high/low 모두 minor 범위 → minor_diff.
- **035420**: close/high minor, low 일치 → minor_diff.
- **005380**: close/high 근접, low minor → minor_diff.
- **051910**: close/high 정확 일치이나 **low_52w가 major_diff**(DB 200,500 vs 네이버 212,000, -5.43%). 원인 분석 필요.

## Decision

- **SAFE TO PROCEED TO CANDIDATE EVENT DESIGN: no**
- reason:
  - validation includes unresolved **major_diff for 005930 and 051910** (both `low_52w`).
  - 52w window basis remains **partial/uncertain**.
  - CandidateEvent persistence must wait until major_diff causes are explained or explicitly accepted as
    source-basis differences. **DB는 수정하지 않는다.**

## Next Required Action

- 005930 `low_52w` 차이(57,600 vs 59,800) 원인 확인.
- 051910 `low_52w` 차이(200,500 vs 212,000) 원인 확인.
- 가능하면 같은 출처(네이버증권)에서 52주 low 산식/기간/수정주가 기준 재확인.
- major_diff 원인이 설명되기 전까지 **CandidateEvent 금지**.
