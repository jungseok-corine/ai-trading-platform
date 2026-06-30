"""MANUAL-SELL-RECON-2 — read-only KIS vs DB reconciliation report.

KIS broker holdings와 local DB positions를 **비교만** 한다. DB write/commit/flush 없음,
주문/스케줄러 없음, broker는 read-only(`get_broker_positions`)만 호출한다.

특히 다음 write-capable 경로는 **호출하지 않는다**:
  - `PositionReconciliationService.reconcile`  (paper DB auto-sync / risk_event 기록 / commit)
  - `PositionService.sync_from_broker_positions`  (DB 동기화)
  - `TradingStateSyncService`  (order/position sync pipeline)

대신 순수 비교 함수 `position_reconciliation_service._compare_positions`(DB write 없음)를 재사용한다.
불일치가 있어도 자동으로 고치지 않는다 — DB reconciliation은 별도 human-approved 작업이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.domain.repositories.account import AccountRepository
from app.domain.repositories.position import PositionRepository
from app.services.position_reconciliation_service import (
    ReconciliationMismatchType,
    _compare_positions,
)
from app.trading.broker.base import BrokerClient

# 기존 reconciliation enum → report용 사람이 읽기 쉬운 타입.
_REPORT_TYPE_MAP: dict[ReconciliationMismatchType, str] = {
    ReconciliationMismatchType.OK: "matched",
    ReconciliationMismatchType.DB_POSITION_NOT_IN_BROKER: "broker_sold_db_open",
    ReconciliationMismatchType.MISSING_SELL_OR_UNSYNCED_POSITION: "broker_qty_less_than_db_qty",
    ReconciliationMismatchType.MISSING_BUY_OR_UNSYNCED_POSITION: "broker_qty_more_than_db_qty",
    ReconciliationMismatchType.BROKER_POSITION_NOT_IN_DB: "broker_holding_db_missing",
    ReconciliationMismatchType.AVG_PRICE_MISMATCH: "price_basis_mismatch",
}

# broker 수량이 DB보다 줄었거나 사라진 경우 → 수동 매도의 실현손익이 DB trade에 없을 수 있음.
_REALIZED_PNL_MISSING_TYPES = {"broker_sold_db_open", "broker_qty_less_than_db_qty"}


@dataclass
class ReconciliationReportItem:
    symbol_code: str
    symbol_name: str | None
    report_type: str
    broker_quantity: int | None
    db_quantity: int | None
    broker_avg_price: Decimal | None
    db_avg_price: Decimal | None
    details: str


@dataclass
class ManualReconciliationReport:
    account_id: int
    broker_account_no: str | None
    market: str
    checked_at: datetime
    broker_holdings_count: int
    db_open_positions_count: int
    matched_count: int
    mismatch_count: int
    mismatches: list[ReconciliationReportItem] = field(default_factory=list)
    broker_only_holdings: list[ReconciliationReportItem] = field(default_factory=list)
    db_only_positions: list[ReconciliationReportItem] = field(default_factory=list)
    matched_positions: list[ReconciliationReportItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ManualReconciliationReportService:
    """KIS holdings ↔ DB positions를 비교하는 read-only report 서비스 (DB write 없음)."""

    def __init__(self, session: AsyncSession, broker: BrokerClient) -> None:
        self._session = session
        self._broker = broker
        self._account_repo = AccountRepository(session)
        self._position_repo = PositionRepository(session)

    async def build_report(
        self,
        account_id: int,
        *,
        market: str = "KR",
        symbols: list[str] | None = None,
        include_zero_quantity_db_positions: bool = False,
    ) -> ManualReconciliationReport:
        account = await self._account_repo.get(account_id)
        if account is None:
            raise ValueError(f"account {account_id} not found")

        # read-only broker 조회(KIS 잔고조회 — 주문 아님).
        broker_positions = await self._broker.get_broker_positions()
        # MISSING_BUY 케이스(미동기 매수)에서 qty=0 row 확인을 위해 closed 포함.
        db_positions = await self._position_repo.list_by_account(account_id, include_closed=True)

        # 순수 비교(=DB write 없음). 기존 reconcile 서비스의 write 경로는 호출하지 않는다.
        comparisons = _compare_positions(broker_positions, db_positions)

        symbol_filter = set(symbols) if symbols else None
        warnings: list[str] = []
        mismatches: list[ReconciliationReportItem] = []
        broker_only: list[ReconciliationReportItem] = []
        db_only: list[ReconciliationReportItem] = []
        matched: list[ReconciliationReportItem] = []

        for c in comparisons:
            if symbol_filter is not None and c.symbol_code not in symbol_filter:
                continue
            report_type = _REPORT_TYPE_MAP.get(c.mismatch_type, c.mismatch_type.value)
            item = ReconciliationReportItem(
                symbol_code=c.symbol_code,
                symbol_name=c.symbol_name,
                report_type=report_type,
                broker_quantity=c.broker_quantity,
                db_quantity=c.db_quantity,
                broker_avg_price=c.broker_avg_price,
                db_avg_price=c.db_avg_price,
                details=c.details,
            )
            if report_type == "matched":
                matched.append(item)
                continue
            mismatches.append(item)
            if report_type == "broker_holding_db_missing":
                broker_only.append(item)
            elif report_type == "broker_sold_db_open":
                db_only.append(item)
            # realized PnL 누락 가능성은 확정하지 말고 warning으로만 표시(write 없음).
            if report_type in _REALIZED_PNL_MISSING_TYPES:
                warnings.append(
                    f"realized_pnl_missing_possible: {c.symbol_code} broker qty "
                    f"({c.broker_quantity}) < DB qty ({c.db_quantity}); "
                    "수동 앱 매도의 실현손익이 DB trades에 없을 수 있음 — human-approved reconciliation 필요."
                )

        # 옵션: qty=0(청산됨) DB row를 정보성으로 포함.
        if include_zero_quantity_db_positions:
            broker_symbols = {p.symbol_code for p in broker_positions}
            for dp in db_positions:
                if dp.quantity != 0 or dp.symbol_code in broker_symbols:
                    continue
                if symbol_filter is not None and dp.symbol_code not in symbol_filter:
                    continue
                matched.append(ReconciliationReportItem(
                    symbol_code=dp.symbol_code,
                    symbol_name=dp.symbol_name,
                    report_type="matched",
                    broker_quantity=None,
                    db_quantity=0,
                    broker_avg_price=None,
                    db_avg_price=dp.avg_entry_price,
                    details="DB position closed (quantity 0) and not held at broker — informational",
                ))

        return ManualReconciliationReport(
            account_id=account_id,
            broker_account_no=account.broker_account_no,
            market=market,
            checked_at=datetime.now(KST),
            broker_holdings_count=len(broker_positions),
            db_open_positions_count=sum(1 for p in db_positions if p.quantity > 0),
            matched_count=len(matched),
            mismatch_count=len(mismatches),
            mismatches=mismatches,
            broker_only_holdings=broker_only,
            db_only_positions=db_only,
            matched_positions=matched,
            warnings=warnings,
        )
