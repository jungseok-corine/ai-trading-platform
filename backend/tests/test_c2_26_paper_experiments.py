"""C-2.26 Paper Experiment Framework 테스트."""

from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, TradeSide
from app.domain.models.trade import Trade
from app.main import app
from app.services.strategy_service import StrategyService
from app.trading.experiment.metrics import compute_metrics


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session

    return _get_db


# --- 순수 지표 계산 -----------------------------------------------------------
def test_compute_metrics_basic() -> None:
    m = compute_metrics([Decimal("100"), Decimal("-50"), Decimal("200"), Decimal("-30")])
    assert m.trades_count == 4
    assert m.win_count == 2
    assert m.loss_count == 2
    assert m.win_rate == Decimal("50.00")
    assert m.avg_profit == Decimal("150.0000")
    assert m.avg_loss == Decimal("40.0000")
    assert m.profit_factor == Decimal("3.7500")
    assert m.expectancy == Decimal("55.0000")
    assert m.max_drawdown == Decimal("50.0000")


def test_compute_metrics_empty_and_no_losses() -> None:
    empty = compute_metrics([])
    assert empty.trades_count == 0
    assert empty.win_rate == Decimal("0")
    assert empty.profit_factor is None
    assert empty.expectancy == Decimal("0")

    no_losses = compute_metrics([Decimal("10"), Decimal("20")])
    assert no_losses.profit_factor is None  # 손실 0 → 손익비 정의 안 됨
    assert no_losses.win_rate == Decimal("100.00")
    assert no_losses.max_drawdown == Decimal("0.0000")


# --- DB 통합: 실험 비교 -------------------------------------------------------
async def _seed_version_with_trades(
    session: AsyncSession, account_id: int, pnls: list[str]
) -> int:
    """strategy + version을 만들고, 해당 version에 pnl 체결들을 넣은 뒤 version_id 반환."""
    svc = StrategyService(session)
    strategy = await svc.create_strategy(f"exp-strategy-{account_id}-{pnls[0] if pnls else 'x'}-{len(pnls)}")
    version = await svc.create_version(strategy.id, parameters={"symbol_code": "005930"})
    for p in pnls:
        session.add(
            Trade(
                account_id=account_id,
                strategy_version_id=version.id,
                symbol_code="005930",
                side=TradeSide.BUY,
                quantity=1,
                pnl_amount=Decimal(p),
                order_status=OrderStatus.FILLED,
            )
        )
    await session.commit()
    return version.id


async def test_experiment_compare_picks_winner(db_session: AsyncSession) -> None:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    db_session.add(account)
    await db_session.commit()

    champion_vid = await _seed_version_with_trades(
        db_session, account.id, ["100", "-50", "200", "-30"]  # expectancy 55
    )
    challenger_vid = await _seed_version_with_trades(
        db_session, account.id, ["10", "-5"]  # expectancy 2.5
    )

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            exp_id = (
                await client.post("/api/v1/experiments", json={"name": "v1 vs v2"})
            ).json()["id"]

            champ = await client.post(
                f"/api/v1/experiments/{exp_id}/variants",
                json={"strategy_version_id": champion_vid, "role": "champion", "label": "v1"},
            )
            assert champ.status_code == 201
            champ_variant_id = champ.json()["id"]

            await client.post(
                f"/api/v1/experiments/{exp_id}/variants",
                json={"strategy_version_id": challenger_vid, "role": "challenger"},
            )

            # 상세 조회에 variant 2개
            detail = await client.get(f"/api/v1/experiments/{exp_id}")
            assert len(detail.json()["variants"]) == 2

            comp = await client.post(f"/api/v1/experiments/{exp_id}/compare")
            assert comp.status_code == 200
            body = comp.json()
            assert body["winner_variant_id"] == champ_variant_id

            champ_metrics = next(
                v["metrics"] for v in body["variants"] if v["variant_id"] == champ_variant_id
            )
            assert champ_metrics["expectancy"] == "55.0000"
            assert champ_metrics["win_rate"] == "50.00"
            assert champ_metrics["max_drawdown"] == "50.0000"
    finally:
        app.dependency_overrides.clear()


async def test_compare_persist_saves_results(db_session: AsyncSession) -> None:
    from app.domain.models.experiment import ExperimentResult
    from sqlalchemy import select

    account = Account(account_type=AccountType.PAPER, broker_account_no="00000001")
    db_session.add(account)
    await db_session.commit()
    vid = await _seed_version_with_trades(db_session, account.id, ["50", "-20"])

    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            exp_id = (
                await client.post("/api/v1/experiments", json={"name": "persist"})
            ).json()["id"]
            await client.post(
                f"/api/v1/experiments/{exp_id}/variants",
                json={"strategy_version_id": vid, "role": "champion"},
            )
            await client.post(f"/api/v1/experiments/{exp_id}/compare", params={"persist": "true"})

        rows = (await db_session.execute(select(ExperimentResult))).scalars().all()
        assert len(rows) == 1
        assert rows[0].trades_count == 2
    finally:
        app.dependency_overrides.clear()


async def test_add_variant_invalid_version_returns_422(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            exp_id = (
                await client.post("/api/v1/experiments", json={"name": "bad variant"})
            ).json()["id"]
            resp = await client.post(
                f"/api/v1/experiments/{exp_id}/variants",
                json={"strategy_version_id": 999999},
            )
            assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


async def test_compare_unknown_experiment_returns_404(db_session: AsyncSession) -> None:
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/experiments/999999/compare")
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
