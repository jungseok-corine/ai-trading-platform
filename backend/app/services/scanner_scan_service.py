from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from app.common.timezone import KST

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.market_context import SymbolThemeMembership, Theme
from app.domain.repositories.investor_flow import InvestorFlowRepository
from app.domain.repositories.market_data import MarketDataRepository
from app.domain.repositories.scanner import ScannerRuleVersionRepository
from app.services.candidate_service import CandidateService, ScanResult
from app.services.macro_regime_service import MacroRegimeService
from app.services.scanner_service import ScannerRuleVersionNotFoundError
from app.trading.scanner.facts import assign_turnover_ranks, compute_symbol_facts



class ScannerScanService:
    """DB에 저장된 시장 데이터/수급으로 종목 facts를 계산해 스캐너 룰을 실행한다 (C-2.31).

    "시장 데이터 → facts 계산 → 룰 평가 → 후보 기록" 루프를 실제 데이터로 돌린다.
    KIS 직접 호출 없이 market_data/investor_flows DB만 읽는다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = ScannerRuleVersionRepository(session)
        self._market_repo = MarketDataRepository(session)
        self._flow_repo = InvestorFlowRepository(session)
        self._candidate_service = CandidateService(session)
        self._macro_service = MacroRegimeService(session)

    async def scan_from_market_data(
        self,
        version_id: int,
        symbol_codes: list[str],
        timeframe: str = "1m",
        volume_window: int = 20,
        lookback: int = 60,
        now: datetime | None = None,
        context_snapshot_id: int | None = None,
    ) -> ScanResult:
        version = await self._version_repo.get(version_id)
        if version is None:
            raise ScannerRuleVersionNotFoundError(version_id)

        now = now or datetime.now(KST)
        facts_by_symbol: dict[str, dict] = {}
        turnover_by_symbol: dict[str, Decimal] = {}

        for symbol in symbol_codes:
            candles = await self._market_repo.list_candles(
                symbol, timeframe=timeframe, limit=lookback
            )
            if not candles:
                continue  # 시장 데이터 없는 종목은 스킵
            closes = [c.close for c in candles]
            volumes = [c.volume for c in candles]

            flows = await self._flow_repo.list_by_symbol(symbol)  # 최신순
            latest_flow = flows[0] if flows else None

            facts = compute_symbol_facts(
                closes,
                volumes,
                latest_flow=latest_flow,
                now=now,
                volume_window=volume_window,
            )
            facts_by_symbol[symbol] = facts
            turnover_by_symbol[symbol] = closes[-1] * Decimal(volumes[-1])

        assign_turnover_ranks(facts_by_symbol, turnover_by_symbol)

        # 매크로 레짐(C-2.63): trading_day 기준 직전 미국장. 반도체 테마 종목 집합도 조회.
        macro = await self._macro_service.regime_as_of(now.date())
        semis_symbols = await self._semis_symbols()

        return await self._candidate_service.scan(
            version_id,
            facts_by_symbol,
            triggered_at=now,
            context_snapshot_id=context_snapshot_id,
            macro=macro,
            semis_symbols=semis_symbols,
        )

    async def _semis_symbols(self) -> set[str]:
        """반도체 테마에 속한 종목 집합(테마명에 '반도체' 포함)."""
        result = await self._session.execute(
            select(SymbolThemeMembership.symbol_code)
            .join(Theme, Theme.id == SymbolThemeMembership.theme_id)
            .where(Theme.name.like("%반도체%"))
            .distinct()
        )
        return {row[0] for row in result.all()}
