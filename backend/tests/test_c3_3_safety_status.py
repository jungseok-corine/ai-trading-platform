"""C-3.3 안전 불변식 점검 패널 테스트."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.services.safety_status_service import SafetyStatusService


async def test_default_is_safe(db_session: AsyncSession) -> None:
    out = await SafetyStatusService(db_session).status()
    # 기본 설정은 실거래 off (안전 불변식)
    assert out["real_trading_enabled"] is False
    assert out["auto_trade_versions"] == 0
    assert out["invariants_ok"] is True
    assert out["warnings"] == []
    # 스케줄러 키들이 노출된다
    assert "strategy_scheduler_enabled" in out["schedulers"]


async def test_auto_trade_version_flags_warning(db_session: AsyncSession) -> None:
    strat = Strategy(name="SafetyStrat", description="t")
    db_session.add(strat)
    await db_session.flush()
    # 활성 버전 + auto_trade_enabled=true → 경고
    db_session.add(StrategyVersion(
        strategy_id=strat.id, version_no=1,
        parameters={"strategy_type": "moving_average_cross", "auto_trade_enabled": True},
        status=StrategyVersionStatus.ACTIVE,
    ))
    # DRAFT 버전의 auto_trade=true는 활성/테스트가 아니므로 카운트 제외
    db_session.add(StrategyVersion(
        strategy_id=strat.id, version_no=2,
        parameters={"strategy_type": "moving_average_cross", "auto_trade_enabled": True},
        status=StrategyVersionStatus.DRAFT,
    ))
    await db_session.flush()

    out = await SafetyStatusService(db_session).status()
    assert out["auto_trade_versions"] == 1
    assert out["invariants_ok"] is False
    assert any("auto_trade_enabled" in w for w in out["warnings"])
