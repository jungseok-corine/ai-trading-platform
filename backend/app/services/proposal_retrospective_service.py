from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ProposalStatus
from app.domain.repositories.scanner_proposal import ScannerRuleProposalRepository
from app.domain.repositories.strategy_proposal import StrategyProposalRepository
from app.domain.repositories.trade import TradeRepository
from app.services.candidate_outcome_service import CandidateOutcomeService
from app.trading.experiment.metrics import compute_metrics

# 회고 판정에 필요한 최소 표본 수(base/new 각각). 부족하면 inconclusive.
MIN_SAMPLES_FOR_VERDICT = 5

VERDICT_IMPROVED = "improved"
VERDICT_WORSE = "worse"
VERDICT_INCONCLUSIVE = "inconclusive"


@dataclass
class RetroEntry:
    """승인된 제안 1건의 회고: base 버전 대비 새 버전이 나아졌는가."""

    proposal_id: int
    kind: str  # "strategy" | "scanner"
    base_version_id: int | None
    created_version_id: int | None
    metric: str  # "expectancy" | "win_rate"
    base_metric: float | None
    new_metric: float | None
    base_samples: int
    new_samples: int
    verdict: str

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "kind": self.kind,
            "base_version_id": self.base_version_id,
            "created_version_id": self.created_version_id,
            "metric": self.metric,
            "base_metric": self.base_metric,
            "new_metric": self.new_metric,
            "base_samples": self.base_samples,
            "new_samples": self.new_samples,
            "verdict": self.verdict,
        }


def _verdict(base: float | None, new: float | None, base_n: int, new_n: int) -> str:
    """표본이 충분할 때만 metric 대소로 판정한다(높을수록 좋은 지표 가정)."""
    if base is None or new is None:
        return VERDICT_INCONCLUSIVE
    if base_n < MIN_SAMPLES_FOR_VERDICT or new_n < MIN_SAMPLES_FOR_VERDICT:
        return VERDICT_INCONCLUSIVE
    if new > base:
        return VERDICT_IMPROVED
    if new < base:
        return VERDICT_WORSE
    return VERDICT_INCONCLUSIVE


class ProposalRetrospectiveService:
    """승인된 AI 제안이 실제로 성과를 개선했는지 회고한다 (C-2.46).

    문서의 "AI 제안이 진짜 효과가 있었나"를 데이터로 닫는 학습 루프. 제안이 만든 새 버전과
    기반(base) 버전의 성과를 같은 지표로 비교한다.
      - 전략 제안: 거래 기대값(expectancy)
      - 스캐너 제안: 후보 30분 후 승률(win_rate)
    표본이 부족하면 섣불리 판정하지 않고 inconclusive로 둔다(read-only 집계).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._strategy_repo = StrategyProposalRepository(session)
        self._scanner_repo = ScannerRuleProposalRepository(session)
        self._trade_repo = TradeRepository(session)
        self._outcome_service = CandidateOutcomeService(session)

    async def _strategy_expectancy(self, version_id: int | None) -> tuple[float | None, int]:
        if version_id is None:
            return None, 0
        trades = await self._trade_repo.list_by_strategy_version(version_id)
        pnls = [t.pnl_amount for t in trades if t.pnl_amount is not None]
        if not pnls:
            return None, 0
        metrics = compute_metrics(pnls)
        return float(metrics.expectancy), metrics.trades_count

    async def _scanner_win_rate(self, version_id: int | None) -> tuple[float | None, int]:
        if version_id is None:
            return None, 0
        analysis = await self._outcome_service.analyze(scanner_rule_version_id=version_id)
        overall = analysis.overall
        return overall.get("win_rate"), overall.get("count") or 0

    async def retrospect_strategy(self, proposal) -> RetroEntry:
        base_metric, base_n = await self._strategy_expectancy(proposal.base_version_id)
        new_metric, new_n = await self._strategy_expectancy(proposal.created_version_id)
        return RetroEntry(
            proposal_id=proposal.id,
            kind="strategy",
            base_version_id=proposal.base_version_id,
            created_version_id=proposal.created_version_id,
            metric="expectancy",
            base_metric=base_metric,
            new_metric=new_metric,
            base_samples=base_n,
            new_samples=new_n,
            verdict=_verdict(base_metric, new_metric, base_n, new_n),
        )

    async def retrospect_scanner(self, proposal) -> RetroEntry:
        base_metric, base_n = await self._scanner_win_rate(proposal.base_version_id)
        new_metric, new_n = await self._scanner_win_rate(proposal.created_version_id)
        return RetroEntry(
            proposal_id=proposal.id,
            kind="scanner",
            base_version_id=proposal.base_version_id,
            created_version_id=proposal.created_version_id,
            metric="win_rate",
            base_metric=base_metric,
            new_metric=new_metric,
            base_samples=base_n,
            new_samples=new_n,
            verdict=_verdict(base_metric, new_metric, base_n, new_n),
        )

    async def list_strategy_retros(self, limit: int = 100) -> list[RetroEntry]:
        proposals = await self._strategy_repo.list_filtered(
            status=ProposalStatus.APPROVED, limit=limit
        )
        return [
            await self.retrospect_strategy(p)
            for p in proposals
            if p.created_version_id is not None
        ]

    async def list_scanner_retros(self, limit: int = 100) -> list[RetroEntry]:
        proposals = await self._scanner_repo.list_filtered(
            status=ProposalStatus.APPROVED, limit=limit
        )
        return [
            await self.retrospect_scanner(p)
            for p in proposals
            if p.created_version_id is not None
        ]

    async def summary(self) -> dict:
        """전략+스캐너 회고를 합쳐 verdict 분포를 집계한다(관제탑용)."""
        retros = await self.list_strategy_retros() + await self.list_scanner_retros()
        counts = {VERDICT_IMPROVED: 0, VERDICT_WORSE: 0, VERDICT_INCONCLUSIVE: 0}
        for r in retros:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
        return {"total": len(retros), **counts}
