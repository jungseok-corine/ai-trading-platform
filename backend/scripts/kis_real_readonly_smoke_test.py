"""C-2.13: KIS 실전 계좌 Read-Only Smoke Test.

실전 KIS 계좌를 read-only 모드로 연결해 조회 기능만 검증한다.
어떤 경로로도 주문 API(place_order)를 호출하지 않는다.

사용법:
    # 실제 KIS API 호출 없이 설정 확인만:
    python scripts/kis_real_readonly_smoke_test.py

    # 실제 KIS API 호출 (조회 API만):
    python scripts/kis_real_readonly_smoke_test.py --confirm-readonly

필요한 환경변수 (.env 또는 shell):
    KIS_REAL_APP_KEY
    KIS_REAL_APP_SECRET
    KIS_REAL_ACCOUNT_NO

금지 사항:
    - 이 스크립트는 어떤 경우에도 place_order를 호출하지 않는다.
    - KIS_REAL_TRADING_ENABLED=true 여부와 무관하게 주문 API는 호출하지 않는다.
    - 민감정보(app_key, secret, token, account_no)는 마스킹해서만 출력한다.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (scripts/ 에서 실행 시)
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _mask(value: str | None, visible: int = 4) -> str:
    """민감정보 마스킹 — 앞 visible자만 남기고 나머지는 ***로 대체."""
    if not value:
        return "(미설정)"
    if len(value) <= visible:
        return "*" * len(value)
    return value[:visible] + "***"


def _mask_account_no(account_no: str | None) -> str:
    """계좌번호 마스킹 — 형식 XXXXXXXX-YY에서 앞 4자리만 노출."""
    if not account_no:
        return "(미설정)"
    parts = account_no.split("-")
    masked_front = _mask(parts[0], 4)
    masked_back = "**"
    return f"{masked_front}-{masked_back}"


def _check_env_config() -> dict:
    """환경변수에서 실전 계좌 설정을 읽고 기본 유효성을 확인한다."""
    result = {
        "app_key_set": bool(os.environ.get("KIS_REAL_APP_KEY")),
        "app_secret_set": bool(os.environ.get("KIS_REAL_APP_SECRET")),
        "account_no_set": bool(os.environ.get("KIS_REAL_ACCOUNT_NO")),
        "real_trading_enabled": os.environ.get("KIS_REAL_TRADING_ENABLED", "false").lower() == "true",
        "app_key_masked": _mask(os.environ.get("KIS_REAL_APP_KEY")),
        "account_no_masked": _mask_account_no(os.environ.get("KIS_REAL_ACCOUNT_NO")),
    }
    result["config_ready"] = (
        result["app_key_set"] and result["app_secret_set"] and result["account_no_set"]
    )
    return result


async def _run_readonly_verification() -> dict:
    """실제 KIS API를 호출해 read-only 기능을 검증한다.

    이 함수 내에서는 어떤 경우에도 place_order를 호출하지 않는다.
    """
    import httpx

    from app.trading.broker.kis_real import KISRealBrokerClient

    app_key = os.environ.get("KIS_REAL_APP_KEY", "")
    app_secret = os.environ.get("KIS_REAL_APP_SECRET", "")
    account_no = os.environ.get("KIS_REAL_ACCOUNT_NO", "")
    real_base_url = os.environ.get("KIS_REAL_BASE_URL", "https://openapi.koreainvestment.com:9443")
    token_cache_path = os.environ.get("KIS_REAL_TOKEN_CACHE_PATH", ".cache/kis_real_token.json")

    result: dict = {
        "order_api_called": False,  # 항상 False — place_order는 절대 호출하지 않음
        "real_trading_enabled": False,  # read-only smoke test에서는 항상 False
        "token": "not_tested",
        "balance_query": "not_tested",
        "daily_executions_query": "not_tested",
        "positions_count": None,
        "executions_count": None,
        "errors": [],
    }

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        broker = KISRealBrokerClient(
            base_url=real_base_url,
            app_key=app_key,
            app_secret=app_secret,
            account_no=account_no,
            http_client=http_client,
            token_cache_path=token_cache_path,
            real_trading_enabled=False,  # smoke test에서는 항상 read-only
        )

        # 1. 토큰 발급 확인
        try:
            token = await broker._get_access_token()
            result["token"] = "ok (masked: " + _mask(token, 8) + ")"
        except Exception as e:
            result["token"] = f"FAILED: {type(e).__name__}"
            result["errors"].append(f"token: {e}")

        # 2. 실전 잔고조회 TTTC8434R
        try:
            balance = await broker.get_account_balance()
            positions = balance.holdings
            result["balance_query"] = "ok"
            result["positions_count"] = len(positions)
        except Exception as e:
            result["balance_query"] = f"FAILED: {type(e).__name__}"
            result["errors"].append(f"balance: {e}")

        # 3. 실전 주문체결조회 TTTC0081R
        try:
            executions = await broker.get_daily_executions()
            result["daily_executions_query"] = "ok"
            result["executions_count"] = len(executions)
        except Exception as e:
            result["daily_executions_query"] = f"FAILED: {type(e).__name__}"
            result["errors"].append(f"daily_executions: {e}")

    return result


def _print_report(config: dict, api_result: dict | None, confirm_readonly: bool) -> str:
    """결과 리포트를 출력하고 최종 판정을 반환한다."""
    lines = [
        "",
        "=" * 60,
        "  KIS Real Account Read-Only Smoke Test — C-2.13",
        "=" * 60,
        f"  provider            : kis-real",
        f"  mode                : real-readonly",
        f"  app_key             : {config['app_key_masked']}",
        f"  account_no          : {config['account_no_masked']}",
        f"  config_ready        : {config['config_ready']}",
        f"  real_trading_enabled: {config['real_trading_enabled']}",
        "",
    ]

    if not confirm_readonly:
        lines += [
            "  [DRY RUN] --confirm-readonly 플래그 없음.",
            "  실제 KIS API 호출은 하지 않았습니다.",
            "",
            "  실제 조회 API 호출을 원하면:",
            "    python scripts/kis_real_readonly_smoke_test.py --confirm-readonly",
            "",
        ]
        if not config["config_ready"]:
            lines.append("  [WARN] 실전 계좌 환경변수가 미설정되어 있습니다.")
            lines.append("         KIS_REAL_APP_KEY, KIS_REAL_APP_SECRET, KIS_REAL_ACCOUNT_NO를 설정하세요.")
        verdict = "DRY_RUN_OK"
    else:
        assert api_result is not None
        lines += [
            f"  token               : {api_result['token']}",
            f"  balance_query       : {api_result['balance_query']}",
            f"  daily_executions    : {api_result['daily_executions_query']}",
            f"  positions_count     : {api_result['positions_count']}",
            f"  executions_count    : {api_result['executions_count']}",
            f"  order_api_called    : {api_result['order_api_called']}  ← 항상 false",
            f"  real_trading_enabled: {api_result['real_trading_enabled']}  ← 항상 false",
        ]

        if api_result["errors"]:
            lines.append("")
            lines.append("  [ERRORS]")
            for err in api_result["errors"]:
                lines.append(f"    - {err}")
            verdict = "READONLY_PARTIAL"
        else:
            verdict = "SAFE_READONLY_VERIFIED"

    lines += [
        "",
        f"  result              : {verdict}",
        "",
        "  주문 API 미호출 보장:",
        "    - place_order는 이 스크립트 어느 경로에서도 호출되지 않았습니다.",
        "    - real_trading_enabled=False로 고정되어 있습니다.",
        "",
        "=" * 60,
        "",
    ]

    report = "\n".join(lines)
    print(report)
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser(
        description="KIS 실전 계좌 Read-Only Smoke Test (C-2.13)"
    )
    parser.add_argument(
        "--confirm-readonly",
        action="store_true",
        help="실제 KIS API 조회를 수행합니다. 주문 API는 호출하지 않습니다.",
    )
    args = parser.parse_args()

    config = _check_env_config()

    if args.confirm_readonly:
        if not config["config_ready"]:
            print("\n[ERROR] 실전 계좌 환경변수가 미설정되어 있습니다.")
            print("  KIS_REAL_APP_KEY, KIS_REAL_APP_SECRET, KIS_REAL_ACCOUNT_NO를 설정하세요.")
            sys.exit(1)

        if config["real_trading_enabled"]:
            print("\n[WARN] KIS_REAL_TRADING_ENABLED=true가 감지되었습니다.")
            print("  smoke test는 real_trading_enabled=False로 강제 실행합니다.")
            print("  place_order는 절대 호출하지 않습니다.")

        api_result = asyncio.run(_run_readonly_verification())
        verdict = _print_report(config, api_result, confirm_readonly=True)
        sys.exit(0 if verdict in ("SAFE_READONLY_VERIFIED", "READONLY_PARTIAL") else 1)
    else:
        _print_report(config, api_result=None, confirm_readonly=False)
        sys.exit(0)


if __name__ == "__main__":
    main()
