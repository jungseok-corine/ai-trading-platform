"""유명 전략 카탈로그 + 자동 입학시험 (C-7.2).

검증된 고전 매매 전략을 DSL 스펙으로 시드하고, 백테스트 입학시험(C-7.5 기준)을
통과한 것만 pending 제안으로 만든다. **승인은 사람 — 어떤 전략도 검증·승인 없이
배치되지 않는다.**

출처는 각 스펙의 source에 기록한다. 실패한 스펙도 백테스트 run은 보존된다(학습 재료).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.strategy import Strategy
from app.domain.models.strategy_proposal import StrategyProposal
from app.services.backtest_service import BacktestService
from app.services.proposal_service import ProposalService
from app.trading.strategy.rule_dsl import validate_rule_spec

logger = logging.getLogger(__name__)

# ── 입학시험 기준 (C-7.5) ────────────────────────────────────────────────
ADMISSION_MIN_TRADES = 5
ADMISSION_MAX_MDD_PCT = 35.0


def passes_admission(agg: dict[str, Any]) -> tuple[bool, str]:
    """백테스트 집계가 입학 기준을 통과하는지. (통과여부, 사유)"""
    trades = agg.get("trade_count") or 0
    ret = agg.get("return_pct")
    mdd = agg.get("max_drawdown_pct")
    bh = agg.get("buy_hold_return_pct")
    if ret is None or mdd is None:
        return False, "백테스트 실패 (데이터 부족)"
    if trades < ADMISSION_MIN_TRADES:
        return False, f"거래 수 부족 ({trades} < {ADMISSION_MIN_TRADES})"
    if ret <= 0:
        return False, f"수익률 음수 ({ret:.1f}%)"
    if mdd >= ADMISSION_MAX_MDD_PCT:
        return False, f"MDD 과대 ({mdd:.1f}% >= {ADMISSION_MAX_MDD_PCT}%)"
    # 단순보유 대비: 수익 우위 또는 (수익은 낮아도) 방어 가치 인정 — 보유 수익의 30% 이상
    if bh is not None and bh > 0 and ret < bh * 0.3:
        return False, f"보유 대비 열위 (전략 {ret:.1f}% vs 보유 {bh:.1f}%)"
    return True, f"통과 (수익 {ret:.1f}%, 거래 {trades}, MDD {mdd:.1f}%)"


# ── 카탈로그: 유명 전략 DSL 스펙 ─────────────────────────────────────────
# 각 항목: 이름, 출처/원리, 적합 레짐 태그(D-31), DSL 스펙
CATALOG: list[dict[str, Any]] = [
    {
        "regime_fit": "range",
        "spec": {
            "name": "bollinger_bounce",
            "source": "볼린저 밴드 평균회귀 (John Bollinger) — 하단 이탈 + RSI 과매도 반등 매수, 중심선 회귀 청산",
            "indicators": {
                "bb_lower": {"fn": "bollinger_lower", "period": 20, "num_std": 2.0},
                "bb_mid": {"fn": "bollinger_mid", "period": 20},
                "rsi14": {"fn": "rsi", "period": 14},
            },
            "entry": {"op": "and", "args": [
                {"op": "lt", "left": {"ref": "price"}, "right": {"ref": "bb_lower"}},
                {"op": "lt", "left": {"ref": "rsi14"}, "right": {"const": 35}},
            ]},
            "exit": {"op": "crosses_above", "left": {"ref": "price"}, "right": {"ref": "bb_mid"}},
        },
    },
    {
        "regime_fit": "trend",
        "spec": {
            "name": "turtle_donchian",
            "source": "터틀 트레이딩 (Richard Dennis) — 20일 신고가 돌파 진입, 10일 신저가 이탈 청산",
            "indicators": {
                "hh20": {"fn": "highest_high", "period": 20},
                "ll10": {"fn": "lowest_low", "period": 10},
            },
            "entry": {"op": "crosses_above", "left": {"ref": "price"}, "right": {"ref": "hh20"}},
            "exit": {"op": "crosses_below", "left": {"ref": "price"}, "right": {"ref": "ll10"}},
        },
    },
    {
        "regime_fit": "trend",
        "spec": {
            "name": "golden_cross_volume",
            "source": "골든크로스 + 거래량 확인 — 20/60 이평 교차를 거래량 급증으로 필터",
            "indicators": {
                "sma20": {"fn": "sma", "period": 20},
                "sma60": {"fn": "sma", "period": 60},
                "vr20": {"fn": "volume_ratio", "period": 20},
            },
            "entry": {"op": "and", "args": [
                {"op": "crosses_above", "left": {"ref": "sma20"}, "right": {"ref": "sma60"}},
                {"op": "gt", "left": {"ref": "vr20"}, "right": {"const": 1.2}},
            ]},
            "exit": {"op": "crosses_below", "left": {"ref": "sma20"}, "right": {"ref": "sma60"}},
        },
    },
    {
        "regime_fit": "range",
        "spec": {
            "name": "stochastic_reversal",
            "source": "스토캐스틱 과매도 반전 (George Lane) — %K 20 이하 진입, 80 이상 청산",
            "indicators": {
                "stoch": {"fn": "stochastic_k", "period": 14},
                "rsi14": {"fn": "rsi", "period": 14},
            },
            "entry": {"op": "and", "args": [
                {"op": "lt", "left": {"ref": "stoch"}, "right": {"const": 20}},
                {"op": "lt", "left": {"ref": "rsi14"}, "right": {"const": 45}},
            ]},
            "exit": {"op": "gt", "left": {"ref": "stoch"}, "right": {"const": 80}},
        },
    },
    {
        "regime_fit": "trend",
        "spec": {
            "name": "macd_positive_cross",
            "source": "MACD 시그널 교차 (Gerald Appel) — 0선 위 골든크로스만 취하는 추세 확인형",
            "indicators": {
                "macd": {"fn": "macd_line", "fast": 12, "slow": 26, "signal": 9},
                "sig": {"fn": "macd_signal", "fast": 12, "slow": 26, "signal": 9},
            },
            "entry": {"op": "and", "args": [
                {"op": "crosses_above", "left": {"ref": "macd"}, "right": {"ref": "sig"}},
                {"op": "gt", "left": {"ref": "macd"}, "right": {"const": 0}},
            ]},
            "exit": {"op": "crosses_below", "left": {"ref": "macd"}, "right": {"ref": "sig"}},
        },
    },
    {
        "regime_fit": "trend",
        "spec": {
            "name": "dual_momentum_lite",
            "source": "듀얼 모멘텀 단순화 (Gary Antonacci) — 장기 절대 모멘텀 양수 + 단기 이평 상향 교차",
            "indicators": {
                "mom60": {"fn": "return_pct", "lookback": 60},
                "sma20": {"fn": "sma", "period": 20},
                "mom20": {"fn": "return_pct", "lookback": 20},
            },
            "entry": {"op": "and", "args": [
                {"op": "gt", "left": {"ref": "mom60"}, "right": {"const": 0}},
                {"op": "crosses_above", "left": {"ref": "price"}, "right": {"ref": "sma20"}},
            ]},
            "exit": {"op": "or", "args": [
                {"op": "lt", "left": {"ref": "mom20"}, "right": {"const": -5}},
                {"op": "crosses_below", "left": {"ref": "price"}, "right": {"ref": "sma20"}},
            ]},
        },
    },
]

# 입학시험 대상 심볼 (일봉 1년 데이터 보유 대형주)
EXAM_SYMBOLS = ["005930", "000660", "005380", "035420", "051910"]


class StrategyCatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._backtest = BacktestService(session)
        self._proposals = ProposalService(session)

    async def seed_and_validate(self, exam_days: int = 365) -> list[dict[str, Any]]:
        """카탈로그 전체를 입학시험에 응시시키고, 통과분만 pending 제안을 만든다."""
        results: list[dict[str, Any]] = []
        for entry in CATALOG:
            spec = entry["spec"]
            validate_rule_spec(spec)  # 카탈로그 자체 결함은 즉시 실패
            agg = await self._exam(spec, exam_days)
            passed, reason = passes_admission(agg)
            item: dict[str, Any] = {
                "name": spec["name"], "regime_fit": entry["regime_fit"],
                "passed": passed, "reason": reason, "exam": agg,
            }
            if passed:
                proposal = await self._create_proposal(entry, agg)
                item["proposal_id"] = proposal.id if proposal else None
                item["deduped"] = proposal is None
            results.append(item)
        return results

    async def _exam(self, spec: dict, exam_days: int) -> dict[str, Any]:
        """5대형주 일봉 백테스트 집계 (제안 유니버스 레그와 같은 방식)."""
        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(days=exam_days)
        legs = []
        for symbol in EXAM_SYMBOLS:
            run = await self._backtest.run(
                strategy_type="rule_based",
                parameters={"rule_spec": spec, "quantity": 1, "timeframe": "1d"},
                symbol_code=symbol, timeframe="1d",
                start_ts=start_ts, end_ts=end_ts,
            )
            if run.status == "succeeded" and run.metrics:
                legs.append(run.metrics)
        if not legs:
            return {"symbols_used": 0}
        n = len(legs)
        return {
            "symbols_used": n,
            "trade_count": sum(m["trade_count"] for m in legs),
            "return_pct": sum(m["return_pct"] for m in legs) / n,
            "max_drawdown_pct": sum(m["max_drawdown_pct"] for m in legs) / n,
            "buy_hold_return_pct": sum(m["buy_hold_return_pct"] for m in legs) / n,
            "win_rate": (
                sum((m["win_rate"] or 0) * m["trade_count"] for m in legs)
                / max(1, sum(m["trade_count"] for m in legs))
            ),
        }

    async def _create_proposal(
        self, entry: dict, agg: dict, source: str = "catalog"
    ) -> StrategyProposal | None:
        """통과 스펙의 pending 제안 생성. 같은 이름의 기존 pending/approved가 있으면 skip."""
        spec = entry["spec"]
        label = "카탈로그" if source == "catalog" else "AI리서치"
        title = f"[{label}] {spec['name']} — 입학시험 통과"
        existing = (
            await self._session.execute(
                select(StrategyProposal).where(
                    StrategyProposal.title == title,
                    StrategyProposal.status.in_(["pending", "approved"]),
                )
            )
        ).scalars().first()
        if existing is not None:
            return None

        strategy = await self._get_or_create_parent(spec)
        params = {
            "strategy_type": "rule_based",
            "rule_spec": spec,
            "symbol_code": "005930",
            "timeframe": "1d",
            "quantity": 1,
            "market": "KR",
            "enabled": True,
            "auto_trade_enabled": False,
            "regime_fit": entry["regime_fit"],
        }
        return await self._proposals.create_proposal(
            strategy_id=strategy.id,
            suggested_parameters=params,
            title=title,
            summary=(
                f"5대형주 일봉 1년 입학시험: 평균 수익 {agg['return_pct']:.1f}%, "
                f"거래 {agg['trade_count']}회, 승률 {agg['win_rate']*100:.0f}%, "
                f"MDD {agg['max_drawdown_pct']:.1f}% (보유 평균 {agg['buy_hold_return_pct']:.1f}%)"
            ),
            rationale=spec["source"],
            risk_notes=(
                f"적합 레짐: {entry['regime_fit']} (D-31 — 부적합 국면에서는 성과 저하 가능). "
                "승인 시 TESTING·신호 전용으로 paper 검증부터."
            ),
            source=source,
        )

    async def _get_or_create_parent(self, spec: dict) -> Strategy:
        name = f"[카탈로그] {spec['name']}"
        existing = (
            await self._session.execute(select(Strategy).where(Strategy.name == name))
        ).scalars().first()
        if existing is not None:
            return existing
        strategy = Strategy(name=name, description=spec["source"])
        self._session.add(strategy)
        await self._session.flush()
        return strategy
