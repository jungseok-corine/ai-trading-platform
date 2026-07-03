"""C-7.4: 전략 종합 선정 보드 — 점수 함수 + 보드 집계."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.services.strategy_selection_service import (
    StrategySelectionService,
    composite_score,
)

_BT_OK = {"status": "succeeded", "return_pct": 50.0, "max_drawdown_pct": 15.0}


def test_composite_score_ranges_and_neutrality():
    # 무데이터 → 전 축 중립 = 50
    neutral = composite_score(
        backtest=None, paper_expectancy=None, paper_samples=0,
        retro_verdict=None, regime_fit=None, current_regime=None,
    )
    assert neutral["total"] == 50.0

    # 좋은 백테스트 + 개선 회고 + 레짐 일치 → 중립보다 높다
    good = composite_score(
        backtest=_BT_OK, paper_expectancy=500.0, paper_samples=12,
        retro_verdict="improved", regime_fit="trend", current_regime="risk_on",
    )
    assert good["total"] > 70

    # 악화 회고 + 레짐 불일치 → 중립보다 낮다
    bad = composite_score(
        backtest={"status": "succeeded", "return_pct": -10.0, "max_drawdown_pct": 40.0},
        paper_expectancy=-800.0, paper_samples=15,
        retro_verdict="worse", regime_fit="trend", current_regime="risk_off",
    )
    assert bad["total"] < 35
    assert 0 <= bad["total"] <= 100 and 0 <= good["total"] <= 100


def test_paper_low_sample_stays_near_neutral():
    """표본 1건의 극단 기대값이 점수를 좌우하지 않는다."""
    s = composite_score(
        backtest=None, paper_expectancy=99999.0, paper_samples=1,
        retro_verdict=None, regime_fit=None, current_regime=None,
    )
    assert s["paper"] <= 22.0  # confidence 0.1 → 중립 근처


@pytest.mark.asyncio
async def test_board_ranks_live_versions(db_session: AsyncSession):
    strategy = Strategy(name="board test", description="t")
    db_session.add(strategy)
    await db_session.flush()
    for no, status in ((1, StrategyVersionStatus.TESTING), (2, StrategyVersionStatus.ARCHIVED)):
        db_session.add(StrategyVersion(
            strategy_id=strategy.id, version_no=no,
            parameters={"strategy_type": "rule_based", "timeframe": "1d", "regime_fit": "trend"},
            status=status,
        ))
    await db_session.commit()

    board = await StrategySelectionService(db_session).board()
    assert board["count"] == 1  # archived 제외
    row = board["rows"][0]
    assert row["regime_fit"] == "trend"
    assert "total" in row["score"]
    assert "사람" in board["note"]
