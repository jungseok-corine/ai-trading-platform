"""AI Analysis Provider Abstraction (Phase C-2.3) 테스트.

검증 항목:
  1. FakeAnalysisProvider.analyze() 성공
  2. result 타입 및 provider 필드
  3. token usage 필드 (prompt/completion/total)
  4. latency_ms 필드 존재
  5. finish_reason 필드
  6. raw 필드 구조
  7. determinism — 동일 prompt → 동일 content
  8. 다른 prompt → 다른 content (hash 포함 확인)
  9. model 인자 override
  10. provider factory — fake 반환
  11. provider factory — openai (미구현) → ProviderNotImplementedError
  12. provider factory — anthropic (미구현) → ProviderNotImplementedError
  13. provider factory — 알 수 없는 이름 → UnknownProviderError
  14. AnalysisProviderError 구조 (provider/message/retryable/status_code/raw)
  15. AnalysisProviderError retryable=True/False 구분
  16. AnalysisProvider ABC — 직접 인스턴스화 불가 확인
  17. 설정에 ai_default_provider / ai_default_model 포함 확인
"""
import pytest

from app.core.config import get_settings
from app.services.ai_analysis import (
    AnalysisProviderError,
    AnalysisProviderResult,
    ProviderNotImplementedError,
    UnknownProviderError,
    get_analysis_provider,
)
from app.services.ai_analysis.base import AnalysisProvider
from app.services.ai_analysis.fake import FakeAnalysisProvider


# ---------------------------------------------------------------------------
# 1. FakeAnalysisProvider.analyze() 성공
# ---------------------------------------------------------------------------


async def test_fake_provider_analyze_returns_result() -> None:
    """FakeAnalysisProvider.analyze()가 AnalysisProviderResult를 반환한다."""
    provider = FakeAnalysisProvider()
    result = await provider.analyze("Test prompt")
    assert isinstance(result, AnalysisProviderResult)


# ---------------------------------------------------------------------------
# 2. result 타입 및 provider 필드
# ---------------------------------------------------------------------------


async def test_fake_provider_result_fields() -> None:
    """result.provider == 'fake', result.model == 'fake-1.0', content는 비어있지 않음."""
    provider = FakeAnalysisProvider()
    result = await provider.analyze("Some analysis prompt")
    assert result.provider == "fake"
    assert result.model == "fake-1.0"
    assert isinstance(result.content, str)
    assert len(result.content) > 0


# ---------------------------------------------------------------------------
# 3. token usage 필드
# ---------------------------------------------------------------------------


async def test_fake_provider_token_usage() -> None:
    """prompt_tokens, completion_tokens, total_tokens가 모두 양수이고 합계가 맞다."""
    provider = FakeAnalysisProvider()
    result = await provider.analyze("Hello world this is a test prompt with multiple words")
    assert result.prompt_tokens is not None
    assert result.completion_tokens is not None
    assert result.total_tokens is not None
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
    assert result.total_tokens == result.prompt_tokens + result.completion_tokens


# ---------------------------------------------------------------------------
# 4. latency_ms 필드
# ---------------------------------------------------------------------------


async def test_fake_provider_latency_ms() -> None:
    """latency_ms가 None이 아닌 양수 값이다."""
    provider = FakeAnalysisProvider()
    result = await provider.analyze("latency test")
    assert result.latency_ms is not None
    assert result.latency_ms > 0


# ---------------------------------------------------------------------------
# 5. finish_reason 필드
# ---------------------------------------------------------------------------


async def test_fake_provider_finish_reason() -> None:
    """finish_reason이 'stop'이다."""
    provider = FakeAnalysisProvider()
    result = await provider.analyze("finish reason test")
    assert result.finish_reason == "stop"


# ---------------------------------------------------------------------------
# 6. raw 필드 구조
# ---------------------------------------------------------------------------


async def test_fake_provider_raw_field() -> None:
    """raw 필드가 dict이고 provider/model/fake 키를 포함한다."""
    provider = FakeAnalysisProvider()
    result = await provider.analyze("raw field test")
    assert isinstance(result.raw, dict)
    assert result.raw.get("provider") == "fake"
    assert result.raw.get("fake") is True
    assert "model" in result.raw


# ---------------------------------------------------------------------------
# 7. determinism — 동일 prompt → 동일 content
# ---------------------------------------------------------------------------


async def test_fake_provider_deterministic_same_prompt() -> None:
    """동일한 prompt에 대해 항상 동일한 content를 반환한다."""
    provider = FakeAnalysisProvider()
    prompt = "Analyze strategy performance for version 42"
    result_a = await provider.analyze(prompt)
    result_b = await provider.analyze(prompt)
    assert result_a.content == result_b.content
    assert result_a.raw == result_b.raw


# ---------------------------------------------------------------------------
# 8. 다른 prompt → 다른 content
# ---------------------------------------------------------------------------


async def test_fake_provider_different_prompts_differ() -> None:
    """서로 다른 prompt는 서로 다른 content를 반환한다."""
    provider = FakeAnalysisProvider()
    result_a = await provider.analyze("Prompt one: strategy A analysis")
    result_b = await provider.analyze("Prompt two: completely different content xyz")
    assert result_a.content != result_b.content


# ---------------------------------------------------------------------------
# 9. model 인자 override
# ---------------------------------------------------------------------------


async def test_fake_provider_model_override() -> None:
    """model 인자를 지정하면 result.model에 반영된다."""
    provider = FakeAnalysisProvider()
    result = await provider.analyze("test prompt", model="custom-model-v99")
    assert result.model == "custom-model-v99"


async def test_fake_provider_default_model_when_none() -> None:
    """model=None이면 provider 기본 모델이 사용된다."""
    provider = FakeAnalysisProvider()
    result = await provider.analyze("test prompt", model=None)
    assert result.model == provider.default_model()


# ---------------------------------------------------------------------------
# 10. factory — fake 반환
# ---------------------------------------------------------------------------


def test_factory_returns_fake_provider() -> None:
    """get_analysis_provider('fake')는 FakeAnalysisProvider를 반환한다."""
    provider = get_analysis_provider("fake")
    assert isinstance(provider, FakeAnalysisProvider)
    assert provider.provider_name() == "fake"


def test_factory_returns_analysis_provider_subclass() -> None:
    """반환된 객체는 AnalysisProvider의 서브클래스다."""
    provider = get_analysis_provider("fake")
    assert isinstance(provider, AnalysisProvider)


# ---------------------------------------------------------------------------
# 11. factory — openai (미구현)
# ---------------------------------------------------------------------------


def test_factory_openai_not_implemented() -> None:
    """get_analysis_provider('openai')는 ProviderNotImplementedError를 발생시킨다."""
    with pytest.raises(ProviderNotImplementedError) as exc_info:
        get_analysis_provider("openai")
    assert exc_info.value.provider_name == "openai"
    assert "openai" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 12. factory — anthropic (미구현)
# ---------------------------------------------------------------------------


def test_factory_anthropic_not_implemented() -> None:
    """get_analysis_provider('anthropic')는 ProviderNotImplementedError를 발생시킨다."""
    with pytest.raises(ProviderNotImplementedError) as exc_info:
        get_analysis_provider("anthropic")
    assert exc_info.value.provider_name == "anthropic"


# ---------------------------------------------------------------------------
# 13. factory — 알 수 없는 이름
# ---------------------------------------------------------------------------


def test_factory_unknown_provider() -> None:
    """알 수 없는 provider 이름은 UnknownProviderError를 발생시킨다."""
    with pytest.raises(UnknownProviderError) as exc_info:
        get_analysis_provider("gpt-banana")
    assert exc_info.value.provider_name == "gpt-banana"
    assert "gpt-banana" in str(exc_info.value)


def test_factory_empty_string_raises() -> None:
    """빈 문자열도 UnknownProviderError를 발생시킨다."""
    with pytest.raises(UnknownProviderError):
        get_analysis_provider("")


# ---------------------------------------------------------------------------
# 14. AnalysisProviderError 구조
# ---------------------------------------------------------------------------


def test_analysis_provider_error_fields() -> None:
    """AnalysisProviderError의 모든 필드가 올바르게 저장된다."""
    err = AnalysisProviderError(
        provider="openai",
        message="Rate limit exceeded",
        retryable=True,
        status_code=429,
        raw={"error": {"type": "rate_limit_error"}},
    )
    assert err.provider == "openai"
    assert err.message == "Rate limit exceeded"
    assert err.retryable is True
    assert err.status_code == 429
    assert err.raw is not None
    assert err.raw["error"]["type"] == "rate_limit_error"


def test_analysis_provider_error_is_exception() -> None:
    """AnalysisProviderError는 Exception을 상속한다."""
    err = AnalysisProviderError(provider="fake", message="test error")
    assert isinstance(err, Exception)
    assert str(err) == "test error"


def test_analysis_provider_error_optional_fields_default() -> None:
    """status_code와 raw는 기본값 None이다."""
    err = AnalysisProviderError(provider="anthropic", message="timeout")
    assert err.status_code is None
    assert err.raw is None


# ---------------------------------------------------------------------------
# 15. AnalysisProviderError retryable 구분
# ---------------------------------------------------------------------------


def test_analysis_provider_error_retryable_true() -> None:
    """retryable=True: 429, 5xx 같은 일시적 오류."""
    err = AnalysisProviderError(
        provider="openai", message="server error", retryable=True, status_code=500
    )
    assert err.retryable is True


def test_analysis_provider_error_retryable_false() -> None:
    """retryable=False: 400 같은 영구적 오류."""
    err = AnalysisProviderError(
        provider="anthropic", message="invalid prompt", retryable=False, status_code=400
    )
    assert err.retryable is False


# ---------------------------------------------------------------------------
# 16. AnalysisProvider ABC — 직접 인스턴스화 불가
# ---------------------------------------------------------------------------


def test_analysis_provider_abc_cannot_instantiate() -> None:
    """AnalysisProvider는 추상 클래스이므로 직접 인스턴스화할 수 없다."""
    with pytest.raises(TypeError):
        AnalysisProvider()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# 17. 설정 — ai_default_provider / ai_default_model
# ---------------------------------------------------------------------------


def test_settings_ai_default_provider() -> None:
    """Settings에 ai_default_provider 필드가 있고 기본값이 'fake'다."""
    settings = get_settings()
    assert hasattr(settings, "ai_default_provider")
    assert settings.ai_default_provider == "fake"


def test_settings_ai_default_model() -> None:
    """Settings에 ai_default_model 필드가 있고 기본값이 'fake-1.0'다."""
    settings = get_settings()
    assert hasattr(settings, "ai_default_model")
    assert settings.ai_default_model == "fake-1.0"
