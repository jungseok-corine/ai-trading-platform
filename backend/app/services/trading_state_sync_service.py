"""C-2.11: Order/Position 통합 동기화 파이프라인.

실행 순서:
  1. OrderSyncService.sync_pending_orders()  — KIS 체결조회 (VTTC0081R/TTTC0081R)
  2. PositionReconciliationService.reconcile(account_id) — 잔고 정합성 검사

정책:
  - order sync 실패 시 reconciliation은 계속 진행하되 warnings에 기록한다.
  - reconciliation 실패 시 warnings에 기록하고 나머지 account를 계속 처리한다.
  - paper 계좌 mismatch: DB를 broker 기준으로 자동 보정 + warning.
  - real 계좌 mismatch: risk_event 생성. DB는 수정하지 않음.
    자동 trading pause는 다음 phase(C-2.12)에서 구현한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import AccountType
from app.domain.repositories.account import AccountRepository
from app.services.order_sync_service import OrderSyncResult, OrderSyncService
from app.services.position_reconciliation_service import (
    ReconciliationResult,
    PositionReconciliationService,
)
from app.trading.broker.base import BrokerClient
from app.trading.broker.error_classifier import exc_message

logger = logging.getLogger(__name__)
_KST = ZoneInfo("Asia/Seoul")


@dataclass
class TradingStateSyncResult:
    account_id: int
    broker_mode: str          # "paper" | "live" | "unknown"
    started_at: datetime
    completed_at: datetime
    # Order sync
    orders_checked: int = 0
    orders_updated: int = 0
    orders_cancelled: int = 0
    order_sync_errors: list[str] = field(default_factory=list)
    order_sync_error_category: str | None = None
    order_sync_skipped_reason: str | None = None
    # Position reconciliation
    positions_compared: int = 0
    mismatches_count: int = 0
    risk_events_created: int = 0
    positions_synced_to_db: bool = False
    position_errors: list[str] = field(default_factory=list)
    # Overall
    warnings: list[str] = field(default_factory=list)


class TradingStateSyncService:
    """OrderSyncService + PositionReconciliationService를 하나의 pipeline으로 조율한다.

    단일 account_id 기준 API 호출(sync_account_trading_state)과
    전체 account 대상 scheduler 호출(sync_all_accounts) 두 가지 진입점을 제공한다.
    """

    def __init__(self, session: AsyncSession, broker: BrokerClient) -> None:
        self._session = session
        self._broker = broker
        self._order_svc = OrderSyncService(session, broker)
        self._reconcile_svc = PositionReconciliationService(session, broker)
        self._account_repo = AccountRepository(session)

    async def sync_account_trading_state(self, account_id: int) -> TradingStateSyncResult:
        """단일 계좌에 대해 order sync + position reconciliation을 순서대로 실행한다.

        order sync 실패 시 reconciliation을 계속 시도한다.
        """
        started_at = datetime.now(_KST)
        warnings: list[str] = []

        account = await self._account_repo.get(account_id)
        if account is None:
            raise ValueError(f"account {account_id} not found")

        broker_mode = _broker_mode(account.account_type)

        order_result = await self._run_order_sync(warnings)
        recon_result, position_errors = await self._run_reconciliation(account_id, warnings)

        completed_at = datetime.now(_KST)
        return _build_result(
            account_id=account_id,
            broker_mode=broker_mode,
            started_at=started_at,
            completed_at=completed_at,
            order_result=order_result,
            recon_result=recon_result,
            position_errors=position_errors,
            warnings=warnings,
        )

    async def sync_all_accounts(self) -> list[TradingStateSyncResult]:
        """DB의 모든 계좌에 대해 pipeline을 실행한다.

        order sync는 1회만 실행하고, 각 계좌의 reconciliation을 순서대로 처리한다.
        어느 한 계좌의 reconciliation 실패가 다른 계좌 처리를 막지 않는다.
        """
        started_at = datetime.now(_KST)
        warnings: list[str] = []

        accounts = await self._account_repo.list()
        if not accounts:
            logger.info("trading state sync: no accounts found, skipping")
            return []

        order_result = await self._run_order_sync(warnings)

        results: list[TradingStateSyncResult] = []
        for account in accounts:
            acc_warnings: list[str] = list(warnings)
            recon_result, position_errors = await self._run_reconciliation(account.id, acc_warnings)
            completed_at = datetime.now(_KST)
            results.append(_build_result(
                account_id=account.id,
                broker_mode=_broker_mode(account.account_type),
                started_at=started_at,
                completed_at=completed_at,
                order_result=order_result,
                recon_result=recon_result,
                position_errors=position_errors,
                warnings=acc_warnings,
            ))

        return results

    async def _run_order_sync(self, warnings: list[str]) -> OrderSyncResult | None:
        try:
            result = await self._order_svc.sync_pending_orders()
            if result.error_category:
                warnings.append(
                    f"order sync failed ({result.error_category}): {'; '.join(result.errors)}"
                )
            return result
        except Exception as exc:  # noqa: BLE001
            msg = f"order sync exception: {exc_message(exc)}"
            logger.warning("trading state sync: %s", msg)
            warnings.append(msg)
            return None

    async def _run_reconciliation(
        self, account_id: int, warnings: list[str]
    ) -> tuple[ReconciliationResult | None, list[str]]:
        errors: list[str] = []
        try:
            result = await self._reconcile_svc.reconcile(account_id)
            return result, errors
        except Exception as exc:  # noqa: BLE001
            msg = f"reconciliation failed for account {account_id}: {exc_message(exc)}"
            logger.warning("trading state sync: %s", msg)
            warnings.append(msg)
            errors.append(msg)
            return None, errors


def _broker_mode(account_type: AccountType | None) -> str:
    if account_type == AccountType.PAPER:
        return "paper"
    if account_type == AccountType.LIVE:
        return "live"
    return "unknown"


def _build_result(
    *,
    account_id: int,
    broker_mode: str,
    started_at: datetime,
    completed_at: datetime,
    order_result: OrderSyncResult | None,
    recon_result: ReconciliationResult | None,
    position_errors: list[str],
    warnings: list[str],
) -> TradingStateSyncResult:
    r = TradingStateSyncResult(
        account_id=account_id,
        broker_mode=broker_mode,
        started_at=started_at,
        completed_at=completed_at,
        warnings=warnings,
    )

    if order_result is not None:
        r.orders_checked = order_result.checked
        r.orders_updated = order_result.updated
        r.orders_cancelled = order_result.stale_cancelled
        r.order_sync_errors = order_result.errors
        r.order_sync_error_category = order_result.error_category
        r.order_sync_skipped_reason = order_result.skipped_reason

    if recon_result is not None:
        r.positions_compared = len(recon_result.comparisons)
        r.mismatches_count = recon_result.mismatch_count
        r.risk_events_created = 1 if recon_result.risk_event_created else 0
        r.positions_synced_to_db = recon_result.synced_to_db

    r.position_errors = position_errors
    return r
