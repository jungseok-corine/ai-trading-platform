# Non-KIS Independent 52-Week Validation (M2.15F-1)

> **읽기 전용 데이터 품질 검증 도구.** 외부 API 자동 호출 없음 · 신규 의존성 없음 · 웹 크롤링 없음 · KIS live/paper
> 호출 없음 · DB write 없음 · CandidateEvent/SignalLog/Trade/Order 없음 · 스케줄러 없음.
> **이 검증은 매매 신호가 아니다.** 통과해도 실거래가 허용되지 않는다.

---

## 1. 왜 non-KIS 독립 검증이 필요한가

M2.15D-1~3A에서 pilot_5(005930/000660/035420/005380/051910)의 저장 일봉을 **KIS 시세**(paper + real 도메인)와
대조해 현재가·52주 high/low가 일치함을 확인했다. 그러나 이 환경에서 KIS paper/real 도메인은 **동일한 데이터**를
반환한다(M2.15D-2). 즉 지금까지의 검증은 **KIS 생태계 내부 정합성**일 뿐, 실세계 시장값과의 **독립적** 일치는
확인되지 않았다.

→ 005930이 close 323,000·52주저 57,600(1년 5.6배), 000660이 1년 ~10배 같은 값이 **실제 시장**을 반영하는지,
아니면 dev/paper 데이터 특성인지를 가르려면 **KIS와 무관한 독립 기준값**이 필요하다.

---

## 2. KIS 내부 정합성 vs non-KIS 독립 검증

| 구분 | 의미 | 한계 |
|------|------|------|
| KIS 내부 정합성(D-2/3A) | 저장값이 KIS paper·real 도메인 시세와 일치 | 두 도메인이 같은 데이터를 반환 → 독립성 아님 |
| **non-KIS 독립 검증(본 문서)** | 저장값이 **KIS 밖** 기준값과도 일치하는지 | 기준값은 **사람이 수동으로** 채워야 함(자동 fetch 금지) |

---

## 3. 이 검증은 데이터 품질 확인이지 매매 신호가 아니다

- 목적: **데이터가 실세계와 부합하는가**(스케일/이력 신뢰성).
- **후보 분류·매수·진입·주문과 무관.** validation_status가 `matched`라도 이는 "데이터가 일관됨"일 뿐,
  "매수하라"가 절대 아니다.
- threshold(아래)는 **검증 보조 기준**이며 매매 판단 기준이 아니다.

---

## 3-0. F-3B DB baseline 요약 & manual fill 준비 (M2.15F-3C)

CandidateEvent 저장 **전 필수 검증 단계**다. F-3B(`db-52w-snapshot`, commit `f61a12b`)의 DB-side baseline:

| symbol | db close | 52w high (date) | 52w low (date) | gain% | bucket |
|---|---:|---:|---:|---:|:--:|
| 005930 | 323,000 | 380,000 (20260619) | 57,600 (20250618) | 460.76 | B |
| 000660 | 2,610,000 | 3,002,000 (20260623) | 242,000 (20250619) | 978.51 | B |
| 035420 | 205,500 | 308,500 (20260609) | 190,300 (20260626) | 7.99 | none |
| 005380 | 499,500 | 787,000 (20260602) | 200,500 (20250618) | 149.13 | none |
| 051910 | 308,000 | 437,500 (20260506) | 200,500 (20250623) | 53.62 | none |

- 수동 입력 절차/규칙: **[manual fill checklist](manual-non-kis-reference-fill-checklist.md)** 참고.
- **규칙**: manual snapshot에는 위 DB baseline을 **`db_*` 필드로만** 넣고, `reference_close/high_52w/low_52w`는
  사람이 non-KIS 출처로 채우기 전까지 **0(placeholder) 유지**. db_* 값을 reference 값으로 복사 금지(독립성 무력화).

## 3-1. 두 파일의 역할 분리 (M2.15F-2)

| 파일 | 역할 | 누가 채우나 |
|------|------|------|
| `backend/app/data/reference/non_kis_52w_reference_pilot5.manual.json` | **runtime manual snapshot** — API가 기본으로 읽는 실제 검증용 기준값 | **사람**(non-KIS 출처 수동 입력) |
| `backend/tests/fixtures/non_kis_52w_reference_pilot5.json` | **테스트용 fixture** — 분류 로직 검증용 | 테스트(명시 주입) |

- **runtime 기본 reference path = `app/data/reference/...manual.json`.** validation service/endpoint는 더 이상
  `tests/fixtures`에 의존하지 않는다(운영 코드가 테스트 디렉토리에 의존하지 않음).
- 테스트는 synthetic dict 또는 `tests/fixtures`를 **명시 주입**해 격리 검증한다.
- 두 파일 모두 현재 placeholder(0) → API 기본 결과는 `placeholder_reference`(또는 DB 없으면 `missing_db_data`).

## 4. Reference 작성 방법 (manual snapshot)

위치(runtime): `backend/app/data/reference/non_kis_52w_reference_pilot5.manual.json`.
(테스트 fixture: `backend/tests/fixtures/non_kis_52w_reference_pilot5.json` — 형식 동일.)

```json
{
  "source_name": "manual_non_kis_reference",
  "source_note": "MANUAL REFERENCE REQUIRED ... Do NOT use for trading decisions.",
  "as_of_date": "YYYY-MM-DD",
  "timeframe": "1d",
  "symbols": [
    { "symbol": "005930", "reference_close": 0, "high_52w": 0, "low_52w": 0,
      "currency": "KRW", "source_url_or_note": "manual placeholder — fill with non-KIS reference" }
  ]
}
```

작성 절차(사람이 수행):
1. KIS와 **무관한** 출처(증권 단말, 거래소 공시, 공개 데이터 등)에서 각 종목의 최근 종가·52주 고가·52주 저가를
   **수동으로** 확인한다. (이 코드/작업은 외부를 자동 호출하지 않는다.)
2. `reference_close`/`high_52w`/`low_52w`를 실제 값으로 채우고 `source_url_or_note`에 출처를 적는다.
3. `as_of_date`를 실제 기준일로 바꾼다.
4. placeholder(0 또는 note에 "placeholder")가 남아 있으면 해당 종목은 `placeholder_reference`로 분류되어 검증되지
   않는다.

**manual snapshot 작성 규칙(반드시 지킬 것):**
- **기준 날짜(`as_of_date`)** 를 명시한다.
- **출처**를 `source_url_or_note`에 명시한다(어느 단말/공시/페이지인지).
- **종가/현재가 기준**을 명시한다(장중 현재가인지 당일 종가인지 — 본 검증의 DB값은 최신 일봉 종가).
- **52주 high/low 기준 기간**을 명시한다(정확히 최근 52주/252거래일인지).
- **수정주가 여부**를 메모한다(원주가 vs 수정주가 — 분할/배당 반영 차이).
- **KIS가 아닌 출처**여야 한다(KIS 단말/시세 사용 금지 — 독립성 목적).
- **매매 판단에 쓰지 말 것.**

---

## 5. pilot_5 기준 설명

| 종목 | 이름(참고) |
|------|------|
| 005930 | 삼성전자 |
| 000660 | SK하이닉스 |
| 035420 | NAVER |
| 005380 | 현대차 |
| 051910 | LG화학 |

기본 fixture는 5종 모두 placeholder(0) — **사람이 실제 non-KIS 값을 채우기 전까지는 검증이 의미 없음**을 명시한다.

---

## 6. Threshold 의미

| 분류 | 조건(저장값 vs 레퍼런스 max |diff|) |
|------|------|
| `matched` | ≤ 0.7% |
| `minor_diff` | 0.7% < |diff| ≤ 2.0% |
| `major_diff` | > 2.0% |
| `missing_db_data` | 해당 종목 `market_data` 1d 행 없음 |
| `missing_reference_data` | fixture에 해당 종목 항목 없음 |
| `placeholder_reference` | 레퍼런스가 placeholder(0/“placeholder”) |

`MINOR_DIFF_PCT=0.7`, `MAJOR_DIFF_PCT=2.0`은 코드 상수(`leader_trend_validation_service.py`). **검증 보조 기준이며
매매 판단 기준이 아니다.**

---

## 7. placeholder 주의사항

- 기본 fixture는 전부 placeholder → API 호출 시 5종 모두 `placeholder_reference`(또는 DB 없으면 `missing_db_data`).
- placeholder는 **테스트를 깨지 않는다**(분류만 placeholder). 실제 검증은 사람이 값을 채운 뒤에만 유효.
- placeholder 값을 매매/판단에 사용하지 말 것.

---

## 7-1. DB-side 52주 snapshot export (M2.15F-3A)

`GET /api/v1/leader-trend/validation/db-52w-snapshot` — **현재 local DB**가 계산한 종목별 52주 기준값을 read-only로
보여준다(매수 신호 아님). **이 endpoint는 non-KIS 값을 가져오지 않는다** — KIS/외부 호출 0, DB write 0. 사람이
manual reference를 채울 때 **무엇을 어떤 기준으로 채워야 하는지**의 DB 측 기준을 제공한다.

응답 플래그: `research_only/not_buy_signal/read_only=true`, `external_reference_auto_fetch/kis_call_used/
db_write_performed=false`. 종목별 필드: row_count · first/last_date · db_reference_close(+date) · db_high_52w(+date) ·
db_low_52w(+date) · low_52w_gain_pct · drawdown_from_52w_high_pct · candidate_bucket_if_any · data_quality_note.

> ⚠ snapshot 결과는 **실행 시점 DB 상태에 의존**한다. repo에 자동 생성 파일을 만들지 않는다 — endpoint 응답을
> **복사해서 report template(§ report-template)** 에 붙여라.

## 8. 사람이 실제 값을 채운 뒤 검증 절차

1. **`GET /api/v1/leader-trend/validation/db-52w-snapshot` 호출** → 각 종목의 DB close/high_52w/low_52w와 **그 날짜**를
   확인한다(어떤 기준으로 채울지 기준점).
2. 각 symbol의 DB close/high_52w/low_52w를 본다.
3. 사람이 **non-KIS 출처**에서 같은 기준(종가/52주 기간/수정주가 여부)의 값을 수동 확인한다.
4. `backend/app/data/reference/non_kis_52w_reference_pilot5.manual.json`에 수동 입력(§4 규칙 준수).
5. `GET /api/v1/leader-trend/validation/non-kis-52w` 호출 → `matched`/`minor_diff`/`major_diff` 분포 확인.
6. validation report template(`non-kis-52w-validation-report-template.md`)에 결과 기록.
7. `major_diff`가 있으면 저장 일봉이 실세계와 크게 어긋남 → **DB를 바로 고치지 말고 원인을 먼저 분류**한다(아래 §8-1).

### 8-1. `major_diff` 원인 분류 (DB 수정 전 반드시 분류)

`major_diff`가 나와도 **즉시 DB를 수정하지 않는다.** 먼저 다음 중 무엇인지 분류한다:
- **단위 문제**: 통화/스케일(예 원 vs 천원) 불일치.
- **수정주가 문제**: 한쪽은 수정주가, 한쪽은 원주가(분할/배당 반영 차이).
- **날짜 범위 차이**: 52주 윈도우/기준일이 서로 다름.
- **종가 vs 현재가 기준 차이**: 레퍼런스가 장중 현재가, DB가 당일 종가 등.
- **데이터 누락**: DB 일봉에 빠진 거래일(고/저 누락).
- **source 자체 차이**: 출처별 정정/거래소 차이.

원인을 분류·기록한 뒤에만(그리고 별도 승인 하에만) 데이터 적재/출처를 재검토한다. **검증은 매매 결정이 아니다.**

---

## 9. 이 검증이 통과해도 실거래 허용이 아니다

- 본 검증은 **데이터 품질** 확인일 뿐이다.
- `KIS_REAL_TRADING_ENABLED`·자동매매·주문·스케줄러/디스패처는 전부 별개이며 **사람의 명시 승인** 없이는 켜지지
  않는다(안전 불변식).
- 검증 `matched`는 "데이터가 신뢰할 만하다"는 의미이지 "거래하라"가 아니다.

---

## 10. 안전 요약

읽기 전용 · 외부 자동 호출 없음 · 신규 의존성 없음 · KIS 호출 없음 · DB write 없음 · 후보/신호/거래/주문/이벤트
생성 없음 · 마이그레이션 없음 · 스케줄러 없음 · `KIS_REAL_TRADING_ENABLED` 미변경.
