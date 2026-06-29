# Non-KIS 52W Validation Report

> 사람이 manual snapshot(`backend/app/data/reference/non_kis_52w_reference_pilot5.manual.json`)에 실제 non-KIS
> 기준값을 채운 뒤, `GET /api/v1/leader-trend/validation/non-kis-52w` 결과를 이 양식으로 기록한다.
> **이 보고서는 데이터 품질 검증 기록이며 매매 신호가 아니다.**

## Snapshot
- validation date:
- DB market_data timeframe:
- DB row count:
- reference file:
- reference source(s):
- as_of_date:
- collected by:

## Safety
- research_only:
- not_buy_signal:
- KIS call used:
- external auto-fetch used:
- DB write performed:
- trading path touched:

## Per-symbol Results

| symbol | db close | ref close | close diff % | db high 52w | ref high 52w | high diff % | db low 52w | ref low 52w | low diff % | status | note |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 005930 | | | | | | | | | | | |
| 000660 | | | | | | | | | | | |
| 035420 | | | | | | | | | | | |
| 005380 | | | | | | | | | | | |
| 051910 | | | | | | | | | | | |

## Summary
- matched:
- minor_diff:
- major_diff:
- missing_db_data:
- missing_reference_data:
- placeholder_reference:

## Findings
- (major_diff가 있으면 §8-1 원인 분류: 단위 / 수정주가 / 날짜 범위 / 종가 vs 현재가 / 데이터 누락 / source 차이)
-

## Decision
- SAFE TO PROCEED TO CANDIDATE EVENT DESIGN: yes/no
- reason:

> 주의: 이 검증이 통과(matched/minor_diff)해도 **실거래 허용이 아니다.** `KIS_REAL_TRADING_ENABLED`/자동매매/주문/
> 스케줄러는 별개이며 사람의 명시 승인 없이는 켜지지 않는다.
