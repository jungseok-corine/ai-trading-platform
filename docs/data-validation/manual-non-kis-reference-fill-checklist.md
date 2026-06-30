# Manual Non-KIS Reference Fill Checklist

## Purpose

- 이 문서는 non-KIS 값을 **자동 수집하지 않고 사람이 직접** 확인하기 위한 체크리스트다.
- 이 값은 **매매 신호가 아니라 데이터 품질 검증용**이다.
- 채우는 대상 파일: `backend/app/data/reference/non_kis_52w_reference_pilot5.manual.json`.

## Before Filling

- DB snapshot endpoint 결과 확인: `GET /api/v1/leader-trend/validation/db-52w-snapshot`
- 기준 commit 확인: `f61a12b`
- 기준 날짜 확인: DB `last_date` = `20260629`
- timeframe: `1d`
- pilot_5만 사용 (005930 / 000660 / 035420 / 005380 / 051910)
- **KIS 출처 사용 금지** (독립성 목적)

## Acceptable Manual Sources (non-KIS)

- 한국거래소/KRX 정보 화면
- 네이버증권
- 다음/카카오증권
- 증권사 HTS/MTS (단 **KIS 제외**)
- 기타 non-KIS 데이터 제공처

## Required Per Symbol

- `reference_close`
- `high_52w`
- `low_52w`
- reference close 기준 날짜
- 52주 high/low 기준 기간
- adjusted / raw 여부
- source name
- source URL 또는 사람이 확인한 화면 설명
- 확인 시각

## Symbol-specific DB Baseline (from F-3B, commit `f61a12b`)

| symbol | rows | first_date | last_date | db close | close date | db 52w high | high date | db 52w low | low date | low gain % | high drawdown % | bucket |
| ------ | ---: | ---------- | --------- | -------: | ---------- | ----------: | --------- | ---------: | -------- | ---------: | --------------: | ------ |
| 005930 | 252 | 20250618 | 20260629 | 323,000 | 20260629 | 380,000 | 20260619 | 57,600 | 20250618 | 460.76 | 15.00 | B |
| 000660 | 252 | 20250618 | 20260629 | 2,610,000 | 20260629 | 3,002,000 | 20260623 | 242,000 | 20250619 | 978.51 | 13.06 | B |
| 035420 | 252 | 20250618 | 20260629 | 205,500 | 20260629 | 308,500 | 20260609 | 190,300 | 20260626 | 7.99 | 33.39 | none |
| 005380 | 252 | 20250618 | 20260629 | 499,500 | 20260629 | 787,000 | 20260602 | 200,500 | 20250618 | 149.13 | 36.53 | none |
| 051910 | 252 | 20250618 | 20260629 | 308,000 | 20260629 | 437,500 | 20260506 | 200,500 | 20250623 | 53.62 | 29.60 | none |

> 위 `db_*` 값은 manual snapshot의 `db_*` 필드에도 들어 있다 — **참고용 baseline일 뿐 reference 값이 아니다.**

## Fill Rules

- **DB 값을 reference 값으로 복사하지 말 것** (독립 검증 목적이 무력화됨).
- source가 **KIS이면 안 됨**.
- **intraday 현재가와 daily close를 섞지 말 것**.
- **수정주가 / 비수정주가 여부를 반드시 기록**할 것.
- 52주 기준 기간이 DB와 다르면 note에 기록할 것.
- `major_diff`가 나와도 **즉시 DB 수정 금지** — 원인 분류 후 다음 단계에서 판단.

## After Filling

- `GET /api/v1/leader-trend/validation/non-kis-52w` 호출
- report template(`non-kis-52w-validation-report-template.md`)에 결과 기록
- `major_diff` / `minor_diff` / `matched` 분류 확인
- CandidateEvent 설계로 넘어갈지 **사람이 판단**(이 검증 통과가 실거래 허용은 아니다)
