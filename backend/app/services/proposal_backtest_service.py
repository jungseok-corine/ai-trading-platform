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
        # 제안 파라미터: 승인(approve)이 suggested_parameters를 **그대로** 새 버전으로 만들므로,
        # 백테스트도 병합 없이 suggested 원문을 검증한다 (승인 결과와 정확히 일치).
        proposed_params = dict(proposal.suggested_parameters or {})

        end_ts = datetime.now(timezone.utc)

        async def _leg(params: dict[str, Any]) -> dict[str, Any]:
            # 레그별로 자기 자신의 대상(단일 종목 또는 유니버스)을 해석한다 —
            # base가 유니버스, 제안이 단일 종목처럼 서로 다른 구조일 수 있다.
            if params.get("universe"):
                leg_symbols = await self._universe_symbols(params, settings)
                if not leg_symbols:
                    return {"status": "failed", "error": "유니버스 종목 해석 결과 없음"}
            else:
                symbol = params.get("symbol_code") or ""
                if not symbol:
                    return {"status": "failed", "error": "symbol_code 없음"}
                leg_symbols = [symbol]
            market = params.get("market", "KR")
            start_ts = self._leg_start(params, end_ts, settings)
            result = await self._run_symbols(params, leg_symbols, market, start_ts, end_ts)
            result["symbols"] = leg_symbols
            return result

        base_result = await _leg(base_params)
        proposed_result = await _leg(proposed_params)
        if base_result.get("error") == "symbol_code 없음" and proposed_result.get(
            "error"
        ) == "symbol_code 없음":
            return {"skipped": "양쪽 모두 대상 심볼 없음 — 백테스트 생략"}

        return {
            "window_days": settings.proposal_backtest_days,
            "generated_at": end_ts.isoformat(),
            "base": base_result,
            "proposed": proposed_result,
            "verdict": _verdict(base_result, proposed_result),
            "note": "저장된 시세 기반 시뮬레이션 — 참고용. 판정과 승인은 사람이 한다.",
        }

    @staticmethod
    def _leg_start(params: dict[str, Any], end_ts: datetime, settings) -> datetime:
        """레그별 시작 시각 — 일봉 전략은 분봉 창(기본 14일)으론 봉이 모자라 1년으로 확장."""
        timeframe = str(params.get("timeframe", "1m")).lower()
        days = 365 if timeframe in ("1d", "d", "day") else settings.proposal_backtest_days
        return end_ts - timedelta(days=days)

    async def _universe_symbols(self, params: dict[str, Any], settings) -> list[str]:
        """유니버스 종목을 해석해 상위 N개(설정)를 반환한다. 실패 시 빈 리스트."""
        from app.domain.models.enums import MarketCode  # noqa: PLC0415
        from app.services.universe_resolver import UniverseResolver  # noqa: PLC0415

        market_filter = params.get("universe_market")
        market = MarketCode(market_filter) if market_filter else None
        resolved = await UniverseResolver(self._session).resolve(
            params["universe"],
            market=market,
            lookback_days=int(params.get("universe_lookback_days", 5)),
        )
        return [r.symbol_code for r in resolved[: settings.proposal_backtest_universe_symbols]]

    async def _run_symbols(
        self,
        params: dict[str, Any],
        symbols: list[str],
        market: str,
        start_ts: datetime,
        end_ts: datetime,
    ) -> dict[str, Any]:
        """심볼별 백테스트 후 집계. 단일 심볼이면 그대로, 복수면 평균/합산."""
        legs = [await self._run_leg(params, s, market, start_ts, end_ts) for s in symbols]
        ok = [leg for leg in legs if leg["status"] == "succeeded"]
        if not ok:
            first_err = next((leg.get("error") for leg in legs if leg.get("error")), None)
            return {"status": "failed", "error": first_err or "모든 심볼 데이터 부족", "per_symbol": legs}
        if len(legs) == 1:
            return legs[0]

        total_trades = sum(leg["trade_count"] for leg in ok)
        total_wins = sum(
            round((leg["win_rate"] or 0) * leg["trade_count"]) for leg in ok
        )
        return {
            "status": "succeeded",
            "mode": "universe",
            "symbols_used": len(ok),
            "timeframe": params.get("timeframe", "1m"),
            "trade_count": total_trades,
            "win_rate": (total_wins / total_trades) if total_trades else None,
            "return_pct": sum(leg["return_pct"] for leg in ok) / len(ok),
            "max_drawdown_pct": sum(leg["max_drawdown_pct"] for leg in ok) / len(ok),
            "buy_hold_return_pct": sum(leg["buy_hold_return_pct"] for leg in ok) / len(ok),
            "per_symbol": legs,
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
