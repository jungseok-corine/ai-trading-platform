from fastapi import Request

from app.trading.broker.base import BrokerClient
from app.trading.broker.kis_overseas_client import KISOverseasClient


def get_broker_client(request: Request) -> BrokerClient:
    return request.app.state.broker_client


def get_overseas_client(request: Request) -> KISOverseasClient | None:
    """미국장 시세 조회용 해외 클라이언트. 미설정 환경(테스트 등)에서는 None."""
    return getattr(request.app.state, "overseas_client", None)
