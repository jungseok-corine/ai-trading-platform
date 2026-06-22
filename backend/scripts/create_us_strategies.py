"""C-5: 미국장(US) 유니버스 전략 시드.

미국 관심종목(universe=watchlist, universe_market=US)에 신호를 내는 전략을 생성한다.
사용자 요청의 '급등 모멘텀'(momentum_surge)을 포함해, 미국 급등주 초입을 노리는
전략과 보조 전략 몇 종을 TESTING 상태로 만든다.

기본 dry-run(DB 변경 없음). --apply 지정 시에만 실제 생성.
멱등: 같은 strategy_type + universe + universe_market 전략이 이미 TESTING/ACTIVE면 skip.

안전:
    - 유니버스 모드는 신호 생성 전용 — auto_trade_enabled=False(강제).
    - 실주문 API 호출 없음. 새 스케줄러 잡 없음(기존 strategy_runner가 실행).
    - 미국 시세는 실전 키(KIS_REAL_APP_KEY/SECRET)와 해외주식 서비스 신청이 필요하다.

사용법:
    .venv/bin/python scripts/create_us_strategies.py
    .venv/bin/python scripts/create_us_strategies.py --apply
    .venv/bin/python scripts/create_us_strategies.py --apply --timeframe 1m
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_ENV_FILE = _BACKEND_DIR / ".env"
if _ENV_FILE.exists():
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(dotenv_path=_ENV_FILE, override=False)


@dataclass(frozen=True)
class StrategyDef:
    parent_name: str
    strategy_type: str
    params: dict


_DEFS: list[StrategyDef] = [
    # 사용자 요청: 미국 급등주 초입 진입(단기 급등 + 거래량 급증).
    StrategyDef(
        parent_name="[US] 급등 모멘텀",
        strategy_type="momentum_surge",
        params={
            "surge_lookback": 5, "surge_threshold_pct": 5.0, "exit_drop_pct": 3.0,
            "volume_window": 20, "volume_multiplier": 2.0,
        },
    ),
    # 보조: 신고가 돌파(거래량 확인) — 추세 추종형.
    StrategyDef(
        parent_name="[US] 전고점 돌파",
        strategy_type="breakout_high",
        params={"breakout_lookback": 20, "exit_lookback": 10, "volume_confirm": True,
                "volume_window": 20, "volume_multiplier": 1.5},
    ),
    # 보조: RSI 평균회귀.
    StrategyDef(
        parent_name="[US] RSI 평균회귀",
        strategy_type="rsi_reversion",
        params={"rsi_period": 14, "oversold": 30, "overbought": 70, "exit_mode": "overbought"},
    ),
]


@dataclass
class SeedResult:
    strategy_type: str
    parent_name: str
    action: str
    strategy_version_id: int | None = None
    note: str = ""


def _build_params(defn: StrategyDef, universe: str, timeframe: str) -> dict:
    from app.trading.strategy.schemas import StrategyVersionParameters

    raw = {
        "strategy_type": defn.strategy_type,
        "universe": universe,
        "universe_market": "US",
        "market": "US",
        "exchange": "NAS",
        "quantity": 1,
        "timeframe": timeframe,
        "enabled": True,
        "auto_trade_enabled": False,  # 유니버스 모드는 신호 전용
        **defn.params,
    }
    return StrategyVersionParameters.model_validate(raw).model_dump()


async def _find_existing(session, strategy_type: str, universe: str):
    from sqlalchemy import select

    from app.domain.models.enums import StrategyVersionStatus
    from app.domain.models.strategy import StrategyVersion

    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.parameters["strategy_type"].astext == strategy_type)
        .where(StrategyVersion.parameters["universe"].astext == universe)
        .where(StrategyVersion.parameters["universe_market"].astext == "US")
        .where(
            StrategyVersion.status.in_(
                (StrategyVersionStatus.TESTING, StrategyVersionStatus.ACTIVE)
            )
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def run(session, *, apply: bool, universe: str, timeframe: str) -> list[SeedResult]:
    from app.domain.models.enums import StrategyVersionStatus
    from app.domain.models.strategy import Strategy, StrategyVersion

    results: list[SeedResult] = []
    for defn in _DEFS:
        params = _build_params(defn, universe, timeframe)

        existing = await _find_existing(session, defn.strategy_type, universe)
        if existing is not None:
            results.append(SeedResult(
                strategy_type=defn.strategy_type, parent_name=defn.parent_name,
                action="skipped_exists", strategy_version_id=existing.id,
                note=f"id={existing.id} status={existing.status.value} → skip",
            ))
            continue

        if not apply:
            results.append(SeedResult(
                strategy_type=defn.strategy_type, parent_name=defn.parent_name,
                action="dry_run", note=f"would create TESTING (universe={universe}, US)",
            ))
            continue

        strategy = Strategy(name=defn.parent_name, description="C-5 미국장 유니버스 전략")
        session.add(strategy)
        await session.flush()
        version = StrategyVersion(
            strategy_id=strategy.id, version_no=1, parameters=params,
            change_description=f"미국장 유니버스 신호 ({universe}, US, TESTING)",
            status=StrategyVersionStatus.TESTING,
        )
        session.add(version)
        await session.flush()
        results.append(SeedResult(
            strategy_type=defn.strategy_type, parent_name=defn.parent_name,
            action="created", strategy_version_id=version.id,
            note=f"strategy_id={strategy.id} version_id={version.id} TESTING",
        ))

    if apply:
        await session.commit()
    return results


def _print(results: list[SeedResult], *, dry_run: bool, universe: str, timeframe: str) -> None:
    mode = "[DRY-RUN]" if dry_run else "[APPLIED]"
    print(f"\n{'=' * 64}\n미국장 유니버스 전략 시드 {mode}  (universe={universe}, US, timeframe={timeframe})\n{'=' * 64}")
    for r in results:
        icon = {"created": "✅", "skipped_exists": "⏭️", "dry_run": "•"}.get(r.action, "•")
        print(f"  {icon} {r.parent_name:<18} [{r.strategy_type}] — {r.note}")
    print("  ※ 모두 auto_trade off(신호 전용), 상태 TESTING. 실주문 없음.")
    print("  ※ 미국 시세에는 실전 키(KIS_REAL_APP_KEY/SECRET) + 해외주식 신청이 필요합니다.")
    print("=" * 64)
    if dry_run:
        print("dry-run 입니다. 실제 생성하려면 --apply 를 붙여 다시 실행하세요.")


async def main(apply: bool, universe: str, timeframe: str) -> int:
    from scripts._common import db_session

    async with db_session() as session:
        results = await run(session, apply=apply, universe=universe, timeframe=timeframe)
    _print(results, dry_run=not apply, universe=universe, timeframe=timeframe)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C-5 미국장 유니버스 전략 시드")
    parser.add_argument("--apply", action="store_true", default=False, help="DB에 실제 생성. 미지정 시 dry-run.")
    parser.add_argument(
        "--universe", default="watchlist", choices=["watchlist", "scanner_candidates"],
        help="신호를 낼 유니버스 (기본: watchlist).",
    )
    parser.add_argument("--timeframe", default="5m", help="캔들 타임프레임 (기본: 5m).")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply, universe=args.universe, timeframe=args.timeframe)))
