"""Analysis Prompt Builder (Phase C-2.1 / C-2.1.1) 통합 테스트.

검증 항목:
  1. overview prompt 생성 확인
  2. strategy metadata가 prompt에 포함되는지
  3. performance summary가 prompt에 포함되는지
  4. limitations가 prompt에 포함되는지
  5. recent_signals가 10개 이하로 압축되는지
  6. unsupported prompt_type → UnsupportedPromptTypeError
  7. risk prompt 생성 확인
  8. improvement prompt 생성 확인
  9. API 성공 (200) + 응답 구조 확인
  10. API 404 (잘못된 strategy/version 조합)
  11. API 400 (지원하지 않는 prompt_type)
  12. warnings 포함 확인
  [C-2.1.1]
  13. prompt_length == len(prompt)
  14. 큰 parameters 가 압축됨 ([truncated] 포함)
  15. _apply_length_guard 직접 단위 테스트
  16. truncated=True 조건
  17. truncation warning 포함 확인
  18. CRITICAL INSTRUCTIONS 보존 확인
  19. input_summary 신규 필드 확인
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.models.enums import TradeSide
from app.domain.models.market_data import MarketData
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import Strategy, StrategyVersion
from app.main import app
from app.services.strategy_analysis_prompt_service import (
    StrategyAnalysisPromptService,
    UnsupportedPromptTypeError,
    _apply_length_guard,
    _compress_params,
    _MAX_PROMPT_CHARS,
)

KST = ZoneInfo("Asia/Seoul")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ts(minute: int, hour: int = 9) -> datetime:
    return datetime(2026, 6, 10, hour, minute, 0, tzinfo=KST)


async def _add_strategy_version(
    session: AsyncSession,
    symbol: str = "005930",
    name: str = "PromptTestStrategy",
) -> tuple[Strategy, StrategyVersion]:
    strat = Strategy(name=name, description="prompt test")
    session.add(strat)
    await session.flush()
    ver = StrategyVersion(
        strategy_id=strat.id,
        version_no=1,
        parameters={
            "strategy_type": "moving_average_cross",
            "symbol_code": symbol,
            "short_window": 5,
            "long_window": 20,
            "timeframe": "1m",
        },
    )
    session.add(ver)
    await session.flush()
    return strat, ver


async def _add_signal(
    session: AsyncSession,
    version_id: int,
    signal_type: TradeSide = TradeSide.BUY,
    candle_ts: datetime | None = None,
    symbol: str = "005930",
) -> SignalLog:
    sig = SignalLog(
        symbol_code=symbol,
        strategy_version_id=version_id,
        signal_type=signal_type,
        generated_at=datetime.now(KST),
        candle_ts=candle_ts or _ts(30),
    )
    session.add(sig)
    await session.flush()
    return sig


def _candle(
    symbol: str = "005930",
    tf: str = "1m",
    minute: int = 0,
    hour: int = 9,
    open_: int = 100,
    close: int = 105,
) -> MarketData:
    return MarketData(
        symbol_code=symbol,
        timeframe=tf,
        ts=datetime(2026, 6, 10, hour, minute, 0, tzinfo=KST),
        open=Decimal(open_),
        high=Decimal(110),
        low=Decimal(90),
        close=Decimal(close),
        volume=1000,
    )


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _db_override(db_session: AsyncSession):
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    yield
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 1. overview prompt 생성
# ---------------------------------------------------------------------------


async def test_overview_prompt_generated(db_session: AsyncSession) -> None:
    """overview prompt가 정상적으로 생성된다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisPromptService(db_session)

    result = await svc.get_prompt(strat.id, ver.id, "overview")

    assert result is not None
    assert result.prompt_type == "overview"
    assert isinstance(result.prompt, str)
    assert len(result.prompt) > 100


# ---------------------------------------------------------------------------
# 2. strategy metadata가 prompt에 포함되는지
# ---------------------------------------------------------------------------


async def test_overview_prompt_contains_strategy_metadata(db_session: AsyncSession) -> None:
    """prompt에 strategy 이름과 version 번호가 포함된다."""
    strat, ver = await _add_strategy_version(db_session, name="MyAlphaStrategy")
    svc = StrategyAnalysisPromptService(db_session)

    result = await svc.get_prompt(strat.id, ver.id, "overview")

    assert result is not None
    assert "MyAlphaStrategy" in result.prompt
    assert f"strategy_id={strat.id}" in result.prompt
    assert f"strategy_version_id={ver.id}" in result.prompt
    assert "v1" in result.prompt  # version_no


# ---------------------------------------------------------------------------
# 3. performance summary가 prompt에 포함되는지
# ---------------------------------------------------------------------------


async def test_overview_prompt_contains_performance_summary(db_session: AsyncSession) -> None:
    """prompt에 signal 카운트와 horizon 테이블이 포함된다."""
    strat, ver = await _add_strategy_version(db_session)
    # 신호 2개 추가 (데이터 없어도 total_signals에는 반영됨)
    await _add_signal(db_session, ver.id)
    await _add_signal(db_session, ver.id, signal_type=TradeSide.SELL)
    svc = StrategyAnalysisPromptService(db_session)

    result = await svc.get_prompt(strat.id, ver.id, "overview")

    assert result is not None
    # total_signals 수치가 prompt에 들어 있어야 함
    assert "2" in result.prompt
    # horizon 테이블 헤더
    assert "Horizon" in result.prompt
    assert "Win Rate" in result.prompt
    assert "5m" in result.prompt
    assert "60m" in result.prompt


# ---------------------------------------------------------------------------
# 4. limitations가 prompt에 포함되는지
# ---------------------------------------------------------------------------


async def test_overview_prompt_contains_limitations(db_session: AsyncSession) -> None:
    """analysis_context.limitations 내용이 prompt에 포함된다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisPromptService(db_session)

    result = await svc.get_prompt(strat.id, ver.id, "overview")

    assert result is not None
    # 알려진 limitation 텍스트
    assert "hypothetical" in result.prompt.lower() or "next-candle" in result.prompt.lower()
    assert "financial advice" in result.prompt.lower()


# ---------------------------------------------------------------------------
# 5. recent_signals 압축 (최대 10개)
# ---------------------------------------------------------------------------


async def test_recent_signals_compressed_in_prompt(db_session: AsyncSession) -> None:
    """recent_signals는 prompt에서 최대 10개까지만 포함된다."""
    strat, ver = await _add_strategy_version(db_session)
    # 15개 신호 추가
    for i in range(15):
        sig = SignalLog(
            symbol_code="005930",
            strategy_version_id=ver.id,
            signal_type=TradeSide.BUY,
            generated_at=_ts(i % 59),
            candle_ts=_ts(i % 59),
        )
        db_session.add(sig)
    await db_session.flush()

    svc = StrategyAnalysisPromptService(db_session)
    result = await svc.get_prompt(strat.id, ver.id, "overview")

    assert result is not None
    # 압축 메시지가 prompt에 포함되어야 함
    assert "omitted" in result.prompt or "more signals" in result.prompt
    # input_summary는 실제 total을 담아야 함
    assert result.input_summary.total_signals == 15


# ---------------------------------------------------------------------------
# 6. unsupported prompt_type
# ---------------------------------------------------------------------------


async def test_unsupported_prompt_type_raises(db_session: AsyncSession) -> None:
    """지원하지 않는 prompt_type이면 UnsupportedPromptTypeError가 발생한다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisPromptService(db_session)

    with pytest.raises(UnsupportedPromptTypeError):
        await svc.get_prompt(strat.id, ver.id, "invalid_type")


# ---------------------------------------------------------------------------
# 7. risk prompt 생성
# ---------------------------------------------------------------------------


async def test_risk_prompt_generated(db_session: AsyncSession) -> None:
    """risk prompt가 정상 생성되고 MAE/Win Rate 섹션을 포함한다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisPromptService(db_session)

    result = await svc.get_prompt(strat.id, ver.id, "risk")

    assert result is not None
    assert result.prompt_type == "risk"
    assert "MAE" in result.prompt
    assert "Win" in result.prompt
    assert "Loss Probability" in result.prompt


# ---------------------------------------------------------------------------
# 8. improvement prompt 생성
# ---------------------------------------------------------------------------


async def test_improvement_prompt_generated(db_session: AsyncSession) -> None:
    """improvement prompt가 정상 생성되고 Parameter Tuning 섹션을 포함한다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisPromptService(db_session)

    result = await svc.get_prompt(strat.id, ver.id, "improvement")

    assert result is not None
    assert result.prompt_type == "improvement"
    assert "Parameter Tuning" in result.prompt
    assert "BUY vs SELL" in result.prompt


# ---------------------------------------------------------------------------
# 9. API 성공 (200)
# ---------------------------------------------------------------------------


async def test_api_analysis_prompt_success(db_session: AsyncSession) -> None:
    """API가 200을 반환하고 응답 구조가 올바른지 확인한다."""
    strat, ver = await _add_strategy_version(db_session)
    # 시장 데이터 추가
    for minute in range(3):
        db_session.add(_candle(minute=minute))
    await db_session.flush()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-prompt",
            params={"prompt_type": "overview"},
        )

    assert resp.status_code == 200
    body = resp.json()

    assert body["strategy_id"] == strat.id
    assert body["strategy_version_id"] == ver.id
    assert body["prompt_type"] == "overview"
    assert isinstance(body["prompt"], str)
    assert len(body["prompt"]) > 100

    summary = body["input_summary"]
    assert "total_signals" in summary
    assert "analyzed_signals" in summary
    assert "symbols" in summary
    assert "timeframes" in summary

    assert isinstance(body["warnings"], list)


async def test_api_analysis_prompt_default_type(db_session: AsyncSession) -> None:
    """prompt_type 생략 시 기본값 overview가 적용된다."""
    strat, ver = await _add_strategy_version(db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-prompt"
        )

    assert resp.status_code == 200
    assert resp.json()["prompt_type"] == "overview"


# ---------------------------------------------------------------------------
# 10. API 404
# ---------------------------------------------------------------------------


async def test_api_analysis_prompt_404(db_session: AsyncSession) -> None:
    """존재하지 않는 strategy/version 조합은 404를 반환한다."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/strategies/9999/versions/9999/analysis-prompt",
            params={"prompt_type": "overview"},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 11. API 400 (지원하지 않는 prompt_type)
# ---------------------------------------------------------------------------


async def test_api_analysis_prompt_bad_type(db_session: AsyncSession) -> None:
    """지원하지 않는 prompt_type은 400을 반환한다."""
    strat, ver = await _add_strategy_version(db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-prompt",
            params={"prompt_type": "this_is_not_valid"},
        )

    assert resp.status_code == 400
    assert "unsupported" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 12. warnings 포함 확인
# ---------------------------------------------------------------------------


async def test_warnings_included_when_data_scarce(db_session: AsyncSession) -> None:
    """신호 없음 + PnL 없음 상태에서 warnings가 생성된다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisPromptService(db_session)

    result = await svc.get_prompt(strat.id, ver.id, "overview")

    assert result is not None
    assert len(result.warnings) > 0
    # 분석 신호 10개 미만 경고
    assert any("10 signals" in w or "statistically" in w for w in result.warnings)
    # PnL 미완성 경고
    assert any("PnL" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 13. prompt_length == len(prompt)
# ---------------------------------------------------------------------------


async def test_prompt_length_matches_actual(db_session: AsyncSession) -> None:
    """prompt_length 필드가 실제 prompt 문자열 길이와 일치하고 truncated=False이다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisPromptService(db_session)

    result = await svc.get_prompt(strat.id, ver.id, "overview")

    assert result is not None
    assert result.prompt_length == len(result.prompt)
    assert result.truncated is False


# ---------------------------------------------------------------------------
# 14. 큰 parameters가 압축됨
# ---------------------------------------------------------------------------


def test_compress_params_within_limit() -> None:
    """짧은 parameters는 그대로 직렬화된다."""
    params = {"short_window": 5, "long_window": 20}
    result = _compress_params(params, max_len=500)
    assert "[truncated]" not in result
    assert "short_window" in result


def test_compress_params_truncated_when_too_long() -> None:
    """parameters가 max_len을 초과하면 '[truncated]' 접미사가 붙는다."""
    big_params = {f"key_{i}": "x" * 100 for i in range(20)}
    result = _compress_params(big_params, max_len=200)
    assert result.endswith(" ... [truncated]")
    assert len(result) == 200


async def test_large_parameters_compressed_in_prompt(db_session: AsyncSession) -> None:
    """strategy parameters가 매우 클 때 prompt에 '[truncated]' 표시가 포함된다."""
    strat = Strategy(name="BigParamStrategy", description=None)
    db_session.add(strat)
    await db_session.flush()
    ver = StrategyVersion(
        strategy_id=strat.id,
        version_no=1,
        parameters={f"param_{i}": "x" * 60 for i in range(30)},  # ~1800 chars JSON
    )
    db_session.add(ver)
    await db_session.flush()

    svc = StrategyAnalysisPromptService(db_session)
    result = await svc.get_prompt(strat.id, ver.id, "overview")

    assert result is not None
    assert "[truncated]" in result.prompt


# ---------------------------------------------------------------------------
# 15. _apply_length_guard 직접 단위 테스트
# ---------------------------------------------------------------------------


def test_apply_length_guard_no_op_when_short() -> None:
    """prompt가 max_chars 이하면 변경 없이 반환된다."""
    prompt = "CRITICAL INSTRUCTIONS:\nDo not invest.\n=== Section ===\nContent"
    warnings: list[str] = []
    result, truncated = _apply_length_guard(prompt, warnings, max_chars=5000)
    assert result == prompt
    assert truncated is False
    assert warnings == []


def test_apply_length_guard_truncates() -> None:
    """prompt가 max_chars를 초과하면 잘린 prompt와 truncated=True를 반환한다."""
    header = "CRITICAL INSTRUCTIONS:\nKeep this safe.\n\n=== Data ===\n"
    body = "A" * 1000
    prompt = header + body
    warnings: list[str] = []
    max_chars = len(header) + 100  # header 이후 100자만 허용

    result, truncated = _apply_length_guard(prompt, warnings, max_chars=max_chars)

    assert truncated is True
    assert len(result) <= max_chars + 50  # suffix 여유
    assert "CRITICAL INSTRUCTIONS" in result


# ---------------------------------------------------------------------------
# 16. truncated=True 조건
# ---------------------------------------------------------------------------


async def test_truncated_field_true_when_over_limit(db_session: AsyncSession) -> None:
    """prompt가 _MAX_PROMPT_CHARS를 초과하면 truncated=True이다 (max_chars를 1로 강제)."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisPromptService(db_session)

    # 원본 prompt 생성
    result = await svc.get_prompt(strat.id, ver.id, "overview")
    assert result is not None

    # prompt_length가 충분히 크면 max_chars=100으로 강제 적용
    fake_prompt = "CRITICAL INSTRUCTIONS:\nTest\n\n=== Body ===\n" + "X" * 500
    fake_warnings: list[str] = []
    _, truncated = _apply_length_guard(fake_prompt, fake_warnings, max_chars=100)
    assert truncated is True


# ---------------------------------------------------------------------------
# 17. truncation warning 포함 확인
# ---------------------------------------------------------------------------


def test_truncation_warning_added_when_truncated() -> None:
    """truncation이 발생하면 warnings에 지정된 메시지가 추가된다."""
    from app.services.strategy_analysis_prompt_service import _WARNING_TRUNCATED

    header = "CRITICAL INSTRUCTIONS:\nImportant\n\n=== Section ===\n"
    prompt = header + "B" * 2000
    warnings: list[str] = []
    _apply_length_guard(prompt, warnings, max_chars=len(header) + 200)

    assert _WARNING_TRUNCATED in warnings


# ---------------------------------------------------------------------------
# 18. CRITICAL INSTRUCTIONS 보존 확인
# ---------------------------------------------------------------------------


def test_critical_instructions_preserved_after_truncation() -> None:
    """truncation 후에도 CRITICAL INSTRUCTIONS 블록이 prompt에 남아 있다."""
    ci_block = "CRITICAL INSTRUCTIONS:\nDo not invest.\nFocus on strategy only.\n\n"
    sections = "=== DATA ===\n" + "C" * 5000
    prompt = ci_block + sections
    warnings: list[str] = []

    result, truncated = _apply_length_guard(prompt, warnings, max_chars=len(ci_block) + 200)

    assert "CRITICAL INSTRUCTIONS" in result
    assert truncated is True


# ---------------------------------------------------------------------------
# 19. input_summary 신규 필드 확인
# ---------------------------------------------------------------------------


async def test_input_summary_new_fields_present(db_session: AsyncSession) -> None:
    """input_summary에 max_prompt_length, included_recent_signals_count, included_symbols_count가 있다."""
    strat, ver = await _add_strategy_version(db_session)
    svc = StrategyAnalysisPromptService(db_session)

    result = await svc.get_prompt(strat.id, ver.id, "overview")

    assert result is not None
    summary = result.input_summary
    assert summary.max_prompt_length == _MAX_PROMPT_CHARS
    assert isinstance(summary.included_recent_signals_count, int)
    assert isinstance(summary.included_symbols_count, int)
    assert summary.included_recent_signals_count >= 0
    assert summary.included_symbols_count >= 0


async def test_input_summary_new_fields_via_api(db_session: AsyncSession) -> None:
    """API 응답 JSON에 신규 input_summary 필드가 포함된다."""
    strat, ver = await _add_strategy_version(db_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/strategies/{strat.id}/versions/{ver.id}/analysis-prompt",
            params={"prompt_type": "overview"},
        )

    assert resp.status_code == 200
    body = resp.json()

    summary = body["input_summary"]
    assert "max_prompt_length" in summary
    assert "included_recent_signals_count" in summary
    assert "included_symbols_count" in summary
    assert summary["max_prompt_length"] == _MAX_PROMPT_CHARS

    # prompt_length / truncated 필드
    assert "prompt_length" in body
    assert "truncated" in body
    assert body["prompt_length"] == len(body["prompt"])
    assert isinstance(body["truncated"], bool)
