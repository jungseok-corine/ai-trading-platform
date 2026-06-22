"""§7.1 인트라데이 이벤트 감시 — 보유/활성 종목 한정 장중 공시 감시."""
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, StrategyVersionStatus
from app.domain.models.position import Position
from app.domain.models.strategy import Strategy, StrategyVersion
from app.services.dart_provider import Disclosure
from app.services.intraday_event_monitor_service import IntradayEventMonitorService


class _FakeDartProvider:
    def __init__(self, disclosures: list[Disclosure]) -> None:
        self._d = disclosures

    async def fetch_disclosures(self, start, end):
        return self._d


def _disc(rcept_no: str, code: str, report_nm: str) -> Disclosure:
    return Disclosure(
        rcept_no=rcept_no, stock_code=code, corp_name="테스트",
        report_nm=report_nm, rcept_dt="20260622",
    )


async def _account(session) -> Account:
    a = Account(account_type=AccountType.PAPER, broker_account_no="00000000-01")
    session.add(a)
    await session.flush()
    return a


async def _active_version(session, **params) -> StrategyVersion:
    strat = Strategy(name="t", description="t")
    session.add(strat)
    await session.flush()
    v = StrategyVersion(
        strategy_id=strat.id, version_no=1,
        parameters={"strategy_type": "rsi_reversion", **params},
        status=StrategyVersionStatus.ACTIVE,
    )
    session.add(v)
    await session.flush()
    return v


async def test_resolve_monitored_symbols(db_session) -> None:
    acc = await _account(db_session)
    # 보유 포지션(수량≠0) + 수량 0(제외)
    db_session.add_all([
        Position(account_id=acc.id, symbol_code="005930", quantity=10),
        Position(account_id=acc.id, symbol_code="111111", quantity=0),  # 청산됨 → 제외
    ])
    # 활성 단일 KR 종목 전략(포함), 유니버스 전략(제외), 미장 전략(제외)
    await _active_version(db_session, symbol_code="000660", market="KR")
    await _active_version(db_session, universe="watchlist")
    await _active_version(db_session, symbol_code="AAPL", market="US")
    await db_session.commit()

    syms = await IntradayEventMonitorService(db_session).resolve_monitored_symbols()
    assert syms == {"005930", "000660"}


async def test_run_once_scopes_to_monitored(db_session) -> None:
    acc = await _account(db_session)
    db_session.add(Position(account_id=acc.id, symbol_code="005930", quantity=5))
    await db_session.commit()

    disclosures = [
        _disc("1", "005930", "단일판매ㆍ공급계약체결"),   # 보유종목 + 중요 → 저장
        _disc("2", "999999", "단일판매ㆍ공급계약체결"),   # 감시 대상 아님 → 제외
        _disc("3", "005930", "[기재정정] IR 일정 안내"),  # 노이즈(중요도 미달) → 제외
    ]
    svc = IntradayEventMonitorService(db_session, provider=_FakeDartProvider(disclosures))

    result = await svc.run_once(min_score=0.5)
    assert result["monitored"] == 1
    assert result["matched"] == 2    # 005930 공시 2건이 감시 대상(999999는 제외)
    assert result["material"] == 1   # 그중 중요도 통과 1건(IR 일정은 노이즈)
    assert result["created"] == 1

    alerts = await svc.recent_alerts(hours=48, min_score=0.0)
    assert len(alerts) == 1
    assert alerts[0]["symbol_code"] == "005930"


async def test_no_monitored_symbols_skips(db_session) -> None:
    svc = IntradayEventMonitorService(db_session, provider=_FakeDartProvider([]))
    result = await svc.run_once()
    assert result["monitored"] == 0
    assert result["skipped_reason"] == "no_monitored_symbols"
    assert await svc.recent_alerts() == []
