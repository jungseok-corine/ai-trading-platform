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

## 4. Reference fixture 작성 방법

위치: `backend/tests/fixtures/non_kis_52w_reference_pilot5.json`.

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

## 8. 사람이 실제 값을 채운 뒤 검증 절차

1. 위 §4대로 fixture에 실제 non-KIS 값을 채운다(커밋 별도 판단).
2. `GET /api/v1/leader-trend/validation/non-kis-52w` 호출(읽기 전용).
3. summary에서 `matched`/`minor_diff`/`major_diff` 분포를 본다.
4. `major_diff`가 있으면 저장 일봉이 실세계와 크게 어긋남 → 데이터 출처/적재 재검토(여전히 매매 결정 아님).
5. 대부분 `matched`/`minor_diff`면 데이터 품질이 실세계와 부합한다는 보조 근거.

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
