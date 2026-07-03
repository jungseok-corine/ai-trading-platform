"""전략 종합 선정 보드 (C-7.4).

"여러 기록을 합해서 알맞은 전략을 골라" — 살아있는 전략 버전마다
백테스트·paper 실적·회고·레짐 적합성을 합산한 종합 점수로 랭킹한다.

**read-only. 실전 배치는 여전히 승격 게이트(사람)** — 이 보드는 판단 재료를 모을 뿐이다.

점수 (0~100):
- 백테스트 (30): 출신 제안의 backtest_summary — 수익률(+), MDD(-)
- Paper 실적 (40): 실거래 기대값·표본 (가장 신뢰 — 실제 모의 체결)
- 회고 (15): 이 버전을 만든 제안의 retro 판정 (improved/worse)
- 레짐 적합 (15): regime_fit 태그 vs 현재 매크로 레짐 (D-31)
표본이 없는 축은 중립(절반) 점수 — 새 전략이 부당하게 유리/불리하지 않게.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.models.strategy_proposal import StrategyProposal
from app.services.macro_regime_service import MacroRegimeService
from app.services.proposal_retrospective_service import ProposalRetrospectiveService

# 레짐 → 적합 태그 매핑 (D-31): risk_on은 추세 우호, risk_off는 방어(횡보형) 우호
_REGIME_PREFERS = {"risk_on": "trend", "risk_off": "range"}


def composite_score(
    *,
    backtest: dict[str, Any] | None,
    paper_expectancy: float | None,
    paper_samples: int,
    retro_verdict: str | None,
    regime_fit: str | None,
    current_regime: str | None,
) -> dict[str, Any]:
    """축별 부분 점수와 합계를 계산한다 (순수 함수 — 테스트 용이)."""
    # 백테스트 (0~30, 무데이터 15)
    if backtest and backtest.get("status") == "succeeded":
        ret = float(backtest.get("return_pct") or 0)
        mdd = float(backtest.get("max_drawdown_pct") or 0)
        bt_score = max(0.0, min(30.0, 15.0 + ret * 0.15 - max(0.0, mdd - 20.0) * 0.5))
    else:
        bt_score = 15.0

    # Paper (0~40, 무표본 20) — 기대값 부호·크기 + 표본 신뢰 가중
    if paper_expectancy is not None and paper_samples > 0:
        confidence = min(1.0, paper_samples / 10.0)
        raw = 20.0 + max(-20.0, min(20.0, paper_expectancy * 0.02))
        paper_score = 20.0 + (raw - 20.0) * confidence
    else:
        paper_score = 20.0

    # 회고 (0~15, 무판정 7.5)
    retro_score = {"improved": 15.0, "worse": 0.0}.get(retro_verdict or "", 7.5)

    # 레짐 적합 (0~15, 태그 없으면 7.5)
    if regime_fit and current_regime:
        preferred = _REGIME_PREFERS.get(current_regime)
        regime_score = 15.0 if preferred == regime_fit else (7.5 if preferred is None else 3.0)
    else:
        regime_score = 7.5

    total = round(bt_score + paper_score + retro_score + regime_score, 1)
    return {
        "total": total,
        "backtest": round(bt_score, 1),
        "paper": round(paper_score, 1),
        "retrospective": round(retro_score, 1),
        "regime": round(regime_score, 1),
    }


class StrategySelectionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._retro = ProposalRetrospectiveService(session)
        self._macro = MacroRegimeService(session)

    async def board(self) -> dict[str, Any]:
        versions = (
            (await self._session.execute(
                select(StrategyVersion, Strategy)
                .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
                .where(StrategyVersion.status.in_(
                    [StrategyVersionStatus.ACTIVE, StrategyVersionStatus.TESTING]
                ))
            )).all()
        )
        macro = await self._macro.latest_regime()
        current_regime = macro.get("regime")

        # 버전 → 출신 제안 (백테스트·회고의 근거)
        proposals = (
            (await self._session.execute(
                select(StrategyProposal).where(StrategyProposal.created_version_id.is_not(None))
            )).scalars().all()
        )
        by_version = {p.created_version_id: p for p in proposals}

        rows: list[dict[str, Any]] = []
        for version, strategy in versions:
            params = version.parameters or {}
            proposal = by_version.get(version.id)
            backtest = (proposal.backtest_summary or {}).get("proposed") if proposal else None

            expectancy, samples = await self._retro._strategy_expectancy(version.id)  # noqa: SLF001
            retro_verdict = None
            if proposal is not None:
                retro_verdict = (await self._retro.retrospect_strategy(proposal)).verdict

            score = composite_score(
                backtest=backtest,
                paper_expectancy=expectancy,
                paper_samples=samples,
                retro_verdict=retro_verdict,
                regime_fit=params.get("regime_fit"),
                current_regime=current_regime,
            )
            rows.append({
                "strategy_version_id": version.id,
                "strategy_name": strategy.name,
                "strategy_type": params.get("strategy_type"),
                "timeframe": params.get("timeframe", "1m"),
                "status": version.status.value,
                "regime_fit": params.get("regime_fit"),
                "paper_samples": samples,
                "score": score,
            })

        rows.sort(key=lambda r: r["score"]["total"], reverse=True)
        return {
            "current_regime": current_regime,
            "count": len(rows),
            "rows": rows,
            "note": (
                "종합 점수는 판단 재료 — 실전 배치는 승격 게이트에서 사람이 결정한다. "
                "paper 표본이 적은 전략은 중립 점수로 시작해 실적이 쌓이며 갈린다."
            ),
        }
