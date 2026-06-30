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

## DB-side 52W Snapshot (paste from endpoint)

> `GET /api/v1/leader-trend/validation/db-52w-snapshot` 응답을 그대로 붙인다(자동 생성 파일 없음).

```json

```

## Manual Reference Basis (per source)

각 종목별로 사람이 채운 기준을 기록한다:

| symbol | source(non-KIS) | close basis (종가/현재가) | 52w period (기간 기준) | adjusted? (수정주가 여부) | as_of_date |
|---|---|---|---|---|---|
| 005930 | | | | | |
| 000660 | | | | | |
| 035420 | | | | | |
| 005380 | | | | | |
| 051910 | | | | | |

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

## Manual Reference Fill Evidence

각 종목별로 사람이 채운 근거를 기록한다(반드시 non-KIS):

| symbol | source name | source URL / 화면 설명 | close basis | 52w window basis | adjusted/raw | 확인 시각 | evidence note |
|---|---|---|---|---|---|---|---|
| 005930 | | | | | | | |
| 000660 | | | | | | | |
| 035420 | | | | | | | |
| 005380 | | | | | | | |
| 051910 | | | | | | | |

## Do not proceed if (다음 중 하나라도 해당하면 CandidateEvent 단계로 넘어가지 않는다)

- [ ] `placeholder_reference`가 남아 있음 (실제 값 미입력)
- [ ] `major_diff` 원인 불명 (§8-1 분류 미완료)
- [ ] KIS 출처가 섞임 (독립성 위반)
- [ ] close 기준이 intraday/current price와 daily close로 섞임
- [ ] 52w window basis 불명
- [ ] adjusted / raw basis 불명

## Decision
- SAFE TO PROCEED TO CANDIDATE EVENT DESIGN: yes/no
- reason:

> 주의: 이 검증이 통과(matched/minor_diff)해도 **실거래 허용이 아니다.** `KIS_REAL_TRADING_ENABLED`/자동매매/주문/
> 스케줄러는 별개이며 사람의 명시 승인 없이는 켜지지 않는다.
