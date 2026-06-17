"""Dual Debate smoke test 스크립트 테스트 (C-2.7.6).

실제 네트워크/DB 호출 없음 — AnalysisRunService를 AsyncMock으로 대체한다.

검증 항목:
  1.  --confirm 없으면 실행 안 함, exit code 0
  2.  --confirm 없으면 안내 메시지 출력
  3.  --confirm 없으면 service 미호출
  4.  성공 run → exit code 0
  5.  FAILED run → exit code 1
  6.  strategy/version not found (None 반환) → exit code 1, 안내 메시지 출력
  7.  run_id 출력 확인
  8.  status 출력 확인
  9.  input_hash / prompt_hash 출력 확인
  10. responses count 출력 확인
  11. 각 response role 출력 확인
  12. response provider/model 출력 확인
  13. response tokens 출력 확인
  14. response content 앞 300자만 출력 (긴 content 잘림 확인)
  15. response error_message 출력 (실패 response)
  16. run error_message 출력
  17. Anthropic credit 관련 hint 출력
  18. OpenAI quota 관련 hint 출력
  19. parse_args — 기본값 확인
  20. parse_args — 명시적 인자 파싱
  21. parse_args — strategy-id 필수 검증
  22. service.create_run 호출 시 올바른 인자 확인
  23. enable_critique=True, enable_synthesis=True 전달 확인
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# scripts 디렉토리를 import 가능하게 설정
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ai_dual_debate_smoke_test import (
    main_async,
    parse_args,
    print_response,
    print_run_result,
    run_debate,
)

# ---------------------------------------------------------------------------
# helpers — 실제 SQLAlchemy 모델 대신 SimpleNamespace 사용
# ---------------------------------------------------------------------------


def _make_response(
    role: str = "primary_analysis",
    provider: str = "openai",
    model: str = "gpt-4o",
    content: str = "Analysis result.",
    prompt_tokens: int = 100,
    completion_tokens: int = 200,
    total_tokens: int = 300,
    latency_ms: int = 1234,
    finish_reason: str = "stop",
    error_message: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        role=role,
        provider=provider,
        model=model,
        content=content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        finish_reason=finish_reason,
        error_message=error_message,
    )


def _make_run(
    run_id: int = 42,
    status: str = "succeeded",
    input_hash: str = "abc123",
    prompt_hash: str = "def456",
    error_message: str | None = None,
    responses: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=run_id,
        status=SimpleNamespace(value=status),
        input_hash=input_hash,
        prompt_hash=prompt_hash,
        error_message=error_message,
        responses=responses if responses is not None else [],
    )


def _make_service(run: SimpleNamespace | None = None) -> AsyncMock:
    """AnalysisRunService를 대체하는 AsyncMock."""
    svc = AsyncMock()
    svc.create_run.return_value = run
    return svc


def _full_run() -> SimpleNamespace:
    """5개 response를 가진 완전한 debate run."""
    return _make_run(
        run_id=99,
        status="succeeded",
        responses=[
            _make_response(role="primary_analysis", provider="openai"),
            _make_response(role="secondary_analysis", provider="anthropic", model="claude-sonnet-4-6"),
            _make_response(role="primary_critique", provider="openai"),
            _make_response(role="secondary_critique", provider="anthropic", model="claude-sonnet-4-6"),
            _make_response(role="synthesis", provider="openai"),
        ],
    )


# ---------------------------------------------------------------------------
# 1. --confirm 없으면 실행 안 함, exit code 0
# ---------------------------------------------------------------------------


async def test_no_confirm_exits_0() -> None:
    """--confirm 없으면 exit code 0으로 종료한다."""
    args = parse_args(["--strategy-id", "1", "--version-id", "1"])
    out = StringIO()
    exit_code = await main_async(args, _out=out)
    assert exit_code == 0


# ---------------------------------------------------------------------------
# 2. --confirm 없으면 안내 메시지 출력
# ---------------------------------------------------------------------------


async def test_no_confirm_prints_guidance() -> None:
    """--confirm 없으면 --confirm 추가 안내와 실행 예시를 출력한다."""
    args = parse_args(["--strategy-id", "3", "--version-id", "7"])
    out = StringIO()
    await main_async(args, _out=out)
    output = out.getvalue()

    assert "--confirm" in output
    assert "3" in output   # strategy_id
    assert "7" in output   # version_id


# ---------------------------------------------------------------------------
# 3. --confirm 없으면 service 미호출
# ---------------------------------------------------------------------------


async def test_no_confirm_does_not_call_service() -> None:
    """--confirm 없으면 AnalysisRunService.create_run()을 호출하지 않는다."""
    args = parse_args(["--strategy-id", "1", "--version-id", "1"])
    svc = _make_service(_full_run())
    out = StringIO()

    await main_async(args, _service=svc, _out=out)

    svc.create_run.assert_not_called()


# ---------------------------------------------------------------------------
# 4. 성공 run → exit code 0
# ---------------------------------------------------------------------------


async def test_success_run_exit_code_0() -> None:
    """status=succeeded run → exit code 0."""
    args = parse_args(["--strategy-id", "1", "--version-id", "1", "--confirm"])
    svc = _make_service(_full_run())
    out = StringIO()

    exit_code = await main_async(args, _service=svc, _out=out)

    assert exit_code == 0


# ---------------------------------------------------------------------------
# 5. FAILED run → exit code 1
# ---------------------------------------------------------------------------


async def test_failed_run_exit_code_1() -> None:
    """status=failed run → exit code 1."""
    failed_run = _make_run(
        run_id=10,
        status="failed",
        error_message="primary(openai): HTTP 429 insufficient_quota: quota exceeded",
        responses=[
            _make_response(role="primary_analysis", error_message="HTTP 429: quota exceeded"),
        ],
    )
    args = parse_args(["--strategy-id", "1", "--version-id", "1", "--confirm"])
    svc = _make_service(failed_run)
    out = StringIO()

    exit_code = await main_async(args, _service=svc, _out=out)

    assert exit_code == 1


# ---------------------------------------------------------------------------
# 6. strategy/version not found → exit code 1, 안내 메시지
# ---------------------------------------------------------------------------


async def test_strategy_not_found_exit_code_1() -> None:
    """create_run이 None을 반환하면 exit code 1과 안내 메시지를 출력한다."""
    args = parse_args(["--strategy-id", "999", "--version-id", "999", "--confirm"])
    svc = _make_service(None)   # None → not found
    out = StringIO()

    exit_code = await main_async(args, _service=svc, _out=out)

    assert exit_code == 1
    output = out.getvalue()
    assert "999" in output
    assert "찾을 수 없습니다" in output or "not found" in output.lower()


# ---------------------------------------------------------------------------
# 7. run_id 출력 확인
# ---------------------------------------------------------------------------


def test_print_run_result_shows_run_id() -> None:
    """print_run_result가 run_id를 출력한다."""
    run = _make_run(run_id=77)
    out = StringIO()
    print_run_result(run, file=out)
    assert "77" in out.getvalue()


# ---------------------------------------------------------------------------
# 8. status 출력 확인
# ---------------------------------------------------------------------------


def test_print_run_result_shows_status() -> None:
    """print_run_result가 status를 출력한다."""
    run = _make_run(status="succeeded")
    out = StringIO()
    print_run_result(run, file=out)
    assert "SUCCEEDED" in out.getvalue()


def test_print_run_result_shows_failed_status() -> None:
    """print_run_result가 FAILED status를 출력한다."""
    run = _make_run(status="failed")
    out = StringIO()
    print_run_result(run, file=out)
    assert "FAILED" in out.getvalue()


# ---------------------------------------------------------------------------
# 9. input_hash / prompt_hash 출력 확인
# ---------------------------------------------------------------------------


def test_print_run_result_shows_hashes() -> None:
    """print_run_result가 input_hash와 prompt_hash를 출력한다."""
    run = _make_run(input_hash="hash_input_001", prompt_hash="hash_prompt_002")
    out = StringIO()
    print_run_result(run, file=out)
    output = out.getvalue()
    assert "hash_input_001" in output
    assert "hash_prompt_002" in output


# ---------------------------------------------------------------------------
# 10. responses count 출력 확인
# ---------------------------------------------------------------------------


def test_print_run_result_shows_response_count() -> None:
    """print_run_result가 responses 개수를 출력한다."""
    run = _make_run(responses=[_make_response() for _ in range(5)])
    out = StringIO()
    print_run_result(run, file=out)
    assert "5" in out.getvalue()


# ---------------------------------------------------------------------------
# 11. 각 response role 출력 확인
# ---------------------------------------------------------------------------


def test_print_run_result_shows_all_roles() -> None:
    """print_run_result가 모든 response role을 출력한다."""
    run = _full_run()
    out = StringIO()
    print_run_result(run, file=out)
    output = out.getvalue()

    assert "primary_analysis" in output
    assert "secondary_analysis" in output
    assert "primary_critique" in output
    assert "secondary_critique" in output
    assert "synthesis" in output


# ---------------------------------------------------------------------------
# 12. response provider/model 출력 확인
# ---------------------------------------------------------------------------


def test_print_response_shows_provider_and_model() -> None:
    """print_response가 provider와 model을 출력한다."""
    resp = _make_response(provider="openai", model="gpt-4o-test")
    out = StringIO()
    print_response(resp, 1, file=out)
    output = out.getvalue()
    assert "openai" in output
    assert "gpt-4o-test" in output


# ---------------------------------------------------------------------------
# 13. response tokens 출력 확인
# ---------------------------------------------------------------------------


def test_print_response_shows_tokens() -> None:
    """print_response가 prompt/completion/total_tokens를 출력한다."""
    resp = _make_response(prompt_tokens=111, completion_tokens=222, total_tokens=333)
    out = StringIO()
    print_response(resp, 1, file=out)
    output = out.getvalue()
    assert "111" in output
    assert "222" in output
    assert "333" in output


# ---------------------------------------------------------------------------
# 14. content 앞 300자만 출력 (잘림 확인)
# ---------------------------------------------------------------------------


def test_print_response_truncates_long_content() -> None:
    """긴 content는 앞 300자만 표시하고 '...'을 붙인다."""
    long_content = "X" * 500
    resp = _make_response(content=long_content)
    out = StringIO()
    print_response(resp, 1, file=out)
    output = out.getvalue()

    assert "..." in output
    # 500자 전체가 출력되지 않는지 확인 (300자 + "...")
    assert "X" * 400 not in output


def test_print_response_short_content_no_ellipsis() -> None:
    """짧은 content는 잘리지 않고 '...'이 붙지 않는다."""
    resp = _make_response(content="Short content.")
    out = StringIO()
    print_response(resp, 1, file=out)
    output = out.getvalue()
    assert "Short content." in output


# ---------------------------------------------------------------------------
# 15. response error_message 출력
# ---------------------------------------------------------------------------


def test_print_response_shows_error_message() -> None:
    """error_message가 있는 response에는 ERROR 항목이 출력된다."""
    resp = _make_response(
        role="secondary_analysis",
        error_message="HTTP 400 invalid_request_error: credit balance too low",
        content=None,
    )
    out = StringIO()
    print_response(resp, 2, file=out)
    output = out.getvalue()
    assert "ERROR" in output
    assert "credit balance too low" in output


# ---------------------------------------------------------------------------
# 16. run error_message 출력
# ---------------------------------------------------------------------------


def test_print_run_result_shows_error_message() -> None:
    """run에 error_message가 있으면 출력한다."""
    run = _make_run(
        status="failed",
        error_message="secondary(anthropic): HTTP 400: credit balance",
    )
    out = StringIO()
    print_run_result(run, file=out)
    assert "credit balance" in out.getvalue()


# ---------------------------------------------------------------------------
# 17. Anthropic credit hint 출력
# ---------------------------------------------------------------------------


def test_print_run_result_anthropic_credit_hint() -> None:
    """Anthropic credit balance 에러 메시지가 있으면 힌트를 출력한다."""
    run = _make_run(
        status="failed",
        error_message="secondary: HTTP 400 invalid_request_error: credit balance is too low",
    )
    out = StringIO()
    print_run_result(run, file=out)
    output = out.getvalue()
    assert "anthropic" in output.lower() or "console.anthropic" in output.lower()


# ---------------------------------------------------------------------------
# 18. OpenAI quota hint 출력
# ---------------------------------------------------------------------------


def test_print_run_result_openai_quota_hint() -> None:
    """OpenAI quota 에러 메시지가 있으면 힌트를 출력한다."""
    run = _make_run(
        status="failed",
        error_message="primary(openai): HTTP 429 insufficient_quota: exceeded quota",
    )
    out = StringIO()
    print_run_result(run, file=out)
    output = out.getvalue()
    assert "openai" in output.lower() or "platform.openai" in output.lower()


# ---------------------------------------------------------------------------
# 19. parse_args — 기본값 확인
# ---------------------------------------------------------------------------


def test_parse_args_defaults() -> None:
    """parse_args가 --prompt-type, --provider, --secondary-provider 기본값을 설정한다."""
    args = parse_args(["--strategy-id", "5", "--version-id", "2"])
    assert args.strategy_id == 5
    assert args.version_id == 2
    assert args.prompt_type == "overview"
    assert args.provider == "openai"
    assert args.secondary_provider == "anthropic"
    assert args.confirm is False


# ---------------------------------------------------------------------------
# 20. parse_args — 명시적 인자 파싱
# ---------------------------------------------------------------------------


def test_parse_args_explicit_values() -> None:
    """parse_args가 명시적으로 지정된 인자를 올바르게 파싱한다."""
    args = parse_args([
        "--strategy-id", "10",
        "--version-id", "3",
        "--prompt-type", "risk",
        "--provider", "fake",
        "--secondary-provider", "fake",
        "--confirm",
    ])
    assert args.strategy_id == 10
    assert args.version_id == 3
    assert args.prompt_type == "risk"
    assert args.provider == "fake"
    assert args.secondary_provider == "fake"
    assert args.confirm is True


# ---------------------------------------------------------------------------
# 21. parse_args — strategy-id 필수 검증
# ---------------------------------------------------------------------------


def test_parse_args_missing_strategy_id_raises() -> None:
    """--strategy-id 없으면 argparse가 SystemExit을 발생시킨다."""
    with pytest.raises(SystemExit):
        parse_args(["--version-id", "1"])


def test_parse_args_missing_version_id_raises() -> None:
    """--version-id 없으면 argparse가 SystemExit을 발생시킨다."""
    with pytest.raises(SystemExit):
        parse_args(["--strategy-id", "1"])


# ---------------------------------------------------------------------------
# 22. service.create_run 올바른 인자로 호출 확인
# ---------------------------------------------------------------------------


async def test_service_called_with_correct_args() -> None:
    """run_debate가 service.create_run을 올바른 인자로 호출한다."""
    svc = _make_service(_full_run())
    out = StringIO()

    await run_debate(
        svc,
        strategy_id=5,
        version_id=2,
        prompt_type="overview",
        provider="openai",
        secondary_provider="anthropic",
        file=out,
    )

    svc.create_run.assert_called_once_with(
        strategy_id=5,
        version_id=2,
        prompt_type="overview",
        provider_name="openai",
        mode="dual",
        secondary_provider_name="anthropic",
        enable_critique=True,
        enable_synthesis=True,
    )


# ---------------------------------------------------------------------------
# 23. enable_critique=True, enable_synthesis=True 전달 확인
# ---------------------------------------------------------------------------


async def test_enable_critique_and_synthesis_always_true() -> None:
    """run_debate는 항상 enable_critique=True, enable_synthesis=True로 호출한다."""
    svc = _make_service(_full_run())
    out = StringIO()

    await run_debate(svc, 1, 1, "overview", "openai", "anthropic", file=out)

    call_kwargs = svc.create_run.call_args.kwargs
    assert call_kwargs["enable_critique"] is True
    assert call_kwargs["enable_synthesis"] is True
