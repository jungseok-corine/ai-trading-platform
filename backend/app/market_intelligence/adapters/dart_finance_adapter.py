"""DART 재무제표 어댑터 스켈레톤 (C-2.21.1b).

기존 DartFinanceProvider/DartFinanceIngestService가 IntelligenceAdapter 패턴으로
표현될 경우 어떤 모습이 되는지를 보여주는 스켈레톤이다.

중요:
- 이 파일은 아직 실제 수집을 수행하지 않는다.
- 기존 DartFinanceIngestService 동작을 변경하지 않는다.
- 외부 API를 호출하지 않는다.
- 실제 연결은 C-2.22 이후 점진적으로 진행한다.
"""
from __future__ import annotations

from app.domain.models.enums import (
    IntelligenceEventStatus,
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    MarketCode,
)
from app.market_intelligence.adapters.base import (
    IntelligenceAdapter,
    IntelligenceEventCandidate,
    IntelligenceRawItem,
    build_dedup_hash,
)

# 이 어댑터가 등록될 source_key — IntelligenceSource.source_key와 일치해야 함.
DART_FINANCE_SOURCE_KEY = "dart_finance"


class DartFinanceAdapter(IntelligenceAdapter):
    """DART XBRL 재무제표 → IntelligenceAdapter 스켈레톤.

    기존 DartFinanceProvider + DartFinanceIngestService가 제공하는 데이터를
    어댑터 패턴으로 노출하는 방법을 보여준다.

    TODO (C-2.22+): fetch()에서 DartFinanceProvider를 실제로 호출하도록 연결.
    """

    source_key = DART_FINANCE_SOURCE_KEY
    source_type = IntelligenceSourceType.FINANCIALS
    provider = IntelligenceProvider.DART
    market_scope = IntelligenceMarketScope.KR

    async def fetch(self) -> list[IntelligenceRawItem]:
        """미구현 — 실제 연결은 C-2.22+에서 진행한다."""
        raise NotImplementedError(
            "DartFinanceAdapter.fetch() is a skeleton. "
            "Use DartFinanceIngestService directly until C-2.22 integration."
        )

    def normalize(self, raw: IntelligenceRawItem) -> IntelligenceEventCandidate:
        """미구현 — 스켈레톤 시그니처만 제공한다."""
        corp_code = raw.raw_data.get("corp_code", "")
        bsns_year = raw.raw_data.get("bsns_year", "")
        reprt_code = raw.raw_data.get("reprt_code", "")
        fs_div = raw.raw_data.get("fs_div", "CFS")

        return IntelligenceEventCandidate(
            source_key=self.source_key,
            event_type="financials_annual" if reprt_code == "11011" else "financials_interim",
            title=f"{raw.title} ({bsns_year} {reprt_code})",
            dedup_hash=build_dedup_hash(self.source_key, corp_code, bsns_year, reprt_code, fs_div),
            market=MarketCode.KR,
            symbol_code=raw.symbol_code,
            raw_payload=raw.raw_data,
            status=IntelligenceEventStatus.NORMALIZED,
        )
