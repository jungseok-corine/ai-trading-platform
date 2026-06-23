from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.repositories.financial_statement import FinancialStatementRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.macro_regime_service import MacroRegimeService
from app.services.news_curator_service import NewsCuratorService
from app.services.proposal_retrospective_service import ProposalRetrospectiveService
from app.services.strategy_analysis_input_service import StrategyAnalysisInputService
from app.services.trade_tape_service import TradeTapeService


def resolve_analysis_market(params: dict) -> MarketCode:
    """전략 파라미터에서 분석 시장(KR/US)을 추론한다.

    단일종목은 `market`, 유니버스는 `universe_market`을 본다. 혼합(universe_market=None)이거나
    미지정이면 KR로 둔다(하위호환 — 구조적 시장 분리는 운영상 KR/US 전략 분리로 갈음).
    """
    value = params.get("market") or params.get("universe_market")
    return MarketCode.US if value == "US" else MarketCode.KR


class AnalysisBundleService:
    """LLM 분석에 바로 넣을 '전체 번들'을 하나로 합친다 (C-2.53).

    기존 조각들을 재사용해 추가만 한다(기존 스키마 변경 없음):
      - 전략 입력(성과·신호 요약)  : StrategyAnalysisInputService (C-2.0)
      - 그날 매매 테이프            : TradeTapeService (C-2.52, 압축+사전계산+가드)
      - 전일 미국장 매크로 레짐     : MacroRegimeService (C-2.49)
      - 관련 뉴스/수동 주입         : NewsContextService (source=manual 포함)
      - 애널리스트 노트(수동 주입)  : 호출 시 전달

    온디맨드 read-only 조립. 실제 LLM 호출은 이후 단계(C-2.54)에서 이 번들을 입력으로 쓴다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = StrategyVersionRepository(session)
        self._input_svc = StrategyAnalysisInputService(session)
        self._tape_svc = TradeTapeService(session)
        self._macro_svc = MacroRegimeService(session)
        self._news_curator = NewsCuratorService(session)
        self._retro_svc = ProposalRetrospectiveService(session)
        self._finstat_repo = FinancialStatementRepository(session)

    async def build_full(
        self,
        strategy_version_id: int,
        trading_day: date,
        *,
        market: MarketCode | None = None,
        analyst_note: str | None = None,
        news_limit: int = 10,
    ) -> dict | None:
        """strategy_version의 trading_day 전체 분석 번들을 만든다. 버전 없으면 None.

        market=None이면 전략 파라미터(market/universe_market)에서 분석 시장을 추론한다 —
        US 전략은 US 공시(EDGAR)·뉴스를 받도록. 명시되면 그 값을 쓴다(API 오버라이드용).
        """
        version = await self._version_repo.get(strategy_version_id)
        if version is None:
            return None

        params = version.parameters or {}
        if market is None:
            market = resolve_analysis_market(params)
        # "" → None: universe 전략은 symbol_code가 없으므로 시장 수준 뉴스로 폴백.
        symbol_code: str | None = params.get("symbol_code") or None

        strategy_input = await self._input_svc.get_analysis_input(
            version.strategy_id, strategy_version_id
        )
        trade_tape = await self._tape_svc.build_for_version(
            strategy_version_id, trading_day, market=market
        )
        # 룩어헤드 방지: trading_day 직전 미국 세션 기준 레짐(같은 날 미국장은 미래).
        macro = await self._macro_svc.regime_as_of(trading_day)

        # 중요도 큐레이션(C-2.57): symbol_code 없는 universe 전략은 시장 수준 뉴스를 수집.
        news: list[dict] = await self._news_curator.curate(
            market=market, symbol_code=symbol_code, limit=news_limit
        )

        financials = await self._build_financials(symbol_code)

        return {
            "meta": {
                "strategy_id": version.strategy_id,
                "strategy_version_id": strategy_version_id,
                "symbol_code": symbol_code or "",
                "trading_day": trading_day.isoformat(),
                "market": market.value,
            },
            "strategy_input": strategy_input.model_dump(mode="json")
            if strategy_input is not None else None,
            "trade_tape": trade_tape,
            "macro": macro,
            "news": news,
            "financials": financials,
            "retrospective": await self._retro_svc.summary(),
            "analyst_note": analyst_note,
        }

    async def _build_financials(self, symbol_code: str | None) -> dict | None:
        """symbol_code의 최신 연간 재무제표 요약을 반환한다. 없으면 None."""
        if not symbol_code:
            return None
        row = await self._finstat_repo.get_latest_annual(symbol_code)
        if row is None:
            return None
        return {
            "bsns_year": row.bsns_year,
            "reprt_code": row.reprt_code,
            "fs_div": row.fs_div,
            "key_items": row.key_items,
        }
