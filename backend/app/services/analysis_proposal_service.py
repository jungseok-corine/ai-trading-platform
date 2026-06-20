from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.proposal_service import InvalidProposalError, ProposalService
from app.trading.analysis.analysis_output import parse_analysis_output

logger = logging.getLogger(__name__)


class AnalysisProposalService:
    """LLM 분석 출력(JSON)을 검증해 전략 개선 제안(pending)으로 연결한다 (C-2.56).

    AI는 제안자일 뿐 — 생성되는 제안은 pending이며 사람 승인 전에는 반영되지 않는다.
    confidence가 임계 미만이거나 param_change가 없거나 JSON 파싱 실패면 제안을 만들지 않는다
    (데이터/근거 부족 시 자제). 잘못된 파라미터(미등록 strategy_type 등)는 검증에서 걸러낸다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = StrategyVersionRepository(session)
        self._proposal_service = ProposalService(session)

    async def create_from_text(
        self,
        strategy_id: int,
        version_id: int,
        analysis_text: str,
        ai_analysis_run_id: int | None = None,
        min_confidence: float = 0.5,
    ) -> StrategyProposal | None:
        out = parse_analysis_output(analysis_text)
        if out is None:
            return None
        best = out.best_hypothesis(min_confidence)
        if best is None:
            return None

        version = await self._version_repo.get(version_id)
        if version is None or version.strategy_id != strategy_id:
            return None

        # base 파라미터 위에 param_change를 덮어쓴다(strategy_type 등 기존 키 보존).
        suggested = {**(version.parameters or {}), **best.param_change}
        verdict = out.verdict or "improve"
        rationale = best.rationale or "; ".join(out.mistakes) or "LLM 분석 기반 개선 제안."

        try:
            return await self._proposal_service.create_proposal(
                strategy_id=strategy_id,
                suggested_parameters=suggested,
                title=f"AI 분석 제안: {best.hypothesis[:120]}",
                summary=f"verdict={verdict}, confidence={best.confidence}",
                rationale=rationale,
                expected_effect="; ".join(out.key_observations) or None,
                risk_notes=out.risk_notes,
                base_version_id=version_id,
                source="ai_llm",
                ai_analysis_run_id=ai_analysis_run_id,
            )
        except InvalidProposalError as exc:
            # 모델이 미등록 strategy_type 등 잘못된 파라미터를 제안 → 제안 생성하지 않음.
            logger.warning("LLM proposal rejected by validation (v%s): %s", version_id, exc)
            return None
