"""M2.15B-4 — daily candle pagination tests (네트워크 없이 MockTransport, 실 KIS/실 키 미사용).

KIS 1회 ~100봉 한도를 end-date 페이징으로 넘어 최대 count(예 252)를 모으고 business_date dedupe하는지 검증.
DB 쓰기 없음 · SignalLog/Trade/Order 0 · 주문 미호출.
"""
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from unittest.mock import AsyncMock

from app.trading.broker.kis_paper import KISPaperBrokerClient

PAGE_LIMIT = 100


def _make_client(handler) -> KISPaperBrokerClient:
    broker = KISPaperBrokerClient(
        account_no="50000000-01", market_div_code="J",
        base_url="https://openapivts.koreainvestment.com:29443",
        app_key="FAKE", app_secret="s",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        token_cache_path=Path("/tmp/test_kis_pg.json"),
        rate_limit_min_interval_seconds=0.0, rate_limit_cooldown_seconds=0.0,
        request_max_retries=0,  # 빠른 테스트(재시도 없음)
    )
    broker._get_access_token = AsyncMock(return_value="tok")  # type: ignore[method-assign]
    return broker


def _dates_desc(n: int, base: date = date(2026, 6, 29)) -> list[str]:
    """영업일 근사로 n개의 거래일(내림차순 YYYYMMDD) 생성(주말 제외)."""
    out, d = [], base
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def _row(ds: str, close: int = 5000):
    return {"stck_bsop_date": ds, "stck_oprc": str(close), "stck_hgpr": str(close + 50),
            "stck_lwpr": str(close - 50), "stck_clpr": str(close), "acml_vol": "100",
            "acml_tr_pbmn": "620000"}


def _windowed_handler(all_dates: list[str], extra_rows=None):
    """KIS 모사: FID_INPUT_DATE_2(cur_end) 이하 거래일 중 최신 ~100개 반환(최신일 우선)."""
    rows_by_date = {d: _row(d) for d in all_dates}
    if extra_rows:
        rows_by_date.update(extra_rows)
    ordered = sorted(rows_by_date.keys(), reverse=True)

    def handler(request: httpx.Request) -> httpx.Response:
        q = dict(httpx.QueryParams(request.url.query.decode()))
        end = q["FID_INPUT_DATE_2"]
        page = [rows_by_date[d] for d in ordered if d <= end][:PAGE_LIMIT]
        return httpx.Response(200, json={"rt_cd": "0", "msg1": "ok", "output2": page})
    return handler


# --- pagination ---------------------------------------------------------------
async def test_single_page_20():
    c = await _make_client(_windowed_handler(_dates_desc(300))).get_daily_candles("005930", count=20)
    assert len(c) == 20


async def test_paginates_to_252_deduped_and_ordered():
    res = await _make_client(_windowed_handler(_dates_desc(300))).get_daily_candles("005930", count=252)
    assert len(res) == 252
    ds = [x.business_date for x in res]
    assert ds == sorted(ds, reverse=True)        # 최신일 우선 결정적 정렬
    assert len(set(ds)) == 252                    # dedupe(중복 없음)


async def test_capped_to_requested_count():
    res = await _make_client(_windowed_handler(_dates_desc(300))).get_daily_candles("005930", count=150)
    assert len(res) == 150


async def test_empty_page_stops_pagination():
    # 50봉만 존재 → 252 요청해도 50만 반환(빈 페이지에서 중단, 무한 루프 없음)
    res = await _make_client(_windowed_handler(_dates_desc(50))).get_daily_candles("005930", count=252)
    assert len(res) == 50


async def test_non_moving_oldest_stops():
    # cur_end 무시하고 항상 같은 10봉 반환 → 진척 없음 → 중단(행 무한 누적/루프 없음)
    fixed = [_row(d) for d in _dates_desc(10)]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rt_cd": "0", "output2": fixed})

    res = await _make_client(handler).get_daily_candles("005930", count=252)
    assert len(res) == 10  # dedupe로 10개만, 무한 루프 없이 종료


async def test_max_pages_cap_bounds_calls():
    calls = {"n": 0}
    all_dates = _dates_desc(2000)  # 매우 길게 → page 캡이 호출 수 제한
    rows_by_date = {d: _row(d) for d in all_dates}
    ordered = sorted(rows_by_date, reverse=True)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        end = dict(httpx.QueryParams(request.url.query.decode()))["FID_INPUT_DATE_2"]
        page = [rows_by_date[d] for d in ordered if d <= end][:PAGE_LIMIT]
        return httpx.Response(200, json={"rt_cd": "0", "output2": page})

    from app.trading.broker.kis_paper import MAX_DAILY_PAGES
    await _make_client(handler).get_daily_candles("005930", count=400)
    assert calls["n"] <= MAX_DAILY_PAGES


async def test_invalid_rows_skipped_in_page():
    dates = _dates_desc(5)
    extra = {dates[2]: {"stck_bsop_date": dates[2], "stck_oprc": ".", "stck_hgpr": "1",
                        "stck_lwpr": "1", "stck_clpr": "1"}}  # 결측 가격 → skip
    res = await _make_client(_windowed_handler(dates, extra_rows=extra)).get_daily_candles("005930", count=10)
    assert dates[2] not in [x.business_date for x in res]
    assert len(res) == 4


async def test_trading_value_preserved():
    res = await _make_client(_windowed_handler(_dates_desc(3))).get_daily_candles("005930", count=3)
    assert all(x.trading_value is not None for x in res)


async def test_transient_500_on_later_page_raises():
    dates = _dates_desc(300)
    rows_by_date = {d: _row(d) for d in dates}
    ordered = sorted(rows_by_date, reverse=True)
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] >= 2:
            return httpx.Response(500, text="server error")  # 2번째 페이지 transient 실패
        end = dict(httpx.QueryParams(request.url.query.decode()))["FID_INPUT_DATE_2"]
        page = [rows_by_date[d] for d in ordered if d <= end][:PAGE_LIMIT]
        return httpx.Response(200, json={"rt_cd": "0", "output2": page})

    from app.trading.broker.kis_client import KISAPIError
    with pytest.raises(KISAPIError):  # 후속 페이지 실패는 안전히 raise(collector가 종목 단위로 흡수)
        await _make_client(handler).get_daily_candles("005930", count=252)
