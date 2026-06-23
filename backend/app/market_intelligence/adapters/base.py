"""Market Intelligence 어댑터 base 인터페이스 (C-2.21.1b).

새 데이터 소스는 IntelligenceAdapter를 상속해 구현한다.
어댑터는 수집(fetch) → 정규화(normalize) → 저장(이벤트 생성)의 흐름을 담당하며,
소스별 로직은 어댑터 내부에만 존재한다.

패턴:
  - IntelligenceRawItem: 외부 API 응답의 최소 표준화 DTO
  - IntelligenceEventCandidate: normalize 결과물; IntelligenceEvent 생성에 사용
  - IntelligenceAdapter: 구체 어댑터가 상속할 추상 클래스
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.models.enums import (
    IntelligenceEventStatus,
    IntelligenceMarketScope,
    IntelligenceProvider,
    IntelligenceSourceType,
    MarketCode,
)


@dataclass
class IntelligenceRawItem:
    """외부 소스에서 수집한 원본 데이터 DTO.

    어댑터의 fetch() 반환값. 아직 정규화되지 않은 원본 구조.
    raw_data에 원본 페이로드를 그대로 담는다.
    """

    raw_id: str                      # 외부 시스템의 고유 ID (dedup 생성용)
    title: str
    raw_data: dict[str, Any]
    occurred_at: datetime | None = None
    symbol_code: str | None = None
    source_ref: str | None = None    # URL 또는 원문 링크


@dataclass
class IntelligenceEventCandidate:
    """정규화된 이벤트 후보 DTO.

    normalize()의 반환값; IntelligenceEvent row 생성에 1:1 대응한다.
    dedup_hash를 직접 지정할 수 없는 경우 build_dedup_hash()를 사용한다.
    """

    source_key: str
    event_type: str
    title: str
    dedup_hash: str
    occurred_at: datetime | None = None
    market: MarketCode | None = None
    symbol_code: str | None = None
    summary: str | None = None
    source_ref: str | None = None
    importance_score: float | None = None
    confidence_score: float | None = None
    raw_payload: dict[str, Any] | None = None
    status: IntelligenceEventStatus = IntelligenceEventStatus.RAW
    extra: dict[str, Any] = field(default_factory=dict)


def build_dedup_hash(*parts: str) -> str:
    """source_key + 이벤트 식별 필드들을 SHA-256으로 해싱해 dedup_hash를 생성한다.

    순서와 값이 같으면 항상 동일한 hash를 반환한다.
    """
    payload = json.dumps(list(parts), ensure_ascii=False, sort_keys=False)
    return hashlib.sha256(payload.encode()).hexdigest()


class IntelligenceAdapter(ABC):
    """Market Intelligence 어댑터 추상 기반 클래스.

    구체 어댑터는 이 클래스를 상속하고 source_key / source_type / provider /
    market_scope 클래스 속성과 fetch() / normalize() 메서드를 구현한다.

    흐름:
      raw_items = await adapter.fetch()
      candidates = [adapter.normalize(item) for item in raw_items]
      # → 각 candidate로 IntelligenceEvent 생성/upsert
    """

    source_key: str                        # IntelligenceSource.source_key와 일치해야 함
    source_type: IntelligenceSourceType
    provider: IntelligenceProvider
    market_scope: IntelligenceMarketScope

    @abstractmethod
    async def fetch(self) -> list[IntelligenceRawItem]:
        """외부 소스에서 원본 데이터를 수집한다.

        네트워크 호출이 없는 어댑터(MANUAL 등)도 동일 서명을 유지한다.
        실패 시 AdapterFetchError를 raise한다.
        """

    @abstractmethod
    def normalize(self, raw: IntelligenceRawItem) -> IntelligenceEventCandidate:
        """원본 데이터를 IntelligenceEventCandidate로 정규화한다.

        dedup_hash는 이 메서드 내에서 build_dedup_hash()로 생성해야 한다.
        """


class AdapterFetchError(Exception):
    """어댑터 수집 실패(네트워크/인증/rate limit 등)."""
