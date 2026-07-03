"""C-7.3: LLM 전략 리서처 — 스펙 추출·검증·입학시험·제안 생성.

안전 검증: 알 수 없는 fn은 invalid_spec으로 폐기(코드 실행 차단),
중복 이름 거부, 통과분만 pending(source=llm_researcher).
"""
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.strategy_proposal import StrategyProposal
from app.services.strategy_researcher import (
    StrategyResearcherService,
    build_researcher_prompt,
    extract_specs,
)
from tests.test_c7_strategy_catalog import _seed_trending_daily
from app.services.strategy_catalog import EXAM_SYMBOLS

VALID_SPEC = {
    "name": "llm_trend_follow",
    "source": "테스트용 — 이평 상향 교차 추세추종",
    "regime_fit": "trend",
    "indicators": {"sma10": {"fn": "sma", "period": 10}, "sma30": {"fn": "sma", "period": 30}},
    "entry": {"op": "crosses_above", "left": {"ref": "sma10"}, "right": {"ref": "sma30"}},
    "exit": {"op": "crosses_below", "left": {"ref": "sma10"}, "right": {"ref": "sma30"}},
}
INVALID_SPEC = {
    "name": "evil_exec",
    "indicators": {"x": {"fn": "python_eval", "period": 1}},
    "entry": {"op": "gt", "left": {"ref": "x"}, "right": {"const": 0}},
    "exit": {"op": "lt", "left": {"ref": "x"}, "right": {"const": 0}},
}
DUP_SPEC = {**VALID_SPEC, "name": "bollinger_bounce"}  # 카탈로그와 중복


def test_extract_specs_tolerant():
    raw = "설명입니다\n```json\n" + json.dumps([VALID_SPEC]) + "\n```\n끝"
    assert len(extract_specs(raw)) == 1
    assert extract_specs("json 아님") == []
    assert extract_specs("[broken json") == []


def test_prompt_contains_vocab_and_dedup():
    prompt = build_researcher_prompt(["bollinger_bounce"], 3)
    assert "crosses_above" in prompt and "bollinger_bounce" in prompt


class _FakeProvider:
    def __init__(self, content: str) -> None:
        self._content = content

    async def analyze(self, prompt, *, model=None, timeout_seconds=None):
        class R:
            content = self._content
        return R()


@pytest.mark.asyncio
async def test_research_pipeline_classifies_and_proposes(db_session: AsyncSession, monkeypatch):
    for sym in EXAM_SYMBOLS:
        await _seed_trending_daily(db_session, sym)

    canned = json.dumps([VALID_SPEC, INVALID_SPEC, DUP_SPEC])
    monkeypatch.setattr(
        "app.services.strategy_researcher.get_analysis_provider",
        lambda name: _FakeProvider(canned),
    )

    result = await StrategyResearcherService(db_session).research(count=3)
    statuses = {o["name"]: o["status"] for o in result["outcomes"]}
    assert statuses["evil_exec"] == "invalid_spec"       # 임의 fn 차단
    assert statuses["bollinger_bounce"] == "duplicate"   # 카탈로그 중복 거부
    assert statuses["llm_trend_follow"] in ("passed", "failed_exam")  # 시험 응시

    if statuses["llm_trend_follow"] == "passed":
        p = (
            (await db_session.execute(
                select(StrategyProposal).where(StrategyProposal.source == "llm_researcher")
            )).scalars().first()
        )
        assert p is not None and p.status.value == "pending"
        assert p.suggested_parameters["auto_trade_enabled"] is False
