"""PAPER-RESUME-4B — dormant limited single-symbol paper candidate 생성 helper.

제한된 paper 자동주문 재개 후보를 **dormant(DRAFT + auto_trade_enabled=false)** 로 안전하게 생성한다.
강제 불변식:
  - status = DRAFT (스케줄러 list_active(active/testing) 대상 아님 → 신호조차 생성 안 함)
  - parameters.auto_trade_enabled = False (주문 시도 안 함)
  - parameters.universe_auto_trade = False, `universe` key 없음 (single-symbol 보장, broad universe 아님)
  - 같은 name의 strategy가 이미 있으면 생성하지 않고 DuplicateError

주문/스케줄러/RiskConfig/broker 미접촉. Trade/Order/SignalLog/CandidateEvent 생성 없음.
"""
from __future__ import annotations

from app.domain.models.enums import StrategyVersionStatus
from app.domain.models.strategy import Strategy, StrategyVersion
from app.domain.repositories.account import AccountRepository
from app.domain.repositories.strategy import StrategyRepository, StrategyVersionRepository
from app.services.strategy_service import StrategyService
from app.trading.strategy.registry import registered_types


class LimitedCandidateValidationError(Exception):
    """dormant 후보 생성 정책 위반."""


class LimitedCandidateDuplicateError(Exception):
    """같은 name의 strategy가 이미 존재."""


class SignalOnlyEnableError(Exception):
    """signal-only 전환 정책 위반(주문 위험 차단)."""


class DisableUniverseAutoTradeError(Exception):
    """broad universe auto-trade 비활성 정책 위반."""


_BROAD_UNIVERSES = ("watchlist", "scanner_candidates")


async def create_dormant_limited_candidate(
    session,
    *,
    name: str,
    description: str,
    parameters: dict,
) -> tuple[Strategy, StrategyVersion]:
    """dormant limited single-symbol candidate(Strategy + DRAFT StrategyVersion)를 생성한다.

    parameters는 호출자가 구성하되, 안전 불변식은 여기서 강제 검증/주입한다.
    """
    p = dict(parameters)

    # --- 안전 불변식 검증 ---------------------------------------------------
    if not p.get("symbol_code"):
        raise LimitedCandidateValidationError("symbol_code required (single-symbol mode)")
    if "universe" in p:
        raise LimitedCandidateValidationError("`universe` key must be absent (no broad universe)")
    if p.get("universe_auto_trade") is True:
        raise LimitedCandidateValidationError("universe_auto_trade must be false")
    if p.get("auto_trade_enabled") is True:
        raise LimitedCandidateValidationError("auto_trade_enabled must be false at creation")
    if p.get("market") != "KR":
        raise LimitedCandidateValidationError("market must be 'KR'")
    if not p.get("account_id"):
        raise LimitedCandidateValidationError("account_id required")
    strategy_type = p.get("strategy_type")
    if strategy_type not in registered_types():
        raise LimitedCandidateValidationError(
            f"strategy_type {strategy_type!r} not in registry {registered_types()}")

    # 안전 플래그를 명시적으로 강제(누락 시 주입).
    p["auto_trade_enabled"] = False
    p["universe_auto_trade"] = False

    # --- 중복 방지 ----------------------------------------------------------
    existing = await StrategyRepository(session).list_with_version_counts()
    if any(s.name == name for s, _ in existing):
        raise LimitedCandidateDuplicateError(f"strategy named {name!r} already exists")

    # --- 생성(DRAFT) --------------------------------------------------------
    svc = StrategyService(session)
    strategy = await svc.create_strategy(name=name, description=description)
    version = await svc.create_version(
        strategy_id=strategy.id,
        parameters=p,
        change_description="PAPER-RESUME-4B dormant limited single-symbol candidate",
        status=StrategyVersionStatus.DRAFT,
    )
    return strategy, version


async def enable_signal_only_testing(
    session, *, strategy_id: int, version_id: int
) -> StrategyVersion:
    """DRAFT candidate를 **signal-only TESTING**으로 전환한다(주문 비활성 유지).

    status 컬럼만 DRAFT→TESTING으로 바꾼다. parameters(특히 auto_trade_enabled/universe_auto_trade)는
    절대 건드리지 않으며, 다음 가드를 위반하면 변경하지 않고 raise한다:
      - 현재 status가 DRAFT가 아니면 거부(이미 testing/active 등).
      - parameters.auto_trade_enabled is True → 거부(주문 위험).
      - parameters.universe_auto_trade is True → 거부(broad universe).
      - parameters에 `universe` key 존재 → 거부.
    TESTING은 scheduler list_active 대상이 되어 신호가 생성될 수 있으나, auto_trade_enabled=false라
    주문 시도는 하지 않는다(signal-only).
    """
    version = await StrategyVersionRepository(session).get(version_id)
    if version is None or version.strategy_id != strategy_id:
        raise SignalOnlyEnableError(f"version {version_id} (strategy {strategy_id}) not found")
    if version.status != StrategyVersionStatus.DRAFT:
        raise SignalOnlyEnableError(
            f"status가 {version.status.value} — DRAFT만 signal-only TESTING으로 전환 가능")
    p = version.parameters or {}
    if p.get("auto_trade_enabled") is True:
        raise SignalOnlyEnableError("auto_trade_enabled=true — signal-only 전환 불가(주문 위험)")
    if p.get("universe_auto_trade") is True:
        raise SignalOnlyEnableError("universe_auto_trade=true — 전환 불가(broad universe)")
    if "universe" in p:
        raise SignalOnlyEnableError("`universe` key present — 전환 불가")

    # status 컬럼만 변경(parameters 미변경).
    return await StrategyService(session).update_version(
        strategy_id, version_id, status=StrategyVersionStatus.TESTING)


async def disable_universe_auto_trade(
    session, *, strategy_id: int, version_id: int
) -> StrategyVersion:
    """broad universe 전략의 자동주문을 끈다: parameters.universe_auto_trade → false.

    가드(위반 시 변경하지 않고 raise):
      - parameters에 `universe` key가 없으면(=single-symbol) 거부 → v329 같은 단일종목 후보 보호.
      - universe가 broad(watchlist/scanner_candidates)가 아니면 거부.
      - parameters.universe_auto_trade가 true가 아니면 거부(이미 꺼짐/무관).
      - 연결 account가 paper가 아니면 거부(live 보호).
    status는 변경하지 않는다(signal 관찰은 남길 수 있음). auto_trade_enabled가 true면 함께 false로.
    """
    version = await StrategyVersionRepository(session).get(version_id)
    if version is None or version.strategy_id != strategy_id:
        raise DisableUniverseAutoTradeError(f"version {version_id} (strategy {strategy_id}) not found")
    p = dict(version.parameters or {})
    if "universe" not in p:
        raise DisableUniverseAutoTradeError("single-symbol version (no `universe` key) — refuse")
    if p.get("universe") not in _BROAD_UNIVERSES:
        raise DisableUniverseAutoTradeError(f"universe {p.get('universe')!r} not broad — refuse")
    if p.get("universe_auto_trade") is not True:
        raise DisableUniverseAutoTradeError("universe_auto_trade is not true — nothing to disable")

    account_id = p.get("account_id")
    if account_id is not None:
        from app.domain.models.enums import AccountType  # noqa: PLC0415
        account = await AccountRepository(session).get(int(account_id))
        if account is not None and account.account_type != AccountType.PAPER:
            raise DisableUniverseAutoTradeError(
                f"account {account_id} is {account.account_type.value} — refuse (paper only)")

    p["universe_auto_trade"] = False
    if p.get("auto_trade_enabled") is True:
        p["auto_trade_enabled"] = False

    # parameters JSONB만 변경(status 미변경).
    return await StrategyService(session).update_version(strategy_id, version_id, parameters=p)
