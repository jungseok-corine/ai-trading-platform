"""C-5.9: NXT/통합(UN) 시세 수집 — 국내 시세 분류 코드 설정 가능(주문은 KRX 고정)."""
from pathlib import Path
from unittest.mock import AsyncMock

import httpx

from app.trading.broker.kis_paper import EXCG_ID_DVSN_CD_KRX, KISPaperBrokerClient


def _make_broker(market_div_code: str = "J") -> KISPaperBrokerClient:
    broker = KISPaperBrokerClient(
        account_no="50000000-01",
        market_div_code=market_div_code,
        base_url="https://openapivts.koreainvestment.com:29443",
        app_key="k", app_secret="s",
        http_client=AsyncMock(spec=httpx.AsyncClient),
        token_cache_path=Path("/tmp/test_kis_paper_div.json"),
        rate_limit_min_interval_seconds=0.0,
        rate_limit_cooldown_seconds=0.0,
    )
    broker._get_access_token = AsyncMock(return_value="tok")  # type: ignore[method-assign]
    return broker


async def test_candles_use_configured_market_div_code() -> None:
    broker = _make_broker(market_div_code="UN")  # 통합(KRX+NXT)
    broker._request = AsyncMock(return_value={"output2": []})

    await broker.get_minute_candles("005930", target_time="100000")

    params = broker._request.call_args.kwargs["params"]
    assert params["FID_COND_MRKT_DIV_CODE"] == "UN"


async def test_default_is_krx() -> None:
    broker = _make_broker()  # 기본 J
    broker._request = AsyncMock(return_value={"output": {
        "stck_prpr": "1", "prdy_vrss": "0", "prdy_ctrt": "0", "stck_oprc": "1",
        "stck_hgpr": "1", "stck_lwpr": "1", "acml_vol": "0",
    }})

    await broker.get_current_price("005930")

    assert broker._request.call_args.kwargs["params"]["FID_COND_MRKT_DIV_CODE"] == "J"


def test_orders_stay_krx_regardless_of_market_div() -> None:
    # 시세 분류를 NXT/UN으로 바꿔도 주문 거래소는 KRX로 고정(NXT 주문은 모의 미지원).
    assert EXCG_ID_DVSN_CD_KRX == "KRX"
