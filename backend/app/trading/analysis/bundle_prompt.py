"""분석 번들(C-2.53)을 LLM 프롬프트용 압축 텍스트 블록으로 변환한다 (C-2.55).

원칙: 원시 캔들 배열은 넣지 않는다. 매매별 '사전계산 지표'(VWAP 대비/레인지 위치/거래량
z-score/MFE·MAE)와 당일 요약·특이분봉·매크로·뉴스·활동진단만 압축해 넘긴다 — 토큰을
줄이고 LLM이 산수하지 않게 한다. 순수 함수.
"""
from __future__ import annotations

_MAX_TRADES = 12
_MAX_NOTABLE = 10
_MAX_NEWS = 8


def _fmt_num(v, suffix: str = "") -> str:
    if v is None:
        return "n/a"
    return f"{v}{suffix}"


def _trade_line(t: dict) -> str:
    f = t.get("features", {})
    status = t.get("status", "?")
    basis = f.get("excursion_basis", "")
    realized = f.get("realized_return_pct")
    realized_txt = "미실현" if realized is None else f"실현 {realized}%"
    return (
        f"- {t.get('side')} {t.get('entry_price')} (status={status}, {realized_txt}, "
        f"VWAP대비 {_fmt_num(f.get('entry_vs_vwap_pct'), '%')}, "
        f"레인지위치 {_fmt_num(f.get('entry_range_percentile'), '%')}, "
        f"거래량z {_fmt_num(f.get('entry_volume_zscore'))}, "
        f"MFE {_fmt_num(f.get('mfe_pct'), '%')} MAE {_fmt_num(f.get('mae_pct'), '%')}"
        f"{(' [' + basis + ']') if basis else ''})"
    )


def format_bundle_for_prompt(bundle: dict, assessment: dict | None = None) -> str:
    """번들 + 활동진단을 압축 텍스트 블록으로 만든다."""
    lines: list[str] = ["[추가 컨텍스트 — 그날 매매 테이프 / 매크로 / 뉴스 / 활동 진단]"]

    if assessment:
        lines.append(
            f"■ 활동 진단: band={assessment.get('band')}, 신호 {assessment.get('signal_count')}건, "
            f"시장활발={assessment.get('market_active')} — {assessment.get('reason', '')}"
        )

    macro = bundle.get("macro") or {}
    if macro.get("regime") and macro.get("regime") != "unknown":
        lines.append(
            f"■ 전일 미국장 매크로: regime={macro.get('regime')}, "
            f"VIX {_fmt_num(macro.get('vix'))}({macro.get('vix_level')}), "
            f"미국장 {macro.get('us_trend')}, 반도체 {macro.get('semis_strength')} "
            f"(기준일 {macro.get('session_date')})"
        )
    else:
        lines.append("■ 전일 미국장 매크로: 데이터 없음(unknown)")

    # C-6.11: 인트라데이 변동성 레짐 — 그날 장이 평소보다 얼마나 요동쳤는지.
    regime = bundle.get("intraday_regime")
    if regime:
        lines.append(
            f"■ 당일 변동성 레짐: {regime.get('regime')} "
            f"(평소 대비 배율 {_fmt_num(regime.get('vol_ratio'))}, "
            f"표본 {regime.get('symbols_used')}종목) — "
            "elevated/extreme이면 신호 노이즈·슬리피지 증가 가능성을 감안하라"
        )

    tape = bundle.get("trade_tape") or {}
    summ = tape.get("day_summary")
    if summ:
        lines.append(
            f"■ 당일 시세: 시 {summ.get('open')} 고 {summ.get('high')} 저 {summ.get('low')} "
            f"종 {summ.get('close')}, VWAP {summ.get('vwap')}, 레인지 {_fmt_num(summ.get('range_pct'), '%')}, "
            f"분봉 {summ.get('candle_count')}개"
        )
    trades = tape.get("trades") or []
    if trades:
        lines.append(f"■ 그날 매매({len(trades)}건):")
        lines.extend(_trade_line(t) for t in trades[:_MAX_TRADES])
        if len(trades) > _MAX_TRADES:
            lines.append(f"  …외 {len(trades) - _MAX_TRADES}건")
    else:
        lines.append("■ 그날 매매: 없음")

    notable = tape.get("notable_events") or []
    if notable:
        items = "; ".join(
            f"{n.get('ts', '')[11:16]} {_fmt_num(n.get('return_pct'), '%')} "
            f"[{','.join(n.get('reasons', []))}]"
            for n in notable[:_MAX_NOTABLE]
        )
        lines.append(f"■ 특이 분봉({len(notable)}): {items}")

    news = bundle.get("news") or []
    if news:
        items = "; ".join(
            f"[{n.get('source', '?')}/{n.get('category', '?')}] {n.get('headline', '')}"
            for n in news[:_MAX_NEWS]
        )
        lines.append(f"■ 종목 뉴스·공시({len(news)}, 중요도순): {items}")
    else:
        lines.append("■ 종목 뉴스·공시: 없음(또는 중요도 미달로 제외)")

    retro = bundle.get("retrospective") or {}
    if retro.get("total"):
        lines.append(
            f"■ 과거 AI 제안 회고: 총 {retro.get('total')}건 — 개선 {retro.get('improved', 0)}, "
            f"악화 {retro.get('worse', 0)}, 판단보류 {retro.get('inconclusive', 0)}. "
            "(악화가 많으면 제안에 더 신중하라)"
        )

    note = bundle.get("analyst_note")
    if note:
        lines.append(f"■ 애널리스트 노트(사람 입력): {note}")

    lines.append(
        "지시: 위 데이터를 근거로 이 매매/전략의 실수와 개선 가설을 '구체적 파라미터 수준'으로 진단하라. "
        "신호가 적고 시장이 활발했다면 진입 조건이 과도하게 빡센지 함께 판단하라."
    )
    return "\n".join(lines)
