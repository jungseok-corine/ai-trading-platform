"""M2.15B-2 — daily candle collector tests (네트워크 없이 MockTransport / FakeProvider).

실 KIS/실 키 미사용 · dry-run 무쓰기 · 멱등 upsert · 인트라데이 미덮어쓰기 · SignalLog/Trade/Order 0.
테스트 DB(트랜잭션 롤백)에서만 데이터 생성 — dev DB 미실행.
"""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from app.common.timezone import KST
from app.domain.models.market_data import MarketData
from app.domain.models.signal_log import SignalLog
from app.domain.models.trade import Trade
from app.trading.broker.kis_paper import KISPaperBrokerClient, _parse_daily_row
from app.trading.broker.schemas import DailyCandle
import scripts.collect_daily_candles as cli
from app.services.market_data_daily_collector import (
    DAILY_TIMEFRAME, MarketDataDailyCollector, sanitize,
)

FAKE_KEY = "FAKE_TEST_KEY"


async def _count(s, m):
    return (await s.execute(select(func.count()).select_from(m))).scalar_one()


def _dc(date: str, o, h, lo, c, v, tv=None) -> DailyCandle:
    return DailyCandle(business_date=date, open_price=Decimal(o), high_price=Decimal(h),
                       low_price=Decimal(lo), close_price=Decimal(c), volume=v, trading_value=tv)


class _FakeProvider:
    def __init__(self, by_symbol=None, raises=None):
        self._by = by_symbol or {}
        self._raises = raises or {}

    async def get_daily_candles(self, symbol_code, count=252, **kw):
        if symbol_code in self._raises:
            raise self._raises[symbol_code]
        return self._by.get(symbol_code, [])


# --- parse / mapping ---------------------------------------------------------
def test_parse_daily_row_valid():
    c = _parse_daily_row({"stck_bsop_date": "20260626", "stck_oprc": "5000", "stck_hgpr": "5100",
                          "stck_lwpr": "4950", "stck_clpr": "5050", "acml_vol": "1234",
                          "acml_tr_pbmn": "6200000"})
    assert c is not None and c.business_date == "20260626" and c.close_price == Decimal("5050")
    assert c.volume == 1234 and c.trading_value == Decimal("6200000")


def test_parse_daily_row_missing_or_invalid():
    assert _parse_daily_row({"stck_bsop_date": "."}) is None
    assert _parse_daily_row({"stck_bsop_date": "20260626", "stck_oprc": ".", "stck_hgpr": "1",
                             "stck_lwpr": "1", "stck_clpr": "1"}) is None  # 결측 가격
    c = _parse_daily_row({"stck_bsop_date": "20260626", "stck_oprc": "1", "stck_hgpr": "2",
                          "stck_lwpr": "1", "stck_clpr": "2", "acml_vol": "x"})
    assert c is not None and c.volume == 0  # 비정상 volume → 0


async def test_get_daily_candles_maps_and_no_secret_leak():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rt_cd": "0", "msg1": "ok", "output2": [
            {"stck_bsop_date": "20260626", "stck_oprc": "5000", "stck_hgpr": "5100",
             "stck_lwpr": "4950", "stck_clpr": "5050", "acml_vol": "100"},
            {"stck_bsop_date": "20260625", "stck_oprc": "4900", "stck_hgpr": "4980",
             "stck_lwpr": "4880", "stck_clpr": "4950", "acml_vol": "90"},
        ]})

    broker = KISPaperBrokerClient(
        account_no="50000000-01", market_div_code="J",
        base_url="https://openapivts.koreainvestment.com:29443",
        app_key=FAKE_KEY, app_secret="s",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        token_cache_path=Path("/tmp/test_kis_daily.json"),
        rate_limit_min_interval_seconds=0.0, rate_limit_cooldown_seconds=0.0,
    )
    broker._get_access_token = AsyncMock(return_value="tok")  # type: ignore[method-assign]
    candles = await broker.get_daily_candles("005930", count=252)
    assert len(candles) == 2 and candles[0].close_price == Decimal("5050")


def test_sanitize_masks_secrets():
    out = sanitize("err appkey=ABC123 token=XYZ api_key=zzz")
    for tok in ("ABC123", "XYZ", "zzz"):
        assert tok not in out
    assert "***REDACTED***" in out


# --- collector dry-run / coverage (no writes) --------------------------------
async def test_dry_run_no_writes(db_session: AsyncSession):
    before = await _count(db_session, MarketData)
    col = MarketDataDailyCollector(db_session)
    rep = await col.collect(["005930"], count=252, execute=False)
    assert rep.mode == "dry_run" and rep.writes == 0
    assert "no DB writes" in " ".join(rep.warnings).lower() or any("DRY-RUN" in w for w in rep.warnings)
    assert await _count(db_session, MarketData) == before


async def test_coverage_report_thresholds(db_session: AsyncSession):
    # 25개 일봉 seed
    for i in range(25):
        db_session.add(MarketData(symbol_code="005930", timeframe=DAILY_TIMEFRAME,
                                  ts=datetime(2026, 1, 1, tzinfo=KST).replace(day=(i % 28) + 1),
                                  open=Decimal("1"), high=Decimal("1"), low=Decimal("1"),
                                  close=Decimal("1"), volume=1))
    await db_session.flush()
    rep = await MarketDataDailyCollector(db_session).coverage_report(["005930"])
    row = rep["per_symbol"][0]
    assert row["daily_candles"] == 25 and row["has_20"] is True and row["has_50"] is False
    assert row["ready_for_52w"] is False


# --- collector execute (test DB only) ---------------------------------------
async def test_execute_idempotent_upsert(db_session: AsyncSession):
    prov = _FakeProvider({"005930": [_dc("20260626", "5000", "5100", "4950", "5050", 100),
                                     _dc("20260625", "4900", "4980", "4880", "4950", 90)]})
    sl0 = await _count(db_session, SignalLog); tr0 = await _count(db_session, Trade)
    col = MarketDataDailyCollector(db_session, daily_provider=prov)
    rep = await col.collect(["005930"], execute=True)
    assert rep.mode == "execute" and rep.per_symbol[0].status == "success"
    assert rep.per_symbol[0].inserted == 2
    n1 = await _count(db_session, MarketData)
    # 재실행 → 멱등(중복 없음)
    rep2 = await MarketDataDailyCollector(db_session, daily_provider=prov).collect(["005930"], execute=True)
    assert rep2.per_symbol[0].status == "skipped_fresh"
    assert await _count(db_session, MarketData) == n1
    # SignalLog/Trade 미생성
    assert await _count(db_session, SignalLog) == sl0
    assert await _count(db_session, Trade) == tr0


async def test_execute_does_not_overwrite_intraday(db_session: AsyncSession):
    ts = datetime(2026, 6, 26, 9, 30, tzinfo=KST)
    db_session.add(MarketData(symbol_code="005930", timeframe="5m", ts=ts,
                              open=Decimal("1"), high=Decimal("2"), low=Decimal("1"),
                              close=Decimal("2"), volume=7))
    await db_session.flush()
    prov = _FakeProvider({"005930": [_dc("20260626", "5000", "5100", "4950", "5050", 100)]})
    await MarketDataDailyCollector(db_session, daily_provider=prov).collect(["005930"], execute=True)
    intraday = await db_session.get(MarketData, ("005930", "5m", ts))
    assert intraday is not None and intraday.close == Decimal("2") and intraday.volume == 7  # 불변


async def test_execute_conflict_conservative(db_session: AsyncSession):
    ts = datetime(2026, 6, 26, tzinfo=KST)
    db_session.add(MarketData(symbol_code="005930", timeframe=DAILY_TIMEFRAME, ts=ts,
                              open=Decimal("1"), high=Decimal("1"), low=Decimal("1"),
                              close=Decimal("9"), volume=1))  # 다른 종가
    await db_session.flush()
    prov = _FakeProvider({"005930": [_dc("20260626", "5000", "5100", "4950", "5050", 100)]})
    rep = await MarketDataDailyCollector(db_session, daily_provider=prov).collect(["005930"], execute=True)
    assert rep.per_symbol[0].status == "conflict"
    row = await db_session.get(MarketData, ("005930", DAILY_TIMEFRAME, ts))
    assert row.close == Decimal("9")  # 보존(미덮어쓰기)
    # overwrite=True면 갱신
    rep2 = await MarketDataDailyCollector(db_session, daily_provider=prov).collect(
        ["005930"], execute=True, overwrite=True)
    assert rep2.per_symbol[0].status == "success"
    await db_session.refresh(row)
    assert row.close == Decimal("5050")


async def test_execute_partial_success_and_classification(db_session: AsyncSession):
    prov = _FakeProvider(
        {"005930": [_dc("20260626", "5000", "5100", "4950", "5050", 100)]},
        raises={"000660": RuntimeError("KIS API error rate limit EGW00201"),
                "111111": RuntimeError("bad symbol")},
    )
    rep = await MarketDataDailyCollector(db_session, daily_provider=prov).collect(
        ["005930", "000660", "111111"], execute=True)
    by = {r.symbol_code: r.status for r in rep.per_symbol}
    assert by["005930"] == "success"
    assert by["000660"] == "failed_transient"   # rate/EGW00201
    assert by["111111"] == "failed_permanent"


async def test_execute_insufficient_data(db_session: AsyncSession):
    prov = _FakeProvider({"005930": []})
    rep = await MarketDataDailyCollector(db_session, daily_provider=prov).collect(["005930"], execute=True)
    assert rep.per_symbol[0].status == "insufficient_data"


# --- script guards (pure) ----------------------------------------------------
class _FakeSettings:
    def __init__(self, app_env="development", real=False, runner=False, dispatcher=False,
                 db_url="postgresql+asyncpg://trading:trading@localhost:5432/trading_platform"):
        self.app_env = app_env
        self.kis_real_trading_enabled = real
        self.paper_signal_session_runner_enabled = runner
        self.paper_signal_recurring_plan_dispatcher_enabled = dispatcher
        self.database_url = db_url


def test_guard_all_good():
    assert cli.evaluate_guards(_FakeSettings(), confirm=True, execute=True) == []


def test_guard_missing_confirm_and_execute():
    assert any("confirm" in x for x in cli.evaluate_guards(_FakeSettings(), confirm=False, execute=True))
    assert any("execute" in x for x in cli.evaluate_guards(_FakeSettings(), confirm=True, execute=False))


def test_guard_production_and_flags_and_db():
    assert cli.evaluate_guards(_FakeSettings(app_env="production"), confirm=True, execute=True)
    assert cli.evaluate_guards(_FakeSettings(real=True), confirm=True, execute=True)
    assert cli.evaluate_guards(_FakeSettings(runner=True), confirm=True, execute=True)
    assert cli.evaluate_guards(_FakeSettings(dispatcher=True), confirm=True, execute=True)
    assert cli.evaluate_guards(
        _FakeSettings(db_url="postgresql+asyncpg://u:p@prod-db.example.com/main"),
        confirm=True, execute=True)
