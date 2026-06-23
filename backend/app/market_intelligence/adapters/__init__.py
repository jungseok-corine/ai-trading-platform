"""Market Intelligence 어댑터 구현체 패키지.

새 데이터 소스를 추가할 때는 IntelligenceAdapter를 상속해 이 패키지 아래에 배치한다.
"""
from app.market_intelligence.adapters.dart_disclosure_adapter import DartDisclosureAdapter
from app.market_intelligence.adapters.generic_rss_adapter import GenericRssAdapter

__all__ = [
    "DartDisclosureAdapter",
    "GenericRssAdapter",
]
