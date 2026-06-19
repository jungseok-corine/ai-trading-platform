from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.candidate_event import CandidateEvent
from app.domain.models.daily_report import DailyResearchReport
from app.domain.models.enums import MarketCode, StrategyVersionStatus, TradeSide
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import StrategyVersion
from app.domain.models.trade import Trade
from app.domain.repositories.daily_report import DailyResearchReportRepository
from app.domain.repositories.news_context import UsMarketSnapshotRepository

KST = ZoneInfo("Asia/Seoul")


class DailyReportService:
    """매일 장마감 후 시장/전략/스캐너/체결 활동을 집계해 리포트를 생성한다 (C-2.29).

    집계는 결정적(deterministic)이며, 추후 LLM 내러티브를 sections 위에 덧붙일 수 있다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DailyResearchReportRepository(session)
        self._us_repo = UsMarketSnapshotRepository(session)

    async def generate(
        self, report_date: date | None = None, market: MarketCode = MarketCode.KR
    ) -> DailyResearchReport:
        """report_date(기본 오늘, KST)의 활동을 집계해 리포트를 생성/갱신한다."""
        if report_date is None:
            report_date = datetime.now(KST).date()

        start = datetime.combine(report_date, time.min, tzinfo=KST)
        end = start + timedelta(days=1)

        signal_total, signal_by_type = await self._signal_stats(start, end)
        trade_stats = await self._trade_stats(start, end)
        candidates = await self._count(CandidateEvent, CandidateEvent.triggered_at, start, end)
        active_strategies = await self._active_strategy_count()
        us_prev = await self._us_repo.get_latest()

        sections = {
            "market": market.value,
            "report_date": report_date.isoformat(),
            "active_strategies": active_strategies,
            "signal_activity": {
                "total": signal_total,
                "buy": signal_by_type.get(TradeSide.BUY.value, 0),
                "sell": signal_by_type.get(TradeSide.SELL.value, 0),
            },
            "trade_summary": trade_stats,
            "scanner_activity": {"candidates": candidates},
            "us_previous_session": (
                {
                    "session_date": us_prev.session_date.isoformat(),
                    "nasdaq_change_pct": str(us_prev.nasdaq_change_pct)
                    if us_prev.nasdaq_change_pct is not None
                    else None,
                    "sox_change_pct": str(us_prev.sox_change_pct)
                    if us_prev.sox_change_pct is not None
                    else None,
                }
                if us_prev is not None
                else None
            ),
        }
        summary = self._build_summary(report_date, sections)

        existing = await self._repo.get_by_date(market, report_date)
        if existing is not None:
            await self._repo.update(existing, summary=summary, sections=sections)
            await self._session.commit()
            return existing

        report = await self._repo.create(
            market=market, report_date=report_date, summary=summary, sections=sections
        )
        await self._session.commit()
        return report

    async def get_report(
        self, report_date: date, market: MarketCode = MarketCode.KR
    ) -> DailyResearchReport | None:
        return await self._repo.get_by_date(market, report_date)

    async def list_reports(
        self, market: MarketCode | None = None, limit: int = 30
    ) -> list[DailyResearchReport]:
        return await self._repo.list_recent(market=market, limit=limit)

    # --- aggregation -----------------------------------------------------
    async def _count(self, model, ts_column, start: datetime, end: datetime) -> int:
        result = await self._session.execute(
            select(func.count(model.id)).where(ts_column >= start, ts_column < end)
        )
        return result.scalar() or 0

    async def _signal_stats(
        self, start: datetime, end: datetime
    ) -> tuple[int, dict[str, int]]:
        result = await self._session.execute(
            select(SignalLog.signal_type, func.count(SignalLog.id))
            .where(SignalLog.generated_at >= start, SignalLog.generated_at < end)
            .group_by(SignalLog.signal_type)
        )
        by_type: dict[str, int] = {}
        total = 0
        for sig_type, count in result.all():
            value = sig_type.value if hasattr(sig_type, "value") else str(sig_type)
            by_type[value] = count
            total += count
        return total, by_type

    async def _trade_stats(self, start: datetime, end: datetime) -> dict:
        result = await self._session.execute(
            select(Trade.pnl_amount).where(
                Trade.created_at >= start, Trade.created_at < end
            )
        )
        pnls = [row[0] for row in result.all()]
        closed = [p for p in pnls if p is not None]
        wins = [p for p in closed if p > 0]
        losses = [p for p in closed if p < 0]
        realized = sum(closed, Decimal("0"))
        return {
            "trades": len(pnls),
            "closed": len(closed),
            "win_count": len(wins),
            "loss_count": len(losses),
            "realized_pnl": str(realized),
        }

    async def _active_strategy_count(self) -> int:
        result = await self._session.execute(
            select(func.count(StrategyVersion.id)).where(
                StrategyVersion.status.in_(
                    [StrategyVersionStatus.ACTIVE, StrategyVersionStatus.TESTING]
                )
            )
        )
        return result.scalar() or 0

    @staticmethod
    def _build_summary(report_date: date, sections: dict) -> str:
        sig = sections["signal_activity"]
        trade = sections["trade_summary"]
        return (
            f"[{report_date.isoformat()}] "
            f"활성 전략 {sections['active_strategies']}개, "
            f"신호 {sig['total']}건(매수 {sig['buy']}/매도 {sig['sell']}), "
            f"체결 {trade['trades']}건(실현손익 {trade['realized_pnl']}), "
            f"후보 종목 {sections['scanner_activity']['candidates']}건."
        )
