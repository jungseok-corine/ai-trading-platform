"""Intelligence 후보 기반 스캐너 룰 개선 제안 생성기 (C-2.25).

LLM이 최근 IntelligenceCandidate 패턴과 시장 맥락을 분석해 기존 스캐너 룰의
개선 버전을 '제안'한다.

안전 원칙:
- 기존 ScannerRule 개선만 허용. 새 ScannerRule 생성 금지.
- 제안은 항상 pending(ProposalStatus.PENDING). 자동 approve 금지.
- 승인 시 기존 ScannerProposalService.approve() 흐름으로 DRAFT version만 생성됨.
- 외부 네트워크 호출 없음. DB에 이미 있는 데이터만 사용.
- 이벤트 기반 자동 트리거 없음. 온디맨드 또는 스케줄러(기본 비활성)만.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.intelligence_candidate import IntelligenceCandidateRepository
from app.domain.repositories.intelligence import IntelligenceEventRepository
from app.domain.repositories.scanner import ScannerRuleRepository, ScannerRuleVersionRepository
from app.domain.repositories.scanner_proposal import ScannerRuleProposalRepository
from app.services.ai_analysis.base import AnalysisProvider
from app.services.macro_regime_service import MacroRegimeService
from app.services.scanner_proposal_service import ScannerProposalService
from app.services.theme_activity_service import ThemeActivityService
from app.trading.scanner.conditions import InvalidConditionError, validate_conditions

logger = logging.getLogger(__name__)

INTELLIGENCE_AI_SOURCE = "intelligence_ai"

# 프롬프트에 포함할 후보 수 상한 (토큰 비용 통제)
_MAX_CANDIDATES = 20
# 제안할 수 있는 최대 룰 수
_MAX_PROPOSALS_PER_RUN = 5


_CONDITION_SCHEMA = """\
유효한 조건 타입 및 params:
1. volume_spike    — {"type": "volume_spike", "params": {"multiplier": <양의 실수>}}
   * 거래량이 평균의 multiplier배 이상인 종목을 포착
2. turnover_rank   — {"type": "turnover_rank", "params": {"max_rank": <양의 정수>}}
   * 거래대금 순위가 max_rank 이내인 종목을 포착 (낮을수록 엄격)
3. price_change_pct — {"type": "price_change_pct", "params": {"min_pct": <실수>}}
   * 가격 변동률이 min_pct% 이상인 종목을 포착
4. investor_flow   — {"type": "investor_flow", "params": {"foreign": "net_buy"|"net_sell", \
"institution": "net_buy"|"net_sell", "individual": "net_buy"|"net_sell"}}
   * foreign/institution/individual 중 1개 이상 지정. 수급 방향 필터.
5. time_bucket     — {"type": "time_bucket", "params": {"buckets": ["morning"|"afternoon"|"close"]}}
   * 장 시간대 필터. buckets는 비어있지 않은 리스트.
조건은 AND 시맨틱으로 평가된다 (모두 충족해야 후보가 됨)."""


def _build_prompt(
    candidates_text: str,
    rules_text: str,
    active_themes: list[str],
    macro_regime: str,
    valid_rule_ids: set[int],
) -> str:
    themes_str = ", ".join(active_themes) if active_themes else "없음"
    rule_ids_str = ", ".join(str(i) for i in sorted(valid_rule_ids))

    return f"""\
당신은 한국·미국 주식 시장의 정량 분석 전문가입니다.
아래의 Intelligence 후보 종목 패턴과 시장 맥락을 바탕으로, 기존 스캐너 룰의 조건을 개선 제안합니다.

=== 핵심 제약 (반드시 준수) ===
- 반드시 아래 나열된 기존 scanner_rule_id 중 하나만 사용하세요: [{rule_ids_str}]
- 새 ScannerRule을 생성하지 마세요
- 제안 없으면 빈 배열 []을 반환하세요
- 최대 {_MAX_PROPOSALS_PER_RUN}개 제안

=== 유효한 조건 타입 ===
{_CONDITION_SCHEMA}

=== 매크로 레짐 ===
{macro_regime}

=== 활성 테마 ===
{themes_str}

=== 최근 Intelligence 후보 종목 (score 상위, 최신 {_MAX_CANDIDATES}건) ===
{candidates_text}

=== 개선 대상 스캐너 룰 (기존 active/testing 버전) ===
{rules_text}

=== 출력 형식 ===
반드시 아래 형식의 JSON 배열만 반환하세요. 다른 텍스트를 포함하지 마세요.
[
  {{
    "scanner_rule_id": <기존 id>,
    "base_version_id": <기존 version id>,
    "suggested_conditions": [
      {{"type": "<조건타입>", "params": {{...}}}}
    ],
    "title": "<제안 제목 (100자 이내)>",
    "rationale": "<이 조건을 제안하는 이유>",
    "expected_effect": "<예상 효과>"
  }}
]
"""


def _format_candidates(candidates, events_by_id: dict) -> str:
    if not candidates:
        return "없음"
    lines = []
    for c in candidates:
        ev = events_by_id.get(c.intelligence_event_id)
        ev_title = ev.title if ev else ""
        ev_summary = (ev.summary or "")[:200] if ev else ""
        occurred = ev.occurred_at.strftime("%Y-%m-%d") if (ev and ev.occurred_at) else ""
        themes = ", ".join(c.matched_themes or []) or "없음"
        lines.append(
            f"- [{c.market.value}] {c.symbol_code} | score={c.score} | "
            f"themes=[{themes}] | source={c.source_type}\n"
            f"  이벤트: {ev_title[:100]} {f'({occurred})' if occurred else ''}\n"
            f"  {ev_summary}"
        )
    return "\n".join(lines)


def _format_rules(versions, rules_by_id: dict) -> str:
    if not versions:
        return "없음"
    lines = []
    for v in versions:
        rule = rules_by_id.get(v.scanner_rule_id)
        rule_name = rule.name if rule else f"rule_{v.scanner_rule_id}"
        lines.append(
            f"- scanner_rule_id={v.scanner_rule_id} | version_id={v.id} "
            f"| v{v.version_no} | status={v.status.value}\n"
            f"  룰: {rule_name}\n"
            f"  현재 조건: {json.dumps(v.conditions, ensure_ascii=False)}"
        )
    return "\n".join(lines)


def _extract_json_array(content: str) -> list:
    """LLM 응답에서 JSON 배열을 추출한다. 코드블록 마커를 제거 후 파싱."""
    # ```json ... ``` 또는 ``` ... ``` 블록 안 내용 추출
    cleaned = re.sub(r"```(?:json)?\s*", "", content)
    cleaned = re.sub(r"```", "", cleaned).strip()

    # 첫 번째 '[' ~ 마지막 ']' 범위 추출
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON 배열을 찾을 수 없음")
    return json.loads(cleaned[start : end + 1])


@dataclass
class ProposalGenerationSummary:
    candidates_analyzed: int = 0
    scanner_rules_considered: int = 0
    proposals_created: int = 0
    skipped_existing_pending: int = 0
    skipped_invalid: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "candidates_analyzed": self.candidates_analyzed,
            "scanner_rules_considered": self.scanner_rules_considered,
            "proposals_created": self.proposals_created,
            "skipped_existing_pending": self.skipped_existing_pending,
            "skipped_invalid": self.skipped_invalid,
            "errors": self.errors,
        }


class IntelligenceScannerProposalGenerator:
    """Intelligence 후보 패턴을 LLM으로 분석해 기존 스캐너 룰 개선 제안을 생성한다 (C-2.25).

    - 새 ScannerRule 생성 없음
    - 제안은 항상 pending (자동 approve 없음)
    - 외부 네트워크 호출 없음
    - AnalysisProvider는 생성자로 주입 (테스트 시 FakeAnalysisProvider 서브클래스 주입 가능)
    """

    def __init__(self, session: AsyncSession, provider: AnalysisProvider | None = None) -> None:
        self._session = session
        self._candidate_repo = IntelligenceCandidateRepository(session)
        self._event_repo = IntelligenceEventRepository(session)
        self._rule_repo = ScannerRuleRepository(session)
        self._version_repo = ScannerRuleVersionRepository(session)
        self._proposal_repo = ScannerRuleProposalRepository(session)
        self._proposal_service = ScannerProposalService(session)
        self._theme_svc = ThemeActivityService(session)
        self._macro_svc = MacroRegimeService(session)

        if provider is None:
            from app.core.config import get_settings
            from app.services.ai_analysis.factory import get_analysis_provider
            provider = get_analysis_provider(get_settings().ai_analysis_provider)
        self._provider = provider

    async def generate(
        self,
        candidate_limit: int = _MAX_CANDIDATES,
    ) -> ProposalGenerationSummary:
        """최근 IntelligenceCandidate와 활성 스캐너 룰을 분석해 개선 제안을 생성한다."""
        summary = ProposalGenerationSummary()

        # 1. 기존 active/testing 버전 조회
        versions = await self._version_repo.list_active()
        if not versions:
            return summary
        summary.scanner_rules_considered = len(versions)

        # 2. 해당 ScannerRule 메타 조회
        rule_ids = list({v.scanner_rule_id for v in versions})
        rules = []
        for rid in rule_ids:
            r = await self._rule_repo.get(rid)
            if r is not None:
                rules.append(r)
        rules_by_id = {r.id: r for r in rules}
        valid_rule_ids = {v.scanner_rule_id for v in versions}
        valid_version_ids = {v.id for v in versions}
        version_by_id = {v.id: v for v in versions}

        # 3. 이미 pending 제안이 있는 base_version_id 수집 (중복 방지)
        pending_version_ids = await self._proposal_repo.pending_base_version_ids()

        # 4. 상위 IntelligenceCandidate 조회
        candidates = await self._candidate_repo.list_recent(limit=candidate_limit)
        summary.candidates_analyzed = len(candidates)

        # 5. 연결된 IntelligenceEvent 조회
        event_ids = [c.intelligence_event_id for c in candidates if c.intelligence_event_id]
        events_by_id: dict = {}
        for eid in event_ids:
            ev = await self._event_repo.get(eid)
            if ev is not None:
                events_by_id[eid] = ev

        # 6. 활성 테마 조회
        try:
            theme_result = await self._theme_svc.get_active_themes()
            active_themes: list[str] = theme_result.get("active_themes", [])
        except Exception:  # noqa: BLE001
            active_themes = []

        # 7. 매크로 레짐 조회
        try:
            macro = await self._macro_svc.latest_regime()
            macro_regime = macro.get("regime", "unknown")
        except Exception:  # noqa: BLE001
            macro_regime = "unknown"

        # 8. 프롬프트 생성
        candidates_text = _format_candidates(candidates[:_MAX_CANDIDATES], events_by_id)
        rules_text = _format_rules(versions, rules_by_id)
        prompt = _build_prompt(
            candidates_text=candidates_text,
            rules_text=rules_text,
            active_themes=active_themes,
            macro_regime=macro_regime,
            valid_rule_ids=valid_rule_ids,
        )

        # 9. LLM 호출
        try:
            result = await self._provider.analyze(prompt)
        except Exception as exc:  # noqa: BLE001
            summary.errors.append(f"LLM 호출 실패: {exc}")
            return summary

        # 10. JSON 파싱
        try:
            proposals_raw = _extract_json_array(result.content or "")
        except (ValueError, json.JSONDecodeError) as exc:
            summary.errors.append(f"JSON 파싱 실패: {exc}")
            return summary

        if not isinstance(proposals_raw, list):
            summary.errors.append("LLM이 배열이 아닌 형식을 반환함")
            return summary

        # 11. 제안별 처리
        created_count = 0
        for item in proposals_raw:
            if created_count >= _MAX_PROPOSALS_PER_RUN:
                break
            if not isinstance(item, dict):
                summary.skipped_invalid += 1
                continue

            rule_id = item.get("scanner_rule_id")
            version_id = item.get("base_version_id")
            suggested = item.get("suggested_conditions")
            title = (item.get("title") or "")[:200]
            rationale = item.get("rationale") or ""
            expected_effect = item.get("expected_effect") or ""

            # 기존 DB에 있는 rule_id/version_id만 허용
            if rule_id not in valid_rule_ids:
                summary.skipped_invalid += 1
                summary.errors.append(f"unknown scanner_rule_id={rule_id} — 건너뜀")
                continue
            if version_id not in valid_version_ids:
                summary.skipped_invalid += 1
                summary.errors.append(f"unknown base_version_id={version_id} — 건너뜀")
                continue

            # rule_id와 version_id 대응 확인
            version = version_by_id.get(version_id)
            if version is None or version.scanner_rule_id != rule_id:
                summary.skipped_invalid += 1
                summary.errors.append(
                    f"version_id={version_id}이 rule_id={rule_id}에 속하지 않음 — 건너뜀"
                )
                continue

            # 이미 pending 제안이 있으면 건너뜀
            if version_id in pending_version_ids:
                summary.skipped_existing_pending += 1
                continue

            # conditions 검증
            if not suggested:
                summary.skipped_invalid += 1
                summary.errors.append(f"rule_id={rule_id}: suggested_conditions 비어있음 — 건너뜀")
                continue
            try:
                validate_conditions(suggested)
            except (InvalidConditionError, Exception) as exc:
                summary.skipped_invalid += 1
                summary.errors.append(f"rule_id={rule_id}: 조건 검증 실패 — {exc}")
                continue

            if not title:
                title = f"Intelligence 기반 스캐너 개선 (rule_id={rule_id})"

            # 제안 저장
            try:
                await self._proposal_service.create_proposal(
                    scanner_rule_id=rule_id,
                    suggested_conditions=suggested,
                    title=title,
                    rationale=rationale,
                    expected_effect=expected_effect,
                    risk_notes="Intelligence 후보 패턴 기반 LLM 제안. 사람 승인 후 DRAFT 버전 생성.",
                    base_version_id=version_id,
                    source=INTELLIGENCE_AI_SOURCE,
                )
                pending_version_ids.add(version_id)
                created_count += 1
                summary.proposals_created += 1
            except Exception as exc:  # noqa: BLE001
                summary.errors.append(f"rule_id={rule_id}: 제안 저장 실패 — {exc}")

        return summary
