"""KISClientBase._request() 재시도 동작 테스트.

실제 KIS 서버에 요청하지 않는다 — httpx.AsyncClient와 _get_access_token을 mock으로 대체.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.trading.broker.exceptions import KISAPIError
from app.trading.broker.kis_client import KISClientBase


def _make_client(max_retries: int = 2) -> tuple[KISClientBase, AsyncMock]:
    """토큰 발급 없이 동작하는 KISClientBase 인스턴스를 반환한다."""
    http_mock = AsyncMock(spec=httpx.AsyncClient)
    client = KISClientBase(
        base_url="https://test.example.com",
        app_key="test_key",
        app_secret="test_secret",
        http_client=http_mock,
        token_cache_path=Path("/tmp/test_token_cache.json"),
        rate_limit_min_interval_seconds=0.0,
        rate_limit_cooldown_seconds=0.0,
        request_max_retries=max_retries,
        request_retry_base_delay_seconds=0.0,
        request_retry_max_delay_seconds=0.0,
    )
    client._get_access_token = AsyncMock(return_value="fake_token")  # type: ignore[method-assign]
    return client, http_mock


def _ok_response(output: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    data: dict = {"rt_cd": "0", "msg_cd": "", "msg1": "정상처리 되었습니다."}
    if output is not None:
        data["output"] = output
    resp.json.return_value = data
    return resp


def _api_error_response(msg_cd: str, msg1: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"rt_cd": "1", "msg_cd": msg_cd, "msg1": msg1}
    return resp


async def test_retry_on_read_timeout_then_success() -> None:
    """ReadTimeout 후 재시도에서 성공하면 정상 응답을 반환한다."""
    client, http_mock = _make_client(max_retries=2)
    http_mock.request.side_effect = [
        httpx.ReadTimeout("timeout"),
        _ok_response({"key": "val"}),
    ]

    result = await client._request("GET", "/test", tr_id="TESTTR01")

    assert result["rt_cd"] == "0"
    assert http_mock.request.call_count == 2


async def test_retry_on_remote_protocol_error() -> None:
    """RemoteProtocolError(서버 연결 끊김) 후 재시도에서 성공하면 정상 응답을 반환한다."""
    client, http_mock = _make_client(max_retries=2)
    http_mock.request.side_effect = [
        httpx.RemoteProtocolError("server disconnected"),
        _ok_response(),
    ]

    result = await client._request("GET", "/test", tr_id="TESTTR01")

    assert result["rt_cd"] == "0"
    assert http_mock.request.call_count == 2


async def test_max_retries_exceeded_raises() -> None:
    """max_retries=2이면 총 3번(초기+2회) 시도 후 예외를 전파한다."""
    client, http_mock = _make_client(max_retries=2)
    http_mock.request.side_effect = httpx.ReadTimeout("timeout")

    with pytest.raises(httpx.ReadTimeout):
        await client._request("GET", "/test", tr_id="TESTTR01")

    assert http_mock.request.call_count == 3


async def test_non_retryable_error_raises_immediately() -> None:
    """토큰 오류(EGW00121)는 재시도 대상이 아니므로 즉시 raise한다."""
    client, http_mock = _make_client(max_retries=2)
    http_mock.request.return_value = _api_error_response("EGW00121", "토큰이 유효하지 않습니다")

    with pytest.raises(KISAPIError) as exc_info:
        await client._request("GET", "/test", tr_id="TESTTR01")

    assert exc_info.value.msg_cd == "EGW00121"
    assert http_mock.request.call_count == 1


async def test_retryable_false_does_not_retry() -> None:
    """retryable=False이면 ReadTimeout이 발생해도 재시도하지 않는다 (주문 API 보호)."""
    client, http_mock = _make_client(max_retries=2)
    http_mock.request.side_effect = httpx.ReadTimeout("timeout")

    with pytest.raises(httpx.ReadTimeout):
        await client._request("GET", "/test", tr_id="TESTTR01", retryable=False)

    assert http_mock.request.call_count == 1


async def test_rate_limit_error_is_retried() -> None:
    """EGW00201(초당 거래건수 초과)는 재시도 대상이다."""
    client, http_mock = _make_client(max_retries=2)
    http_mock.request.side_effect = [
        _api_error_response("EGW00201", "초당 거래건수를 초과하였습니다"),
        _ok_response(),
    ]

    result = await client._request("GET", "/test", tr_id="TESTTR01")

    assert result["rt_cd"] == "0"
    assert http_mock.request.call_count == 2


async def test_connect_timeout_is_retried() -> None:
    """ConnectTimeout도 재시도 대상이다."""
    client, http_mock = _make_client(max_retries=1)
    http_mock.request.side_effect = [
        httpx.ConnectTimeout("connect timed out"),
        _ok_response(),
    ]

    result = await client._request("GET", "/test", tr_id="TESTTR01")

    assert result["rt_cd"] == "0"
    assert http_mock.request.call_count == 2


async def test_max_retries_zero_does_not_retry() -> None:
    """max_retries=0이면 재시도 없이 즉시 raise한다."""
    client, http_mock = _make_client(max_retries=0)
    http_mock.request.side_effect = httpx.ReadTimeout("timeout")

    with pytest.raises(httpx.ReadTimeout):
        await client._request("GET", "/test", tr_id="TESTTR01")

    assert http_mock.request.call_count == 1
