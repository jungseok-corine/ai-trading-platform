"""Phase C-2.1 / C-2.1.1: Analysis Prompt Builder + Prompt Length Guard.

StrategyAnalysisInputRead payload를 LLM 분석용 prompt로 변환한다.
실제 LLM API 호출 없음 — prompt preview 생성만 수행한다.

설계 원칙:
  - StrategyAnalysisInputService 재사용 (payload 수집 로직 중복 없음)
  - prompt_type 구조를 열어두어 future extension 지원
  - 현재 구현: overview / risk / improvement
  - 데이터 부족 시에도 prompt 생성 (warnings 섹션에 명시)
  - parameters JSONB가 클 경우 안전하게 축약
  - prompt 전체 길이 상한 적용 (CRITICAL INSTRUCTIONS 보호)
  - LLM API 호출 절대 없음
"""
from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.strategy_analysis_input_service import StrategyAnalysisInputService
from app.trading.strategy.schemas import (
    AnalysisInputRecentSignal,
    AnalysisPromptInputSummary,
    StrategyAnalysisInputRead,
    StrategyAnalysisPromptRead,
    StrategyVersionActualTradingPerformance,
    StrategyVersionPerformanceByHorizon,
    StrategyVersionPerformanceBySignalType,
    StrategyVersionPerformanceBySymbol,
)

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

SUPPORTED_PROMPT_TYPES: frozenset[str] = frozenset({"overview", "risk", "improvement"})

_MAX_SYMBOLS_IN_PROMPT = 10
_MAX_RECENT_SIGNALS_IN_PROMPT = 10     # 20개 → 10개로 압축
_MAX_PARAMS_STR_LEN = 500              # parameters JSONB 문자열 상한
_MAX_PROMPT_CHARS = 20_000             # prompt 전체 길이 상한

_TRUNCATION_SUFFIX = "\n\n[... prompt truncated to fit maximum length ...]"
_WARNING_TRUNCATED = "Prompt was truncated to fit the maximum length."


# ---------------------------------------------------------------------------
# error
# ---------------------------------------------------------------------------


class UnsupportedPromptTypeError(ValueError):
    def __init__(self, prompt_type: str) -> None:
        super().__init__(
            f"unsupported prompt_type: '{prompt_type}'. "
            f"supported: {', '.join(sorted(SUPPORTED_PROMPT_TYPES))}"
        )
        self.prompt_type = prompt_type


# ---------------------------------------------------------------------------
# parameter compression
# ---------------------------------------------------------------------------


def _compress_params(params: dict, max_len: int = _MAX_PARAMS_STR_LEN) -> str:
    """parameters dict를 prompt 삽입용 문자열로 변환한다.

    전체 JSON 직렬화 결과가 max_len을 초과하면 앞부분만 유지하고
    잘렸다는 표시(" ... [truncated]")를 명확히 남긴다.
    """
    full_str = json.dumps(params, ensure_ascii=False, default=str)
    if len(full_str) <= max_len:
        return full_str
    suffix = " ... [truncated]"
    return full_str[: max_len - len(suffix)] + suffix


# ---------------------------------------------------------------------------
# prompt length guard
# ---------------------------------------------------------------------------


def _find_safe_cut_position(prompt: str) -> int:
    """CRITICAL INSTRUCTIONS 블록이 끝나는 위치를 반환한다.

    CRITICAL INSTRUCTIONS 이후 첫 번째 '=== ' 섹션 헤더 직전을 보호 구간으로 삼는다.
    블록을 찾지 못하면 0을 반환해 어디서든 자를 수 있게 한다.
    """
    ci_pos = prompt.find("CRITICAL INSTRUCTIONS")
    if ci_pos == -1:
        return 0
    after_ci = prompt.find("\n===", ci_pos)
    if after_ci == -1:
        return len(prompt)   # 전체를 보호 구간으로 설정
    return after_ci          # 첫 번째 섹션 헤더 이전 개행 위치


def _apply_length_guard(
    prompt: str,
    warnings: list[str],
    max_chars: int = _MAX_PROMPT_CHARS,
) -> tuple[str, bool]:
    """prompt 길이가 max_chars를 초과하면 안전하게 잘라낸다.

    CRITICAL INSTRUCTIONS 블록은 잘리지 않도록 보장한다.
    반환값: (최종 prompt, truncated: bool)
    """
    if len(prompt) <= max_chars:
        return prompt, False

    safe_pos = _find_safe_cut_position(prompt)

    # max_chars가 CRITICAL INSTRUCTIONS 끝보다 작으면 자를 수 없음
    if max_chars <= safe_pos:
        warnings.append(
            f"Prompt length ({len(prompt)} chars) exceeds maximum ({max_chars} chars). "
            "CRITICAL INSTRUCTIONS is preserved; truncation was not applied."
        )
        return prompt, False

    # suffix 공간을 확보한 위치에서 자름; safe_pos보다 앞으로 가지 않음
    cut_at = max(safe_pos, max_chars - len(_TRUNCATION_SUFFIX))
    truncated_prompt = prompt[:cut_at] + _TRUNCATION_SUFFIX
    warnings.append(_WARNING_TRUNCATED)
    return truncated_prompt, True


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------


def _pct(val: Decimal | str | None, *, as_rate: bool = False) -> str:
    """Decimal/str 값을 % 문자열로 포맷한다.

    as_rate=True: 0-1 scale → ×100 (win_rate 용)
    as_rate=False: 이미 % 단위 (return_pct 용)
    """
    if val is None:
        return "N/A"
    n = float(val)
    if as_rate:
        n *= 100
    sign = "+" if n > 0 else ""
    return f"{sign}{n:.2f}%"


def _horizon_table(rows: list[StrategyVersionPerformanceByHorizon]) -> str:
    lines = [
        "Horizon | Count | Win Rate | Avg Dir.Return | Avg MFE  | Avg MAE",
        "--------|-------|----------|----------------|----------|--------",
    ]
    for h in rows:
        wr = _pct(h.win_rate, as_rate=True) if h.count > 0 else "N/A"
        dr = _pct(h.avg_directional_return_pct) if h.count > 0 else "N/A"
        mfe = _pct(h.avg_mfe_pct) if h.avg_mfe_pct is not None else "N/A"
        mae = _pct(h.avg_mae_pct) if h.avg_mae_pct is not None else "N/A"
        lines.append(
            f"{h.horizon_minutes}m      | {h.count:<5} | {wr:<8} | {dr:<14} | {mfe:<8} | {mae}"
        )
    return "\n".join(lines)


def _signal_type_table(rows: list[StrategyVersionPerformanceBySignalType]) -> str:
    if not rows:
        return "  (no signal type data)"
    lines = [
        "Type | Signals | Analyzed | 5m Win Rate | 5m Avg Dir.Return",
        "-----|---------|----------|-------------|------------------",
    ]
    for st in rows:
        wr = _pct(st.win_rate_5m, as_rate=True) if st.win_rate_5m is not None else "N/A"
        dr = (
            _pct(st.avg_directional_return_pct_5m)
            if st.avg_directional_return_pct_5m is not None
            else "N/A"
        )
        lines.append(
            f"{st.signal_type.upper():<4} | {st.signal_count:<7} | {st.analyzed_count:<8} | {wr:<11} | {dr}"
        )
    return "\n".join(lines)


def _symbol_table(rows: list[StrategyVersionPerformanceBySymbol]) -> str:
    if not rows:
        return "  (no symbol data)"
    sliced = rows[:_MAX_SYMBOLS_IN_PROMPT]
    lines = [
        "Symbol   | Signals | Analyzed | 5m Win Rate | 5m Avg Dir.Return",
        "---------|---------|----------|-------------|------------------",
    ]
    for s in sliced:
        wr = _pct(s.win_rate_5m, as_rate=True) if s.win_rate_5m is not None else "N/A"
        dr = (
            _pct(s.avg_directional_return_pct_5m)
            if s.avg_directional_return_pct_5m is not None
            else "N/A"
        )
        lines.append(
            f"{s.symbol_code:<8} | {s.signal_count:<7} | {s.analyzed_count:<8} | {wr:<11} | {dr}"
        )
    if len(rows) > _MAX_SYMBOLS_IN_PROMPT:
        lines.append(f"  ... and {len(rows) - _MAX_SYMBOLS_IN_PROMPT} more symbols (truncated)")
    return "\n".join(lines)


def _actual_trading_section(actual: StrategyVersionActualTradingPerformance | None) -> str:
    if actual is None:
        return "  (no actual trading data)"
    pnl_str = (
        f"{float(actual.total_pnl_amount):+.0f} KRW"
        if actual.total_pnl_amount is not None
        else "N/A (pnl_amount not recorded)"
    )
    win_str = str(actual.win_trade_count) if actual.win_trade_count is not None else "N/A"
    loss_str = str(actual.loss_trade_count) if actual.loss_trade_count is not None else "N/A"
    return (
        f"  Orders: {actual.trade_count}, Filled: {actual.filled_count}\n"
        f"  Realized PnL: {pnl_str}\n"
        f"  Win/Loss Trades: {win_str} / {loss_str}\n"
        f"  Note: {actual.note}"
    )


def _recent_signals_section(signals: list[AnalysisInputRecentSignal]) -> str:
    if not signals:
        return "  (no recent signals)"
    sliced = signals[:_MAX_RECENT_SIGNALS_IN_PROMPT]
    lines = [
        "ID    | Symbol   | Type | Generated At        | 5m Dir.Return | 5m Win",
        "------|----------|------|---------------------|---------------|-------",
    ]
    for s in sliced:
        o = s.outcome_5m
        dr = (
            _pct(o.directional_return_pct)
            if o and o.directional_return_pct is not None
            else "N/A"
        )
        win = ("Win" if o.is_win else "Loss") if o and o.is_win is not None else "N/A"
        ts_str = s.generated_at.strftime("%Y-%m-%d %H:%M") if s.generated_at else "N/A"
        lines.append(
            f"{s.signal_id:<5} | {s.symbol_code:<8} | {s.signal_type.upper():<4} | "
            f"{ts_str:<19} | {dr:<13} | {win}"
        )
    if len(signals) > _MAX_RECENT_SIGNALS_IN_PROMPT:
        lines.append(
            f"  ... {len(signals) - _MAX_RECENT_SIGNALS_IN_PROMPT} more signals omitted"
        )
    return "\n".join(lines)


def _limitations_section(limitations: list[str]) -> str:
    return "\n".join(f"  - {lim}" for lim in limitations)


# ---------------------------------------------------------------------------
# prompt builders
# ---------------------------------------------------------------------------


def _build_overview_prompt(payload: StrategyAnalysisInputRead) -> str:
    s = payload.strategy
    p = payload.performance
    md = payload.market_data
    ctx = payload.analysis_context

    params_str = _compress_params(s.parameters)
    symbols_str = ", ".join(md.symbols) if md.symbols else "(none)"
    timeframes_str = ", ".join(md.timeframes) if md.timeframes else "(none)"
    latest_ts_str = str(md.latest_ts)[:19] if md.latest_ts else "(no data)"
    n_recent = min(len(payload.recent_signals), _MAX_RECENT_SIGNALS_IN_PROMPT)
    n_total_recent = len(payload.recent_signals)

    return f"""You are a quantitative trading strategy analyst reviewing backtesting data from a Korean paper trading system (KIS VTS).

CRITICAL INSTRUCTIONS:
- Do NOT provide investment advice. Do NOT recommend buying or selling any asset.
- Focus ONLY on evaluating the strategy system and suggesting improvements.
- Clearly distinguish between signal-based simulated outcomes and actual executed trade performance.
- For SELL signals, directional_return_pct > 0 means the price fell as expected (good outcome).
- When data is insufficient, explicitly state this in your analysis.
- Output must be structured using EXACTLY the section headers specified at the end.

=== STRATEGY METADATA ===
Strategy Name : {s.strategy_name} (strategy_id={s.strategy_id})
Version       : v{s.version_no} (strategy_version_id={s.strategy_version_id})
Status        : {s.status}
Parameters    : {params_str}

=== SIGNAL PERFORMANCE SUMMARY (simulated, hypothetical entry) ===
Total Signals    : {p.total_signals}
Analyzed         : {p.analyzed_signals}  (market data available)
Skipped          : {p.skipped_signals}   (insufficient market data)

{_horizon_table(p.by_horizon)}

By Signal Type:
{_signal_type_table(p.by_signal_type)}

By Symbol (top {_MAX_SYMBOLS_IN_PROMPT}):
{_symbol_table(p.by_symbol)}

=== ACTUAL TRADING PERFORMANCE (executed trades only) ===
{_actual_trading_section(p.actual_trading)}

=== MARKET DATA ===
Symbols            : {symbols_str}
Timeframes         : {timeframes_str}
Latest Data        : {latest_ts_str}
Total Candles      : {md.row_count}

=== RECENT SIGNALS (last {n_recent} of {n_total_recent}, core fields only) ===
{_recent_signals_section(payload.recent_signals)}

=== DATA LIMITATIONS ===
{_limitations_section(ctx.limitations)}

=== ANALYSIS REQUEST ===
Analyze this strategy version and provide your assessment using EXACTLY these section headers:

## Summary
2-3 sentence high-level overview of signal quality and overall performance.

## Signal Quality
Assess win rates and directional returns. Is the signal generation meaningful or near-random?

## Horizon Analysis
Which time horizons (5m/15m/30m/60m) show the strongest signal quality? Does edge decay over time?

## BUY vs SELL
Compare BUY and SELL signal performance. Which direction shows better quality?

## Symbol Bias
Is performance distributed across symbols or concentrated in a few? Name specific symbols if notable.

## Actual Trading vs Signal Outcome
Compare simulated signal-based outcomes with actual executed trade results. Note any discrepancies.

## Risks / Data Limitations
List key risks and data gaps that limit the reliability of this analysis.

## Improvement Ideas
Suggest 2-3 concrete parameter or logic changes that could improve signal quality.

## Next Experiments
Propose 2-3 specific, testable experiments to validate your improvement hypotheses.""".strip()


def _build_risk_prompt(payload: StrategyAnalysisInputRead) -> str:
    s = payload.strategy
    p = payload.performance
    md = payload.market_data
    ctx = payload.analysis_context

    params_str = _compress_params(s.parameters)
    mae_lines = []
    for h in p.by_horizon:
        mae_str = _pct(h.avg_mae_pct) if h.avg_mae_pct is not None else "N/A"
        mfe_str = _pct(h.avg_mfe_pct) if h.avg_mfe_pct is not None else "N/A"
        wr_str = _pct(h.win_rate, as_rate=True) if h.count > 0 else "N/A"
        mae_lines.append(
            f"  {h.horizon_minutes}m: Win={wr_str}, MFE={mfe_str}, MAE={mae_str}, Count={h.count}"
        )

    return f"""You are a quantitative trading risk analyst reviewing a Korean paper trading strategy.

CRITICAL INSTRUCTIONS:
- Do NOT provide investment advice.
- Focus on identifying risks, failure modes, and reliability issues.
- Distinguish between simulated signal outcomes and actual trade performance.
- Quantify uncertainty explicitly where data is limited.

=== STRATEGY ===
{s.strategy_name} v{s.version_no} | Status: {s.status}
Parameters: {params_str}

=== RISK INDICATORS ===
Total Signals: {p.total_signals} | Analyzed: {p.analyzed_signals} | Skipped: {p.skipped_signals}
Market Data  : {md.row_count} candles | Symbols: {", ".join(md.symbols) or "(none)"}

MFE / MAE / Win Rate by Horizon:
{chr(10).join(mae_lines)}

By Symbol (top {_MAX_SYMBOLS_IN_PROMPT}):
{_symbol_table(p.by_symbol)}

Actual Trading:
{_actual_trading_section(p.actual_trading)}

=== DATA LIMITATIONS ===
{_limitations_section(ctx.limitations)}

=== RISK ANALYSIS REQUEST ===
Provide risk assessment using EXACTLY these section headers:

## Loss Probability
Assess likelihood of loss based on win rates and MAE values across horizons.

## MAE / MFE Analysis
Is the strategy risking more (MAE) than it gains (MFE)?

## Symbol Concentration Risk
Is performance reliable across symbols or dangerously concentrated?

## Data Sufficiency
Is there enough signal data to draw reliable conclusions?

## Market Data Gaps
Are there gaps in market data that could distort the analysis?

## Live Trading Risks
What risks emerge when transitioning from paper trading signals to live execution?

## Risk Mitigation Suggestions
Propose 2-3 specific risk controls or safeguards for this strategy.""".strip()


def _build_improvement_prompt(payload: StrategyAnalysisInputRead) -> str:
    s = payload.strategy
    p = payload.performance
    ctx = payload.analysis_context

    params_str = _compress_params(s.parameters)

    return f"""You are a quantitative strategy engineer optimizing a Korean paper trading strategy.

CRITICAL INSTRUCTIONS:
- Do NOT provide investment advice.
- Focus on parameter optimization and logic improvements only.
- All suggestions must be testable with the existing backtesting framework.
- Distinguish between short-term parameter tuning and structural improvements.

=== CURRENT STRATEGY ===
{s.strategy_name} v{s.version_no} | Status: {s.status}
Parameters: {params_str}

=== CURRENT PERFORMANCE ===
Signals: {p.total_signals} total, {p.analyzed_signals} analyzed, {p.skipped_signals} skipped

{_horizon_table(p.by_horizon)}

By Signal Type:
{_signal_type_table(p.by_signal_type)}

By Symbol (top {_MAX_SYMBOLS_IN_PROMPT}):
{_symbol_table(p.by_symbol)}

=== DATA LIMITATIONS ===
{_limitations_section(ctx.limitations)}

=== IMPROVEMENT ANALYSIS REQUEST ===
Provide improvement suggestions using EXACTLY these section headers:

## Parameter Tuning
What parameter changes (e.g. short_window, long_window, timeframe) could improve performance?

## Signal Filter Ideas
What additional conditions or filters could reduce false signals?

## BUY vs SELL Separation
Should BUY and SELL logic be handled separately? What evidence supports this?

## Horizon Optimization
Which horizon is most reliable? Should the strategy be optimized for a specific target horizon?

## Structural Improvements
What deeper architecture changes would most improve this strategy type?

## Prioritized Action Plan
List 3 improvement actions in order of expected impact, with rationale.""".strip()


# ---------------------------------------------------------------------------
# warnings builder
# ---------------------------------------------------------------------------


def _build_warnings(payload: StrategyAnalysisInputRead) -> list[str]:
    warnings: list[str] = []
    p = payload.performance

    if p.actual_trading is None or p.actual_trading.total_pnl_amount is None:
        warnings.append("Actual trading PnL may be incomplete.")

    if p.total_signals > _MAX_RECENT_SIGNALS_IN_PROMPT:
        warnings.append(
            f"Only recent {_MAX_RECENT_SIGNALS_IN_PROMPT} signals are included in the prompt."
        )

    if p.skipped_signals > 0:
        warnings.append(
            f"{p.skipped_signals} signal(s) skipped due to insufficient market data."
        )

    if p.analyzed_signals < 10:
        warnings.append(
            "Fewer than 10 signals analyzed — results may not be statistically reliable."
        )

    if not payload.market_data.symbols:
        warnings.append("No market data symbols found for this strategy version.")

    return warnings


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------


class StrategyAnalysisPromptService:
    def __init__(self, session: AsyncSession) -> None:
        self._input_svc = StrategyAnalysisInputService(session)

    async def get_prompt(
        self,
        strategy_id: int,
        version_id: int,
        prompt_type: str,
        extra_context: str | None = None,
    ) -> StrategyAnalysisPromptRead | None:
        """prompt를 생성하고 length guard를 적용한 뒤 반환한다.

        strategy/version을 찾을 수 없으면 None.
        unsupported prompt_type이면 UnsupportedPromptTypeError.
        extra_context가 있으면 프롬프트 끝에 추가 컨텍스트 블록으로 덧붙인다(C-2.55).
        """
        if prompt_type not in SUPPORTED_PROMPT_TYPES:
            raise UnsupportedPromptTypeError(prompt_type)

        payload = await self._input_svc.get_analysis_input(strategy_id, version_id)
        if payload is None:
            return None

        if prompt_type == "overview":
            prompt_text = _build_overview_prompt(payload)
        elif prompt_type == "risk":
            prompt_text = _build_risk_prompt(payload)
        else:  # "improvement"
            prompt_text = _build_improvement_prompt(payload)

        if extra_context:
            prompt_text = f"{prompt_text}\n\n{extra_context}"

        warnings = _build_warnings(payload)
        prompt_text, truncated = _apply_length_guard(prompt_text, warnings)

        included_signals = min(len(payload.recent_signals), _MAX_RECENT_SIGNALS_IN_PROMPT)
        included_symbols = min(len(payload.performance.by_symbol), _MAX_SYMBOLS_IN_PROMPT)

        return StrategyAnalysisPromptRead(
            strategy_id=strategy_id,
            strategy_version_id=version_id,
            prompt_type=prompt_type,
            prompt=prompt_text,
            prompt_length=len(prompt_text),
            truncated=truncated,
            input_summary=AnalysisPromptInputSummary(
                total_signals=payload.performance.total_signals,
                analyzed_signals=payload.performance.analyzed_signals,
                symbols=payload.market_data.symbols,
                timeframes=payload.market_data.timeframes,
                max_prompt_length=_MAX_PROMPT_CHARS,
                included_recent_signals_count=included_signals,
                included_symbols_count=included_symbols,
            ),
            warnings=warnings,
        )
