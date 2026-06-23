from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import account, market, orders, positions, risk_config, signals, strategies, watchlists
from app.api.v1 import ai_providers as ai_providers_api
from app.api.v1 import analysis_runs as analysis_runs_api
from app.api.v1 import analysis_bundle as analysis_bundle_api
from app.api.v1 import assignments as assignments_api
from app.api.v1 import daily_analysis as daily_analysis_api
from app.api.v1 import dart as dart_api
from app.api.v1 import dart_finance as dart_finance_api
from app.api.v1 import edgar as edgar_api
from app.api.v1 import candidates as candidates_api
from app.api.v1 import daily_reports as daily_reports_api
from app.api.v1 import data_freshness as data_freshness_api
from app.api.v1 import data_refresh as data_refresh_api
from app.api.v1 import autonomous_jobs as autonomous_jobs_api
from app.api.v1 import engine as engine_api
from app.api.v1 import experiments as experiments_api
from app.api.v1 import investor_flows as investor_flows_api
from app.api.v1 import market_context as market_context_api
from app.api.v1 import market_data as market_data_api
from app.api.v1 import news_context as news_context_api
from app.api.v1 import promotions as promotions_api
from app.api.v1 import ai_cost as ai_cost_api
from app.api.v1 import analysis_audit as analysis_audit_api
from app.api.v1 import operations_digest as operations_digest_api
from app.api.v1 import operations_overview as operations_overview_api
from app.api.v1 import operations_snapshot as operations_snapshot_api
from app.api.v1 import portfolio_summary as portfolio_summary_api
from app.api.v1 import promotion_readiness as promotion_readiness_api
from app.api.v1 import risk_events as risk_events_api
from app.api.v1 import scheduler_health as scheduler_health_api
from app.api.v1 import trade_activity as trade_activity_api
from app.api.v1 import proposal_funnel as proposal_funnel_api
from app.api.v1 import safety_status as safety_status_api
from app.api.v1 import proposal_retrospective as proposal_retrospective_api
from app.api.v1 import research_funnel as research_funnel_api
from app.api.v1 import research_pipeline as research_pipeline_api
from app.api.v1 import research_status as research_status_api
from app.api.v1 import scanner_proposals as scanner_proposals_api
from app.api.v1 import scanner_review as scanner_review_api
from app.api.v1 import scanner_rules as scanner_rules_api
from app.api.v1 import seed as seed_api
from app.api.v1 import strategy_proposals as strategy_proposals_api
from app.api.v1 import strategy_review as strategy_review_api
from app.api.v1 import trading_guard as trading_guard_api
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import engine
from app.scheduler.lifecycle import shutdown_scheduler, start_scheduler
from app.trading.broker.kis_investor_flow_client import KISInvestorFlowClient
from app.trading.broker.kis_overseas_client import KISOverseasClient
from app.trading.broker.kis_overseas_paper import KISOverseasPaperBrokerClient
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
        market_div_code=settings.kr_market_div_code,
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

    # 해외주식(미국장) 시세 조회 클라이언트 (실전 도메인 전용 read-only, 주문 없음).
    # 미국 분봉은 모의 미지원이므로 실전 자격증명 우선 사용.
    app.state.overseas_client = KISOverseasClient(
        base_url=settings.kis_real_base_url,
        app_key=investor_flow_app_key,
        app_secret=investor_flow_app_secret,
        http_client=http_client,
        token_cache_path=".cache/kis_overseas_token.json",
        rate_limit_min_interval_seconds=settings.kis_rate_limit_min_interval_seconds,
        rate_limit_cooldown_seconds=settings.kis_rate_limit_cooldown_seconds,
        request_max_retries=settings.kis_request_max_retries,
        request_retry_base_delay_seconds=settings.kis_request_retry_base_delay_seconds,
        request_retry_max_delay_seconds=settings.kis_request_retry_max_delay_seconds,
    )

    # 해외주식(미국장) 모의투자 주문/잔고 브로커 (Phase 2).
    # 주문/잔고는 모의(VTS) 도메인+모의 자격증명, 시세는 위 실전 read-only 클라이언트에 위임.
    # 실전 주문 tr_id(TTTT)는 사용하지 않는다 — 실거래 비활성 불변식 유지.
    app.state.overseas_broker_client = KISOverseasPaperBrokerClient(
        base_url=settings.kis_paper_base_url,
        app_key=settings.kis_app_key,
        app_secret=settings.kis_app_secret,
        account_no=settings.kis_account_no,
        quotes_client=app.state.overseas_client,
        http_client=http_client,
        token_cache_path=".cache/kis_overseas_paper_token.json",
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
app.include_router(autonomous_jobs_api.router, prefix="/api/v1")
app.include_router(market_data_api.router, prefix="/api/v1")
app.include_router(analysis_runs_api.router, prefix="/api/v1")
app.include_router(analysis_bundle_api.router, prefix="/api/v1")
app.include_router(daily_analysis_api.router, prefix="/api/v1")
app.include_router(dart_api.router, prefix="/api/v1")
app.include_router(dart_finance_api.router, prefix="/api/v1")
app.include_router(edgar_api.router, prefix="/api/v1")
app.include_router(ai_providers_api.router, prefix="/api/v1")
app.include_router(trading_guard_api.router, prefix="/api/v1")
app.include_router(investor_flows_api.router, prefix="/api/v1")
app.include_router(market_context_api.router, prefix="/api/v1")
app.include_router(scanner_rules_api.router, prefix="/api/v1")
app.include_router(seed_api.router, prefix="/api/v1")
app.include_router(scanner_proposals_api.router, prefix="/api/v1")
app.include_router(scanner_review_api.router, prefix="/api/v1")
app.include_router(candidates_api.router, prefix="/api/v1")
app.include_router(assignments_api.router, prefix="/api/v1")
app.include_router(experiments_api.router, prefix="/api/v1")
app.include_router(strategy_proposals_api.router, prefix="/api/v1")
app.include_router(strategy_review_api.router, prefix="/api/v1")
app.include_router(news_context_api.router, prefix="/api/v1")
app.include_router(daily_reports_api.router, prefix="/api/v1")
app.include_router(promotions_api.router, prefix="/api/v1")
app.include_router(proposal_retrospective_api.router, prefix="/api/v1")
app.include_router(data_refresh_api.router, prefix="/api/v1")
app.include_router(data_freshness_api.router, prefix="/api/v1")
app.include_router(research_pipeline_api.router, prefix="/api/v1")
app.include_router(research_status_api.router, prefix="/api/v1")
app.include_router(research_funnel_api.router, prefix="/api/v1")
app.include_router(ai_cost_api.router, prefix="/api/v1")
app.include_router(proposal_funnel_api.router, prefix="/api/v1")
app.include_router(safety_status_api.router, prefix="/api/v1")
app.include_router(analysis_audit_api.router, prefix="/api/v1")
app.include_router(operations_overview_api.router, prefix="/api/v1")
app.include_router(operations_digest_api.router, prefix="/api/v1")
app.include_router(operations_snapshot_api.router, prefix="/api/v1")
app.include_router(portfolio_summary_api.router, prefix="/api/v1")
app.include_router(trade_activity_api.router, prefix="/api/v1")
app.include_router(risk_events_api.router, prefix="/api/v1")
app.include_router(promotion_readiness_api.router, prefix="/api/v1")
app.include_router(scheduler_health_api.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}
