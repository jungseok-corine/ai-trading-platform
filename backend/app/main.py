from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.v1 import account, market, risk_config
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import engine
from app.trading.broker.kis_paper import KISPaperBrokerClient

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging()

    http_client = httpx.AsyncClient(timeout=10.0)
    app.state.broker_client = KISPaperBrokerClient(
        base_url=settings.kis_paper_base_url,
        app_key=settings.kis_app_key,
        app_secret=settings.kis_app_secret,
        account_no=settings.kis_account_no,
        http_client=http_client,
        token_cache_path=settings.kis_token_cache_path,
    )

    yield

    await http_client.aclose()
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(market.router, prefix="/api/v1")
app.include_router(account.router, prefix="/api/v1")
app.include_router(risk_config.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
