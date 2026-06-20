"""C-3.8 운영 다이제스트 + 알림 채널 테스트."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus
from app.domain.models.strategy import Strategy
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
