"""C-2.46 AI 제안 회고 테스트."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

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
from app.domain.models.market_data import MarketData
from app.domain.models.trade import Trade
from app.main import app
from app.services.proposal_retrospective_service import ProposalRetrospectiveService
from app.services.proposal_service import ProposalService
from app.services.scanner_proposal_service import ScannerProposalService
from app.services.scanner_service import ScannerService
from app.services.strategy_service import StrategyService

KST = ZoneInfo("Asia/Seoul")
T = datetime(2026, 6, 17, 10, 0, tzinfo=KST)


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


async def _trades(session, account_id, version_id, pnl: str, n: int) -> None:
    for _ in range(n):
        session.add(Trade(account_id=account_id, strategy_version_id=version_id,
                          symbol_code="005930", side=TradeSide.BUY, quantity=1,
                          pnl_amount=Decimal(pnl), order_status=OrderStatus.FILLED))


async def test_strategy_retro_improved(db_session: AsyncSession) -> None:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    db_session.add(account)
    await db_session.commit()
    svc = StrategyService(db_session)
    strategy = await svc.create_strategy("retro")
    base = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "moving_average_cross", "long_window": 20},
        status=StrategyVersionStatus.TESTING,
    )
    await _trades(db_session, account.id, base.id, "-10", 6)  # base 손실
    await db_session.commit()

    pservice = ProposalService(db_session)
    proposal = await pservice.create_proposal(
        strategy_id=strategy.id,
        suggested_parameters={"strategy_type": "moving_average_cross", "long_window": 25},
        title="장기선 확대", base_version_id=base.id,
    )
    approved, new_version = await pservice.approve(proposal.id, reviewed_by="u")
    await _trades(db_session, account.id, new_version.id, "20", 6)  # 새 버전 수익
    await db_session.commit()

    retro = await ProposalRetrospectiveService(db_session).retrospect_strategy(approved)
    assert retro.metric == "expectancy"
    assert retro.base_metric == -10.0
    assert retro.new_metric == 20.0
    assert retro.verdict == "improved"


async def test_strategy_retro_inconclusive_when_sparse(db_session: AsyncSession) -> None:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    db_session.add(account)
    await db_session.commit()
    svc = StrategyService(db_session)
    strategy = await svc.create_strategy("retro2")
    base = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "moving_average_cross", "long_window": 20},
        status=StrategyVersionStatus.TESTING,
    )
    await _trades(db_session, account.id, base.id, "-10", 6)
    await db_session.commit()
    pservice = ProposalService(db_session)
    proposal = await pservice.create_proposal(
        strategy_id=strategy.id,
        suggested_parameters={"strategy_type": "moving_average_cross", "long_window": 25},
        title="t", base_version_id=base.id,
    )
    approved, new_version = await pservice.approve(proposal.id)
    await _trades(db_session, account.id, new_version.id, "20", 2)  # 표본 부족(2건)
    await db_session.commit()

    retro = await ProposalRetrospectiveService(db_session).retrospect_strategy(approved)
    assert retro.new_samples == 2
    assert retro.verdict == "inconclusive"


def _candle(symbol: str, off: int, close: str) -> MarketData:
    c = Decimal(close)
    return MarketData(symbol_code=symbol, timeframe="1m", ts=T + timedelta(minutes=off),
                      open=c, high=c, low=c, close=c, volume=1000)


async def test_scanner_retro_and_summary(db_session: AsyncSession) -> None:
    scanner = ScannerService(db_session)
    rule = await scanner.create_rule("r")
    base = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    # base 버전: 5종목 전패(win_rate 0)
    for i, sym in enumerate(["00001", "00002", "00003", "00004", "00005"]):
        db_session.add_all([_candle(sym, 0, "100"), _candle(sym, 30, "90")])
        db_session.add(CandidateEvent(scanner_rule_version_id=base.id, symbol_code=sym,
                                      triggered_at=T, score=80, matched_conditions=["volume_spike"]))
    await db_session.commit()

    sps = ScannerProposalService(db_session)
    proposal = await sps.create_proposal(
        scanner_rule_id=rule.id,
        suggested_conditions=[{"type": "volume_spike", "params": {"multiplier": 2.6}}],
        title="강화", base_version_id=base.id,
    )
    approved, new_version = await sps.approve(proposal.id)
    # 새 버전: 5종목 전승(win_rate 100)
    for sym in ["10001", "10002", "10003", "10004", "10005"]:
        db_session.add_all([_candle(sym, 0, "100"), _candle(sym, 30, "110")])
        db_session.add(CandidateEvent(scanner_rule_version_id=new_version.id, symbol_code=sym,
                                      triggered_at=T, score=80, matched_conditions=["volume_spike"]))
    await db_session.commit()

    service = ProposalRetrospectiveService(db_session)
    retro = await service.retrospect_scanner(approved)
    assert retro.metric == "win_rate"
    assert retro.base_metric == 0.0
    assert retro.new_metric == 100.0
    assert retro.verdict == "improved"

    summary = await service.summary()
    assert summary["total"] == 1
    assert summary["improved"] == 1


async def test_retro_via_api(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/proposal-retrospective/summary")
            assert resp.status_code == 200
            assert resp.json() == {"total": 0, "improved": 0, "worse": 0, "inconclusive": 0}

            strat = await client.get("/api/v1/proposal-retrospective/strategy")
            assert strat.status_code == 200
            assert strat.json() == []
    finally:
        app.dependency_overrides.clear()
