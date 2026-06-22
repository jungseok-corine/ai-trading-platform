# KIS 해외주식(미국장) OpenAPI 엔드포인트 레퍼런스

> 출처: `docs/kis-api/한국투자증권_오픈API_전체문서_20260616_030000.xlsx` 에서 발췌·정리.
> 멀티마켓(미국장) 확장 작업의 빠른 참조용. 상세 응답 필드는 원본 xlsx의 해당 시트 참조.
> ⚠️ 키/시크릿은 코드/문서에 절대 노출 금지. 미국 시세 일부는 **모의투자 미지원** → 실전 도메인+키로 **read-only** 조회.

## 시세 (Phase 1 — 신호 생성에 사용)

| 용도 | URL | 실전 TR_ID | 모의 | 비고 |
|------|-----|-----------|------|------|
| **분봉조회** | `GET /uapi/overseas-price/v1/quotations/inquire-time-itemchartprice` | `HHDFS76950200` | ❌ 미지원 | **NMIN으로 N분봉 직접**(5=5분봉). 1회 최대 120건 |
| 현재체결가 | `GET /uapi/overseas-price/v1/quotations/price` | `HHDFS00000300` | ✅ | 단일 종목 현재가 |
| 복수종목 시세 | `GET /uapi/overseas-price/v1/quotations/multprice` | `HHDFS76220000` | ❌ | 최대 **10종목/회** |
| 기간별시세(일) | `GET /uapi/overseas-price/v1/quotations/dailyprice` | `HHDFS76240000` | ✅ | 일봉 |
| 종목/지수/환율 기간별 | `GET /uapi/overseas-price/v1/quotations/inquire-daily-chartprice` | `FHKST03030100` | ✅ | 일/주/월 |

### 분봉조회 (HHDFS76950200) 상세 — Phase 1 핵심

**Query Params**
| 파라미터 | 필수 | 설명 |
|---|---|---|
| `AUTH` | Y | `""` 공백 |
| `EXCD` | Y | 거래소: **NYS**(뉴욕) **NAS**(나스닥) **AMS**(아멕스) HKS/SHS/SZS/… |
| `SYMB` | Y | 종목코드 (ex. `TSLA`, `AAPL`) |
| `NMIN` | Y | 분갭 (1=1분봉, 5=5분봉, …) |
| `PINC` | Y | 전일포함 0/1 (다음조회 시 1) |
| `NEXT` | Y | 처음 `""`, 다음 `"1"` |
| `NREC` | Y | 요청개수 (최대 120) |
| `FILL` | Y | `""` 공백 |
| `KEYB` | Y | 처음 `""` (다음조회 시 직전 마지막 분봉 키) |

**Response `output2`(배열)**: `kymd`(한국일자) `khms`(한국시간) `open` `high` `low` `last`(종가) `evol`(체결량) `eamt`(체결대금)
→ 공통 `MinuteCandle`로 매핑: business_date=kymd, trade_time=khms, open/high/low/close=last, volume=evol.

## 거래 (Phase 2 — 미국 (모의)주문, 나중)

| 용도 | URL | 실전 TR_ID | 모의 TR_ID |
|------|-----|-----------|-----------|
| 잔고 | `GET /uapi/overseas-stock/v1/trading/inquire-balance` | `TTTS3012R` | `VTTS3012R` ✅ |
| 주문 | `POST /uapi/overseas-stock/v1/trading/order` | 미국매수 `TTTT1002U` / 미국매도 `TTTT1006U` | 미국매수 `VTTT1002U` / 미국매도 `VTTT1001U` ✅ |
| 주문체결내역 | `GET /uapi/overseas-stock/v1/trading/inquire-ccnl` | — | (원본 시트 참조) |

> 참고: 해외 **잔고/주문은 모의(VTS) 지원**(VTTT/VTTS) → 향후 US 모의주문 구현 가능. 단 **분봉 시세는 모의 미지원**이라 신호 생성용 캔들은 실전 read-only로 가져온다.

## 시장 구분 매핑 (코드)

- `MarketCode.KR` → 국내(domestic-stock), `FID_INPUT_ISCD`=6자리 코드
- `MarketCode.US` → 해외(overseas-price/stock), `EXCD`(거래소)+`SYMB`(티커)
- 미국 거래소 코드: NASDAQ→`NAS`, NYSE→`NYS`, AMEX→`AMS`
