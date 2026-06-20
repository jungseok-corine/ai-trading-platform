"""C-2.56 LLM 출력(JSON) → 검증 → pending 제안 연결 테스트."""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.account import Account
from app.domain.models.enums import AccountType, OrderStatus, StrategyVersionStatus, TradeSide
from app.domain.models.enums import ProposalStatus
from app.domain.models.trade import Trade
from app.services.analysis_proposal_service import AnalysisProposalService
from app.services.proposal_service import ProposalService
from app.services.strategy_service import StrategyService
from app.trading.analysis.analysis_output import parse_analysis_output

_GOOD = """여기 분석입니다.
```json
{"verdict": "improve", "key_observations": ["매수 승률 9%"],
 "mistakes": ["VWAP 아래 매수"],
 "hypotheses": [{"hypothesis": "장기선 확대", "param_change": {"long_window": 30},
                 "confidence": 0.8, "rationale": "휩쏘 감소"}],
 "risk_notes": "기회 감소", "confidence": 0.7}
```
끝."""

_LOW_CONF = '{"verdict":"investigate","hypotheses":[{"hypothesis":"x","param_change":{"long_window":30},"confidence":0.2}],"confidence":0.2}'
_NO_PARAM = '{"verdict":"keep","hypotheses":[{"hypothesis":"유지","param_change":{},"confidence":0.9}],"confidence":0.9}'
_NOT_JSON = "JSON이 전혀 없는 자유 텍스트 응답."


# --- 순수 파서 --------------------------------------------------------------
def test_parse_extracts_json_from_codefence() -> None:
    out = parse_analysis_output(_GOOD)
    assert out is not None
    assert out.verdict == "improve"
    best = out.best_hypothesis(0.5)
    assert best is not None
    assert best.param_change == {"long_window": 30}


def test_parse_none_when_no_json() -> None:
    assert parse_analysis_output(_NOT_JSON) is None


def test_best_hypothesis_respects_confidence_and_param() -> None:
    assert parse_analysis_output(_LOW_CONF).best_hypothesis(0.5) is None  # 확신도 낮음
    assert parse_analysis_output(_NO_PARAM).best_hypothesis(0.5) is None  # param_change 없음


# --- 서비스: 텍스트 → 제안 --------------------------------------------------
async def _seed_version(session: AsyncSession) -> tuple[int, int]:
    account = Account(account_type=AccountType.PAPER, broker_account_no="00000000")
    session.add(account)
    await session.commit()
    svc = StrategyService(session)
    strategy = await svc.create_strategy("llm")
    version = await svc.create_version(
        strategy.id,
        parameters={"strategy_type": "moving_average_cross", "long_window": 20,
                    "symbol_code": "005930"},
        status=StrategyVersionStatus.TESTING,
    )
    session.add(Trade(account_id=account.id, strategy_version_id=version.id,
                      symbol_code="005930", side=TradeSide.BUY, quantity=1,
                      pnl_amount=Decimal("-10"), order_status=OrderStatus.FILLED))
    await session.commit()
    return strategy.id, version.id


async def test_create_proposal_from_good_output(db_session: AsyncSession) -> None:
    sid, vid = await _seed_version(db_session)
    proposal = await AnalysisProposalService(db_session).create_from_text(
        sid, vid, _GOOD, ai_analysis_run_id=None, min_confidence=0.5
    )
    assert proposal is not None
    assert proposal.status == ProposalStatus.PENDING
    assert proposal.suggested_parameters["long_window"] == 30
    assert proposal.suggested_parameters["strategy_type"] == "moving_average_cross"  # 보존
    assert proposal.source == "ai_llm"


async def test_no_proposal_when_low_confidence_or_no_json(db_session: AsyncSession) -> None:
    sid, vid = await _seed_version(db_session)
    svc = AnalysisProposalService(db_session)
    assert await svc.create_from_text(sid, vid, _LOW_CONF) is None
    assert await svc.create_from_text(sid, vid, _NOT_JSON) is None
    # 제안이 하나도 안 생겼는지
    assert await ProposalService(db_session).list_proposals(status=ProposalStatus.PENDING) == []


async def test_invalid_strategy_type_rejected(db_session: AsyncSession) -> None:
    sid, vid = await _seed_version(db_session)
    # 모델이 strategy_type을 미등록 값으로 바꾸려 하면 검증에서 걸러 None.
    bad = ('{"verdict":"improve","confidence":0.9,'
           '"hypotheses":[{"hypothesis":"교체","param_change":{"strategy_type":"bogus"},'
           '"confidence":0.9}]}')
    assert await AnalysisProposalService(db_session).create_from_text(sid, vid, bad) is None
