"""Paper Signal Session 분석 prompt 빌더.

PaperSignalAnalysisInput payload(dict)를 LLM 분석용 markdown prompt로 변환한다.
**실제 LLM 호출 없음** — prompt 문자열 생성만 한다.

- 전체 길이 상한(_MAX_PROMPT_CHARS)을 적용하고 잘리면 warning을 남긴다.
- CRITICAL INSTRUCTIONS로 실거래/주문/제안 자동생성 등을 명시적으로 금지한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

_MAX_PROMPT_CHARS = 20_000
_TRUNCATION_SUFFIX = "\n\n[... prompt truncated to fit maximum length ...]"
_WARNING_TRUNCATED = "Prompt was truncated to fit the maximum length."

_CRITICAL_INSTRUCTIONS = """\
## CRITICAL INSTRUCTIONS (must obey)
This is a READ-ONLY paper SIGNAL-ONLY analysis. No order is or will be placed.
You MUST NOT:
- give any direct or live trading recommendation, or an instruction to buy/sell now;
- instruct to place an order, enable auto-trading, enable a scheduler/job, or connect a real account;
- propose or imply an automatic strategy change or automatic proposal creation;
- recommend increasing any risk limit;
- claim statistical significance or reliability when the analyzed sample is small
  (always reference analyzed_count vs pending_count and treat low counts as inconclusive).
Your output is analysis for a human reviewer only. It triggers no action.
"""

_SECTIONS = """\
## Produce a markdown report with these sections
1. Session summary
2. Signal quality assessment
3. Candidate / proposal validity assessment
4. Outcome interpretation (reference analyzed vs pending counts; be explicit about uncertainty)
5. Risk notes
6. Data limitations
7. Recommendation for HUMAN REVIEW only (no trading action)
"""


@dataclass
class PromptResult:
    prompt: str
    prompt_length: int
    truncated: bool
    warnings: list[str]


class PaperSignalAnalysisPromptService:
    def build(self, analysis_input: dict) -> PromptResult:
        """분석 입력 payload(dict)로 bounded markdown prompt를 만든다."""
        warnings: list[str] = []
        payload_json = json.dumps(analysis_input, ensure_ascii=False, indent=2, default=str)

        body = (
            "# Paper Signal Session Analysis\n\n"
            "You are a careful trading research analyst. Analyze the following PAPER SIGNAL-ONLY "
            "session. The linked strategy version is DRAFT and is never executed by the live runner; "
            "no trades or orders exist.\n\n"
            f"{_CRITICAL_INSTRUCTIONS}\n"
            f"{_SECTIONS}\n"
            "## Analysis input (read-only payload)\n"
            "```json\n"
            f"{payload_json}\n"
            "```\n"
        )

        truncated = False
        if len(body) > _MAX_PROMPT_CHARS:
            keep = _MAX_PROMPT_CHARS - len(_TRUNCATION_SUFFIX)
            body = body[:keep] + _TRUNCATION_SUFFIX
            truncated = True
            warnings.append(_WARNING_TRUNCATED)

        return PromptResult(
            prompt=body,
            prompt_length=len(body),
            truncated=truncated,
            warnings=warnings,
        )
