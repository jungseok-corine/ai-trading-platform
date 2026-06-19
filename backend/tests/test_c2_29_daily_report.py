"""C-2.29 Daily AI Research Report 테스트."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import (
    AccountType,
    OrderStatus,
    ScannerRuleStatus,
    StrategyVersionStatus,
    TradeSide,
)
from app.domain.models.signal_log import SignalLog
from app.domain.models.trade import Trade
from app.main import app
from app.services.scanner_service import ScannerService
from app.services.strategy_service import StrategyService

KST = ZoneInfo("Asia/Seoul")
REPORT_DAY = date(2026, 6, 17)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


def _at(hour: int) -> datetime:
    return datetime(2026, 6, 17, hour, 0, tzinfo=KST)


async def _seed_day(session: AsyncSession) -> None:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    session.add(account)
    await session.commit()

    svc = StrategyService(session)
    strategy = await svc.create_strategy("daily-report-strategy")
    version = await svc.create_version(
        strategy.id,
        parameters={"symbol_code": "005930"},
        status=StrategyVersionStatus.TESTING,  # active_strategies에 잡힘
    )

    # 신호 2건 (매수 1, 매도 1)
    session.add(
        SignalLog(symbol_code="005930", signal_type=TradeSide.BUY, generated_at=_at(10),
                  strategy_version_id=version.id)
    )
    session.add(
        SignalLog(symbol_code="005930", signal_type=TradeSide.SELL, generated_at=_at(11),
                  strategy_version_id=version.id)
    )
    # 체결 2건 (pnl +100, -40)
    for pnl in (Decimal("100"), Decimal("-40")):
        session.add(
            Trade(account_id=account.id, strategy_version_id=version.id, symbol_code="005930",
                  side=TradeSide.BUY, quantity=1, pnl_amount=pnl,
                  order_status=OrderStatus.FILLED, created_at=_at(12))
        )

    # 후보 1건 (scanner rule version 필요)
    scanner = ScannerService(session)
    rule = await scanner.create_rule("vol")
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    session.add(
        CandidateEvent(scanner_rule_version_id=sv.id, symbol_code="005930", score=80,
                       triggered_at=_at(9))
    )
    await session.commit()


async def test_generate_report_aggregates_day(db_session: AsyncSession) -> None:
    await _seed_day(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            gen = await client.post(
                "/api/v1/daily-reports/generate",
                params={"report_date": REPORT_DAY.isoformat(), "market": "KR"},
            )
            assert gen.status_code == 201
            sections = gen.json()["sections"]
            assert sections["signal_activity"] == {"total": 2, "buy": 1, "sell": 1}
            assert sections["trade_summary"]["trades"] == 2
            assert sections["trade_summary"]["win_count"] == 1
            assert sections["trade_summary"]["loss_count"] == 1
            assert Decimal(sections["trade_summary"]["realized_pnl"]) == Decimal("60")
            assert sections["scanner_activity"]["candidates"] == 1
            assert sections["active_strategies"] >= 1
            assert gen.json()["summary"].startswith("[2026-06-17]")
    finally:
        app.dependency_overrides.clear()


async def test_generate_is_idempotent_per_date(db_session: AsyncSession) -> None:
    await _seed_day(db_session)
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            first = await client.post(
                "/api/v1/daily-reports/generate", params={"report_date": REPORT_DAY.isoformat()}
            )
            second = await client.post(
                "/api/v1/daily-reports/generate", params={"report_date": REPORT_DAY.isoformat()}
            )
            assert first.json()["id"] == second.json()["id"]  # 같은 row 갱신

            listing = await client.get("/api/v1/daily-reports")
            same_date = [r for r in listing.json() if r["report_date"] == REPORT_DAY.isoformat()]
            assert len(same_date) == 1
    finally:
        app.dependency_overrides.clear()


async def test_empty_day_report_and_get(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/daily-reports/generate", params={"report_date": "2026-06-01"}
            )
            got = await client.get("/api/v1/daily-reports/2026-06-01")
            assert got.status_code == 200
            assert got.json()["sections"]["signal_activity"]["total"] == 0
            assert got.json()["sections"]["trade_summary"]["trades"] == 0

            missing = await client.get("/api/v1/daily-reports/2025-01-01")
            assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
