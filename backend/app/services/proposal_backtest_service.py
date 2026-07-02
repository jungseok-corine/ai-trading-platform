"""제안 백테스트 자동 첨부 (C-6.1b).

전략 제안(StrategyProposal)이 생성될 때, base 버전 파라미터와 제안 파라미터를
같은 기간의 저장된 market_data 위에서 각각 백테스트해 비교 결과를
`strategy_proposals.backtest_summary`에 저장한다.

목적: "이 제안이 과거 데이터에서는 어땠나"를 사람이 승인 전에 즉시 볼 수 있게 —
paper에서 며칠 걸리는 1차 검증을 초 단위로 앞당긴다.

경계:
- **판정은 사람** — verdict는 참고 라벨일 뿐, 승인 흐름을 자동으로 바꾸지 않는다.
- 주문/브로커 호출 없음 (BacktestService 재사용 — DB read + 계산).
- 실패는 삼킨다 — 백테스트가 안 돼도 제안 생성은 성공해야 한다.
- 유니버스 전략(단일 symbol 없음)은 v1에서 건너뛴다(사유 기록).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models.strategy_proposal import StrategyProposal
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.backtest_service import BacktestService

logger = logging.getLogger(__name__)

# verdict 판정 최소 거래 수 — 이보다 적으면 insufficient_data
MIN_TRADES_FOR_VERDICT = 5
# return_pct 차이가 이보다 작으면 inconclusive (백분율 포인트)
VERDICT_MARGIN_PP = 1.0


class ProposalBacktestService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = StrategyVersionRepository(session)
        self._backtest = BacktestService(session)

    async def attach(self, proposal: StrategyProposal) -> dict[str, Any] | None:
        """제안에 백테스트 비교를 첨부한다. 저장된 summary(또는 skip 사유)를 반환."""
        summary = await self._build_summary(proposal)
        if summary is None:
            return None
        proposal.backtest_summary = summary
        await self._session.commit()
        return summary

    async def _build_summary(self, proposal: StrategyProposal) -> dict[str, Any] | None:
        settings = get_settings()
        if proposal.base_version_id is None:
            return {"skipped": "base 버전 없음 — 비교 기준이 없어 백테스트 생략"}
        base_version = await self._version_repo.get(proposal.base_version_id)
        if base_version is None:
            return {"skipped": "base 버전 조회 실패"}

        base_params: dict[str, Any] = dict(base_version.parameters or {})
        symbol = base_params.get("symbol_code") or ""
        if base_params.get("universe") or not symbol:
            return {"skipped": "유니버스/무심볼 전략 — 단일 종목 백테스트 대상 아님 (v1)"}

        # 제안 파라미터: suggested가 완전한 파라미터면 그대로, 부분이면 base 위에 병합.
        suggested = dict(proposal.suggested_parameters or {})
        proposed_params = {**base_params, **suggested}

        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(days=settings.proposal_backtest_days)
        market = base_params.get("market", "KR")

        base_result = await self._run_leg(base_params, symbol, market, start_ts, end_ts)
        proposed_result = await self._run_leg(proposed_params, symbol, market, start_ts, end_ts)

        return {
            "window_days": settings.proposal_backtest_days,
            "symbol_code": symbol,
            "generated_at": end_ts.isoformat(),
            "base": base_result,
            "proposed": proposed_result,
            "verdict": _verdict(base_result, proposed_result),
            "note": "저장된 시세 기반 시뮬레이션 — 참고용. 판정과 승인은 사람이 한다.",
        }

    async def _run_leg(
        self,
        params: dict[str, Any],
        symbol: str,
        market: str,
        start_ts: datetime,
        end_ts: datetime,
    ) -> dict[str, Any]:
        run = await self._backtest.run(
            strategy_type=params.get("strategy_type", ""),
            parameters=params,
            symbol_code=symbol,
            timeframe=params.get("timeframe", "1m"),
            start_ts=start_ts,
            end_ts=end_ts,
            market=market,
        )
        if run.status != "succeeded" or not run.metrics:
            return {"status": "failed", "error": run.error_message, "run_id": run.id}
        m = run.metrics
        return {
            "status": "succeeded",
            "run_id": run.id,
            "timeframe": params.get("timeframe", "1m"),
            "trade_count": m["trade_count"],
            "win_rate": m["win_rate"],
            "return_pct": m["return_pct"],
            "max_drawdown_pct": m["max_drawdown_pct"],
            "buy_hold_return_pct": m["buy_hold_return_pct"],
        }


def _verdict(base: dict[str, Any], proposed: dict[str, Any]) -> str:
    """참고용 라벨: proposed_better / base_better / inconclusive / insufficient_data."""
    if base.get("status") != "succeeded" or proposed.get("status") != "succeeded":
        return "insufficient_data"
    if (
        base.get("trade_count", 0) < MIN_TRADES_FOR_VERDICT
        or proposed.get("trade_count", 0) < MIN_TRADES_FOR_VERDICT
    ):
        return "insufficient_data"
    diff = proposed["return_pct"] - base["return_pct"]
    if diff > VERDICT_MARGIN_PP:
        return "proposed_better"
    if diff < -VERDICT_MARGIN_PP:
        return "base_better"
    return "inconclusive"
