"""C-2.65 뉴스 큐레이터 LLM 정밀화 테스트 (provider 주입)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.services.ai_analysis.schemas import AnalysisProviderResult
from app.services.news_context_service import NewsContextService
from app.services.news_curator_service import NewsCuratorService
from app.trading.analysis.news_llm_score import build_news_scoring_prompt, parse_news_scores

KST = ZoneInfo("Asia/Seoul")
T = datetime(2026, 6, 18, 9, 0, tzinfo=KST)


class _FakeProvider:
    def __init__(self, content):
        self._content = content

    async def analyze(self, prompt, **kw):
        return AnalysisProviderResult(
            provider="fake", model="mini", content=self._content,
            prompt_tokens=1, completion_tokens=1, total_tokens=2, latency_ms=1,
            finish_reason="stop", raw={},
        )


# --- 순수 파서 --------------------------------------------------------------
def test_prompt_and_parse() -> None:
    p = build_news_scoring_prompt(["A 헤드라인", "B 헤드라인"])
    assert "0. A 헤드라인" in p and "JSON" in p
    scores = parse_news_scores('답: [{"i":0,"score":0.9},{"i":1,"score":0.1}]', 2)
    assert scores == [0.9, 0.1]


def test_parse_clamps_and_handles_missing() -> None:
    assert parse_news_scores('[{"i":0,"score":1.5}]', 2) == [1.0, None]
    assert parse_news_scores("JSON 없음", 3) == [None, None, None]


# --- 서비스: LLM이 룰이 놓친 중요 뉴스를 보강 ------------------------------
async def test_llm_rescues_rule_missed_news(db_session: AsyncSession) -> None:
    news_svc = NewsContextService(db_session)
    # 키워드 없는 헤드라인 → 룰 점수 낮음(0.3, min 0.5 미달 → 룰만이면 제외)
    await news_svc.create_news(headline="회장 갑작스런 입장 발표", published_at=T,
                               market=MarketCode.KR, symbol_code="005930", source="manual")
    await db_session.commit()

    # 룰만(LLM 주입 안 함) → 제외됨
    rule_only = await NewsCuratorService(db_session).curate(symbol_code="005930", min_score=0.5)
    assert len(rule_only) == 0

    # LLM이 0.85로 평가 → 보강되어 포함
    provider = _FakeProvider('[{"i":0,"score":0.85}]')
    curated = await NewsCuratorService(db_session, llm_provider=provider).curate(
        symbol_code="005930", min_score=0.5
    )
    assert len(curated) == 1
    assert curated[0]["llm_score"] == 0.85
    assert curated[0]["materiality"] == 0.85


async def test_llm_failure_falls_back_to_rule(db_session: AsyncSession) -> None:
    news_svc = NewsContextService(db_session)
    await news_svc.create_news(headline="자기주식 취득 결정", published_at=T,  # 룰 high 0.9
                               market=MarketCode.KR, symbol_code="005930", source="dart")
    await db_session.commit()
    # LLM이 JSON 못 주더라도 룰 점수로 포함
    provider = _FakeProvider("형식 깨진 응답")
    curated = await NewsCuratorService(db_session, llm_provider=provider).curate(
        symbol_code="005930", min_score=0.5
    )
    assert len(curated) == 1
    assert curated[0]["rule_score"] == 0.9
