from fastapi import Request

from app.trading.broker.base import BrokerClient


def get_broker_client(request: Request) -> BrokerClient:
    return request.app.state.broker_client
