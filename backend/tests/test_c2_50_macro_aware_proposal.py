"""C-2.50 매크로 레짐을 반영한 스캐너 제안 테스트."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.enums import ScannerRuleStatus
from app.domain.models.market_data import MarketData
from app.domain.models.news_context import UsMarketSnapshot
from app.services.scanner_proposal_generator import (
    ScannerProposalGenerator,
    tighten_conditions,
)
from app.services.scanner_service import ScannerService

KST = ZoneInfo("Asia/Seoul")
T = datetime(2026, 6, 17, 10, 0, tzinfo=KST)


def _candle(symbol: str, off: int, close: str) -> MarketData:
    c = Decimal(close)
    return MarketData(symbol_code=symbol, timeframe="1m", ts=T + timedelta(minutes=off),
                      open=c, high=c, low=c, close=c, volume=1000)


def test_aggressive_tightening_is_stronger() -> None:
    conds = [{"type": "volume_spike", "params": {"multiplier": 2.0}},
             {"type": "turnover_rank", "params": {"max_rank": 100}}]
    normal = {c["type"]: c["params"] for c in tighten_conditions(conds).conditions}
    aggro = {c["type"]: c["params"] for c in tighten_conditions(conds, aggressive=True).conditions}
    assert normal["volume_spike"]["multiplier"] == 2.6  # 2.0 * 1.3
    assert aggro["volume_spike"]["multiplier"] == 2.9  # 2.0 * 1.45
    assert normal["turnover_rank"]["max_rank"] == 70  # 100 * 0.7
    assert aggro["turnover_rank"]["max_rank"] == 60  # 100 * 0.6


async def _seed_low_winrate(session: AsyncSession) -> int:
    scanner = ScannerService(session)
    rule = await scanner.create_rule("weak")
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    wins = {"005930"}
    for sym in ["005930", "000660", "035420", "051910", "006400"]:
        exit_close = "110" if sym in wins else "90"
        session.add_all([_candle(sym, 0, "100"), _candle(sym, 30, exit_close)])
        session.add(CandidateEvent(scanner_rule_version_id=sv.id, symbol_code=sym,
                                   triggered_at=T, score=80, matched_conditions=["volume_spike"]))
    await session.commit()
    return sv.id


async def test_risk_off_makes_proposal_more_conservative(db_session: AsyncSession) -> None:
    sv_id = await _seed_low_winrate(db_session)
    # 위험회피(risk_off): VIX 높음
    db_session.add(UsMarketSnapshot(session_date=date(2026, 6, 16), vix=Decimal("32.0"),
                                    nasdaq_change_pct=Decimal("-1.5")))
    await db_session.commit()

    proposal = await ScannerProposalGenerator(db_session).generate_for_version(sv_id)
    assert proposal is not None
    mult = {c["type"]: c["params"] for c in proposal.suggested_conditions}["volume_spike"]["multiplier"]
    assert mult == 2.9  # aggressive (×1.45)
    assert "risk_off" in proposal.rationale
    assert "위험회피" in proposal.rationale


async def test_risk_on_uses_normal_tightening(db_session: AsyncSession) -> None:
    sv_id = await _seed_low_winrate(db_session)
    db_session.add(UsMarketSnapshot(session_date=date(2026, 6, 16), vix=Decimal("12.0"),
                                    nasdaq_change_pct=Decimal("1.5"), sp500_change_pct=Decimal("1.2")))
    await db_session.commit()

    proposal = await ScannerProposalGenerator(db_session).generate_for_version(sv_id)
    assert proposal is not None
    mult = {c["type"]: c["params"] for c in proposal.suggested_conditions}["volume_spike"]["multiplier"]
    assert mult == 2.6  # normal (×1.3)
    assert "risk_on" in proposal.rationale


async def test_no_us_snapshot_still_proposes_normally(db_session: AsyncSession) -> None:
    sv_id = await _seed_low_winrate(db_session)
    # 미국장 데이터 없음 → regime unknown → 일반 강화
    proposal = await ScannerProposalGenerator(db_session).generate_for_version(sv_id)
    assert proposal is not None
    mult = {c["type"]: c["params"] for c in proposal.suggested_conditions}["volume_spike"]["multiplier"]
    assert mult == 2.6
