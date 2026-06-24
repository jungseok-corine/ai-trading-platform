"""C-3.8 운영 다이제스트 + 알림 채널 테스트."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus, StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_proposal import StrategyProposal
from app.services.notifications import get_notification_channel
from app.services.notifications.channels import LogChannel, NoneChannel
from app.services.operations_digest_service import OperationsDigestService


async def test_digest_empty_is_ok(db_session: AsyncSession) -> None:
    d = await OperationsDigestService(db_session).build()
    assert d["severity"] == "ok"
    assert d["has_alerts"] is False
    assert "없습니다" in d["summary_line"]


async def test_digest_flags_pending_proposals(db_session: AsyncSession) -> None:
    strat = Strategy(name="DigestStrat", description="t")
    db_session.add(strat)
    await db_session.flush()
    db_session.add(StrategyProposal(
        strategy_id=strat.id, title="p", suggested_parameters={"x": 1},
        status=ProposalStatus.PENDING,
    ))
    await db_session.flush()

    svc = OperationsDigestService(db_session)
    d = await svc.build()
    assert d["has_alerts"] is True
    assert d["severity"] == "attention"
    assert any("검토 대기" in a["text"] for a in d["alerts"])
    # 평문 렌더 포함
    text = svc.render_text(d)
    assert "검토 대기" in text


async def test_digest_softens_paper_auto_trade_copy(db_session: AsyncSession) -> None:
    """실거래 OFF + paper/test auto_trade → 강한 '안전 불변식' 문구 대신 운영 안내(심각도는 유지)."""
    strat = Strategy(name="PaperAutoTrade", description="t")
    db_session.add(strat)
    await db_session.flush()
    db_session.add(StrategyVersion(
        strategy_id=strat.id, version_no=1,
        parameters={"strategy_type": "moving_average_cross", "symbol_code": "005930",
                    "auto_trade_enabled": True},
        status=StrategyVersionStatus.ACTIVE,
    ))
    await db_session.flush()

    d = await OperationsDigestService(db_session).build()
    texts = [a["text"] for a in d["alerts"]]
    # 부드러운 paper/test 운영 안내가 있어야 한다.
    assert any("테스트 자동매매 전략" in t and "paper/test" in t for t in texts), texts
    # 강한 '안전 불변식: auto_trade_enabled …' 문구는 없어야 한다.
    assert not any("안전 불변식: auto_trade_enabled" in t for t in texts), texts
    # 심각도(severity)는 보수적으로 유지 — copy만 부드럽게.
    assert d["severity"] == "alert"


# --- 알림 채널 -------------------------------------------------------------
def test_factory_defaults_to_none() -> None:
    assert isinstance(get_notification_channel(None), NoneChannel)
    assert isinstance(get_notification_channel("unknown"), NoneChannel)
    assert isinstance(get_notification_channel("log"), LogChannel)


async def test_none_channel_does_not_send() -> None:
    r = await NoneChannel().send("s", "b")
    assert r.sent is False and r.provider == "none"


async def test_log_channel_sends() -> None:
    r = await LogChannel().send("s", "b")
    assert r.sent is True and r.provider == "log"
