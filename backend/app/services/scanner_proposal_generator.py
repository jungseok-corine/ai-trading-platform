from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ScannerConditionType
from app.domain.models.scanner_proposal import ScannerRuleProposal
from app.domain.repositories.scanner import ScannerRuleVersionRepository
from app.services.candidate_outcome_service import CandidateOutcomeService
from app.services.scanner_proposal_service import ScannerProposalService
from app.services.scanner_service import ScannerRuleVersionNotFoundError

# 제안을 만들기 위한 최소 분석 후보 수. 데이터가 적으면 제안하지 않는다(문서 2.3: 데이터 부족 시 자제).
MIN_CANDIDATES_FOR_SUGGESTION = 5
# 전체 승률이 이 값 미만일 때만 '조건 강화'를 제안한다.
WIN_RATE_THRESHOLD = 50.0
# 조건 강화 배수(진입 문턱 강화).
TIGHTEN_FACTOR = Decimal("1.3")
# turnover_rank는 더 낮을수록 엄격하므로 줄인다.
RANK_FACTOR = Decimal("0.7")


def _round1(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


@dataclass
class _TightenResult:
    conditions: list[dict]
    changes: list[str]  # 사람이 읽을 수 있는 변경 설명


def tighten_conditions(conditions: list[dict]) -> _TightenResult:
    """스캐너 조건을 결정적으로 강화한다(진입 문턱을 높여 약한 신호를 줄인다).

    - volume_spike.multiplier ×1.3
    - price_change_pct.min_pct ×1.3
    - turnover_rank.max_rank ×0.7 (최소 1)
    investor_flow / time_bucket 같은 범주형 조건은 강화 기준이 모호하여 그대로 둔다.
    """
    new_conditions: list[dict] = []
    changes: list[str] = []

    for cond in conditions:
        ctype = cond.get("type")
        params = dict(cond.get("params") or {})

        if ctype == ScannerConditionType.VOLUME_SPIKE.value:
            cur = Decimal(str(params.get("multiplier", 1.5)))
            new = _round1(cur * TIGHTEN_FACTOR)
            if Decimal(str(new)) <= cur:
                new = float(cur + Decimal("0.5"))
            params["multiplier"] = new
            changes.append(f"volume_spike multiplier {cur} → {new}")
        elif ctype == ScannerConditionType.PRICE_CHANGE_PCT.value:
            cur = Decimal(str(params.get("min_pct", 0)))
            new = _round1(cur * TIGHTEN_FACTOR)
            if Decimal(str(new)) <= cur:
                new = float(cur + Decimal("1.0"))
            params["min_pct"] = new
            changes.append(f"price_change_pct min_pct {cur} → {new}")
        elif ctype == ScannerConditionType.TURNOVER_RANK.value:
            cur = int(params.get("max_rank", 100))
            new = max(1, int((Decimal(cur) * RANK_FACTOR).to_integral_value()))
            if new >= cur:
                new = max(1, cur - 1)
            params["max_rank"] = new
            changes.append(f"turnover_rank max_rank {cur} → {new}")

        new_conditions.append({"type": ctype, "params": params})

    return _TightenResult(conditions=new_conditions, changes=changes)


class ScannerProposalGenerator:
    """후보 성과 분석(C-2.38)을 근거로 스캐너 룰 개선 제안을 자동 생성한다 (C-2.39).

    스캐너 조건은 AND로 평가되므로 한 버전 안에서 조건별 성과가 동일하다(by_condition이 같음).
    따라서 '전체 승률(overall win_rate)'을 기준으로 강화 여부를 판단한다. 전체 승률이 낮으면
    진입 문턱을 높이는 '조건 강화' 제안을 만들고, 승인 전에는 룰에 반영되지 않는다(pending).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._version_repo = ScannerRuleVersionRepository(session)
        self._outcome_service = CandidateOutcomeService(session)
        self._proposal_service = ScannerProposalService(session)

    async def generate_for_version(
        self,
        version_id: int,
        horizon_minutes: int = 30,
    ) -> ScannerRuleProposal | None:
        version = await self._version_repo.get(version_id)
        if version is None:
            raise ScannerRuleVersionNotFoundError(version_id)

        analysis = await self._outcome_service.analyze(
            scanner_rule_version_id=version_id, horizon_minutes=horizon_minutes
        )
        overall = analysis.overall
        count = overall.get("count") or 0
        win_rate = overall.get("win_rate")

        # 데이터가 부족하거나 승률이 기준 이상이면 제안하지 않는다.
        if count < MIN_CANDIDATES_FOR_SUGGESTION:
            return None
        if win_rate is None or win_rate >= WIN_RATE_THRESHOLD:
            return None

        tightened = tighten_conditions(version.conditions or [])
        if not tightened.changes:
            return None
        # 강화 결과가 기존과 동일하면(실제 변경 없음) 제안하지 않는다.
        if tightened.conditions == (version.conditions or []):
            return None

        base_reason = (
            f"최근 {count}건 후보의 {horizon_minutes}분 후 승률이 {win_rate}%로 "
            f"기준({WIN_RATE_THRESHOLD}%) 미만입니다."
        )
        change_text = "; ".join(tightened.changes)

        return await self._proposal_service.create_proposal(
            scanner_rule_id=version.scanner_rule_id,
            suggested_conditions=tightened.conditions,
            title=f"스캐너 조건 강화 (v{version.version_no})",
            summary=f"진입 문턱을 높여 약한 신호를 줄입니다: {change_text}",
            rationale=f"{base_reason} 조건을 강화해 후보 품질을 높입니다.",
            expected_effect="후보 수 감소, 약한 신호 제거로 평균 후보 품질 개선 가능.",
            risk_notes="조건이 강해져 기회가 줄어들 수 있습니다. 새 버전으로 비교 검증이 필요합니다.",
            base_version_id=version_id,
            source="ai",
        )
