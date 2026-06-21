"""C-4: 유니버스 신호 스캔용 스타터 전략 시드.

서로 다른 매매 원리의 전략 4종을 universe(기본 watchlist) 전체에 신호를 내는
TESTING 버전으로 생성한다. 종목을 하나씩 지정하지 않아도 관심종목(또는 스캐너 후보)
전체에서 신호가 쌓인다.

기본 dry-run(DB 변경 없음). --apply 지정 시에만 실제 생성.
멱등: 같은 strategy_type의 universe 전략이 이미 TESTING/ACTIVE면 skip.

안전:
    - 유니버스 모드는 신호 생성 전용 — auto_trade_enabled=False (강제).
    - broker.place_order 등 실주문 API 호출 없음.
    - 새 스케줄러 잡 추가 없음(기존 strategy_runner가 TESTING 버전을 그대로 실행).

사용법:
    .venv/bin/python scripts/create_universe_strategies.py
    .venv/bin/python scripts/create_universe_strategies.py --apply
    .venv/bin/python scripts/create_universe_strategies.py --apply --universe scanner_candidates
    .venv/bin/python scripts/create_universe_strategies.py --apply --timeframe 1d
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


# ---------------------------------------------------------------------------
# 생성할 스타터 전략 정의 (서로 다른 매매 원리 4종)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StrategyDef:
    parent_name: str
    strategy_type: str
    params: dict


_DEFS: list[StrategyDef] = [
    StrategyDef(
        parent_name="[유니버스] RSI 평균회귀",
        strategy_type="rsi_reversion",
        params={"rsi_period": 14, "oversold": 30, "overbought": 70, "exit_mode": "overbought"},
    ),
    StrategyDef(
        parent_name="[유니버스] MACD 추세추종",
        strategy_type="macd_trend",
        params={"fast_period": 12, "slow_period": 26, "signal_period": 9, "require_above_zero": False},
    ),
    StrategyDef(
        parent_name="[유니버스] 전고점 돌파",
        strategy_type="breakout_high",
        params={"breakout_lookback": 20, "exit_lookback": 10, "volume_confirm": False},
    ),
    StrategyDef(
        parent_name="[유니버스] 눌림목 매수",
        strategy_type="pullback_trend",
        params={"short_window": 10, "long_window": 50},
    ),
]


@dataclass
class SeedResult:
    strategy_type: str
    parent_name: str
    action: str  # "created" | "skipped_exists" | "dry_run"
    strategy_version_id: int | None = None
    note: str = ""


def _build_params(defn: StrategyDef, universe: str, timeframe: str) -> dict:
    """전략 파라미터 dict를 만들고 StrategyVersionParameters로 검증한다."""
    from app.trading.strategy.schemas import StrategyVersionParameters

    raw = {
        "strategy_type": defn.strategy_type,
        "universe": universe,
        "quantity": 1,
        "timeframe": timeframe,
        "enabled": True,
        "auto_trade_enabled": False,  # 유니버스 모드는 신호 전용
        **defn.params,
    }
    # 검증(잘못된 파라미터면 여기서 즉시 실패) 후 정규화된 dict 반환
    return StrategyVersionParameters.model_validate(raw).model_dump()


async def _find_existing(session, strategy_type: str, universe: str):
    from sqlalchemy import select

    from app.domain.models.enums import StrategyVersionStatus
    from app.domain.models.strategy import StrategyVersion

    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.parameters["strategy_type"].astext == strategy_type)
        .where(StrategyVersion.parameters["universe"].astext == universe)
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
                action="dry_run", note=f"would create TESTING (universe={universe})",
            ))
            continue

        strategy = Strategy(name=defn.parent_name, description="C-4 유니버스 스타터 전략")
        session.add(strategy)
        await session.flush()
        version = StrategyVersion(
            strategy_id=strategy.id, version_no=1, parameters=params,
            change_description=f"유니버스 신호 스캔 ({universe}, TESTING)",
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
    print(f"\n{'=' * 64}\n유니버스 스타터 전략 시드 {mode}  (universe={universe}, timeframe={timeframe})\n{'=' * 64}")
    for r in results:
        icon = {"created": "✅", "skipped_exists": "⏭️", "dry_run": "•"}.get(r.action, "•")
        print(f"  {icon} {r.parent_name:<22} [{r.strategy_type}] — {r.note}")
    print("  ※ 모두 auto_trade off(신호 전용), 상태 TESTING. 실주문 없음.")
    print("=" * 64)
    if dry_run:
        print("dry-run 입니다. 실제 생성하려면 --apply 를 붙여 다시 실행하세요.")


async def main(apply: bool, universe: str, timeframe: str) -> int:
    from app.db.session import async_session_factory, engine

    async with async_session_factory() as session:
        results = await run(session, apply=apply, universe=universe, timeframe=timeframe)
    await engine.dispose()
    _print(results, dry_run=not apply, universe=universe, timeframe=timeframe)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C-4 유니버스 스타터 전략 시드")
    parser.add_argument("--apply", action="store_true", default=False, help="DB에 실제 생성. 미지정 시 dry-run.")
    parser.add_argument(
        "--universe", default="watchlist", choices=["watchlist", "scanner_candidates"],
        help="신호를 낼 유니버스 (기본: watchlist).",
    )
    parser.add_argument("--timeframe", default="5m", help="캔들 타임프레임 (기본: 5m).")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply, universe=args.universe, timeframe=args.timeframe)))
