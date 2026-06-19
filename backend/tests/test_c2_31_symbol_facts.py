"""C-2.31 Symbol Facts Computation & Scan Loop 테스트."""

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.investor_flow import InvestorFlow
from app.domain.models.market_data import MarketData
from app.main import app
from app.services.scanner_service import ScannerService
from app.domain.models.enums import ScannerRuleStatus
from app.trading.scanner.facts import (
    assign_turnover_ranks,
    compute_price_change_pct,
    compute_symbol_facts,
    compute_volume_ratio,
    flow_direction,
    time_bucket,
)

KST = ZoneInfo("Asia/Seoul")


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


# --- 순수 함수 ----------------------------------------------------------------
def test_time_bucket() -> None:
    base = datetime(2026, 6, 17, 0, 0, tzinfo=KST)
    assert time_bucket(base.replace(hour=8)) == "premarket"
    assert time_bucket(base.replace(hour=9, minute=30)) == "morning"
    assert time_bucket(base.replace(hour=12)) == "midday"
    assert time_bucket(base.replace(hour=14)) == "afternoon"
    assert time_bucket(base.replace(hour=16)) == "after_hours"


def test_flow_direction() -> None:
    assert flow_direction(100) == "net_buy"
    assert flow_direction(-100) == "net_sell"
    assert flow_direction(0) == "neutral"
    assert flow_direction(None) is None


def test_volume_ratio_and_price_change() -> None:
    volumes = [1000] * 19 + [5000]  # 20개
    ratio = compute_volume_ratio(volumes, 20)
    assert ratio is not None and ratio > Decimal("4")  # 5000 / 1200

    assert compute_volume_ratio([1000], 20) is None  # 데이터 부족

    closes = [Decimal("100")] * 5 + [Decimal("110")]
    assert compute_price_change_pct(closes) == Decimal("10")
    assert compute_price_change_pct(closes, reference_price=Decimal("100")) == Decimal("10")


def test_assign_turnover_ranks() -> None:
    facts = {"A": {}, "B": {}, "C": {}}
    turnover = {"A": Decimal("100"), "B": Decimal("300"), "C": Decimal("200")}
    assign_turnover_ranks(facts, turnover)
    assert facts["B"]["turnover_rank"] == 1
    assert facts["C"]["turnover_rank"] == 2
    assert facts["A"]["turnover_rank"] == 3


def test_compute_symbol_facts_integrates_flow() -> None:
    class _Flow:
        foreign_net_buy_quantity = 1000
        institution_net_buy_quantity = -50
        individual_net_buy_quantity = 0

    facts = compute_symbol_facts(
        [Decimal("100"), Decimal("105")],
        [1000] * 19 + [4000],
        latest_flow=_Flow(),
        now=datetime(2026, 6, 17, 9, 30, tzinfo=KST),
        volume_window=20,
    )
    assert facts["foreign_flow"] == "net_buy"
    assert facts["institution_flow"] == "net_sell"
    assert facts["individual_flow"] == "neutral"
    assert facts["time_bucket"] == "morning"
    assert facts["price_change_pct"] == 5.0


# --- 통합: 시장 데이터로 스캔 -------------------------------------------------
async def _seed_market_data(session: AsyncSession) -> None:
    base = datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc)

    # A: 거래량 급증 + 상승 10%
    for i in range(25):
        close = Decimal("110") if i == 24 else Decimal("100")
        vol = 5000 if i == 24 else 1000
        session.add(
            MarketData(symbol_code="005930", timeframe="1m", ts=base.replace(minute=i),
                       open=close, high=close, low=close, close=close, volume=vol)
        )
    # B: 변화 없음
    for i in range(25):
        session.add(
            MarketData(symbol_code="000660", timeframe="1m", ts=base.replace(minute=i),
                       open=Decimal("100"), high=Decimal("100"), low=Decimal("100"),
                       close=Decimal("100"), volume=1000)
        )
    # A 수급: 외국인 순매수
    session.add(
        InvestorFlow(symbol_code="005930", trade_date=datetime(2026, 6, 16).date(),
                     foreign_net_buy_quantity=10000, institution_net_buy_quantity=5000,
                     individual_net_buy_quantity=-15000)
    )
    await session.commit()


async def test_scan_market_computes_facts_and_records_candidate(db_session: AsyncSession) -> None:
    await _seed_market_data(db_session)
    scanner = ScannerService(db_session)
    rule = await scanner.create_rule("morning spike")
    version = await scanner.create_version(
        rule.id,
        conditions=[
            {"type": "volume_spike", "params": {"multiplier": 2.0}},
            {"type": "price_change_pct", "params": {"min_pct": 5.0}},
            {"type": "investor_flow", "params": {"foreign": "net_buy"}},
            {"type": "turnover_rank", "params": {"max_rank": 5}},
        ],
        status=ScannerRuleStatus.TESTING,
    )

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            scan = await client.post(
                f"/api/v1/scanner-rules/{rule.id}/versions/{version.id}/scan-market",
                json={"symbol_codes": ["005930", "000660"], "timeframe": "1m", "volume_window": 20},
            )
            assert scan.status_code == 201
            body = scan.json()
            assert body["scanned"] == 2
            assert body["matched"] == 1  # A만 통과

            cand = body["candidates"][0]
            assert cand["symbol_code"] == "005930"
            assert cand["facts"]["volume_ratio"] > 2
            assert cand["facts"]["price_change_pct"] >= 5
            assert cand["facts"]["turnover_rank"] == 1
            assert cand["facts"]["foreign_flow"] == "net_buy"
    finally:
        app.dependency_overrides.clear()


async def test_scan_market_unknown_version_404(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/api/v1/scanner-rules/1/versions/999999/scan-market",
                json={"symbol_codes": ["005930"]},
            )
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
