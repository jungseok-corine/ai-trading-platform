"""Intelligence 후보 기반 전략 배정 Heuristic Generator (C-2.26).

IntelligenceCandidate의 matched_themes, why_text, source_type을 분석해
적합한 strategy_type을 heuristic 규칙으로 결정하고 IntelligenceStrategyProposal을 생성한다.

규칙 (우선순위 순):
  1. MOMENTUM  : matched_themes/why_text에 모멘텀·급등·급상승 신호        → momentum_surge
  2. BREAKOUT  : matched_themes/why_text에 돌파·52주·신고가 신호          → breakout_high
  3. PULLBACK  : matched_themes/why_text에 눌림·조정·반등 신호            → pullback_trend
  4. FLOW      : source_type=disclosure/공시 + 거래량 확인 필요            → volume_confirmed_ma_cross
  5. FLOW2     : source_type 또는 why_text에 수급·외국인·기관 신호         → flow_confirmed_volume_ma_cross
  6. REVERSION : matched_themes/why_text에 과열·반락·RSI 신호             → rsi_reversion
  7. MACD      : matched_themes/why_text에 MACD·추세 신호                 → macd_trend
  8. FALLBACK  : 위 조건 모두 미해당                                       → moving_average_cross

- LLM/AI Provider 호출 없음
- StrategyVersion 자동 생성 없음
- StrategyAssignmentLog 자동 생성 없음
- auto_trade_enabled 절대 True 금지
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import IntelligenceCandidateStatus, IntelligenceStrategyProposalStatus
from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.domain.repositories.intelligence_strategy_proposal import (
    IntelligenceStrategyProposalRepository,
)
from app.trading.strategy.registry import registered_types

_SOURCE = "heuristic"
_MAX_CANDIDATES = 50

# ── 각 전략 타입의 키워드 패턴 ────────────────────────────────────────────────
# 순서가 우선순위. 앞에 있는 룰이 먼저 매칭된다.
_RULES: list[tuple[str, list[str]]] = [
    (
        "momentum_surge",
        ["momentum", "급등", "급상승", "급격", "폭등", "surge", "spike"],
    ),
    (
        "breakout_high",
        ["breakout", "돌파", "52주", "신고가", "연고가", "break", "high", "상단돌파"],
    ),
    (
        "pullback_trend",
        ["pullback", "눌림", "조정", "반등", "되돌림", "rebound", "correction"],
    ),
    (
        "volume_confirmed_ma_cross",
        ["공시", "disclosure", "dart", "edgar", "거래량확인", "volume_confirm"],
    ),
    (
        "flow_confirmed_volume_ma_cross",
        ["수급", "외국인", "기관", "flow", "foreign", "institution", "순매수", "순매도"],
    ),
    (
        "rsi_reversion",
        ["과열", "반락", "rsi", "reversion", "overbought", "oversold", "반전"],
    ),
    (
        "macd_trend",
        ["macd", "추세", "trend", "골든크로스", "데드크로스", "golden", "dead"],
    ),
]

_FALLBACK = "moving_average_cross"


@dataclass
class AssignmentGenerationSummary:
    candidates_analyzed: int = 0
    proposals_created: int = 0
    skipped_existing: int = 0
    skipped_invalid: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "candidates_analyzed": self.candidates_analyzed,
            "proposals_created": self.proposals_created,
            "skipped_existing": self.skipped_existing,
            "skipped_invalid": self.skipped_invalid,
            "errors": self.errors,
        }


def _normalize(text: str) -> str:
    return text.lower().replace(" ", "").replace("_", "")


def _match_strategy(
    matched_themes: list | None,
    why_text: str | None,
    source_type: str | None,
) -> tuple[str, dict]:
    """heuristic 매칭으로 strategy_type과 score_components를 반환한다."""
    combined = " ".join(
        [
            " ".join(matched_themes or []),
            why_text or "",
            source_type or "",
        ]
    )
    combined_lower = _normalize(combined)

    score_components: dict[str, object] = {
        "matched_themes": matched_themes or [],
        "why_text_snippet": (why_text or "")[:100],
        "source_type": source_type or "",
    }

    for strategy_type, keywords in _RULES:
        matched = [kw for kw in keywords if _normalize(kw) in combined_lower]
        if matched:
            score_components["matched_rule"] = strategy_type
            score_components["matched_keywords"] = matched
            return strategy_type, score_components

    score_components["matched_rule"] = _FALLBACK
    score_components["matched_keywords"] = []
    return _FALLBACK, score_components


def _build_rationale(
    strategy_type: str,
    score_components: dict,
    candidate_score: int,
) -> str:
    matched_keywords = score_components.get("matched_keywords", [])
    themes = score_components.get("matched_themes", [])
    source = score_components.get("source_type", "")

    parts = [f"heuristic → {strategy_type}"]
    if matched_keywords:
        parts.append(f"매칭 키워드: {', '.join(str(k) for k in matched_keywords)}")
    if themes:
        parts.append(f"테마: {', '.join(str(t) for t in themes)}")
    if source:
        parts.append(f"소스: {source}")
    parts.append(f"후보 점수: {candidate_score}")
    return " | ".join(parts)


def _confidence(candidate_score: int, matched_keywords: list) -> float:
    """0.0–1.0 사이 confidence. 점수와 키워드 수에 비례."""
    base = min(candidate_score / 100.0, 1.0) * 0.6
    kw_bonus = min(len(matched_keywords) * 0.1, 0.4)
    return round(base + kw_bonus, 3)


def _make_dedup_hash(candidate_id: int, strategy_type: str) -> str:
    raw = f"{candidate_id}:{strategy_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


class IntelligenceStrategyAssignmentGenerator:
    """PENDING IntelligenceCandidate에서 heuristic 기반 전략 배정 제안을 생성한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._candidate_repo = IntelligenceCandidateRepository(session)
        self._proposal_repo = IntelligenceStrategyProposalRepository(session)

    async def generate(self, candidate_limit: int = _MAX_CANDIDATES) -> AssignmentGenerationSummary:
        summary = AssignmentGenerationSummary()
        valid_types = set(registered_types())

        candidates = await self._candidate_repo.list_recent(
            status=IntelligenceCandidateStatus.PENDING,
            limit=candidate_limit,
        )
        summary.candidates_analyzed = len(candidates)

        for candidate in candidates:
            try:
                existing = await self._proposal_repo.existing_for_candidate(candidate.id)
                if existing is not None:
                    summary.skipped_existing += 1
                    continue

                strategy_type, score_components = _match_strategy(
                    candidate.matched_themes,
                    candidate.why_text,
                    candidate.source_type,
                )

                if strategy_type not in valid_types:
                    summary.skipped_invalid += 1
                    summary.errors.append(
                        f"candidate {candidate.id}: 등록되지 않은 strategy_type={strategy_type!r}"
                    )
                    continue

                dedup_hash = _make_dedup_hash(candidate.id, strategy_type)
                existing_hash = await self._proposal_repo.existing_hashes([dedup_hash])
                if dedup_hash in existing_hash:
                    summary.skipped_existing += 1
                    continue

                matched_keywords = score_components.get("matched_keywords", [])
                confidence = _confidence(candidate.score, matched_keywords)
                rationale = _build_rationale(strategy_type, score_components, candidate.score)

                suggested_parameters = {
                    "timeframe": "5m",
                    "quantity": 1,
                    "strategy_type": strategy_type,
                }

                await self._proposal_repo.create(
                    intelligence_candidate_id=candidate.id,
                    symbol_code=candidate.symbol_code,
                    market=candidate.market,
                    suggested_strategy_type=strategy_type,
                    suggested_parameters=suggested_parameters,
                    rationale=rationale,
                    confidence_score=confidence,
                    score_components=score_components,
                    source=_SOURCE,
                    status=IntelligenceStrategyProposalStatus.PENDING,
                    dedup_hash=dedup_hash,
                )
                summary.proposals_created += 1

            except Exception as exc:
                summary.errors.append(f"candidate {candidate.id}: {exc}")

        await self._session.commit()
        return summary
