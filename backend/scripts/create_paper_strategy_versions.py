"""C-2.20: PAPER 계좌에 volume_confirmed_ma_cross / flow_confirmed_volume_ma_cross
전략 버전을 DB에 등록하는 스크립트.

기본 dry-run. --apply 옵션이 있어야 실제로 DB에 반영한다.
멱등성 보장: 동일 (strategy_type, symbol_code, account_id)가 이미 존재하면 skip 또는
status=draft인 경우 testing으로 업데이트한다.

사용법:
    # Dry-run (기본)
    .venv/bin/python scripts/create_paper_strategy_versions.py

    # 실제 DB 적용
    .venv/bin/python scripts/create_paper_strategy_versions.py --apply

    # 계좌 지정 (미지정 시 첫 번째 PAPER 계좌 자동 선택)
    .venv/bin/python scripts/create_paper_strategy_versions.py --apply --account-id 230

    # 종목 지정 (기본값: 005930)
    .venv/bin/python scripts/create_paper_strategy_versions.py --apply --symbol-code 005930

금지 사항:
    - broker.place_order를 호출하지 않는다.
    - auto_trade_enabled=true 전략은 생성하지 않는다.
    - LIVE 계좌는 사용하지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_ENV_FILE = _BACKEND_DIR / ".env"
if _ENV_FILE.exists():
    from dotenv import load_dotenv  # type: ignore[import-untyped]
    load_dotenv(dotenv_path=_ENV_FILE, override=False)


# ---------------------------------------------------------------------------
# 생성할 전략 정의
# ---------------------------------------------------------------------------

_VOLUME_CONFIRMED_PARAMS = {
    "strategy_type": "volume_confirmed_ma_cross",
    "short_window": 5,
    "long_window": 20,
    "volume_window": 20,
    "volume_multiplier": 1.5,
    "quantity": 1,
    "timeframe": "5m",
    "enabled": True,
    "auto_trade_enabled": False,
}

_FLOW_CONFIRMED_PARAMS = {
    "strategy_type": "flow_confirmed_volume_ma_cross",
    "short_window": 5,
    "long_window": 20,
    "volume_window": 20,
    "volume_multiplier": 1.5,
    "flow_lookback_days": 5,
    "max_flow_age_days": 5,
    "flow_mode": "foreign_or_institution",
    "require_flow_data": True,
    "quantity": 1,
    "timeframe": "5m",
    "enabled": True,
    "auto_trade_enabled": False,
}

_STRATEGY_DEFINITIONS = [
    {
        "strategy_type": "volume_confirmed_ma_cross",
        "change_description": "거래량 확인 MA크로스 전략 (PAPER TESTING)",
        "base_params": _VOLUME_CONFIRMED_PARAMS,
    },
    {
        "strategy_type": "flow_confirmed_volume_ma_cross",
        "change_description": "수급 확인 MA크로스 전략 (PAPER TESTING)",
        "base_params": _FLOW_CONFIRMED_PARAMS,
    },
]

_PARENT_STRATEGY_NAME = "PAPER 자동매매"


# ---------------------------------------------------------------------------
# 결과 구조체
# ---------------------------------------------------------------------------

@dataclass
class ActivationResult:
    strategy_type: str
    symbol_code: str
    account_id: int
    action: str  # "created" | "updated_to_testing" | "skipped_already_active" | "dry_run"
    strategy_version_id: int | None = None
    existing_status: str | None = None
    note: str = field(default="")


# ---------------------------------------------------------------------------
# 핵심 로직 (import해서 테스트 가능)
# ---------------------------------------------------------------------------

async def _find_paper_account(session, account_id: int | None = None):
    """PAPER 계좌를 찾아 반환한다. account_id가 지정되면 해당 계좌 검증."""
    from sqlalchemy import select
    from app.domain.models.account import Account
    from app.domain.models.enums import AccountType

    if account_id is not None:
        result = await session.execute(select(Account).where(Account.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            raise ValueError(f"account_id={account_id} not found")
        if account.account_type != AccountType.PAPER:
            raise ValueError(
                f"account_id={account_id} is {account.account_type.value} (PAPER만 허용)"
            )
        return account

    result = await session.execute(
        select(Account).where(Account.account_type == AccountType.PAPER).limit(1)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise ValueError("PAPER 계좌가 DB에 없습니다. --account-id로 지정하거나 먼저 계좌를 등록하세요.")
    return account


async def _find_or_create_strategy(session, name: str):
    """Strategy를 이름으로 찾거나 없으면 생성한다."""
    from sqlalchemy import select
    from app.domain.models.strategy import Strategy

    result = await session.execute(select(Strategy).where(Strategy.name == name))
    strategy = result.scalar_one_or_none()
    if strategy is not None:
        return strategy, False

    strategy = Strategy(name=name, description="PAPER 자동매매용 전략 그룹")
    session.add(strategy)
    await session.flush()
    return strategy, True


async def _find_existing_version(session, strategy_type: str, symbol_code: str, account_id: int):
    """JSONB 파라미터 쿼리로 기존 strategy_version을 탐색한다.

    parameters->>'strategy_type' = X AND parameters->>'symbol_code' = Y AND
    parameters->>'account_id' = Z 인 첫 번째 row를 반환한다.
    """
    from sqlalchemy import select
    from app.domain.models.strategy import StrategyVersion

    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.parameters["strategy_type"].astext == strategy_type)
        .where(StrategyVersion.parameters["symbol_code"].astext == symbol_code)
        .where(StrategyVersion.parameters["account_id"].astext == str(account_id))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _run_activation(
    session,
    account_id: int,
    symbol_code: str,
    apply: bool = False,
) -> list[ActivationResult]:
    """각 전략 타입에 대해 TESTING status의 strategy_version을 생성/업데이트한다.

    apply=False: dry-run (DB 변경 없음, 결과만 반환)
    apply=True: 실제 DB 적용
    """
    from sqlalchemy import select
    from app.domain.models.enums import StrategyVersionStatus
    from app.domain.models.strategy import Strategy, StrategyVersion

    results: list[ActivationResult] = []

    for defn in _STRATEGY_DEFINITIONS:
        stype = defn["strategy_type"]

        existing = await _find_existing_version(session, stype, symbol_code, account_id)

        if existing is not None:
            existing_status = existing.status.value
            if existing.status in (StrategyVersionStatus.TESTING, StrategyVersionStatus.ACTIVE):
                results.append(ActivationResult(
                    strategy_type=stype,
                    symbol_code=symbol_code,
                    account_id=account_id,
                    action="skipped_already_active",
                    strategy_version_id=existing.id,
                    existing_status=existing_status,
                    note=f"status={existing_status} → skip",
                ))
                continue

            if existing.status == StrategyVersionStatus.DRAFT:
                if not apply:
                    results.append(ActivationResult(
                        strategy_type=stype,
                        symbol_code=symbol_code,
                        account_id=account_id,
                        action="dry_run",
                        strategy_version_id=existing.id,
                        existing_status=existing_status,
                        note=f"id={existing.id}, status=draft → would update to testing",
                    ))
                    continue

                existing.status = StrategyVersionStatus.TESTING
                await session.flush()
                results.append(ActivationResult(
                    strategy_type=stype,
                    symbol_code=symbol_code,
                    account_id=account_id,
                    action="updated_to_testing",
                    strategy_version_id=existing.id,
                    existing_status="draft",
                    note=f"id={existing.id}: draft → testing",
                ))
                continue

        # 존재하지 않으면 새로 생성
        if not apply:
            results.append(ActivationResult(
                strategy_type=stype,
                symbol_code=symbol_code,
                account_id=account_id,
                action="dry_run",
                note=f"would create {stype} for {symbol_code} under account {account_id}",
            ))
            continue

        strategy, strategy_created = await _find_or_create_strategy(session, _PARENT_STRATEGY_NAME)

        max_version_result = await session.execute(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy.id)
            .order_by(StrategyVersion.version_no.desc())
            .limit(1)
        )
        latest = max_version_result.scalar_one_or_none()
        next_version_no = (latest.version_no + 1) if latest else 1

        params = dict(defn["base_params"])
        params["symbol_code"] = symbol_code
        params["account_id"] = account_id

        version = StrategyVersion(
            strategy_id=strategy.id,
            version_no=next_version_no,
            parameters=params,
            change_description=defn["change_description"],
            status=StrategyVersionStatus.TESTING,
        )
        session.add(version)
        await session.flush()

        results.append(ActivationResult(
            strategy_type=stype,
            symbol_code=symbol_code,
            account_id=account_id,
            action="created",
            strategy_version_id=version.id,
            note=f"id={version.id}, version_no={version.version_no}",
        ))

    return results


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

def _print_results(results: list[ActivationResult], apply: bool) -> None:
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"\n=== create_paper_strategy_versions [{mode}] ===")
    for r in results:
        icon = {
            "created": "[+]",
            "updated_to_testing": "[↑]",
            "skipped_already_active": "[=]",
            "dry_run": "[~]",
        }.get(r.action, "[?]")
        print(f"  {icon} {r.strategy_type} / {r.symbol_code} / account={r.account_id}")
        print(f"       action={r.action}  {r.note}")
    print()
    if not apply:
        print("  → dry-run: DB 변경 없음. --apply 옵션으로 실제 적용하세요.")


async def _main(account_id: int | None, symbol_code: str, apply: bool) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        account = await _find_paper_account(session, account_id)
        print(f"대상 계좌: id={account.id}, type={account.account_type.value}")

        results = await _run_activation(session, account.id, symbol_code, apply=apply)

        if apply:
            await session.commit()

    await engine.dispose()
    _print_results(results, apply)


def main() -> None:
    parser = argparse.ArgumentParser(description="PAPER 전략 버전 활성화 스크립트")
    parser.add_argument(
        "--apply", action="store_true", default=False,
        help="이 옵션 없이는 dry-run만 수행합니다."
    )
    parser.add_argument(
        "--account-id", type=int, default=None,
        help="PAPER 계좌 ID (미지정 시 첫 번째 PAPER 계좌 자동 선택)"
    )
    parser.add_argument(
        "--symbol-code", type=str, default="005930",
        help="전략 적용 종목 코드 (기본값: 005930)"
    )
    args = parser.parse_args()

    asyncio.run(_main(args.account_id, args.symbol_code, args.apply))


if __name__ == "__main__":
    main()
