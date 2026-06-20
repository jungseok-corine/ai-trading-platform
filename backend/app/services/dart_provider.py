"""DART(전자공시) OpenAPI 공시 수집 provider (C-2.59).

opendart.fss.or.kr 의 공시검색(list.json)을 호출해 최근 공시를 가져온다. 응답에 stock_code가
포함되어 종목 매핑 없이 바로 종목별 필터가 가능하다. 무료 키 1개(crtfc_key)면 된다.
httpx client 주입으로 네트워크 없이 테스트 가능. 순수 파서 분리.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx

DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
# 공시 원문 뷰어 URL(중복 수집 방지용 dedup 키로도 쓴다).
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"


class DartProviderError(Exception):
    """DART 조회 실패(네트워크/인증/rate limit/잘못된 키 등)."""


@dataclass
class Disclosure:
    rcept_no: str
    stock_code: str | None
    corp_name: str
    report_nm: str
    rcept_dt: str  # YYYYMMDD

    @property
    def url(self) -> str:
        return DART_VIEWER_URL.format(rcept_no=self.rcept_no)


def parse_dart_list(body: dict) -> list[Disclosure]:
    """list.json 응답을 Disclosure 목록으로 파싱한다.

    status "000"=정상, "013"=데이터 없음(빈 목록), 그 외는 DartProviderError.
    """
    status = body.get("status")
    if status == "013":  # 조회된 데이터 없음
        return []
    if status != "000":
        raise DartProviderError(f"DART error status={status}: {body.get('message')}")
    out: list[Disclosure] = []
    for item in body.get("list", []):
        rcept_no = item.get("rcept_no")
        if not rcept_no:
            continue
        out.append(Disclosure(
            rcept_no=rcept_no,
            stock_code=(item.get("stock_code") or "").strip() or None,
            corp_name=item.get("corp_name", ""),
            report_nm=item.get("report_nm", ""),
            rcept_dt=item.get("rcept_dt", ""),
        ))
    return out


class DartProvider:
    """DART 공시검색 호출. 무료 crtfc_key 필요."""

    def __init__(
        self,
        api_key: str | None,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    async def fetch_disclosures(
        self,
        bgn_de: date,
        end_de: date,
        page_count: int = 100,
    ) -> list[Disclosure]:
        """bgn_de~end_de 범위의 최근 공시를 가져온다(corp_code 없이 시장 전체)."""
        if not self._api_key:
            raise DartProviderError("DART_API_KEY is not set")

        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        owns = self._client is None
        try:
            resp = await client.get(DART_LIST_URL, params={
                "crtfc_key": self._api_key,
                "bgn_de": bgn_de.strftime("%Y%m%d"),
                "end_de": end_de.strftime("%Y%m%d"),
                "page_no": 1,
                "page_count": page_count,
            })
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as e:
            raise DartProviderError(f"DART request failed: {e}") from e
        finally:
            if owns:
                await client.aclose()
        return parse_dart_list(body)
