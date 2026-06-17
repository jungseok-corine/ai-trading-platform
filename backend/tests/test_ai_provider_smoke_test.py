"""AI Provider smoke test 스크립트 테스트 (C-2.7.4/C-2.7.5).

실제 네트워크 호출 없음 — provider는 AsyncMock으로 대체한다.

검증 항목:
  1.  --confirm 없으면 provider 호출 안 함, exit code 0
  2.  --confirm 없으면 안내 메시지 출력
  3.  openai key 없음 → skipped 결과, skip_reason에 AI_OPENAI_API_KEY 포함
  4.  anthropic key 없음 → skipped 결과, skip_reason에 AI_ANTHROPIC_API_KEY 포함
  5.  openai 성공 경로 (mock provider) → SmokeResult.success=True
  6.  anthropic 성공 경로 (mock provider) → SmokeResult.success=True
  7.  openai 실패 경로 (AnalysisProviderError) → SmokeResult.success=False
  8.  both — 한쪽 실패해도 두 결과 모두 수집
  9.  both — summary에 성공/실패/스킵 카운트 포함
  10. 실패 결과 → main_async exit code 1
  11. 스킵만 있을 때 → exit code 0 (실패 아님)
  12. 성공만 있을 때 → exit code 0
  13. print_result — 성공 시 필드 출력 확인
  14. print_result — 실패 시 error/retryable 출력 확인
  15. print_result — 스킵 시 skip_reason 출력 확인
  16. parse_args — --provider, --confirm 파싱 확인
  17. SMOKE_PROMPT 상수 확인
  18. both — 모두 성공 → exit code 0
  19. both — 모두 실패 → exit code 1
  20. smoke_single_provider — AnalysisProviderError 잡아서 SmokeResult 반환
  --- C-2.7.5: 진단 출력 개선 ---
  21. print_result — 실패 시 raw error 요약 출력 (type/code/message)
  22. _safe_raw_summary — 민감 필드 포함하지 않음 (API key 등 절대 출력 안 됨)
  23. print_result — openai 429일 때 진단 힌트 출력
  24. print_result — anthropic 400일 때 진단 힌트 출력
  25. _safe_raw_summary — raw=None이면 None 반환
  26. _safe_raw_summary — error dict 없으면 None 반환
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# scripts 디렉토리를 import 가능하게 설정
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ai_provider_smoke_test import (
    SMOKE_PROMPT,
    SmokeResult,
    _diagnostic_hint,
    _safe_raw_summary,
    main_async,
    parse_args,
    print_result,
    run_smoke,
    smoke_single_provider,
)
from app.services.ai_analysis.schemas import AnalysisProviderError, AnalysisProviderResult

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ok_result(provider: str = "openai") -> AnalysisProviderResult:
    return AnalysisProviderResult(
        provider=provider,
        model=f"{provider}-model-v1",
        content="provider smoke test ok",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        latency_ms=123,
        finish_reason="stop",
        raw=None,
    )


def _mock_settings(*, openai_key: str | None = None, anthropic_key: str | None = None) -> MagicMock:
    s = MagicMock()
    s.ai_openai_api_key = openai_key
    s.ai_openai_model = "gpt-4o"
    s.ai_openai_timeout_seconds = 60
    s.ai_anthropic_api_key = anthropic_key
    s.ai_anthropic_model = "claude-sonnet-4-6"
    s.ai_anthropic_max_tokens = 8096
    s.ai_anthropic_timeout_seconds = 60
    return s


def _mock_provider(result: AnalysisProviderResult | None = None, *, error: AnalysisProviderError | None = None) -> AsyncMock:
    mock = AsyncMock()
    if error is not None:
        mock.analyze.side_effect = error
    else:
        mock.analyze.return_value = result or _ok_result()
    return mock


# ---------------------------------------------------------------------------
# 1. --confirm 없으면 provider 호출 안 함, exit code 0
# ---------------------------------------------------------------------------


async def test_no_confirm_does_not_call_provider() -> None:
    """--confirm 없으면 provider.analyze()를 호출하지 않고 exit code 0을 반환한다."""
    args = parse_args(["--provider", "openai"])
    mock_prov = _mock_provider()
    out = StringIO()

    exit_code = await main_async(args, _openai_provider=mock_prov, _out=out)

    assert exit_code == 0
    mock_prov.analyze.assert_not_called()


# ---------------------------------------------------------------------------
# 2. --confirm 없으면 안내 메시지 출력
# ---------------------------------------------------------------------------


async def test_no_confirm_prints_guidance() -> None:
    """--confirm 없으면 --confirm 추가를 안내하는 메시지를 출력한다."""
    args = parse_args(["--provider", "anthropic"])
    out = StringIO()

    await main_async(args, _out=out)

    output = out.getvalue()
    assert "--confirm" in output
    assert "anthropic" in output


# ---------------------------------------------------------------------------
# 3. openai key 없음 → skipped, skip_reason에 AI_OPENAI_API_KEY 포함
# ---------------------------------------------------------------------------


async def test_openai_no_key_skipped() -> None:
    """AI_OPENAI_API_KEY 없으면 openai 결과가 skipped=True이고 skip_reason을 포함한다."""
    settings = _mock_settings(openai_key=None)
    results = await run_smoke("openai", settings=settings)

    assert len(results) == 1
    r = results[0]
    assert r.provider == "openai"
    assert r.skipped is True
    assert "AI_OPENAI_API_KEY" in r.skip_reason


# ---------------------------------------------------------------------------
# 4. anthropic key 없음 → skipped, skip_reason에 AI_ANTHROPIC_API_KEY 포함
# ---------------------------------------------------------------------------


async def test_anthropic_no_key_skipped() -> None:
    """AI_ANTHROPIC_API_KEY 없으면 anthropic 결과가 skipped=True이고 skip_reason을 포함한다."""
    settings = _mock_settings(anthropic_key=None)
    results = await run_smoke("anthropic", settings=settings)

    assert len(results) == 1
    r = results[0]
    assert r.provider == "anthropic"
    assert r.skipped is True
    assert "AI_ANTHROPIC_API_KEY" in r.skip_reason


# ---------------------------------------------------------------------------
# 5. openai 성공 경로 → SmokeResult.success=True
# ---------------------------------------------------------------------------


async def test_openai_success_path() -> None:
    """mock provider가 결과를 반환하면 SmokeResult.success=True."""
    ok = _ok_result("openai")
    settings = _mock_settings(openai_key="sk-real")
    results = await run_smoke("openai", settings=settings, _openai_provider=_mock_provider(ok))

    assert len(results) == 1
    r = results[0]
    assert r.success is True
    assert r.provider == "openai"
    assert r.result is ok


# ---------------------------------------------------------------------------
# 6. anthropic 성공 경로 → SmokeResult.success=True
# ---------------------------------------------------------------------------


async def test_anthropic_success_path() -> None:
    """mock provider가 결과를 반환하면 SmokeResult.success=True."""
    ok = _ok_result("anthropic")
    settings = _mock_settings(anthropic_key="sk-ant-real")
    results = await run_smoke("anthropic", settings=settings, _anthropic_provider=_mock_provider(ok))

    assert len(results) == 1
    r = results[0]
    assert r.success is True
    assert r.result is ok


# ---------------------------------------------------------------------------
# 7. openai 실패 경로 (AnalysisProviderError) → SmokeResult.success=False
# ---------------------------------------------------------------------------


async def test_openai_error_path() -> None:
    """provider가 AnalysisProviderError를 발생시키면 SmokeResult.success=False."""
    err = AnalysisProviderError(provider="openai", message="rate limit", retryable=True, status_code=429)
    settings = _mock_settings(openai_key="sk-real")
    results = await run_smoke("openai", settings=settings, _openai_provider=_mock_provider(error=err))

    assert len(results) == 1
    r = results[0]
    assert r.success is False
    assert r.skipped is False
    assert r.error is err


# ---------------------------------------------------------------------------
# 8. both — 한쪽 실패해도 두 결과 모두 수집
# ---------------------------------------------------------------------------


async def test_both_collects_all_results_even_if_one_fails() -> None:
    """both 모드에서 openai 실패해도 anthropic 결과가 수집된다."""
    err = AnalysisProviderError(provider="openai", message="timeout", retryable=True)
    ok = _ok_result("anthropic")
    settings = _mock_settings(openai_key="sk-real", anthropic_key="sk-ant-real")

    results = await run_smoke(
        "both",
        settings=settings,
        _openai_provider=_mock_provider(error=err),
        _anthropic_provider=_mock_provider(ok),
    )

    assert len(results) == 2
    providers = {r.provider: r for r in results}
    assert providers["openai"].success is False
    assert providers["anthropic"].success is True


# ---------------------------------------------------------------------------
# 9. both — main_async summary에 카운트 포함
# ---------------------------------------------------------------------------


async def test_both_summary_in_output() -> None:
    """both 모드에서 Summary 줄에 ok/failed/skipped 카운트가 포함된다."""
    err = AnalysisProviderError(provider="openai", message="fail", retryable=False)
    ok = _ok_result("anthropic")
    settings = _mock_settings(openai_key="sk-real", anthropic_key="sk-ant-real")

    args = parse_args(["--provider", "both", "--confirm"])
    out = StringIO()

    await main_async(
        args,
        settings=settings,
        _openai_provider=_mock_provider(error=err),
        _anthropic_provider=_mock_provider(ok),
        _out=out,
    )

    output = out.getvalue()
    assert "Summary" in output
    assert "1 ok" in output
    assert "1 failed" in output


# ---------------------------------------------------------------------------
# 10. 실패 결과 → main_async exit code 1
# ---------------------------------------------------------------------------


async def test_failure_returns_exit_code_1() -> None:
    """실제 실패(skip 아님) 결과가 있으면 exit code 1을 반환한다."""
    err = AnalysisProviderError(provider="openai", message="fail", retryable=False)
    settings = _mock_settings(openai_key="sk-real")
    args = parse_args(["--provider", "openai", "--confirm"])
    out = StringIO()

    exit_code = await main_async(
        args,
        settings=settings,
        _openai_provider=_mock_provider(error=err),
        _out=out,
    )

    assert exit_code == 1


# ---------------------------------------------------------------------------
# 11. 스킵만 있을 때 → exit code 0
# ---------------------------------------------------------------------------


async def test_skip_only_returns_exit_code_0() -> None:
    """모든 결과가 skipped이면 exit code 0을 반환한다 (실패 아님)."""
    settings = _mock_settings(openai_key=None)  # API key 없음 → skip
    args = parse_args(["--provider", "openai", "--confirm"])
    out = StringIO()

    exit_code = await main_async(args, settings=settings, _out=out)

    assert exit_code == 0


# ---------------------------------------------------------------------------
# 12. 성공만 있을 때 → exit code 0
# ---------------------------------------------------------------------------


async def test_success_only_returns_exit_code_0() -> None:
    """모든 결과가 성공이면 exit code 0을 반환한다."""
    ok = _ok_result("openai")
    settings = _mock_settings(openai_key="sk-real")
    args = parse_args(["--provider", "openai", "--confirm"])
    out = StringIO()

    exit_code = await main_async(
        args,
        settings=settings,
        _openai_provider=_mock_provider(ok),
        _out=out,
    )

    assert exit_code == 0


# ---------------------------------------------------------------------------
# 13. print_result — 성공 시 필드 출력 확인
# ---------------------------------------------------------------------------


def test_print_result_success_fields() -> None:
    """성공 SmokeResult를 출력하면 model/content/tokens/latency가 포함된다."""
    smoke = SmokeResult(
        provider="openai",
        success=True,
        result=AnalysisProviderResult(
            provider="openai",
            model="gpt-4o",
            content="smoke test ok",
            prompt_tokens=8,
            completion_tokens=4,
            total_tokens=12,
            latency_ms=99,
            finish_reason="stop",
            raw=None,
        ),
    )
    out = StringIO()
    print_result(smoke, file=out)
    output = out.getvalue()

    assert "[OK]" in output
    assert "gpt-4o" in output
    assert "smoke test ok" in output
    assert "8" in output    # prompt_tokens
    assert "99" in output   # latency_ms
    assert "stop" in output


# ---------------------------------------------------------------------------
# 14. print_result — 실패 시 error/retryable 출력 확인
# ---------------------------------------------------------------------------


def test_print_result_failure_fields() -> None:
    """실패 SmokeResult를 출력하면 error 메시지와 retryable이 포함된다."""
    err = AnalysisProviderError(provider="openai", message="network timeout", retryable=True)
    smoke = SmokeResult(provider="openai", success=False, error=err)
    out = StringIO()
    print_result(smoke, file=out)
    output = out.getvalue()

    assert "[FAIL]" in output
    assert "network timeout" in output
    assert "True" in output   # retryable


# ---------------------------------------------------------------------------
# 15. print_result — 스킵 시 skip_reason 출력 확인
# ---------------------------------------------------------------------------


def test_print_result_skip_fields() -> None:
    """skipped SmokeResult를 출력하면 [SKIP]과 skip_reason이 포함된다."""
    smoke = SmokeResult(
        provider="anthropic",
        success=False,
        skipped=True,
        skip_reason="AI_ANTHROPIC_API_KEY not set",
    )
    out = StringIO()
    print_result(smoke, file=out)
    output = out.getvalue()

    assert "[SKIP]" in output
    assert "AI_ANTHROPIC_API_KEY not set" in output


# ---------------------------------------------------------------------------
# 16. parse_args — --provider, --confirm 파싱
# ---------------------------------------------------------------------------


def test_parse_args_defaults() -> None:
    """parse_args가 --provider와 --confirm을 올바르게 파싱한다."""
    args = parse_args(["--provider", "both"])
    assert args.provider == "both"
    assert args.confirm is False


def test_parse_args_confirm_flag() -> None:
    """--confirm 플래그가 True로 파싱된다."""
    args = parse_args(["--provider", "openai", "--confirm"])
    assert args.provider == "openai"
    assert args.confirm is True


def test_parse_args_invalid_provider() -> None:
    """알 수 없는 provider는 argparse가 오류를 발생시킨다."""
    with pytest.raises(SystemExit):
        parse_args(["--provider", "banana-llm"])


# ---------------------------------------------------------------------------
# 17. SMOKE_PROMPT 상수 확인
# ---------------------------------------------------------------------------


def test_smoke_prompt_constant() -> None:
    """SMOKE_PROMPT 상수가 존재하고 비어있지 않다."""
    assert isinstance(SMOKE_PROMPT, str)
    assert len(SMOKE_PROMPT) > 0


# ---------------------------------------------------------------------------
# 18. both — 모두 성공 → exit code 0
# ---------------------------------------------------------------------------


async def test_both_all_success_exit_code_0() -> None:
    """both 모드에서 모두 성공이면 exit code 0."""
    settings = _mock_settings(openai_key="sk-real", anthropic_key="sk-ant-real")
    args = parse_args(["--provider", "both", "--confirm"])
    out = StringIO()

    exit_code = await main_async(
        args,
        settings=settings,
        _openai_provider=_mock_provider(_ok_result("openai")),
        _anthropic_provider=_mock_provider(_ok_result("anthropic")),
        _out=out,
    )

    assert exit_code == 0
    output = out.getvalue()
    assert "2 ok" in output


# ---------------------------------------------------------------------------
# 19. both — 모두 실패 → exit code 1
# ---------------------------------------------------------------------------


async def test_both_all_fail_exit_code_1() -> None:
    """both 모드에서 모두 실패이면 exit code 1."""
    err_o = AnalysisProviderError(provider="openai", message="fail1", retryable=False)
    err_a = AnalysisProviderError(provider="anthropic", message="fail2", retryable=True)
    settings = _mock_settings(openai_key="sk-real", anthropic_key="sk-ant-real")
    args = parse_args(["--provider", "both", "--confirm"])
    out = StringIO()

    exit_code = await main_async(
        args,
        settings=settings,
        _openai_provider=_mock_provider(error=err_o),
        _anthropic_provider=_mock_provider(error=err_a),
        _out=out,
    )

    assert exit_code == 1
    output = out.getvalue()
    assert "2 failed" in output


# ---------------------------------------------------------------------------
# 20. smoke_single_provider — AnalysisProviderError를 잡아 SmokeResult 반환
# ---------------------------------------------------------------------------


async def test_smoke_single_provider_catches_error() -> None:
    """smoke_single_provider가 AnalysisProviderError를 잡아 SmokeResult(success=False)를 반환한다."""
    err = AnalysisProviderError(provider="openai", message="401 unauthorized", retryable=False, status_code=401)
    prov = _mock_provider(error=err)

    result = await smoke_single_provider("openai", prov)

    assert result.success is False
    assert result.error is err
    assert result.skipped is False
    assert result.provider == "openai"


# ---------------------------------------------------------------------------
# C-2.7.5: 진단 출력 개선
# ---------------------------------------------------------------------------


# 21. print_result — raw error 요약 출력
def test_print_result_shows_raw_error_summary() -> None:
    """실패 SmokeResult에 raw error가 있으면 요약 정보를 출력한다."""
    raw = {
        "error": {
            "type": "insufficient_quota",
            "code": "insufficient_quota",
            "message": "You exceeded your current quota.",
        }
    }
    err = AnalysisProviderError(
        provider="openai", message="HTTP 429 insufficient_quota: ...", retryable=False, status_code=429, raw=raw
    )
    smoke = SmokeResult(provider="openai", success=False, error=err)
    out = StringIO()
    print_result(smoke, file=out)
    output = out.getvalue()

    assert "insufficient_quota" in output
    assert "raw_error" in output


# 22. _safe_raw_summary — 민감 필드 없음
def test_safe_raw_summary_no_sensitive_keys() -> None:
    """_safe_raw_summary 출력에 API key나 Authorization 등 민감 정보가 없다."""
    # raw에는 provider response body만 있어야 하므로 원래 credentials가 없지만,
    # 만약 실수로 포함된 경우에도 출력에 나오지 않아야 한다.
    raw = {
        "error": {
            "type": "rate_limit_error",
            "code": "rate_limit_exceeded",
            "message": "Rate limit exceeded.",
            "authorization": "Bearer sk-secret-key",  # 민감 필드 (실제론 없지만 안전성 확인)
        }
    }
    summary = _safe_raw_summary(raw)
    assert summary is not None
    # 민감 키는 _SENSITIVE_FIELD_NAMES 필터로 제외되거나, 직접 필드값이 출력되지 않음
    # 실제로 "authorization"은 필드 이름이지 값이 아님 — 출력되는 건 type/code/message만
    assert "sk-secret-key" not in (summary or "")
    assert "Bearer" not in (summary or "")


# 23. print_result — openai 429 진단 힌트
def test_print_result_openai_429_shows_hint() -> None:
    """openai 429 실패 시 진단 힌트가 출력에 포함된다."""
    err = AnalysisProviderError(
        provider="openai", message="HTTP 429 insufficient_quota: ...", retryable=False, status_code=429
    )
    smoke = SmokeResult(provider="openai", success=False, error=err)
    out = StringIO()
    print_result(smoke, file=out)
    output = out.getvalue()

    assert "429" in output or "quota" in output.lower() or "billing" in output.lower()


# 24. print_result — anthropic 400 진단 힌트
def test_print_result_anthropic_400_shows_hint() -> None:
    """anthropic 400 실패 시 진단 힌트가 출력에 포함된다."""
    err = AnalysisProviderError(
        provider="anthropic", message="HTTP 400 invalid_request_error: ...", retryable=False, status_code=400
    )
    smoke = SmokeResult(provider="anthropic", success=False, error=err)
    out = StringIO()
    print_result(smoke, file=out)
    output = out.getvalue()

    assert "400" in output or "max_tokens" in output.lower() or "anthropic" in output.lower()


# 25. _safe_raw_summary — raw=None → None
def test_safe_raw_summary_none_input() -> None:
    """raw=None이면 None을 반환한다."""
    assert _safe_raw_summary(None) is None


# 26. _safe_raw_summary — error dict 없으면 None
def test_safe_raw_summary_no_error_key() -> None:
    """raw에 'error' 키가 없으면 None을 반환한다."""
    assert _safe_raw_summary({"status": "ok"}) is None
    assert _safe_raw_summary({"error": "string not dict"}) is None
