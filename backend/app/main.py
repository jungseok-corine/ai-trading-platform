from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import account, market, orders, positions, risk_config, signals, strategies
from app.api.v1 import engine as engine_api
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import engine
from app.scheduler.lifecycle import shutdown_scheduler, start_scheduler
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

    start_scheduler(app)

    yield

    shutdown_scheduler(app)
    await http_client.aclose()
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router, prefix="/api/v1")
app.include_router(account.router, prefix="/api/v1")
app.include_router(risk_config.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(positions.router, prefix="/api/v1")
app.include_router(signals.router, prefix="/api/v1")
app.include_router(strategies.router, prefix="/api/v1")
app.include_router(engine_api.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
