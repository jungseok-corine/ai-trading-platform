"""C-2.14: 실전 계좌 등록 및 안전 상태 초기화 서비스.

실전 계좌를 DB에 등록하고 TradingGuardState(paused) + RiskConfig(emergency_stop=True)를
보수적인 기본값으로 초기화한다.

안전 원칙:
  - 등록 직후 계좌는 반드시 pause + emergency_stop 상태여야 한다.
  - 이미 resume 상태인 TradingGuardState를 재등록하면 pause로 되돌린다 (보수적).
  - 이미 emergency_stop=False인 RiskConfig를 재등록하면 True로 되돌린다 (보수적).
  - place_order는 이 서비스에서 호출하지 않는다.
  - 계좌번호 전체값은 외부에 노출하지 않는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.enums import AccountType, PauseSource
from app.domain.repositories.account import AccountRepository
from app.domain.repositories.risk import RiskConfigRepository
from app.domain.repositories.trading_guard import TradingGuardRepository

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")

# 실전 계좌 초기 RiskConfig 보수적 기본값
# 실전 운영 전 반드시 검토하고 조정할 것.
LIVE_ACCOUNT_DEFAULT_RISK_CONFIG: dict = {
    "max_daily_loss_amount": Decimal("100000"),   # 일 최대 손실 10만원
    "max_position_size": Decimal("500000"),        # 종목당 최대 50만원
    "max_open_positions": 1,                       # 동시 보유 최대 1종목
    "max_trades_per_day": 2,                       # 일 최대 주문 2건
    "consecutive_loss_limit": 2,                   # 연속 손실 최대 2회
    "emergency_stop": True,                        # 등록 즉시 emergency_stop
}

_INITIAL_PAUSE_REASON = (
    "Live account registered in read-only mode. "
    "Manual review required before trading. "
    "Set KIS_REAL_TRADING_ENABLED=true and resume via trading-guard API only after full verification."
)


@dataclass
class RegistrationResult:
    """실전 계좌 등록 결과."""

    account_id: int
    account_type: str                     # "live"
    account_status: str                   # "created" | "already_exists"
    masked_account_no: str
    trading_guard_paused: bool
    guard_status: str                     # "created" | "updated_to_paused" | "already_paused"
    emergency_stop: bool
    risk_config_status: str               # "created" | "updated_emergency_stop" | "already_set"
    real_trading_enabled: bool = False    # 항상 False (env 기준)
    order_api_called: bool = False        # 항상 False
    readonly_verified: bool = False
    errors: list[str] = field(default_factory=list)


def _mask_account_no(account_no: str | None) -> str:
    """계좌번호 앞 4자리만 노출하고 나머지를 마스킹한다."""
    if not account_no:
        return "(미설정)"
    parts = account_no.split("-")
    front = parts[0]
    masked_front = front[:4] + "*" * max(0, len(front) - 4)
    return f"{masked_front}-**"


class LiveAccountRegistrationService:
    """실전 계좌 등록 및 안전 상태 초기화.

    멱등성 보장:
      - 같은 broker_account_no가 이미 있으면 안전 상태를 보수적으로 재적용한다.
      - 중복 Account 행을 생성하지 않는다.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._account_repo = AccountRepository(session)
        self._risk_config_repo = RiskConfigRepository(session)
        self._guard_repo = TradingGuardRepository(session)

    async def register(
        self,
        broker_account_no: str,
        alias: str | None = None,
        real_trading_enabled: bool = False,
    ) -> RegistrationResult:
        """실전 계좌를 등록하고 안전 상태를 초기화한다.

        이미 등록된 계좌가 있으면 안전 상태(pause/emergency_stop)만 보수적으로 재적용한다.
        place_order는 절대 호출하지 않는다.
        """
        masked = _mask_account_no(broker_account_no)
        result = RegistrationResult(
            account_id=0,
            account_type="live",
            account_status="",
            masked_account_no=masked,
            trading_guard_paused=False,
            guard_status="",
            emergency_stop=False,
            risk_config_status="",
            real_trading_enabled=real_trading_enabled,
        )

        # 1. Account 등록 (멱등)
        existing = await self._account_repo.get_by_broker_account_no(broker_account_no)
        if existing is not None:
            if existing.account_type != AccountType.LIVE:
                result.errors.append(
                    f"Existing account {masked} is not LIVE (type={existing.account_type.value}). "
                    "Cannot register as live account."
                )
                return result
            result.account_id = existing.id
            result.account_status = "already_exists"
            logger.info(
                "live account registration: account already exists id=%d masked=%s",
                existing.id, masked,
            )
        else:
            account = await self._account_repo.create(
                account_type=AccountType.LIVE,
                broker_account_no=broker_account_no,
                alias=alias,
            )
            result.account_id = account.id
            result.account_status = "created"
            logger.info(
                "live account registration: created account id=%d masked=%s",
                account.id, masked,
            )

        # 2. RiskConfig 초기화 (멱등 + 보수적)
        risk_cfg = await self._risk_config_repo.get_by_account_id(result.account_id)
        if risk_cfg is None:
            await self._risk_config_repo.create(
                account_id=result.account_id,
                **LIVE_ACCOUNT_DEFAULT_RISK_CONFIG,
            )
            result.emergency_stop = True
            result.risk_config_status = "created"
            logger.info(
                "live account registration: created risk_config emergency_stop=True for account=%d",
                result.account_id,
            )
        else:
            if not risk_cfg.emergency_stop:
                await self._risk_config_repo.update(risk_cfg, emergency_stop=True)
                result.risk_config_status = "updated_emergency_stop"
                logger.warning(
                    "live account registration: forced emergency_stop=True for account=%d (was False)",
                    result.account_id,
                )
            else:
                result.risk_config_status = "already_set"
            result.emergency_stop = True

        # 3. TradingGuardState 초기화 (멱등 + 보수적)
        now = datetime.now(_KST)
        guard = await self._guard_repo.get_by_account_id(result.account_id)
        if guard is None:
            await self._guard_repo.create(
                account_id=result.account_id,
                is_paused=True,
                pause_reason=_INITIAL_PAUSE_REASON,
                pause_source=PauseSource.MANUAL,
                paused_at=now,
                paused_by="registration",
            )
            result.trading_guard_paused = True
            result.guard_status = "created"
            logger.info(
                "live account registration: created trading_guard paused for account=%d",
                result.account_id,
            )
        elif not guard.is_paused:
            # resume 상태여도 보수적으로 pause로 되돌린다
            await self._guard_repo.update(
                guard,
                is_paused=True,
                pause_reason=_INITIAL_PAUSE_REASON,
                pause_source=PauseSource.MANUAL,
                paused_at=now,
                paused_by="registration",
                resolved_at=None,
                resolved_by=None,
                resolution_note=None,
            )
            result.trading_guard_paused = True
            result.guard_status = "updated_to_paused"
            logger.warning(
                "live account registration: forced pause for account=%d (was resumed)",
                result.account_id,
            )
        else:
            result.trading_guard_paused = True
            result.guard_status = "already_paused"

        await self._session.commit()

        logger.info(
            "live account registration complete: account_id=%d status=%s guard=%s risk=%s",
            result.account_id, result.account_status, result.guard_status, result.risk_config_status,
        )
        return result
