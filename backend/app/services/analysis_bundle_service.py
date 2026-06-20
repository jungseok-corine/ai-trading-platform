from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import MarketCode
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.macro_regime_service import MacroRegimeService
from app.services.news_curator_service import NewsCuratorService
from app.services.proposal_retrospective_service import ProposalRetrospectiveService
from app.services.strategy_analysis_input_service import StrategyAnalysisInputService
from app.services.trade_tape_service import TradeTapeService


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

    async def build_full(
        self,
        strategy_version_id: int,
        trading_day: date,
        *,
        market: MarketCode = MarketCode.KR,
        analyst_note: str | None = None,
        news_limit: int = 10,
    ) -> dict | None:
        """strategy_version의 trading_day 전체 분석 번들을 만든다. 버전 없으면 None."""
        version = await self._version_repo.get(strategy_version_id)
        if version is None:
            return None

        symbol_code = (version.parameters or {}).get("symbol_code", "")

        strategy_input = await self._input_svc.get_analysis_input(
            version.strategy_id, strategy_version_id
        )
        trade_tape = await self._tape_svc.build_for_version(
            strategy_version_id, trading_day
        )
        # 룩어헤드 방지: trading_day 직전 미국 세션 기준 레짐(같은 날 미국장은 미래).
        macro = await self._macro_svc.regime_as_of(trading_day)

        # 중요도 큐레이션(C-2.57): 주가 영향 없는 노이즈는 거르고 중요한 것만 상위로.
        news: list[dict] = []
        if symbol_code:
            news = await self._news_curator.curate(
                market=market, symbol_code=symbol_code, limit=news_limit
            )

        return {
            "meta": {
                "strategy_id": version.strategy_id,
                "strategy_version_id": strategy_version_id,
                "symbol_code": symbol_code,
                "trading_day": trading_day.isoformat(),
                "market": market.value,
            },
            "strategy_input": strategy_input.model_dump(mode="json")
            if strategy_input is not None else None,
            "trade_tape": trade_tape,
            "macro": macro,
            "news": news,
            "retrospective": await self._retro_svc.summary(),
            "analyst_note": analyst_note,
        }
