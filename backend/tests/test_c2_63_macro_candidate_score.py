"""C-2.63 매크로 레짐을 후보 점수에 반영 테스트."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import ScannerRuleStatus
from app.services.candidate_service import CandidateService
from app.services.scanner_service import ScannerService
from app.trading.scanner.macro_score import macro_score_adjustment


# --- 순수 함수 --------------------------------------------------------------
def test_risk_off_lowers_score() -> None:
    assert macro_score_adjustment(100, "risk_off", None, False) == 85
    assert macro_score_adjustment(100, "neutral", None, False) == 100
    assert macro_score_adjustment(100, "risk_on", None, False) == 100  # 105 → cap 100


def test_semis_boost_and_weak() -> None:
    # 80*1.05=84, *1.15=96.6 → round 97
    assert macro_score_adjustment(80, "risk_on", "strong", True) == 97
    assert macro_score_adjustment(80, "neutral", "weak", True) == 72  # 80*0.9


async def _seed_version(session) -> int:
    scanner = ScannerService(session)
    rule = await scanner.create_rule("macro-score")
    sv = await scanner.create_version(
        rule.id, conditions=[{"type": "volume_spike", "params": {"multiplier": 2.0}}],
        status=ScannerRuleStatus.TESTING,
    )
    return sv.id


async def test_scan_applies_macro_to_score(db_session: AsyncSession) -> None:
    sv_id = await _seed_version(db_session)
    facts = {"005930": {"volume_ratio": 3.0}}  # 조건 충족 → score 100
    result = await CandidateService(db_session).scan(
        sv_id, facts, macro={"regime": "risk_off", "semis_strength": "weak"},
    )
    assert result.matched == 1
    c = result.candidates[0]
    assert c.score == 85  # risk_off 하향
    assert c.facts["_base_score"] == 100
    assert c.facts["_macro_regime"] == "risk_off"


async def test_scan_without_macro_keeps_score(db_session: AsyncSession) -> None:
    sv_id = await _seed_version(db_session)
    result = await CandidateService(db_session).scan(sv_id, {"005930": {"volume_ratio": 3.0}})
    assert result.candidates[0].score == 100
