"""AI Provider smoke test — 실제 API 호출 수동 검증 스크립트 (C-2.7.4).

pytest에서 절대 실행하지 마세요. 이 스크립트는 실제 네트워크 호출을 합니다.

Usage:
    # dry run (API 호출 없음):
    python scripts/ai_provider_smoke_test.py --provider openai

    # 실제 API 호출:
    python scripts/ai_provider_smoke_test.py --provider openai --confirm
    python scripts/ai_provider_smoke_test.py --provider anthropic --confirm
    python scripts/ai_provider_smoke_test.py --provider both --confirm

Required environment variables:
    AI_OPENAI_API_KEY      — openai provider 사용 시
    AI_ANTHROPIC_API_KEY   — anthropic provider 사용 시
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

# backend 디렉토리를 sys.path에 추가 (repo root 또는 backend/ 어디서 실행해도 동작)
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ai_analysis.base import AnalysisProvider
from app.services.ai_analysis.schemas import AnalysisProviderError, AnalysisProviderResult

SMOKE_PROMPT = "Return exactly: provider smoke test ok"
_KNOWN_PROVIDERS = ("openai", "anthropic", "both")

# API key 관련 필드명 — 출력에서 절대 포함하지 않는다
_SENSITIVE_FIELD_NAMES = frozenset({
    "authorization", "x-api-key", "api_key", "api-key",
    "secret", "token", "password", "credential",
})


# ---------------------------------------------------------------------------
# 결과 타입
# ---------------------------------------------------------------------------


@dataclass
class SmokeResult:
    provider: str
    success: bool
    result: AnalysisProviderResult | None = None
    error: AnalysisProviderError | None = None
    skipped: bool = False
    skip_reason: str = ""


# ---------------------------------------------------------------------------
# 핵심 로직 (테스트 가능, 네트워크 의존성 없음)
# ---------------------------------------------------------------------------


async def smoke_single_provider(
    provider_name: str,
    provider: AnalysisProvider,
) -> SmokeResult:
    """provider.analyze()를 smoke prompt로 호출하고 결과를 반환한다."""
    try:
        result = await provider.analyze(SMOKE_PROMPT)
        return SmokeResult(provider=provider_name, success=True, result=result)
    except AnalysisProviderError as exc:
        return SmokeResult(provider=provider_name, success=False, error=exc)


def _safe_raw_summary(raw: dict | None) -> str | None:
    """raw error dict에서 진단에 유용한 정보만 추출한다.

    API key, Authorization, X-Api-Key 등 민감한 값은 절대 포함하지 않는다.
    raw는 항상 provider의 HTTP response body이므로 credentials가 없지만,
    명시적으로 필터링해 안전성을 보장한다.
    """
    if not isinstance(raw, dict):
        return None
    err = raw.get("error")
    if not isinstance(err, dict):
        return None

    parts: list[str] = []
    for key in ("type", "code", "param"):
        val = err.get(key)
        if val is not None and str(key).lower() not in _SENSITIVE_FIELD_NAMES:
            parts.append(f"{key}={val!r}")
    msg = err.get("message", "")
    if msg:
        truncated = msg[:200] + ("..." if len(msg) > 200 else "")
        parts.append(f"message={truncated!r}")

    return "  ".join(parts) if parts else None


def _diagnostic_hint(provider: str, status_code: int | None) -> str | None:
    """provider별 진단 힌트를 반환한다. 실패 원인 파악에 도움이 되는 점검 목록."""
    if provider == "openai" and status_code == 429:
        return (
            "OpenAI 429 진단:\n"
            "  1. https://platform.openai.com/usage 에서 사용량/잔액 확인\n"
            "  2. https://platform.openai.com/account/billing 에서 결제 수단 확인\n"
            "  3. error.code=insufficient_quota → 크레딧 충전 후 재시도\n"
            "  4. error.code=rate_limit_exceeded → 잠시 대기 후 재시도"
        )
    if provider == "anthropic" and status_code == 400:
        return (
            "Anthropic 400 진단:\n"
            "  1. https://console.anthropic.com/ 에서 잔액/플랜 확인\n"
            "  2. 모델 이름이 유효한지 확인 (AI_ANTHROPIC_MODEL 환경변수)\n"
            "  3. max_tokens 값이 모델 한도 내인지 확인 (AI_ANTHROPIC_MAX_TOKENS)\n"
            "  4. anthropic-version 헤더: 2023-06-01 유지 필요\n"
            "  5. messages 필드: [{\"role\": \"user\", \"content\": \"...\"}] 형식 확인"
        )
    return None


def print_result(smoke: SmokeResult, *, file=None) -> None:
    """SmokeResult를 사람이 읽기 좋은 형식으로 출력한다."""
    if file is None:
        file = sys.stdout

    if smoke.skipped:
        print(f"[SKIP] {smoke.provider}: {smoke.skip_reason}", file=file)
        return

    if smoke.success:
        r = smoke.result
        print(f"[OK]   {smoke.provider}", file=file)
        print(f"       model            : {r.model}", file=file)
        print(f"       content          : {r.content[:120]!r}", file=file)
        print(f"       prompt_tokens    : {r.prompt_tokens}", file=file)
        print(f"       completion_tokens: {r.completion_tokens}", file=file)
        print(f"       total_tokens     : {r.total_tokens}", file=file)
        print(f"       latency_ms       : {r.latency_ms}", file=file)
        print(f"       finish_reason    : {r.finish_reason}", file=file)
    else:
        exc = smoke.error
        print(f"[FAIL] {smoke.provider}", file=file)
        print(f"       error    : {exc.message}", file=file)
        print(f"       retryable: {exc.retryable}", file=file)
        if exc.status_code is not None:
            print(f"       status   : {exc.status_code}", file=file)

        raw_summary = _safe_raw_summary(exc.raw)
        if raw_summary:
            print(f"       raw_error: {raw_summary}", file=file)

        hint = _diagnostic_hint(smoke.provider, exc.status_code)
        if hint:
            print(file=file)
            for line in hint.splitlines():
                print(f"       {line}", file=file)


async def run_smoke(
    provider_arg: str,
    *,
    settings=None,
    _openai_provider: AnalysisProvider | None = None,
    _anthropic_provider: AnalysisProvider | None = None,
) -> list[SmokeResult]:
    """smoke test를 실행하고 결과 목록을 반환한다.

    _openai_provider / _anthropic_provider 를 주입하면 실제 provider 대신 해당 객체를 사용한다.
    이 매개변수는 테스트 전용이다.
    """
    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()

    providers_to_run: list[str] = ["openai", "anthropic"] if provider_arg == "both" else [provider_arg]
    results: list[SmokeResult] = []

    for name in providers_to_run:
        if name == "openai":
            if _openai_provider is not None:
                prov: AnalysisProvider = _openai_provider
            elif not settings.ai_openai_api_key:
                results.append(SmokeResult(
                    provider="openai",
                    success=False,
                    skipped=True,
                    skip_reason=(
                        "AI_OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
                        "export AI_OPENAI_API_KEY=<key> 후 재실행하세요."
                    ),
                ))
                continue
            else:
                from app.services.ai_analysis.openai_provider import OpenAIAnalysisProvider
                prov = OpenAIAnalysisProvider(
                    api_key=settings.ai_openai_api_key,
                    default_model=settings.ai_openai_model,
                    default_timeout_seconds=settings.ai_openai_timeout_seconds,
                )
            results.append(await smoke_single_provider("openai", prov))

        elif name == "anthropic":
            if _anthropic_provider is not None:
                prov = _anthropic_provider
            elif not settings.ai_anthropic_api_key:
                results.append(SmokeResult(
                    provider="anthropic",
                    success=False,
                    skipped=True,
                    skip_reason=(
                        "AI_ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. "
                        "export AI_ANTHROPIC_API_KEY=<key> 후 재실행하세요."
                    ),
                ))
                continue
            else:
                from app.services.ai_analysis.anthropic_provider import AnthropicAnalysisProvider
                prov = AnthropicAnalysisProvider(
                    api_key=settings.ai_anthropic_api_key,
                    default_model=settings.ai_anthropic_model,
                    default_timeout_seconds=settings.ai_anthropic_timeout_seconds,
                    max_tokens=settings.ai_anthropic_max_tokens,
                )
            results.append(await smoke_single_provider("anthropic", prov))

    return results


async def main_async(
    args: argparse.Namespace,
    *,
    settings=None,
    _openai_provider: AnalysisProvider | None = None,
    _anthropic_provider: AnalysisProvider | None = None,
    _out=None,
) -> int:
    """메인 로직. exit code를 반환한다.

    _out: 출력 대상 (None이면 sys.stdout). 테스트에서 StringIO를 넣을 수 있다.
    """
    out = _out or sys.stdout

    # --confirm 없으면 안내만 출력하고 종료
    if not args.confirm:
        print("실제 API 호출을 하려면 --confirm 플래그를 추가하세요.", file=out)
        print(file=out)
        print(f"  선택한 provider: {args.provider}", file=out)
        print(file=out)
        print("사용 예시:", file=out)
        print(
            f"  python scripts/ai_provider_smoke_test.py "
            f"--provider {args.provider} --confirm",
            file=out,
        )
        print(file=out)
        print("주의: 이 스크립트는 실제 OpenAI/Anthropic API를 호출합니다.", file=out)
        print("      pytest에서 실행하지 마세요.", file=out)
        return 0

    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()

    print(f"=== AI Provider Smoke Test: {args.provider} ===", file=out)
    print(f"prompt: {SMOKE_PROMPT!r}", file=out)
    print(file=out)

    results = await run_smoke(
        args.provider,
        settings=settings,
        _openai_provider=_openai_provider,
        _anthropic_provider=_anthropic_provider,
    )

    for r in results:
        print_result(r, file=out)
        print(file=out)

    success_count = sum(1 for r in results if r.success)
    fail_count = sum(1 for r in results if not r.success and not r.skipped)
    skip_count = sum(1 for r in results if r.skipped)

    print(
        f"=== Summary: {success_count} ok, {fail_count} failed, {skip_count} skipped ===",
        file=out,
    )

    return 1 if fail_count > 0 else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Provider smoke test — 실제 API 호출 수동 검증 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
환경 변수:
  AI_OPENAI_API_KEY      openai provider 사용 시 필요
  AI_ANTHROPIC_API_KEY   anthropic provider 사용 시 필요

주의: pytest에서 이 스크립트를 실행하거나 import하지 마세요.
      실제 네트워크 비용이 발생합니다.
        """.strip(),
    )
    parser.add_argument(
        "--provider",
        choices=list(_KNOWN_PROVIDERS),
        required=True,
        help="테스트할 provider (openai | anthropic | both)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="이 플래그 없이는 실제 API를 호출하지 않습니다.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
