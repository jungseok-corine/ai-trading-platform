from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import account, market, orders, positions, risk_config, signals, strategies, watchlists
from app.api.v1 import ai_providers as ai_providers_api
from app.api.v1 import analysis_runs as analysis_runs_api
from app.api.v1 import engine as engine_api
from app.api.v1 import investor_flows as investor_flows_api
from app.api.v1 import market_context as market_context_api
from app.api.v1 import market_data as market_data_api
from app.api.v1 import trading_guard as trading_guard_api
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import engine
from app.scheduler.lifecycle import shutdown_scheduler, start_scheduler
from app.trading.broker.kis_investor_flow_client import KISInvestorFlowClient
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
        rate_limit_min_interval_seconds=settings.kis_rate_limit_min_interval_seconds,
        rate_limit_cooldown_seconds=settings.kis_rate_limit_cooldown_seconds,
        request_max_retries=settings.kis_request_max_retries,
        request_retry_base_delay_seconds=settings.kis_request_retry_base_delay_seconds,
        request_retry_max_delay_seconds=settings.kis_request_retry_max_delay_seconds,
    )

    # 투자자 수급 조회 클라이언트 (실전 도메인 전용 read-only API).
    # 실전 자격증명이 설정된 경우 우선 사용, 없으면 paper 자격증명으로 시도한다.
    # 자격증명이 비어 있으면 클라이언트는 초기화되지만 실제 API 호출 시 KISAPIError가 발생한다.
    investor_flow_app_key = settings.kis_real_app_key or settings.kis_app_key
    investor_flow_app_secret = settings.kis_real_app_secret or settings.kis_app_secret
    app.state.investor_flow_client = KISInvestorFlowClient(
        base_url=settings.kis_real_base_url,
        app_key=investor_flow_app_key,
        app_secret=investor_flow_app_secret,
        http_client=http_client,
        token_cache_path=".cache/kis_investor_flow_token.json",
        rate_limit_min_interval_seconds=settings.kis_rate_limit_min_interval_seconds,
        rate_limit_cooldown_seconds=settings.kis_rate_limit_cooldown_seconds,
        request_max_retries=settings.kis_request_max_retries,
        request_retry_base_delay_seconds=settings.kis_request_retry_base_delay_seconds,
        request_retry_max_delay_seconds=settings.kis_request_retry_max_delay_seconds,
    )

    await start_scheduler(app)

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
app.include_router(watchlists.router, prefix="/api/v1")
app.include_router(engine_api.router, prefix="/api/v1")
app.include_router(market_data_api.router, prefix="/api/v1")
app.include_router(analysis_runs_api.router, prefix="/api/v1")
app.include_router(ai_providers_api.router, prefix="/api/v1")
app.include_router(trading_guard_api.router, prefix="/api/v1")
app.include_router(investor_flows_api.router, prefix="/api/v1")
app.include_router(market_context_api.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
