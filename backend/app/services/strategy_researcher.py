"""LLM 전략 리서처 (C-7.3).

LLM에게 "널리 알려진 검증된 매매 전략"을 DSL 스펙으로 제안받아,
스키마 검증 → 입학시험(C-7.5) → 통과분만 pending 제안을 만든다.

안전 경계:
- LLM은 **DSL JSON만** 생성 — 코드 실행 없음. 검증 실패 스펙은 폐기(기록만).
- 기본 provider는 settings.ai_default_provider (기본 fake — 실수 유료호출 방지).
- 수동 트리거 API 전용 — 스케줄러 잡 없음 (비용 통제).
- 승인은 사람.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.strategy_proposal import StrategyProposal
from app.services.ai_analysis.factory import get_analysis_provider
from app.services.strategy_catalog import CATALOG, StrategyCatalogService, passes_admission
from app.trading.strategy.rule_dsl import RuleSpecError, validate_rule_spec

logger = logging.getLogger(__name__)

_DSL_GUIDE = """
전략 스펙 JSON 형식 (이 어휘만 사용 — 다른 fn/op는 거부됨):
- indicators: {"이름": {"fn": <fn>, ...파라미터}}
  fn 목록: sma(period), ema(period), rsi(period), atr(period),
  bollinger_mid/upper/lower(period, num_std), highest_high(period), lowest_low(period),
  stochastic_k(period), return_pct(lookback), volume_ratio(period),
  macd_line/macd_signal(fast, slow, signal)
- 값 노드: {"ref": "지표명"|"price"|"volume"} 또는 {"const": 숫자}
- 조건 op: gt/gte/lt/lte, crosses_above/crosses_below, and/or/not(args 배열)
- 필수 키: name(영문 스네이크), source(출처·원리 설명, 한국어), indicators, entry, exit
"""


def build_researcher_prompt(existing_names: list[str], count: int) -> str:
    return f"""당신은 퀀트 전략 리서처다. 널리 알려지고 문헌에 근거가 있는 주식 매매 전략
{count}개를 아래 DSL 형식의 JSON 배열로 제안하라.

{_DSL_GUIDE}

규칙:
1. 이미 있는 전략과 중복 금지: {existing_names}
2. 각 전략의 source에 출처(창시자/문헌)와 작동 원리를 명확히 쓸 것
3. 롱 온리 — entry는 매수 조건, exit는 청산 조건
4. 일봉 기준으로 연 3회 이상 거래가 나올 현실적 조건일 것 (과도하게 엄격한 임계 금지)
5. 출력은 JSON 배열만 — 다른 텍스트 없이

JSON 배열:"""


def extract_specs(raw_text: str) -> list[dict[str, Any]]:
    """LLM 출력에서 JSON 배열을 관대하게 추출한다 (코드펜스/설명문 허용)."""
    text = raw_text.strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [s for s in parsed if isinstance(s, dict)]


class StrategyResearcherService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._catalog_service = StrategyCatalogService(session)

    async def research(
        self, *, count: int = 3, provider_name: str | None = None, exam_days: int = 365
    ) -> dict[str, Any]:
        """LLM에게 전략을 제안받아 검증·입학시험을 거쳐 pending 제안을 만든다."""
        settings = get_settings()
        provider = get_analysis_provider(provider_name or settings.ai_default_provider)

        existing = await self._existing_names()
        prompt = build_researcher_prompt(sorted(existing), count)
        result = await provider.analyze(prompt)
        specs = extract_specs(result.content)

        outcomes: list[dict[str, Any]] = []
        for spec in specs:
            name = spec.get("name", "?")
            if name in existing:
                outcomes.append({"name": name, "status": "duplicate"})
                continue
            try:
                validate_rule_spec(spec)
            except RuleSpecError as e:
                outcomes.append({"name": name, "status": "invalid_spec", "reason": str(e)})
                continue
            agg = await self._catalog_service._exam(spec, exam_days)  # noqa: SLF001 - 동일 시험 재사용
            passed, reason = passes_admission(agg)
            item = {"name": name, "status": "passed" if passed else "failed_exam",
                    "reason": reason, "exam": agg}
            if passed:
                proposal = await self._catalog_service._create_proposal(  # noqa: SLF001
                    {"spec": spec, "regime_fit": spec.get("regime_fit", "trend")},
                    agg,
                    source="llm_researcher",
                )
                item["proposal_id"] = proposal.id if proposal else None
            outcomes.append(item)
            existing.add(name)

        return {
            "provider": provider_name or settings.ai_default_provider,
            "requested": count,
            "received": len(specs),
            "outcomes": outcomes,
            "note": "통과 스펙은 pending 제안 — 승인은 사람. LLM 코드 실행 없음(DSL만).",
        }

    async def _existing_names(self) -> set[str]:
        names = {e["spec"]["name"] for e in CATALOG}
        rows = (
            await self._session.execute(
                select(StrategyProposal.suggested_parameters).where(
                    StrategyProposal.source.in_(["catalog", "llm_researcher"])
                )
            )
        ).scalars().all()
        for params in rows:
            spec = (params or {}).get("rule_spec") or {}
            if spec.get("name"):
                names.add(spec["name"])
        return names
