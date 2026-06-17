"""Dual Debate analysis run 수동 smoke test 스크립트 (C-2.7.6).

pytest에서 절대 실행하지 마세요. 이 스크립트는 실제 DB 쓰기 + LLM API 호출을 합니다.

Usage:
    # dry run (어떤 작업을 할지만 표시):
    python scripts/ai_dual_debate_smoke_test.py --strategy-id 1 --version-id 1

    # 실제 실행:
    python scripts/ai_dual_debate_smoke_test.py \\
        --strategy-id 1 --version-id 1 --confirm

    # provider 변경 (기본값: openai + anthropic):
    python scripts/ai_dual_debate_smoke_test.py \\
        --strategy-id 1 --version-id 1 \\
        --provider openai --secondary-provider anthropic \\
        --confirm

실행 흐름:
  dual mode + enable_critique + enable_synthesis
  → Phase-1: primary_analysis + secondary_analysis
  → Phase-2: primary_critique + secondary_critique
  → Phase-3: synthesis
  → 5개 responses가 DB에 저장됨 (모두 성공 시)

Required environment variables:
    AI_OPENAI_API_KEY      — openai provider
    AI_ANTHROPIC_API_KEY   — anthropic provider
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# backend 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ai_analysis.run_service import AnalysisRunService

# ---------------------------------------------------------------------------
# 출력 헬퍼
# ---------------------------------------------------------------------------

_CONTENT_PREVIEW = 300  # content 앞 N자만 표시


def print_response(resp: Any, idx: int, *, file=None) -> None:
    """AiModelResponse 한 건을 출력한다."""
    if file is None:
        file = sys.stdout

    print(f"  [{idx}] {resp.role}", file=file)
    print(f"      provider : {resp.provider}", file=file)
    print(f"      model    : {resp.model}", file=file)

    if resp.error_message:
        print(f"      ERROR    : {resp.error_message}", file=file)
    else:
        pt = resp.prompt_tokens
        ct = resp.completion_tokens
        tt = resp.total_tokens
        print(f"      tokens   : {pt} prompt / {ct} completion / {tt} total", file=file)
        print(f"      latency  : {resp.latency_ms} ms", file=file)
        print(f"      finish   : {resp.finish_reason}", file=file)
        content = resp.content or ""
        preview = content[:_CONTENT_PREVIEW]
        ellipsis = "..." if len(content) > _CONTENT_PREVIEW else ""
        print(f"      content  : {(preview + ellipsis)!r}", file=file)


def print_run_result(run: Any, *, file=None) -> None:
    """AiAnalysisRun (responses 포함)을 출력한다."""
    if file is None:
        file = sys.stdout

    status_val = run.status.value if hasattr(run.status, "value") else str(run.status)

    print("=== Dual Debate Run Result ===", file=file)
    print(f"run_id      : {run.id}", file=file)
    print(f"status      : {status_val.upper()}", file=file)
    print(f"input_hash  : {run.input_hash or '(none)'}", file=file)
    print(f"prompt_hash : {run.prompt_hash or '(none)'}", file=file)

    if run.error_message:
        print(f"error       : {run.error_message}", file=file)
        # 개별 provider 문제 진단 힌트
        msg = run.error_message.lower()
        if "insufficient_quota" in msg or "quota" in msg:
            print(
                "hint        : OpenAI 할당량 초과 — https://platform.openai.com/account/billing 확인",
                file=file,
            )
        if "credit balance" in msg or "invalid_request_error" in msg:
            print(
                "hint        : Anthropic 잔액 부족 — https://console.anthropic.com/ 에서 충전",
                file=file,
            )
    else:
        print("error       : (none)", file=file)

    responses = run.responses or []
    print(f"\nresponses ({len(responses)}):", file=file)
    for i, resp in enumerate(responses, start=1):
        print_response(resp, i, file=file)
        print(file=file)

    length_truncated = [
        resp.role for resp in responses
        if getattr(resp, "finish_reason", None) == "length"
    ]
    if length_truncated:
        for role in length_truncated:
            print(
                f"WARNING: {role} ended with finish_reason=length. "
                "Consider increasing AI_ANTHROPIC_MAX_TOKENS (or AI_OPENAI_MAX_OUTPUT_TOKENS).",
                file=file,
            )


# ---------------------------------------------------------------------------
# 핵심 로직 (테스트 가능)
# ---------------------------------------------------------------------------


async def run_debate(
    service: AnalysisRunService,
    strategy_id: int,
    version_id: int,
    prompt_type: str,
    provider: str,
    secondary_provider: str,
    *,
    file=None,
) -> int:
    """AnalysisRunService로 dual debate run을 실행하고 결과를 출력한다.

    Returns:
        0 if run succeeded, 1 otherwise.
    """
    if file is None:
        file = sys.stdout

    print(
        f"실행: strategy_id={strategy_id}, version_id={version_id}, "
        f"provider={provider}, secondary={secondary_provider}, "
        f"prompt_type={prompt_type}",
        file=file,
    )
    print("모드: dual + critique + synthesis (5 responses 예상)", file=file)
    print(file=file)

    run = await service.create_run(
        strategy_id=strategy_id,
        version_id=version_id,
        prompt_type=prompt_type,
        provider_name=provider,
        mode="dual",
        secondary_provider_name=secondary_provider,
        enable_critique=True,
        enable_synthesis=True,
    )

    if run is None:
        print(
            f"[ERROR] strategy_id={strategy_id} / version_id={version_id} 를 찾을 수 없습니다.",
            file=file,
        )
        print(
            "       전략과 버전이 DB에 존재하는지 확인하세요.",
            file=file,
        )
        return 1

    print_run_result(run, file=file)

    status_val = run.status.value if hasattr(run.status, "value") else str(run.status)
    return 0 if status_val == "succeeded" else 1


async def main_async(
    args: argparse.Namespace,
    *,
    _service: AnalysisRunService | None = None,
    _out=None,
) -> int:
    """메인 로직. exit code를 반환한다.

    _service: 테스트 전용 — 실제 DB session 대신 주입할 서비스.
    _out    : 테스트 전용 — 출력 대상 (None이면 sys.stdout).
    """
    out = _out or sys.stdout

    if not args.confirm:
        print("실제 LLM API 호출 + DB 저장을 하려면 --confirm 플래그를 추가하세요.", file=out)
        print(file=out)
        print(f"  strategy_id      : {args.strategy_id}", file=out)
        print(f"  version_id       : {args.version_id}", file=out)
        print(f"  prompt_type      : {args.prompt_type}", file=out)
        print(f"  provider         : {args.provider}", file=out)
        print(f"  secondary        : {args.secondary_provider}", file=out)
        print(f"  enable_critique  : True", file=out)
        print(f"  enable_synthesis : True", file=out)
        print(file=out)
        print("사용 예시:", file=out)
        print(
            f"  python scripts/ai_dual_debate_smoke_test.py "
            f"--strategy-id {args.strategy_id} "
            f"--version-id {args.version_id} "
            f"--confirm",
            file=out,
        )
        print(file=out)
        print("주의: 실제 API 비용이 발생하며 결과가 DB에 저장됩니다.", file=out)
        return 0

    if _service is not None:
        return await run_debate(
            _service,
            strategy_id=args.strategy_id,
            version_id=args.version_id,
            prompt_type=args.prompt_type,
            provider=args.provider,
            secondary_provider=args.secondary_provider,
            file=out,
        )

    # 실제 DB session 생성
    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        svc = AnalysisRunService(session)
        return await run_debate(
            svc,
            strategy_id=args.strategy_id,
            version_id=args.version_id,
            prompt_type=args.prompt_type,
            provider=args.provider,
            secondary_provider=args.secondary_provider,
            file=out,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dual Debate analysis run 수동 smoke test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
환경 변수:
  AI_OPENAI_API_KEY      openai provider 사용 시 필요
  AI_ANTHROPIC_API_KEY   anthropic provider 사용 시 필요

주의: pytest에서 이 스크립트를 실행하지 마세요.
      실제 LLM API 비용이 발생하고 DB에 데이터가 저장됩니다.
        """.strip(),
    )
    parser.add_argument(
        "--strategy-id",
        type=int,
        required=True,
        dest="strategy_id",
        help="분석할 strategy의 DB id",
    )
    parser.add_argument(
        "--version-id",
        type=int,
        required=True,
        dest="version_id",
        help="분석할 strategy version의 DB id",
    )
    parser.add_argument(
        "--prompt-type",
        default="overview",
        dest="prompt_type",
        help="분석 prompt 유형 (기본값: overview)",
    )
    parser.add_argument(
        "--provider",
        default="openai",
        help="primary provider (기본값: openai)",
    )
    parser.add_argument(
        "--secondary-provider",
        default="anthropic",
        dest="secondary_provider",
        help="secondary provider (기본값: anthropic)",
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
