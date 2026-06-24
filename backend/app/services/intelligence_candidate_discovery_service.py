"""IntelligenceEvent 기반 관심 후보 자동 발굴 서비스 (C-2.24).

LLM을 호출하지 않는다. 검증 가능한 휴리스틱 점수만 사용한다:
  - importance_score (이벤트 중요도 0.0–1.0, × 100 → 0–100 점수)
  - theme synergy bonus (symbol 테마 ∩ 활성 테마)
  - recency bonus (최근 이벤트일수록 소폭 가산)
  - source bonus (공시 > 뉴스)

symbol_code가 없는 이벤트에서 종목을 AI로 추론하지 않는다.
자동 종목-테마 추출 금지. 자동 전략 배정 금지. 실주문 코드 접촉 없음.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.models.enums import IntelligenceCandidateStatus, MarketCode
from app.domain.models.intelligence import IntelligenceEvent
from app.domain.repositories.intelligence import IntelligenceEventRepository
from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.domain.repositories.market_context import (
    SymbolThemeMembershipRepository,
)
from app.market_intelligence.adapters.base import build_dedup_hash
from app.services.theme_activity_service import (
    ThemeActivityService,
    compute_theme_synergy_bonus,
)


@dataclass
class DiscoverySummary:
    events_checked: int = 0
    candidates_created: int = 0
    skipped_duplicate_count: int = 0
    skipped_no_symbol_count: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "events_checked": self.events_checked,
            "candidates_created": self.candidates_created,
            "skipped_duplicate_count": self.skipped_duplicate_count,
            "skipped_no_symbol_count": self.skipped_no_symbol_count,
            "errors": self.errors,
        }


class IntelligenceCandidateDiscoveryService:
    """최근 IntelligenceEvent에서 symbol_code가 있는 이벤트를 후보로 발굴하고 저장한다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._event_repo = IntelligenceEventRepository(session)
        self._candidate_repo = IntelligenceCandidateRepository(session)
        self._membership_repo = SymbolThemeMembershipRepository(session)
        self._theme_activity_svc = ThemeActivityService(session)

    async def discover(
        self,
        lookback_hours: int = 24,
        event_limit: int = 100,
    ) -> DiscoverySummary:
        """최근 N시간 IntelligenceEvent에서 후보를 발굴한다.

        symbol_code가 있는 이벤트만 후보화한다. 없는 이벤트는 skipped_no_symbol_count에 집계.
        dedup_hash로 중복 후보는 건너뛴다.
        """
        events = await self._event_repo.list_recent(hours=lookback_hours, limit=event_limit)

        eligible = [e for e in events if e.symbol_code]
        summary = DiscoverySummary(
            events_checked=len(events),
            skipped_no_symbol_count=len(events) - len(eligible),
        )

        if not eligible:
            return summary

        candidate_hashes = [self._build_dedup_hash(e) for e in eligible]
        existing = await self._candidate_repo.existing_hashes(candidate_hashes)

        _active_themes_cache: dict[MarketCode, list[str]] = {}

        for event in eligible:
            dedup_hash = self._build_dedup_hash(event)
            if dedup_hash in existing:
                summary.skipped_duplicate_count += 1
                continue

            try:
                market = event.market or MarketCode.KR

                if market not in _active_themes_cache:
                    result = await self._theme_activity_svc.get_active_themes(
                        market, lookback_hours=lookback_hours
                    )
                    _active_themes_cache[market] = result["active_themes"]
                active_themes = _active_themes_cache[market]

                symbol_theme_objects = await self._membership_repo.list_themes_for_symbol(
                    event.symbol_code
                )
                symbol_theme_codes = [t.code for t in symbol_theme_objects]

                score, score_components = self._calc_score(event, symbol_theme_codes, active_themes)
                matched_themes = sorted(set(symbol_theme_codes) & set(active_themes))
                why_text = self._build_why_text(event, matched_themes, score_components)

                await self._candidate_repo.create(
                    intelligence_event_id=event.id,
                    symbol_code=event.symbol_code,
                    market=market,
                    score=score,
                    why_text=why_text,
                    status=IntelligenceCandidateStatus.PENDING,
                    source_type=event.event_type,
                    matched_themes=matched_themes,
                    score_components=score_components,
                    dedup_hash=dedup_hash,
                )
                existing.add(dedup_hash)
                summary.candidates_created += 1
            except Exception as exc:  # noqa: BLE001
                summary.errors.append(f"event_id={event.id}: {exc}")

        await self._session.commit()
        return summary

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _build_dedup_hash(event: IntelligenceEvent) -> str:
        return build_dedup_hash("intelligence_candidate", event.dedup_hash)

    @staticmethod
    def _calc_score(
        event: IntelligenceEvent,
        symbol_theme_codes: list[str],
        active_themes: list[str],
    ) -> tuple[int, dict]:
        """휴리스틱 점수 계산. 0~100 범위로 clamp."""
        base_importance = (
            int(float(event.importance_score) * 100) if event.importance_score else 50
        )

        theme_bonus = compute_theme_synergy_bonus(
            symbol_theme_codes, active_themes, bonus_per_theme=10
        )

        collected_at = event.collected_at
        if collected_at is not None:
            if collected_at.tzinfo is None:
                collected_at = collected_at.replace(tzinfo=timezone.utc)
            age_hours = max(0.0, (datetime.now(KST) - collected_at).total_seconds() / 3600)
        else:
            age_hours = 24.0
        recency_bonus = max(0, round(10 * (1 - min(age_hours, 24) / 24)))

        source_bonus = 5 if event.event_type == "disclosure" else 3

        final_score = min(100, max(0, base_importance + theme_bonus + recency_bonus + source_bonus))

        components = {
            "base_importance": base_importance,
            "theme_bonus": theme_bonus,
            "recency_bonus": recency_bonus,
            "source_bonus": source_bonus,
            "final_score": final_score,
        }
        return final_score, components

    @staticmethod
    def _build_why_text(
        event: IntelligenceEvent,
        matched_themes: list[str],
        score_components: dict,
    ) -> str:
        """LLM 미사용, deterministic template으로 why 텍스트 생성."""
        labels = {"news": "뉴스 이벤트", "disclosure": "공시 이벤트"}
        type_label = labels.get(event.event_type, "이벤트")

        if matched_themes:
            themes_str = "/".join(matched_themes)
            desc = f"{type_label} '{event.title}'가 활성 테마({themes_str})와 연결되어 후보로 생성됨"
        else:
            desc = f"{type_label} '{event.title}'에 의해 후보로 생성됨"

        details = [f"importance_score={score_components['base_importance']}"]
        if score_components["theme_bonus"] > 0:
            details.append(f"theme_bonus={score_components['theme_bonus']}")
        if score_components["recency_bonus"] > 0:
            details.append(f"recency_bonus={score_components['recency_bonus']}")

        return f"{desc}. {', '.join(details)}."
