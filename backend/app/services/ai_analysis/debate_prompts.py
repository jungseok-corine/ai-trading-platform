"""Debate workflow prompt builders (C-2.6).

critique prompt: 상대 모델의 분석을 비판하도록 지시한다.
synthesis prompt: 모든 분석/비판을 바탕으로 최종 리포트를 생성하도록 지시한다.

두 prompt 모두:
  - 투자 조언 금지
  - 데이터 기반 지적만 허용
  - CRITICAL INSTRUCTIONS 섹션 포함 (length guard 보존을 위해)
"""
from __future__ import annotations

_CTX_EXCERPT = 2_000   # original analysis prompt에서 제공할 최대 문자 수
_CONTENT_EXCERPT = 3_000   # 각 분석/비판 content에서 제공할 최대 문자 수


def _excerpt(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n[... abbreviated ...]"


def build_critique_prompt(
    original_context: str,
    analysis_to_critique: str,
    critiquing_role: str,
) -> str:
    """상대 모델의 분석을 비판하는 prompt를 생성한다.

    Args:
        original_context: 원본 strategy analysis prompt (context로 포함).
        analysis_to_critique: 비판할 분석 text.
        critiquing_role: 비판하는 모델의 역할 설명 ("primary" | "secondary").
    """
    ctx = _excerpt(original_context, _CTX_EXCERPT)
    analysis = _excerpt(analysis_to_critique, _CONTENT_EXCERPT)

    return f"""\
=== CRITIQUE TASK ===

You are acting as a critical reviewer of a trading strategy analysis produced by another AI model.
Critiquing role: {critiquing_role}

This is a structured academic exercise only. Do NOT provide investment advice.

ORIGINAL ANALYSIS CONTEXT (abbreviated):
---
{ctx}
---

ANALYSIS TO REVIEW:
---
{analysis}
---

INSTRUCTIONS:
- Evaluate the analysis for logical consistency, data interpretation, and completeness.
- Only reference specific data points or claims from the analysis above.
- Do NOT introduce external market predictions or investment recommendations.
- Do not simply disagree — identify concrete gaps, logical errors, or data interpretation issues.

REQUIRED STRUCTURE:
1. Points of Agreement
   (cite specific claims from the analysis that are well-supported by data)
2. Points for Improvement / Gaps
   (cite specific weaknesses, missing data, or questionable interpretations)
3. Overall Assessment
   (1-2 sentences, data-based only)

CRITICAL INSTRUCTIONS
=== Do not provide investment advice. Data-based critique only. ==="""


def build_synthesis_prompt(
    original_context: str,
    primary_content: str,
    secondary_content: str,
    primary_critique_content: str | None = None,
    secondary_critique_content: str | None = None,
) -> str:
    """모든 분석/비판을 통합해 최종 synthesis 리포트를 생성하는 prompt를 만든다.

    Args:
        original_context: 원본 strategy analysis prompt.
        primary_content: primary_analysis 응답 text.
        secondary_content: secondary_analysis 응답 text.
        primary_critique_content: primary_critique 응답 text (없으면 None).
        secondary_critique_content: secondary_critique 응답 text (없으면 None).
    """
    ctx = _excerpt(original_context, _CTX_EXCERPT)
    p_analysis = _excerpt(primary_content, _CONTENT_EXCERPT)
    s_analysis = _excerpt(secondary_content, _CONTENT_EXCERPT)

    critique_section = ""
    if primary_critique_content or secondary_critique_content:
        parts: list[str] = []
        if primary_critique_content:
            p_crit = _excerpt(primary_critique_content, _CONTENT_EXCERPT)
            parts.append(
                f"PRIMARY MODEL CRITIQUE (of secondary analysis):\n---\n{p_crit}\n---"
            )
        if secondary_critique_content:
            s_crit = _excerpt(secondary_critique_content, _CONTENT_EXCERPT)
            parts.append(
                f"SECONDARY MODEL CRITIQUE (of primary analysis):\n---\n{s_crit}\n---"
            )
        critique_section = "\n\n" + "\n\n".join(parts)

    return f"""\
=== SYNTHESIS TASK ===

You are producing a final synthesis report from a dual-model trading strategy analysis session.
This is a structured academic exercise only. Do NOT provide investment advice.

ANALYSIS CONTEXT (abbreviated):
---
{ctx}
---

PRIMARY MODEL ANALYSIS:
---
{p_analysis}
---

SECONDARY MODEL ANALYSIS:
---
{s_analysis}
---{critique_section}

TASK: Produce a final synthesis report with ALL of the following sections:
1. Points of Consensus
   (where both analyses agree, with specific data references)
2. Points of Disagreement
   (unresolved differences between the two analyses)
3. Data Limitations
   (what data is missing, incomplete, or potentially unreliable)
4. Suggested Next Experiments
   (concrete, testable next steps for strategy improvement)

CRITICAL INSTRUCTIONS
=== Do not provide investment advice. Data-driven synthesis only. ==="""
