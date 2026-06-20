"""C-2.51 매크로 레짐을 반영한 전략 제안 테스트."""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, StrategyVersionStatus, TradeSide
from app.domain.models.news_context import UsMarketSnapshot
from app.domain.models.trade import Trade
from app.services.proposal_generator import ProposalGeneratorService, suggest_parameter_change
from app.services.strategy_service import StrategyService
from app.trading.experiment.metrics import compute_metrics


def test_aggressive_volume_strategy_is_stronger() -> None:
    metrics = compute_metrics([Decimal("-10")] * 6)
    normal = suggest_parameter_change(
        "volume_confirmed_ma_cross", {"volume_multiplier": 2.0}, metrics, aggressive=False
    )
    aggro = suggest_parameter_change(
        "volume_confirmed_ma_cross", {"volume_multiplier": 2.0}, metrics, aggressive=True
    )
    assert normal.suggested_parameters["volume_multiplier"] == 2.6  # 2.0 * 1.3
    assert aggro.suggested_parameters["volume_multiplier"] == 2.9  # 2.0 * 1.45
    assert "위험회피" in aggro.rationale


def test_aggressive_ma_widens_more() -> None:
    metrics = compute_metrics([Decimal("-5")] * 6)
    normal = suggest_parameter_change(
        "moving_average_cross", {"long_window": 20}, metrics, aggressive=False
    )
    aggro = suggest_parameter_change(
        "moving_average_cross", {"long_window": 20}, metrics, aggressive=True
    )
    assert normal.suggested_parameters["long_window"] == 25  # +5
    assert aggro.suggested_parameters["long_window"] == 28  # +8


async def _seed_losing(session: AsyncSession) -> tuple[int, int]:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    session.add(account)
    await session.commit()
    svc = StrategyService(session)
    strategy = await svc.create_strategy("macro-strat")
    version = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "volume_confirmed_ma_cross", "volume_multiplier": 2.0},
        status=StrategyVersionStatus.TESTING,
    )
    for _ in range(6):
        session.add(Trade(account_id=account.id, strategy_version_id=version.id,
                          symbol_code="005930", side=TradeSide.BUY, quantity=1,
                          pnl_amount=Decimal("-10"), order_status=OrderStatus.FILLED))
    await session.commit()
    return strategy.id, version.id


async def test_generator_uses_risk_off(db_session: AsyncSession) -> None:
    sid, vid = await _seed_losing(db_session)
    db_session.add(UsMarketSnapshot(session_date=date(2026, 6, 16), vix=Decimal("33.0"),
                                    nasdaq_change_pct=Decimal("-2.0")))
    await db_session.commit()
    proposal = await ProposalGeneratorService(db_session).generate_for_version(sid, vid)
    assert proposal is not None
    assert proposal.suggested_parameters["volume_multiplier"] == 2.9
    assert "위험회피" in proposal.rationale


async def test_generator_normal_without_risk_off(db_session: AsyncSession) -> None:
    sid, vid = await _seed_losing(db_session)
    # 미국장 데이터 없음 → 일반 강화
    proposal = await ProposalGeneratorService(db_session).generate_for_version(sid, vid)
    assert proposal is not None
    assert proposal.suggested_parameters["volume_multiplier"] == 2.6
