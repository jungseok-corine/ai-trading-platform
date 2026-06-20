"""C-2.49 매크로 레짐 분류 + 맥락 캡처 주입 테스트."""

from datetime import date
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.news_context import UsMarketSnapshot
from app.main import app
from app.services.macro_regime_service import MacroRegimeService, classify_macro_regime
from app.services.market_context_capture_service import MarketContextCaptureService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


def _snap(**kw) -> UsMarketSnapshot:
    return UsMarketSnapshot(session_date=date(2026, 6, 18), **kw)


# --- 순수 분류 --------------------------------------------------------------
def test_classify_none_is_unknown() -> None:
    assert classify_macro_regime(None)["regime"] == "unknown"


def test_classify_risk_on() -> None:
    r = classify_macro_regime(_snap(
        vix=Decimal("13.0"), nasdaq_change_pct=Decimal("1.5"),
        sp500_change_pct=Decimal("1.1"), sox_change_pct=Decimal("3.0"),
    ))
    assert r["regime"] == "risk_on"
    assert r["vix_level"] == "low"
    assert r["us_trend"] == "up"
    assert r["semis_strength"] == "strong"


def test_classify_risk_off_on_high_vix() -> None:
    r = classify_macro_regime(_snap(vix=Decimal("30.0"), nasdaq_change_pct=Decimal("0.2")))
    assert r["regime"] == "risk_off"
    assert r["vix_level"] == "high"


def test_classify_risk_off_on_down_market() -> None:
    r = classify_macro_regime(_snap(
        vix=Decimal("18.0"), nasdaq_change_pct=Decimal("-1.2"),
        sp500_change_pct=Decimal("-0.9"),
    ))
    assert r["regime"] == "risk_off"
    assert r["us_trend"] == "down"


def test_classify_neutral() -> None:
    r = classify_macro_regime(_snap(vix=Decimal("18.0"), nasdaq_change_pct=Decimal("0.1")))
    assert r["regime"] == "neutral"


# --- 서비스 / 캡처 ----------------------------------------------------------
async def test_latest_regime_reads_db(db_session: AsyncSession) -> None:
    db_session.add(_snap(vix=Decimal("12.0"), nasdaq_change_pct=Decimal("1.5"),
                         sp500_change_pct=Decimal("1.2")))
    await db_session.commit()
    r = await MacroRegimeService(db_session).latest_regime()
    assert r["regime"] == "risk_on"
    assert r["session_date"] == "2026-06-18"


async def test_capture_embeds_macro(db_session: AsyncSession) -> None:
    db_session.add(_snap(vix=Decimal("30.0"), nasdaq_change_pct=Decimal("-2.0"),
                         sp500_change_pct=Decimal("-1.5")))
    await db_session.commit()
    snapshot = await MarketContextCaptureService(db_session).capture()
    assert snapshot.data["macro"]["regime"] == "risk_off"
    assert snapshot.index_trend == "down"


async def test_macro_via_api_and_status(db_session: AsyncSession) -> None:
    db_session.add(_snap(vix=Decimal("13.0"), nasdaq_change_pct=Decimal("1.5"),
                         sp500_change_pct=Decimal("1.0"), sox_change_pct=Decimal("2.0")))
    await db_session.commit()
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            regime = await client.get("/api/v1/market-context/macro-regime")
            assert regime.status_code == 200
            assert regime.json()["regime"] == "risk_on"

            status = await client.get("/api/v1/research-status")
            assert status.status_code == 200
            assert status.json()["macro"]["regime"] == "risk_on"
    finally:
        app.dependency_overrides.clear()
