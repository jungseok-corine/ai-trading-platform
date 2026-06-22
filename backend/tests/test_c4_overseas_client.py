"""C-4: KIS 해외주식 분봉 클라이언트 — 실제 KIS 호출 없이 mock으로 매핑/정렬 검증.

주문 API는 일절 호출하지 않는다(시세 read-only).
"""
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx

from app.trading.broker.kis_overseas_client import KISOverseasClient


def _make_client() -> tuple[KISOverseasClient, AsyncMock]:
    http_mock = AsyncMock(spec=httpx.AsyncClient)
    client = KISOverseasClient(
        base_url="https://openapi.koreainvestment.com:9443",
        app_key="test_key",
        app_secret="test_secret",
        http_client=http_mock,
        token_cache_path=Path("/tmp/test_overseas_token.json"),
        rate_limit_min_interval_seconds=0.0,
        rate_limit_cooldown_seconds=0.0,
        request_retry_base_delay_seconds=0.0,
        request_retry_max_delay_seconds=0.0,
    )
    client._get_access_token = AsyncMock(return_value="fake_token")  # type: ignore[method-assign]
    return client, http_mock


def _resp(output2: list[dict] | None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    data: dict = {"rt_cd": "0", "msg_cd": "", "msg1": "정상처리 되었습니다."}
    if output2 is not None:
        data["output2"] = output2
    resp.json.return_value = data
    return resp


async def test_overseas_candles_mapped_and_sorted_oldest_first() -> None:
    client, http_mock = _make_client()
    # KIS는 최신→과거 순으로 줄 수 있으므로, 정렬이 오래된 순으로 바로잡는지 검증한다.
    rows = [
        {"kymd": "20260622", "khms": "233000", "open": "250.0", "high": "251.0",
         "low": "249.5", "last": "250.5", "evol": "1000"},
        {"kymd": "20260622", "khms": "232500", "open": "249.0", "high": "250.5",
         "low": "248.0", "last": "250.0", "evol": "2000"},
    ]
    http_mock.request.return_value = _resp(rows)

    candles = await client.get_overseas_minute_candles("AAPL", exchange="NAS", nmin=5)

    assert len(candles) == 2
    # 오래된 순(232500 → 233000)
    assert candles[0].trade_time == "232500"
    assert candles[-1].trade_time == "233000"
    assert candles[-1].close_price == Decimal("250.5")  # last → close
    assert candles[0].volume == 2000  # evol → volume
    assert candles[0].business_date == "20260622"

    # 요청 파라미터 검증 (EXCD/SYMB/NMIN)
    params = http_mock.request.call_args.kwargs["params"]
    assert params["EXCD"] == "NAS"
    assert params["SYMB"] == "AAPL"
    assert params["NMIN"] == "5"
    assert params["AUTH"] == ""


async def test_overseas_empty_output_returns_empty_list() -> None:
    client, http_mock = _make_client()
    http_mock.request.return_value = _resp(None)
    candles = await client.get_overseas_minute_candles("TSLA")
    assert candles == []


async def test_nrec_capped_at_120() -> None:
    client, http_mock = _make_client()
    http_mock.request.return_value = _resp([])
    await client.get_overseas_minute_candles("AAPL", n_records=500)
    assert http_mock.request.call_args.kwargs["params"]["NREC"] == "120"
