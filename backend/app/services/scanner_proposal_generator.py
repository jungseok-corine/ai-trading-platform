from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ScannerConditionType
from app.domain.models.scanner_proposal import ScannerRuleProposal
from app.domain.repositories.scanner import ScannerRuleVersionRepository
from app.services.candidate_outcome_service import CandidateOutcomeService
from app.services.macro_regime_service import MacroRegimeService
from app.services.scanner_proposal_service import ScannerProposalService
from app.services.scanner_service import ScannerRuleVersionNotFoundError

# 제안을 만들기 위한 최소 분석 후보 수. 데이터가 적으면 제안하지 않는다(문서 2.3: 데이터 부족 시 자제).
MIN_CANDIDATES_FOR_SUGGESTION = 5
# 전체 승률이 이 값 미만일 때만 '조건 강화'를 제안한다.
WIN_RATE_THRESHOLD = 50.0
# 조건 강화 배수(진입 문턱 강화). 기본(neutral/risk_on) vs 보수적(risk_off).
TIGHTEN_FACTOR = Decimal("1.3")
TIGHTEN_FACTOR_AGGRESSIVE = Decimal("1.45")
# turnover_rank는 더 낮을수록 엄격하므로 줄인다.
RANK_FACTOR = Decimal("0.7")
RANK_FACTOR_AGGRESSIVE = Decimal("0.6")


def _round1(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


@dataclass
class _TightenResult:
    conditions: list[dict]
    changes: list[str]  # 사람이 읽을 수 있는 변경 설명


def loosen_conditions(conditions: list[dict]) -> _TightenResult:
    """스캐너 조건을 결정적으로 완화한다 (C-6.17 — 후보 기근 탈출).

    tighten_conditions의 역방향: 강화로 문턱이 너무 높아져 후보가 전혀 안 잡히는
    '기근' 상태에서 진입 문턱을 한 단계 낮춘다.
    - volume_spike.multiplier ÷1.3 (최소 1.2 — 무의미한 수준까지 낮추지 않음)
    - price_change_pct.min_pct ÷1.3 (최소 0.5)
    - turnover_rank.max_rank ÷0.7 (최대 100)
    """
    new_conditions: list[dict] = []
    changes: list[str] = []

    for cond in conditions:
        ctype = cond.get("type")
        params = dict(cond.get("params") or {})

        if ctype == ScannerConditionType.VOLUME_SPIKE.value:
            cur = Decimal(str(params.get("multiplier", 1.5)))
            new = max(1.2, _round1(cur / TIGHTEN_FACTOR))
            if Decimal(str(new)) < cur:
                params["multiplier"] = new
                changes.append(f"volume_spike multiplier {cur} → {new}")
        elif ctype == ScannerConditionType.PRICE_CHANGE_PCT.value:
            cur = Decimal(str(params.get("min_pct", 0)))
            new = max(0.5, _round1(cur / TIGHTEN_FACTOR))
            if Decimal(str(new)) < cur:
                params["min_pct"] = new
                changes.append(f"price_change_pct min_pct {cur} → {new}")
        elif ctype == ScannerConditionType.TURNOVER_RANK.value:
            cur = int(params.get("max_rank", 100))
            new = min(100, int((Decimal(cur) / RANK_FACTOR).to_integral_value()))
            if new > cur:
                params["max_rank"] = new
                changes.append(f"turnover_rank max_rank {cur} → {new}")

        new_conditions.append({"type": ctype, "params": params})

    return _TightenResult(conditions=new_conditions, changes=changes)


def tighten_conditions(conditions: list[dict], *, aggressive: bool = False) -> _TightenResult:
    """스캐너 조건을 결정적으로 강화한다(진입 문턱을 높여 약한 신호를 줄인다).

    - volume_spike.multiplier ×1.3 (aggressive ×1.45)
    - price_change_pct.min_pct ×1.3 (aggressive ×1.45)
    - turnover_rank.max_rank ×0.7 (aggressive ×0.6, 최소 1)
    aggressive=True는 매크로 위험회피(risk_off) 국면에서 더 보수적으로 문턱을 높인다(C-2.50).
    investor_flow / time_bucket 같은 범주형 조건은 강화 기준이 모호하여 그대로 둔다.
    """
    mult_factor = TIGHTEN_FACTOR_AGGRESSIVE if aggressive else TIGHTEN_FACTOR
    rank_factor = RANK_FACTOR_AGGRESSIVE if aggressive else RANK_FACTOR
    new_conditions: list[dict] = []
    changes: list[str] = []

    for cond in conditions:
        ctype = cond.get("type")
        params = dict(cond.get("params") or {})

        if ctype == ScannerConditionType.VOLUME_SPIKE.value:
            cur = Decimal(str(params.get("multiplier", 1.5)))
            new = _round1(cur * mult_factor)
            if Decimal(str(new)) <= cur:
                new = float(cur + Decimal("0.5"))
            params["multiplier"] = new
            changes.append(f"volume_spike multiplier {cur} → {new}")
        elif ctype == ScannerConditionType.PRICE_CHANGE_PCT.value:
            cur = Decimal(str(params.get("min_pct", 0)))
            new = _round1(cur * mult_factor)
            if Decimal(str(new)) <= cur:
                new = float(cur + Decimal("1.0"))
            params["min_pct"] = new
            changes.append(f"price_change_pct min_pct {cur} → {new}")
        elif ctype == ScannerConditionType.TURNOVER_RANK.value:
            cur = int(params.get("max_rank", 100))
            new = max(1, int((Decimal(cur) * rank_factor).to_integral_value()))
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
        self._macro_service = MacroRegimeService(session)

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

        # C-6.17 후보 기근 감지: 최근 N일 후보 0건이면 강화의 반대 — 완화를 제안한다.
        # (강화만 있으면 조건이 시장 위로 올라가 0건에 영구히 갇힌다. 2026-06-23 실사례.)
        if await self._is_drought(version_id):
            return await self._propose_loosening(version)

        # 데이터가 부족하거나 승률이 기준 이상이면 제안하지 않는다.
        if count < MIN_CANDIDATES_FOR_SUGGESTION:
            return None
        if win_rate is None or win_rate >= WIN_RATE_THRESHOLD:
            return None

        # 매크로 레짐을 반영한다(C-2.50): risk_off 국면에서는 더 보수적으로 문턱을 높인다.
        macro = await self._macro_service.latest_regime()
        regime = macro.get("regime")
        aggressive = regime == "risk_off"

        tightened = tighten_conditions(version.conditions or [], aggressive=aggressive)
        if not tightened.changes:
            return None
        # 강화 결과가 기존과 동일하면(실제 변경 없음) 제안하지 않는다.
        if tightened.conditions == (version.conditions or []):
            return None

        base_reason = (
            f"최근 {count}건 후보의 {horizon_minutes}분 후 승률이 {win_rate}%로 "
            f"기준({WIN_RATE_THRESHOLD}%) 미만입니다."
        )
        macro_note = ""
        if regime in ("risk_off", "risk_on", "neutral"):
            macro_note = f" 전일 미국장 매크로 레짐은 '{regime}'입니다."
            if aggressive:
                macro_note += " 위험회피 국면이라 강화 폭을 더 키웠습니다."
        change_text = "; ".join(tightened.changes)

        return await self._proposal_service.create_proposal(
            scanner_rule_id=version.scanner_rule_id,
            suggested_conditions=tightened.conditions,
            title=f"스캐너 조건 강화 (v{version.version_no})",
            summary=f"진입 문턱을 높여 약한 신호를 줄입니다: {change_text}",
            rationale=f"{base_reason}{macro_note} 조건을 강화해 후보 품질을 높입니다.",
            expected_effect="후보 수 감소, 약한 신호 제거로 평균 후보 품질 개선 가능.",
            risk_notes="조건이 강해져 기회가 줄어들 수 있습니다. 새 버전으로 비교 검증이 필요합니다.",
            base_version_id=version_id,
            source="ai",
        )

    async def _is_drought(self, version_id: int) -> bool:
        """기근 = 최근 N일간 **스캔은 실제로 돌았는데** 이 버전의 후보가 0건.

        스캔 증거(research_pipeline 성공 실행)가 없으면 기근으로 보지 않는다 —
        시스템이 놀고 있었던 것과 조건이 너무 높은 것은 다른 문제다.
        """
        from datetime import datetime, timedelta, timezone  # noqa: PLC0415

        from sqlalchemy import func, select  # noqa: PLC0415

        from app.core.config import get_settings  # noqa: PLC0415
        from app.domain.models.candidate_event import CandidateEvent  # noqa: PLC0415
        from app.domain.models.enums import SchedulerRunStatus  # noqa: PLC0415
        from app.domain.models.scheduler_run import SchedulerRun  # noqa: PLC0415

        days = get_settings().scanner_drought_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        scans = (
            await self._session.execute(
                select(func.count())
                .select_from(SchedulerRun)
                .where(
                    SchedulerRun.job_id == "research_pipeline",
                    SchedulerRun.status == SchedulerRunStatus.SUCCESS,
                    SchedulerRun.started_at >= cutoff,
                )
            )
        ).scalar_one()
        if scans == 0:
            return False

        count = (
            await self._session.execute(
                select(func.count())
                .select_from(CandidateEvent)
                .where(
                    CandidateEvent.scanner_rule_version_id == version_id,
                    CandidateEvent.triggered_at >= cutoff,
                )
            )
        ).scalar_one()
        return count == 0

    async def _propose_loosening(self, version) -> ScannerRuleProposal | None:
        """후보 기근 상태의 버전에 조건 완화 제안을 만든다 (pending — 승인은 사람)."""
        from app.core.config import get_settings  # noqa: PLC0415

        loosened = loosen_conditions(version.conditions or [])
        if not loosened.changes:
            return None  # 이미 하한까지 완화됨 — 더 낮출 게 없다
        days = get_settings().scanner_drought_days
        change_text = "; ".join(loosened.changes)
        return await self._proposal_service.create_proposal(
            scanner_rule_id=version.scanner_rule_id,
            suggested_conditions=loosened.conditions,
            title=f"스캐너 조건 완화 — 후보 기근 (v{version.version_no})",
            summary=f"최근 {days}일 후보 0건 — 진입 문턱을 한 단계 낮춥니다: {change_text}",
            rationale=(
                f"이 버전은 최근 {days}일간 후보를 한 건도 포착하지 못했습니다. "
                "조건이 현 시장 수준보다 높게 강화되어 있어, 완화 없이는 후보·배정·실험 "
                "루프 전체가 재료 부족으로 멈춥니다."
            ),
            expected_effect="후보 발굴 재개 — 연구 루프에 재료 공급. 후보 품질은 다음 점검에서 재평가.",
            risk_notes="완화로 약한 신호가 늘 수 있습니다. 승인 후 승률이 낮아지면 자동 점검이 다시 강화를 제안합니다.",
            base_version_id=version.id,
            source="ai",
        )
