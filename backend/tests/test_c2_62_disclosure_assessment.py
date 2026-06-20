"""C-2.62 공시 온디맨드 AI 평가 테스트 (provider 주입, 네트워크 없음)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.repositories.news_context import NewsEventRepository
from app.services.ai_analysis.schemas import AnalysisProviderResult
from app.services.disclosure_assessment_service import DisclosureAssessmentService
from app.trading.analysis.disclosure_assessment import (
    build_disclosure_prompt,
    parse_disclosure_assessment,
)

KST = ZoneInfo("Asia/Seoul")


class _FakeProvider:
    def __init__(self, content: str):
        self._content = content

    async def analyze(self, prompt, **kw):
        return AnalysisProviderResult(
            provider="fake", model="fake-1", content=self._content,
            prompt_tokens=1, completion_tokens=1, total_tokens=2, latency_ms=1,
            finish_reason="stop", raw={},
        )


_GOOD = ('판단: ```json\n{"impact":"negative","severity":0.7,"action_hint":"reduce",'
         '"rationale":"유상증자로 희석","confidence":0.8}\n```')


# --- 순수 파서/프롬프트 ----------------------------------------------------
def test_prompt_includes_disclosure() -> None:
    p = build_disclosure_prompt("005930", "유상증자 결정", "high", "삼성전자", "10주 보유")
    assert "유상증자" in p and "005930" in p and "10주 보유" in p and "JSON" in p


def test_parse_good_and_enum_correction() -> None:
    a = parse_disclosure_assessment(_GOOD)
    assert a.impact == "negative"
    assert a.action_hint == "reduce"
    assert a.severity == 0.7
    # 잘못된 enum은 보정
    bad = parse_disclosure_assessment('{"impact":"???","action_hint":"???"}')
    assert bad.impact == "neutral"
    assert bad.action_hint == "watch"


def test_parse_none_when_no_json() -> None:
    assert parse_disclosure_assessment("JSON 없는 자유 텍스트") is None


# --- 서비스 -----------------------------------------------------------------
async def _add(session, headline="유상증자 결정") -> int:
    e = await NewsEventRepository(session).create(
        market=MarketCode.KR, symbol_code="005930", source="dart", headline=headline,
        url=f"https://dart/{headline}", published_at=datetime.now(KST),
        raw_payload={"category": "high", "corp_name": "삼성전자"},
    )
    await session.commit()
    return e.id


async def test_assess_parses_structured(db_session: AsyncSession) -> None:
    nid = await _add(db_session)
    svc = DisclosureAssessmentService(db_session, provider=_FakeProvider(_GOOD))
    result = await svc.assess(nid)
    assert result["assessment"]["impact"] == "negative"
    assert result["assessment"]["action_hint"] == "reduce"
    assert result["raw"] is None


async def test_assess_non_json_keeps_raw(db_session: AsyncSession) -> None:
    nid = await _add(db_session)
    svc = DisclosureAssessmentService(db_session, provider=_FakeProvider("그냥 자유 텍스트"))
    result = await svc.assess(nid)
    assert result["assessment"] is None
    assert "자유 텍스트" in result["raw"]


async def test_assess_unknown_event_none(db_session: AsyncSession) -> None:
    svc = DisclosureAssessmentService(db_session, provider=_FakeProvider(_GOOD))
    assert await svc.assess(999999) is None
