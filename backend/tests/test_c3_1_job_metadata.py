"""C-3.1 자율 잡 위험도/특성 메타데이터 (read-only, 표시 전용).

검증:
- 모든 CONTROLLABLE_JOBS에 메타데이터가 존재한다.
- risk_level / recommended_state가 허용 enum 중 하나다.
- 모든 controllable job은 기본 비활성(env 기본값 False)이다.
- 모든 controllable job은 live trading/order/broker capability가 False다
  (affects_live_trading=False, action_taking=False).
- 분류가 분석 결과와 일치한다(SAFE_ON / MANUAL_FIRST / KEEP_OFF).
- KEEP_OFF 잡은 uses_llm / creates_proposals / cost_risk 중 하나 이상이 True다.
- SAFE_ON 잡은 uses_llm=False, creates_proposals=False다.
- 서비스(list_jobs) 응답에 메타데이터가 포함된다(=API가 직렬화하는 값).
"""
import types

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.scheduler.registry import CONTROLLABLE_JOBS
from app.services.scheduler_control_service import SchedulerControlService

_RISK_LEVELS = {"SAFE_ON", "MANUAL_FIRST", "KEEP_OFF", "DO_NOT_ENABLE"}
_RECOMMENDED = {"ON_OK", "MANUAL_FIRST", "KEEP_OFF"}

# 분석(C 사전분석)에서 합의된 분류 — 회귀 가드.
_EXPECTED_RISK = {
    "operations_digest": "SAFE_ON",
    "daily_report": "SAFE_ON",
    "data_refresh": "MANUAL_FIRST",
    "us_market_refresh": "MANUAL_FIRST",
    "dart_ingest": "MANUAL_FIRST",
    "edgar_ingest": "MANUAL_FIRST",
    "dart_finance": "MANUAL_FIRST",
    "intelligence_ingest": "MANUAL_FIRST",
    "intelligence_discovery": "MANUAL_FIRST",
    "intraday_event_monitor": "MANUAL_FIRST",
    "research_pipeline": "MANUAL_FIRST",
    "intelligence_experiment_autopilot": "MANUAL_FIRST",
    "paper_signal_session_runner": "MANUAL_FIRST",
    "daily_analysis": "KEEP_OFF",
    "scanner_review": "KEEP_OFF",
    "strategy_review": "KEEP_OFF",
    "intelligence_scanner_proposal": "KEEP_OFF",
    "intelligence_evolution": "KEEP_OFF",
}


def test_all_jobs_have_metadata() -> None:
    for j in CONTROLLABLE_JOBS:
        assert j.description, f"{j.job_id}: description 비어있음"
        assert j.risk_level in _RISK_LEVELS, f"{j.job_id}: 잘못된 risk_level {j.risk_level!r}"
        assert j.recommended_state in _RECOMMENDED, (
            f"{j.job_id}: 잘못된 recommended_state {j.recommended_state!r}"
        )
        assert isinstance(j.safety_notes, tuple)


def test_classification_matches_analysis() -> None:
    actual = {j.job_id: j.risk_level for j in CONTROLLABLE_JOBS}
    assert actual == _EXPECTED_RISK


def test_no_job_affects_live_trading() -> None:
    for j in CONTROLLABLE_JOBS:
        assert j.affects_live_trading is False, f"{j.job_id}: affects_live_trading must be False"
        assert j.action_taking is False, f"{j.job_id}: action_taking must be False (no approve/ACTIVE/order)"


def test_all_jobs_default_disabled() -> None:
    settings = get_settings()
    for j in CONTROLLABLE_JOBS:
        assert j.env_enabled(settings) is False, f"{j.job_id}: 기본 비활성이어야 함"


def test_keep_off_jobs_have_risk_flag() -> None:
    for j in CONTROLLABLE_JOBS:
        if j.risk_level == "KEEP_OFF":
            assert j.uses_llm or j.creates_proposals or j.cost_risk, (
                f"{j.job_id}: KEEP_OFF인데 위험 플래그(uses_llm/creates_proposals/cost_risk)가 없음"
            )


def test_safe_on_jobs_are_low_risk() -> None:
    for j in CONTROLLABLE_JOBS:
        if j.risk_level == "SAFE_ON":
            assert j.uses_llm is False, f"{j.job_id}: SAFE_ON인데 uses_llm=True"
            assert j.creates_proposals is False, f"{j.job_id}: SAFE_ON인데 creates_proposals=True"
            assert j.cost_risk is False, f"{j.job_id}: SAFE_ON인데 cost_risk=True"


def test_experiment_autopilot_is_paper_action_only() -> None:
    j = next(x for x in CONTROLLABLE_JOBS if x.job_id == "intelligence_experiment_autopilot")
    assert j.paper_action is True
    assert j.action_taking is False
    assert j.affects_live_trading is False


@pytest.mark.asyncio
async def test_list_jobs_includes_metadata(db_session: AsyncSession) -> None:
    app = types.SimpleNamespace(state=types.SimpleNamespace())
    jobs = await SchedulerControlService(db_session).list_jobs(app, get_settings())
    assert jobs, "list_jobs가 비어있음"
    by_id = {j.job_id: j for j in jobs}
    # 메타데이터가 서비스 응답(=API 직렬화 대상)에 실린다.
    da = by_id["daily_analysis"]
    assert da.risk_level == "KEEP_OFF"
    assert da.uses_llm is True and da.cost_risk is True
    assert da.affects_live_trading is False
    assert da.description
    od = by_id["operations_digest"]
    assert od.risk_level == "SAFE_ON" and od.recommended_state == "ON_OK"
    # 모든 잡에 메타 필드가 채워져 있다.
    for j in jobs:
        assert j.risk_level in _RISK_LEVELS
        assert isinstance(j.safety_notes, list)
