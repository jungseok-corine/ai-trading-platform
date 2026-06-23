"""DART XBRL 재무제표 수집 provider (C-2.21.1).

DART OpenAPI 두 엔드포인트를 순서대로 호출한다:
  1. /api/company.json   — stock_code → corp_code(8자리 DART 고유번호) 조회
  2. /api/fnlttSinglAcnt.json — corp_code + 사업연도 + 보고서코드 + 개별/연결 → 재무항목 목록

DartProvider와 동일한 httpx 주입 패턴 — MockTransport로 네트워크 없이 테스트 가능.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

DART_COMPANY_URL = "https://opendart.fss.or.kr/api/company.json"
DART_FINSTAT_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"

# 재무항목 계정명 → key_items 키 매핑 (DART 계정명은 보고서·버전별로 미세하게 다름)
_ACCOUNT_MAP: dict[str, str] = {
    "매출액": "revenue",
    "수익(매출액)": "revenue",
    "영업수익": "revenue",
    "영업이익": "operating_income",
    "영업이익(손실)": "operating_income",
    "당기순이익": "net_income",
    "당기순이익(손실)": "net_income",
    "자산총계": "total_assets",
    "자본총계": "total_equity",
}


class DartFinanceProviderError(Exception):
    """DART 재무제표 조회 실패(네트워크/인증/데이터 없음 등)."""


@dataclass
class FinanceItem:
    account_nm: str
    thstrm_amount: str | None  # 당기 금액 (문자열, 쉼표 포함)
    frmtrm_amount: str | None  # 전기 금액
    bfefrmtrm_amount: str | None  # 전전기 금액


def _parse_amount(raw: str | None) -> int | None:
    """쉼표·공백 제거 후 정수 변환. 파싱 불가이면 None."""
    if not raw:
        return None
    try:
        return int(raw.replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def parse_finstat_body(body: dict) -> list[FinanceItem]:
    """fnlttSinglAcnt.json 응답을 FinanceItem 목록으로 파싱한다.

    status "000"=정상, "013"=데이터 없음, 그 외 DartFinanceProviderError.
    """
    status = body.get("status")
    if status == "013":
        return []
    if status != "000":
        raise DartFinanceProviderError(
            f"DART finance error status={status}: {body.get('message')}"
        )
    out: list[FinanceItem] = []
    for item in body.get("list", []):
        nm = item.get("account_nm", "")
        if not nm:
            continue
        out.append(FinanceItem(
            account_nm=nm,
            thstrm_amount=item.get("thstrm_amount"),
            frmtrm_amount=item.get("frmtrm_amount"),
            bfefrmtrm_amount=item.get("bfefrmtrm_amount"),
        ))
    return out


def extract_key_items(items: list[FinanceItem]) -> dict:
    """FinanceItem 목록에서 핵심 5개 항목을 정규화한 dict로 반환한다.

    존재하는 항목만 포함한다. 단위: 원.
    """
    result: dict[str, int | None] = {}
    for item in items:
        key = _ACCOUNT_MAP.get(item.account_nm)
        if key and key not in result:
            result[key] = _parse_amount(item.thstrm_amount)
    return result


@dataclass
class DartFinanceProvider:
    """DART XBRL 재무제표 수집 — DartProvider 동형 패턴."""

    _api_key: str | None
    _timeout: float = field(default=15.0, repr=False)
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

    def __init__(
        self,
        api_key: str | None,
        *,
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    async def _get(self, url: str, params: dict) -> dict:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise DartFinanceProviderError(f"DART request failed: {e}") from e
        finally:
            if owns:
                await client.aclose()

    async def fetch_corp_code(self, stock_code: str) -> str:
        """stock_code(6자리) → DART corp_code(8자리)."""
        if not self._api_key:
            raise DartFinanceProviderError("DART_API_KEY is not set")
        body = await self._get(DART_COMPANY_URL, {
            "crtfc_key": self._api_key,
            "stock_code": stock_code,
        })
        status = body.get("status")
        if status != "000":
            raise DartFinanceProviderError(
                f"company lookup failed status={status}: {body.get('message')}"
            )
        corp_code = body.get("corp_code", "")
        if not corp_code:
            raise DartFinanceProviderError(f"no corp_code for stock_code={stock_code}")
        return corp_code

    async def fetch_statements(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str = "11011",
        fs_div: str = "CFS",
    ) -> list[FinanceItem]:
        """단일 재무제표 항목 목록을 가져온다.

        reprt_code: 11011=사업보고서, 11012=반기, 11013=Q1, 11014=Q3
        fs_div: CFS=연결, OFS=개별
        """
        if not self._api_key:
            raise DartFinanceProviderError("DART_API_KEY is not set")
        body = await self._get(DART_FINSTAT_URL, {
            "crtfc_key": self._api_key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        })
        return parse_finstat_body(body)
