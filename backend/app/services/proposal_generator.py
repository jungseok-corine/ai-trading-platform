from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.repositories.strategy import (
    StrategyRepository,
    StrategyVersionRepository,
)
from app.domain.repositories.trade import TradeRepository
from app.services.macro_regime_service import MacroRegimeService
from app.services.proposal_service import ProposalService
from app.services.strategy_service import (
    StrategyNotFoundError,
    StrategyVersionNotFoundError,
)
from app.trading.experiment.metrics import VariantMetrics, compute_metrics

# 제안을 만들기 위한 최소 종료 거래 수. 데이터가 적으면 제안하지 않는다(문서 2.3: 데이터 부족 시 자제).
MIN_TRADES_FOR_SUGGESTION = 5

_VOLUME_STRATEGIES = frozenset(
    {"volume_confirmed_ma_cross", "flow_confirmed_volume_ma_cross"}
)


@dataclass
class ProposalSuggestion:
    suggested_parameters: dict
    title: str
    summary: str
    rationale: str
    expected_effect: str
    risk_notes: str


def suggest_parameter_change(
    strategy_type: str, params: dict, metrics: VariantMetrics, *, aggressive: bool = False
) -> ProposalSuggestion | None:
    """성과 지표에 기반해 파라미터 조정 제안을 만든다. 제안할 게 없으면 None.

    결정적(deterministic) 휴리스틱이다. 데이터 부족이거나 기대값이 양수면 제안하지 않는다.
    aggressive=True(매크로 risk_off)면 강화 폭을 더 키운다(C-2.51).
    """
    if metrics.trades_count < MIN_TRADES_FOR_SUGGESTION:
        return None
    # 기대값이 0 이상이면 현재 전략이 손해는 아니므로 변경을 제안하지 않는다.
    if metrics.expectancy >= 0:
        return None

    base_reason = (
        f"최근 {metrics.trades_count}건 거래의 기대값이 {metrics.expectancy}로 음수입니다"
        f"(승률 {metrics.win_rate}%, 최대낙폭 {metrics.max_drawdown})."
    )
    macro_note = " 위험회피 국면이라 강화 폭을 더 키웠습니다." if aggressive else ""

    if strategy_type in _VOLUME_STRATEGIES:
        current = Decimal(str(params.get("volume_multiplier", 1.5)))
        factor = Decimal("1.45") if aggressive else Decimal("1.3")
        new_value = (current * factor).quantize(Decimal("0.1"))
        if new_value <= current:
            new_value = current + Decimal("0.5")
        suggested = {**params, "volume_multiplier": float(new_value)}
        return ProposalSuggestion(
            suggested_parameters=suggested,
            title=f"거래량 조건 강화: volume_multiplier {current} → {new_value}",
            summary=f"거래량 배수를 {current}에서 {new_value}로 높여 진입 문턱을 강화합니다.",
            rationale=f"{base_reason}{macro_note} 거래량 조건을 강화해 약한 신호 진입을 줄입니다.",
            expected_effect="거래 횟수 감소, 약한 신호 제거로 평균 품질 개선 가능.",
            risk_notes="조건이 강해져 기회가 줄어들 수 있습니다. paper에서 비교 검증이 필요합니다.",
        )

    if strategy_type == "moving_average_cross":
        long_window = int(params.get("long_window", 20))
        new_long = long_window + (8 if aggressive else 5)
        suggested = {**params, "long_window": new_long}
        return ProposalSuggestion(
            suggested_parameters=suggested,
            title=f"장기 이평 확대: long_window {long_window} → {new_long}",
            summary=f"장기 이동평균 기간을 {long_window}에서 {new_long}으로 늘립니다.",
            rationale=f"{base_reason}{macro_note} 장기선을 늘려 휩쏘(whipsaw) 신호를 줄입니다.",
            expected_effect="잦은 교차 신호 감소, 추세 추종 안정화 가능.",
            risk_notes="진입이 느려져 초기 추세를 놓칠 수 있습니다. paper 비교가 필요합니다.",
        )

    # 알 수 없는/지원하지 않는 전략 타입은 제안하지 않는다.
    return None


class ProposalGeneratorService:
    """전략 성과를 분석해 개선 제안(strategy_proposal)을 자동 생성한다 (C-2.32).

    구조화된 파라미터 제안은 결정적 휴리스틱으로 만들고, LLM 내러티브는 기존 AI 분석 run을
    ai_analysis_run_id로 링크해 보강할 수 있다. 생성된 제안은 pending 상태이며, 승인 전에는
    전략에 반영되지 않는다(문서 2.3 / 13.3).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._strategy_repo = StrategyRepository(session)
        self._version_repo = StrategyVersionRepository(session)
        self._trade_repo = TradeRepository(session)
        self._proposal_service = ProposalService(session)
        self._macro_service = MacroRegimeService(session)

    async def generate_for_version(
        self,
        strategy_id: int,
        version_id: int,
        ai_analysis_run_id: int | None = None,
    ) -> StrategyProposal | None:
        strategy = await self._strategy_repo.get(strategy_id)
        if strategy is None:
            raise StrategyNotFoundError(strategy_id)
        version = await self._version_repo.get(version_id)
        if version is None or version.strategy_id != strategy_id:
            raise StrategyVersionNotFoundError(version_id)

        trades = await self._trade_repo.list_by_strategy_version(version_id)
        chronological = list(reversed(trades))
        pnls = [t.pnl_amount for t in chronological if t.pnl_amount is not None]
        metrics = compute_metrics(pnls)

        params = version.parameters or {}
        strategy_type = params.get("strategy_type", "")
        # 매크로 레짐 반영(C-2.51): risk_off면 강화 폭을 더 키운다.
        macro = await self._macro_service.latest_regime()
        aggressive = macro.get("regime") == "risk_off"
        suggestion = suggest_parameter_change(
            strategy_type, params, metrics, aggressive=aggressive
        )
        if suggestion is None:
            return None

        return await self._proposal_service.create_proposal(
            strategy_id=strategy_id,
            suggested_parameters=suggestion.suggested_parameters,
            title=suggestion.title,
            summary=suggestion.summary,
            rationale=suggestion.rationale,
            expected_effect=suggestion.expected_effect,
            risk_notes=suggestion.risk_notes,
            base_version_id=version_id,
            source="ai",
            ai_analysis_run_id=ai_analysis_run_id,
        )
