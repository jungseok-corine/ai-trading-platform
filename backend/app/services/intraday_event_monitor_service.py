"""§7.1 인트라데이 이벤트 감시 — 보유/활성 종목 장중 공시 감시.

일일 분석과 별개로, **전략이 매매 중인 종목**(보유 포지션 + 활성 단일종목 전략)에 한해
장중 중요 공시(DART)를 좁게 감시한다. 범위를 좁혀 비용·노이즈를 최소화한다.

감지된 중요 공시는 news_events에 저장되어 관제탑/알림에 노출된다.
read-only — 감지·표시만 하고 자동매매와 무관하다(대응은 사람).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.position import PositionRepository
from app.domain.repositories.strategy import StrategyVersionRepository
from app.services.dart_provider import DartProvider
from app.services.dart_ingest_service import DartIngestService
from app.services.disclosure_alert_service import DisclosureAlertService


class IntradayEventMonitorService:
    """보유 포지션 + 활성 단일종목 전략 종목에 한해 장중 DART 공시를 감시한다.

    DART는 한국 공시 전용이므로 한국(KR) 종목만 대상으로 한다. 미국 종목은 추후 SEC EDGAR
    연동 시 별도로 합류한다.
    """

    def __init__(self, session: AsyncSession, provider: DartProvider | None = None) -> None:
        self._session = session
        self._ingest = DartIngestService(session, provider)
        self._alert = DisclosureAlertService(session)

    async def resolve_monitored_symbols(self) -> set[str]:
        """감시 대상 = 보유 포지션(수량≠0) ∪ 활성/테스팅 전략의 단일 KR 종목.

        유니버스 전략(관심종목 전체)은 일일 dart_ingest가 이미 넓게 커버하므로 제외하고,
        '실제로 매매/감시 중인' 좁은 집합만 본다(비용·노이즈 최소화).
        """
        symbols: set[str] = set()

        # 보유 포지션(전 계좌, 수량≠0)
        positions = await PositionRepository(self._session).list_by_account()
        symbols |= {p.symbol_code for p in positions}

        # 활성/테스팅 전략의 단일 KR 종목(유니버스 모드 제외)
        versions = await StrategyVersionRepository(self._session).list_active()
        for v in versions:
            params = v.parameters or {}
            if params.get("universe"):
                continue
            if params.get("market", "KR") != "KR":
                continue
            code = params.get("symbol_code")
            if code:
                symbols.add(code)
        return symbols

    async def run_once(self, min_score: float = 0.6) -> dict:
        """감시 대상 종목의 장중 공시를 수집한다. 대상이 없으면 건너뛴다."""
        symbols = await self.resolve_monitored_symbols()
        if not symbols:
            return {"monitored": 0, "skipped_reason": "no_monitored_symbols",
                    "fetched": 0, "matched": 0, "material": 0, "created": 0}
        summary = await self._ingest.ingest(symbols=list(symbols), min_score=min_score)
        return {"monitored": len(symbols), **summary.to_dict()}

    async def recent_alerts(
        self, hours: int = 8, min_score: float = 0.6, limit: int = 50
    ) -> list[dict]:
        """감시 대상 종목의 최근 중요 공시 알림(보유종목 한정)."""
        symbols = await self.resolve_monitored_symbols()
        if not symbols:
            return []
        return await self._alert.recent(
            hours=hours, symbols=list(symbols), min_score=min_score, limit=limit
        )
