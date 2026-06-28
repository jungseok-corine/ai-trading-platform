"""M2.14L — dev-only synthetic pair bootstrap tests.

테스트 DB(트랜잭션 롤백)에서만 데이터 생성. 실 dev DB에는 영속 합성 데이터를 만들지 않는다.
SignalLog/Trade/Order 0 · broker/KIS 미호출 · 스케줄러/디스패처 미활성 검증.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.paper_signal_recurring_run import PaperSignalRecurringRun
from app.domain.models.paper_signal_session import PaperSignalSession
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.trade import Trade
from scripts import dev_seed_synthetic_signal_pair as boot


class _FakeSettings:
    def __init__(self, app_env="development", real=False, runner=False, dispatcher=False,
                 db_url="postgresql+asyncpg://trading:trading@localhost:5432/trading_platform"):
        self.app_env = app_env
        self.kis_real_trading_enabled = real
        self.paper_signal_session_runner_enabled = runner
        self.paper_signal_recurring_plan_dispatcher_enabled = dispatcher
        self.database_url = db_url


async def _count(s, m):
    return (await s.execute(select(func.count()).select_from(m))).scalar_one()


# --- hard guards (pure) ------------------------------------------------------
def test_guard_all_good_passes():
    assert boot.evaluate_guards(_FakeSettings(), confirm=True, execute=True) == []


def test_guard_missing_confirm_refuses():
    r = boot.evaluate_guards(_FakeSettings(), confirm=False, execute=True)
    assert any("confirm" in x for x in r)


def test_guard_missing_execute_refuses():
    r = boot.evaluate_guards(_FakeSettings(), confirm=True, execute=False)
    assert any("execute" in x for x in r)


def test_guard_production_app_env_refuses():
    for env in ("production", "prod", "live-1"):
        r = boot.evaluate_guards(_FakeSettings(app_env=env), confirm=True, execute=True)
        assert any("production" in x for x in r), env


def test_guard_unsafe_flags_refuse():
    assert boot.evaluate_guards(_FakeSettings(real=True), confirm=True, execute=True)
    assert boot.evaluate_guards(_FakeSettings(runner=True), confirm=True, execute=True)
    assert boot.evaluate_guards(_FakeSettings(dispatcher=True), confirm=True, execute=True)


def test_guard_non_local_db_url_refuses():
    r = boot.evaluate_guards(
        _FakeSettings(db_url="postgresql+asyncpg://u:p@prod-db.example.com:5432/main"),
        confirm=True, execute=True,
    )
    assert any("database_url" in x for x in r)


# --- seed core (test DB) -----------------------------------------------------
async def test_seed_creates_only_allowed_records(db_session: AsyncSession):
    sl_before = await _count(db_session, SignalLog)
    tr_before = await _count(db_session, Trade)
    r = await boot.seed_synthetic_pair(db_session, symbol="005930", interval_seconds=60, max_runs=30)

    assert r["reused"] is False
    # 사람이 읽을 id 전부 채워짐
    for k in ("strategy_id", "baseline_version_id", "challenger_version_id",
              "baseline_session_id", "challenger_session_id", "recurring_plan_id"):
        assert r[k]
    # SignalLog/Trade 0 (부트스트랩은 tick하지 않음)
    assert await _count(db_session, SignalLog) == sl_before
    assert await _count(db_session, Trade) == tr_before


async def test_seed_records_are_labeled_and_valid(db_session: AsyncSession):
    r = await boot.seed_synthetic_pair(db_session, symbol="005930", interval_seconds=60, max_runs=30)
    strat = await db_session.get(Strategy, r["strategy_id"])
    b = await db_session.get(PaperSignalSession, r["baseline_session_id"])
    c = await db_session.get(PaperSignalSession, r["challenger_session_id"])
    bv = await db_session.get(StrategyVersion, r["baseline_version_id"])
    plan = await db_session.get(PaperSignalRecurringRun, r["recurring_plan_id"])

    # 라벨
    for tok in ("SYNTHETIC", "NOT_TRADING_EVIDENCE", "DEV_ONLY"):
        assert tok in strat.name
        assert tok in (b.note or "")
        assert tok in (plan.note or "")
    assert b.started_by == "dev_synthetic_bootstrap"
    assert bv.parameters.get("_synthetic") is True
    assert bv.parameters.get("auto_trade_enabled") is False
    # 도메인 유효성
    assert b.status == "active" and c.status == "active"
    assert b.symbol_code == c.symbol_code == "005930"
    assert c.source_type == "signal_challenger"
    assert c.baseline_session_id == b.id
    assert bv.status == StrategyVersionStatus.DRAFT
    # 계획 prepared
    assert plan.status == "prepared"
    assert plan.completed_runs == 0
    assert plan.next_run_at is None
    assert plan.interval_seconds == 60 and plan.max_runs == 30


async def test_seed_is_idempotent(db_session: AsyncSession):
    r1 = await boot.seed_synthetic_pair(db_session, symbol="005930", interval_seconds=60, max_runs=30)
    plans_after_first = await _count(db_session, PaperSignalRecurringRun)
    r2 = await boot.seed_synthetic_pair(db_session, symbol="005930", interval_seconds=60, max_runs=30)
    assert r2["reused"] is True
    assert r2["challenger_session_id"] == r1["challenger_session_id"]
    assert r2["recurring_plan_id"] == r1["recurring_plan_id"]
    # 중복 페어/계획 미생성
    assert await _count(db_session, PaperSignalRecurringRun) == plans_after_first


async def test_seed_force_new_creates_separate_pair(db_session: AsyncSession):
    r1 = await boot.seed_synthetic_pair(db_session, symbol="005930", interval_seconds=60, max_runs=30)
    r2 = await boot.seed_synthetic_pair(db_session, symbol="005930", interval_seconds=60, max_runs=30,
                                        force_new=True)
    assert r2["reused"] is False
    assert r2["challenger_session_id"] != r1["challenger_session_id"]
    assert r2["recurring_plan_id"] != r1["recurring_plan_id"]


async def test_find_existing_pair_none_when_empty(db_session: AsyncSession):
    assert await boot.find_existing_pair(db_session, "005930") is None
