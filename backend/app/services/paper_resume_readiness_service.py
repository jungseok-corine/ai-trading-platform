"""PAPER-RESUME-1 — read-only limited paper auto-trading resume checklist.

제한된 paper 자동 주문 재개 **전** 시스템 상태를 read-only로 점검한다. 자동매매를 켜지 않고,
DB/RiskConfig/scheduler/settings를 수정하지 않으며, 주문/sync write 경로를 호출하지 않는다.

데이터 소스(전부 read-only):
  - settings(`get_settings`) · Account/RiskConfig SELECT · TradingGuardService.is_paused ·
    strategy_versions SELECT · trades/signal_logs SELECT · broker.get_broker_positions(read-only) ·
    MANUAL-SELL-RECON-2 read-only reconciliation report 재사용.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.core.config import get_settings
from app.domain.models.account import Account
from app.domain.models.enums import AccountType, StrategyVersionStatus
from app.domain.models.signal_log import SignalLog
from app.domain.models.strategy import StrategyVersion
from app.domain.models.trade import Trade
from app.domain.repositories.account import AccountRepository
from app.domain.repositories.risk import RiskConfigRepository
from app.services.manual_reconciliation_report_service import (
    ManualReconciliationReportService,
)
from app.services.trading_guard_service import TradingGuardService
from app.trading.broker.base import BrokerClient

PASS = "PASS"
WARN = "WARN"
BLOCK = "BLOCK"
INFO = "INFO"

READY = "READY"
READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
BLOCKED = "BLOCKED"


@dataclass
class CheckItem:
    key: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperResumeReadinessReport:
    account_id: int
    overall_status: str
    checked_at: datetime
    pass_count: int
    warn_count: int
    block_count: int
    items: list[CheckItem] = field(default_factory=list)


class PaperResumeReadinessService:
    """제한된 paper 자동 주문 재개 준비 상태를 read-only로 평가한다 (DB write 없음)."""

    def __init__(self, session: AsyncSession, broker: BrokerClient) -> None:
        self._session = session
        self._broker = broker
        self._account_repo = AccountRepository(session)
        self._risk_repo = RiskConfigRepository(session)
        self._guard = TradingGuardService(session)
        self._recon = ManualReconciliationReportService(session, broker)

    async def build_checklist(self, account_id: int) -> PaperResumeReadinessReport:
        settings = get_settings()
        items: list[CheckItem] = []

        # 1) live trading off (전역 safety invariant).
        if settings.kis_real_trading_enabled:
            items.append(CheckItem(
                "live_trading_disabled", BLOCK,
                "KIS_REAL_TRADING_ENABLED=true — 실거래가 켜져 있어 재개 불가",
                {"kis_real_trading_enabled": True}))
        else:
            items.append(CheckItem(
                "live_trading_disabled", PASS, "실거래 비활성(paper 전용)",
                {"kis_real_trading_enabled": False}))

        # 2) account paper.
        account = await self._account_repo.get(account_id)
        if account is None:
            items.append(CheckItem("account_is_paper", BLOCK, f"account {account_id} 없음"))
        elif account.account_type != AccountType.PAPER:
            items.append(CheckItem(
                "account_is_paper", BLOCK,
                f"account가 paper가 아님 ({account.account_type.value}) — paper만 재개 허용",
                {"account_type": account.account_type.value}))
        else:
            items.append(CheckItem("account_is_paper", PASS, "paper 계좌",
                                   {"account_type": "paper"}))

        # 3) RiskConfig + emergency_stop.
        config = await self._risk_repo.get_by_account_id(account_id)
        if config is None:
            items.append(CheckItem("risk_config", BLOCK, "RiskConfig 없음 — 재개 불가"))
            items.append(CheckItem("emergency_stop", BLOCK, "RiskConfig 없음으로 emergency_stop 확인 불가"))
        else:
            bad = []
            if config.max_position_size <= 0: bad.append("max_position_size<=0")
            if config.max_open_positions <= 0: bad.append("max_open_positions<=0")
            if config.max_daily_loss_amount <= 0: bad.append("max_daily_loss_amount<=0")
            if config.max_trades_per_day <= 0: bad.append("max_trades_per_day<=0")
            rc_details = {
                "max_position_size": str(config.max_position_size),
                "max_open_positions": config.max_open_positions,
                "max_daily_loss_amount": str(config.max_daily_loss_amount),
                "max_trades_per_day": config.max_trades_per_day,
                "consecutive_loss_limit": config.consecutive_loss_limit,
            }
            if bad:
                items.append(CheckItem("risk_config", BLOCK,
                                       f"RiskConfig 값 오류: {', '.join(bad)}", rc_details))
            else:
                items.append(CheckItem("risk_config", PASS, "RiskConfig 값 정상", rc_details))
            if config.emergency_stop:
                items.append(CheckItem("emergency_stop", BLOCK, "emergency_stop=true — 재개 불가",
                                       {"emergency_stop": True}))
            else:
                items.append(CheckItem("emergency_stop", PASS, "emergency_stop=false",
                                       {"emergency_stop": False}))

        # 4) trading guard pause.
        paused = await self._guard.is_paused(account_id)
        if paused:
            items.append(CheckItem("trading_guard_pause", BLOCK,
                                   "trading guard paused — 재개 전 해제 필요", {"is_paused": True}))
        else:
            items.append(CheckItem("trading_guard_pause", PASS, "trading guard 미정지",
                                   {"is_paused": False}))

        # 5) scheduler/dispatcher 상태 (켜기 전 점검이므로 off는 정상).
        broad_on = (
            settings.paper_signal_session_runner_enabled
            or settings.paper_signal_recurring_plan_dispatcher_enabled
        )
        sched_details = {
            "strategy_scheduler_enabled": settings.strategy_scheduler_enabled,
            "paper_signal_session_runner_enabled": settings.paper_signal_session_runner_enabled,
            "paper_signal_recurring_plan_dispatcher_enabled":
                settings.paper_signal_recurring_plan_dispatcher_enabled,
        }
        items.append(CheckItem(
            "scheduler_dispatcher_state", WARN if broad_on else INFO,
            "auto dispatcher가 이미 켜져 있음" if broad_on
            else "auto dispatcher off (재개 전 정상 상태)",
            sched_details))

        # 6) auto-trade scope + full-universe guard.
        single_q = select(func.count()).select_from(StrategyVersion).where(
            StrategyVersion.parameters["auto_trade_enabled"].astext == "true",
            StrategyVersion.status != StrategyVersionStatus.ARCHIVED,
        )
        universe_q = select(func.count()).select_from(StrategyVersion).where(
            StrategyVersion.parameters["universe_auto_trade"].astext == "true",
            StrategyVersion.status != StrategyVersionStatus.ARCHIVED,
        )
        single_n = (await self._session.execute(single_q)).scalar_one()
        universe_n = (await self._session.execute(universe_q)).scalar_one()
        scope_details = {"auto_trade_enabled_count": single_n, "universe_auto_trade_count": universe_n}
        if single_n == 0 and universe_n == 0:
            items.append(CheckItem("auto_trade_scope", WARN,
                                   "auto-trade 전략 0개 — 재개하려면 제한된 allowlist 필요(PAPER-RESUME-2)",
                                   scope_details))
        else:
            items.append(CheckItem("auto_trade_scope", PASS,
                                   f"auto-trade 전략 {single_n + universe_n}개 활성", scope_details))
        # full-universe guard: universe 전략 존재 + dispatcher on → 실제 광범위 자동매매 위험.
        if universe_n > 0 and broad_on:
            items.append(CheckItem("full_universe_guard", BLOCK,
                                   "universe auto-trade 전략 + dispatcher가 켜져 full-universe 자동매매 위험",
                                   scope_details))
        elif universe_n > 0:
            items.append(CheckItem("full_universe_guard", WARN,
                                   "universe auto-trade 전략 존재 — 이번주 full-universe 금지, 제한 allowlist로 좁힐 것",
                                   scope_details))
        else:
            items.append(CheckItem("full_universe_guard", PASS, "universe auto-trade 전략 없음",
                                   scope_details))

        # 7) reconciliation state (read-only report 재사용).
        report = await self._recon.build_report(account_id)
        recon_details = {
            "broker_holdings_count": report.broker_holdings_count,
            "db_open_positions_count": report.db_open_positions_count,
            "mismatch_count": report.mismatch_count,
            "warnings": report.warnings,
        }
        if report.mismatch_count > 0:
            items.append(CheckItem("reconciliation_state", WARN,
                                   f"KIS vs DB 불일치 {report.mismatch_count}건 — 재개 전 reconciliation 필요",
                                   recon_details))
        else:
            items.append(CheckItem("reconciliation_state", PASS, "KIS holdings와 DB positions 일치",
                                   recon_details))

        # 8) current trading state (today loss/trade count).
        today_start = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        today_trades = (await self._session.execute(
            select(func.count()).select_from(Trade).where(
                Trade.account_id == account_id, Trade.entry_time >= today_start))).scalar_one()
        today_realized = (await self._session.execute(
            select(func.coalesce(func.sum(Trade.pnl_amount), 0)).where(
                Trade.account_id == account_id, Trade.exit_time >= today_start))).scalar_one()
        today_realized = Decimal(today_realized)
        max_trades = config.max_trades_per_day if config else 0
        max_loss = config.max_daily_loss_amount if config else Decimal("0")
        state_details = {
            "today_trades": today_trades, "today_realized_pnl": str(today_realized),
            "max_trades_per_day": max_trades, "max_daily_loss_amount": str(max_loss),
        }
        if config and today_trades >= max_trades:
            items.append(CheckItem("current_trading_state", BLOCK,
                                   f"오늘 거래수 한도 도달 ({today_trades} >= {max_trades})", state_details))
        elif config and today_realized <= -max_loss:
            items.append(CheckItem("current_trading_state", BLOCK,
                                   f"오늘 손실 한도 도달 ({today_realized} <= -{max_loss})", state_details))
        else:
            items.append(CheckItem("current_trading_state", PASS,
                                   "오늘 거래수/손실 한도 여유", state_details))

        # 9) BUY readiness (max_open_positions).
        open_count = report.broker_holdings_count
        max_open = config.max_open_positions if config else 0
        buy_details = {"open_positions": open_count, "max_open_positions": max_open,
                       "max_position_size_cap": "active (RISK-FIX-1F)"}
        if config and open_count >= max_open:
            items.append(CheckItem("buy_readiness", WARN,
                                   f"보유 {open_count} >= 한도 {max_open} — 신규 BUY는 max_open_positions로 차단(정상)",
                                   buy_details))
        else:
            items.append(CheckItem("buy_readiness", PASS,
                                   "신규 BUY 여력 있음 (수량은 max_position_size로 cap)", buy_details))

        # 10) SELL readiness (RISK-FIX-1C/1D 이후 risk rule이 SELL을 막지 않음).
        items.append(CheckItem("sell_readiness", PASS,
                               "SELL/exit는 CLL/MPS/MOP에 막히지 않음(RISK-FIX-1C/1D). "
                               "단 MaxDailyLoss/MaxTradesPerDay는 SELL에도 적용됨 — 순서 유의",
                               {"cll_blocks_sell": False, "mps_blocks_sell": False,
                                "mop_blocks_sell": False,
                                "max_daily_loss_can_block_sell": True}))

        # latest trade/signal (info).
        latest_trade = (await self._session.execute(
            select(func.max(Trade.entry_time)).where(Trade.account_id == account_id))).scalar_one()
        latest_signal = (await self._session.execute(
            select(func.max(SignalLog.created_at)))).scalar_one()
        items.append(CheckItem("recent_activity", INFO, "최근 활동(정보)",
                               {"latest_trade": str(latest_trade) if latest_trade else None,
                                "latest_signal": str(latest_signal) if latest_signal else None}))

        block_count = sum(1 for i in items if i.status == BLOCK)
        warn_count = sum(1 for i in items if i.status == WARN)
        pass_count = sum(1 for i in items if i.status == PASS)
        if block_count > 0:
            overall = BLOCKED
        elif warn_count > 0:
            overall = READY_WITH_WARNINGS
        else:
            overall = READY

        return PaperResumeReadinessReport(
            account_id=account_id, overall_status=overall, checked_at=datetime.now(KST),
            pass_count=pass_count, warn_count=warn_count, block_count=block_count, items=items)
