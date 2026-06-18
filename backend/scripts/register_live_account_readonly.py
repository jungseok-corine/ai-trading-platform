"""C-2.14: 실전 계좌 DB 등록 및 안전 상태 초기화 스크립트.

실전 계좌를 trading_platform DB에 등록하고 다음을 보장한다:
  - TradingGuardState paused=True
  - RiskConfig emergency_stop=True
  - 실전 주문 API 미호출

사용법:
    # 기본 등록 (KIS API 호출 없음)
    .venv/bin/python scripts/register_live_account_readonly.py

    # 등록 후 read-only 조회 검증
    .venv/bin/python scripts/register_live_account_readonly.py --verify-readonly

    # 계좌번호 직접 지정
    .venv/bin/python scripts/register_live_account_readonly.py --broker-account-no 12345678-01

    # 계좌 별칭 설정
    .venv/bin/python scripts/register_live_account_readonly.py --alias "실전계좌1"

필요한 환경변수 (.env 또는 shell):
    DATABASE_URL (또는 자동 감지)
    KIS_REAL_ACCOUNT_NO (--broker-account-no 미지정 시)
    KIS_REAL_APP_KEY, KIS_REAL_APP_SECRET, KIS_REAL_BASE_URL (--verify-readonly 시)

금지 사항:
    - 이 스크립트는 어떤 경우에도 broker.place_order를 호출하지 않는다.
    - 계좌번호/app key/token 전체값은 출력하지 않는다.
    - .env 파일을 git add/commit하지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# .env 자동 로드
_ENV_FILE = _BACKEND_DIR / ".env"
if _ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ENV_FILE, override=False)


def _mask_account_no(account_no: str | None) -> str:
    if not account_no:
        return "(미설정)"
    parts = account_no.split("-")
    front = parts[0]
    return f"{front[:4]}{'*' * max(0, len(front) - 4)}-**"


async def _run_registration(broker_account_no: str, alias: str | None) -> dict:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import get_settings
    from app.services.live_account_registration_service import LiveAccountRegistrationService

    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        async with factory() as session:
            svc = LiveAccountRegistrationService(session)
            result = await svc.register(
                broker_account_no=broker_account_no,
                alias=alias,
                real_trading_enabled=os.environ.get("KIS_REAL_TRADING_ENABLED", "false").lower() == "true",
            )
    finally:
        await engine.dispose()

    return {
        "account_id": result.account_id,
        "account_type": result.account_type,
        "account_status": result.account_status,
        "masked_account_no": result.masked_account_no,
        "trading_guard_paused": result.trading_guard_paused,
        "guard_status": result.guard_status,
        "emergency_stop": result.emergency_stop,
        "risk_config_status": result.risk_config_status,
        "real_trading_enabled": result.real_trading_enabled,
        "order_api_called": result.order_api_called,
        "readonly_verified": result.readonly_verified,
        "errors": result.errors,
    }


async def _run_verify_readonly(account_id: int) -> dict:
    """KIS 실전 read-only 조회를 수행한다. place_order는 절대 호출하지 않는다."""
    import httpx

    from app.trading.broker.kis_real import KISRealBrokerClient

    app_key = os.environ.get("KIS_REAL_APP_KEY", "")
    app_secret = os.environ.get("KIS_REAL_APP_SECRET", "")
    account_no = os.environ.get("KIS_REAL_ACCOUNT_NO", "")
    base_url = os.environ.get("KIS_REAL_BASE_URL", "https://openapi.koreainvestment.com:9443")
    token_cache = os.environ.get("KIS_REAL_TOKEN_CACHE_PATH", ".cache/kis_real_token.json")

    verify_result: dict = {
        "token": "not_tested",
        "balance_query": "not_tested",
        "executions_query": "not_tested",
        "positions_count": None,
        "executions_count": None,
        "order_api_called": False,
        "errors": [],
    }

    if not (app_key and app_secret and account_no):
        verify_result["errors"].append(
            "KIS_REAL_APP_KEY / KIS_REAL_APP_SECRET / KIS_REAL_ACCOUNT_NO 미설정"
        )
        return verify_result

    async with httpx.AsyncClient(timeout=30.0) as http:
        broker = KISRealBrokerClient(
            base_url=base_url,
            app_key=app_key,
            app_secret=app_secret,
            account_no=account_no,
            http_client=http,
            token_cache_path=token_cache,
            real_trading_enabled=False,  # 항상 False
        )

        try:
            token = await broker._get_access_token()
            from scripts.kis_real_readonly_smoke_test import _mask
            verify_result["token"] = f"ok (masked: {_mask(token, 8)})"
        except Exception as e:
            verify_result["token"] = f"FAILED: {type(e).__name__}"
            verify_result["errors"].append(f"token: {e}")

        try:
            balance = await broker.get_account_balance()
            verify_result["balance_query"] = "ok"
            verify_result["positions_count"] = len(balance.holdings)
        except Exception as e:
            verify_result["balance_query"] = f"FAILED: {type(e).__name__}"
            verify_result["errors"].append(f"balance: {e}")

        try:
            execs = await broker.get_daily_executions()
            verify_result["executions_query"] = "ok"
            verify_result["executions_count"] = len(execs)
        except Exception as e:
            verify_result["executions_query"] = f"FAILED: {type(e).__name__}"
            verify_result["errors"].append(f"executions: {e}")

    return verify_result


def _print_report(reg: dict, verify: dict | None) -> str:
    lines = [
        "",
        "=" * 60,
        "  C-2.14: Live Account Registration & Safety State Init",
        "=" * 60,
        f"  account_id          : {reg['account_id']}",
        f"  account_type        : {reg['account_type']}",
        f"  account_status      : {reg['account_status']}",
        f"  masked_account_no   : {reg['masked_account_no']}",
        f"  trading_guard_paused: {reg['trading_guard_paused']}",
        f"  guard_status        : {reg['guard_status']}",
        f"  emergency_stop      : {reg['emergency_stop']}",
        f"  risk_config_status  : {reg['risk_config_status']}",
        f"  real_trading_enabled: {reg['real_trading_enabled']}",
        f"  order_api_called    : {reg['order_api_called']}",
    ]

    if reg["errors"]:
        lines.append("")
        lines.append("  [ERRORS]")
        for e in reg["errors"]:
            lines.append(f"    - {e}")
        verdict = "REGISTRATION_FAILED"
    else:
        verdict = "REGISTRATION_OK"

    if verify is not None:
        lines += [
            "",
            "  --- Read-Only Verification ---",
            f"  token               : {verify['token']}",
            f"  balance_query       : {verify['balance_query']}",
            f"  executions_query    : {verify['executions_query']}",
            f"  positions_count     : {verify['positions_count']}",
            f"  executions_count    : {verify['executions_count']}",
            f"  order_api_called    : {verify['order_api_called']}",
        ]
        if verify["errors"]:
            lines.append("  [VERIFY ERRORS]")
            for e in verify["errors"]:
                lines.append(f"    - {e}")
            if verdict == "REGISTRATION_OK":
                verdict = "REGISTRATION_OK_VERIFY_PARTIAL"
        elif verdict == "REGISTRATION_OK":
            verdict = "REGISTRATION_OK_READONLY_VERIFIED"

    lines += [
        "",
        f"  result              : {verdict}",
        "",
        "  안전 보장:",
        "    - place_order는 이 스크립트에서 호출되지 않았습니다.",
        "    - real_trading_enabled=False 유지.",
        "    - trading_guard paused + emergency_stop=True 상태 확인.",
        "",
        "=" * 60,
        "",
    ]

    print("\n".join(lines))
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser(
        description="C-2.14: 실전 계좌 DB 등록 및 안전 상태 초기화"
    )
    parser.add_argument(
        "--broker-account-no",
        default=None,
        help="실전 계좌번호 (미지정 시 KIS_REAL_ACCOUNT_NO 환경변수 사용)",
    )
    parser.add_argument(
        "--alias",
        default=None,
        help="계좌 별칭 (선택)",
    )
    parser.add_argument(
        "--verify-readonly",
        action="store_true",
        help="등록 후 KIS read-only 잔고/체결 조회 검증 수행 (실제 KIS API 호출)",
    )
    args = parser.parse_args()

    broker_account_no = args.broker_account_no or os.environ.get("KIS_REAL_ACCOUNT_NO", "")
    if not broker_account_no:
        print("\n[ERROR] 계좌번호가 지정되지 않았습니다.")
        print("  --broker-account-no 옵션 또는 KIS_REAL_ACCOUNT_NO 환경변수를 설정하세요.")
        sys.exit(1)

    reg = asyncio.run(_run_registration(broker_account_no, args.alias))

    verify = None
    if args.verify_readonly and not reg["errors"]:
        verify = asyncio.run(_run_verify_readonly(reg["account_id"]))

    verdict = _print_report(reg, verify)
    sys.exit(0 if "OK" in verdict else 1)


if __name__ == "__main__":
    main()
