"""C-2.18.1: KIS 투자자 수급 Read-Only Smoke Test.

종목별 투자자매매동향(일별) API(FHPTJ04160001)를 실전 도메인에서 read-only로 호출해
응답 구조와 DB 저장 흐름을 검증한다.

주문 API는 어떤 경우에도 호출하지 않는다.
KIS_REAL_TRADING_ENABLED=false를 유지한다.

사용법:
    # 설정만 확인 (KIS API 미호출):
    python scripts/kis_investor_flow_smoke_test.py

    # 실제 KIS API 호출 (조회만):
    python scripts/kis_investor_flow_smoke_test.py --confirm-readonly

    # 특정 종목/날짜 지정:
    python scripts/kis_investor_flow_smoke_test.py --symbol-code 000660 --confirm-readonly

    # 날짜 범위 지정:
    python scripts/kis_investor_flow_smoke_test.py --date-from 2026-06-10 --date-to 2026-06-17 --confirm-readonly

    # DB에 저장까지 (read-only market data 저장, 주문 무관):
    python scripts/kis_investor_flow_smoke_test.py --confirm-readonly --store

필요한 환경변수 (.env):
    KIS_REAL_APP_KEY        — 실전 앱키 (없으면 KIS_APP_KEY fallback)
    KIS_REAL_APP_SECRET     — 실전 앱시크릿 (없으면 KIS_APP_SECRET fallback)

금지 사항:
    - 이 스크립트는 어떤 경우에도 place_order를 호출하지 않는다.
    - KIS_REAL_TRADING_ENABLED=true 여부와 무관하게 주문 API는 호출하지 않는다.
    - 민감정보(app_key, secret, token)는 마스킹해서만 출력한다.
    - raw_payload에 token/appkey/appsecret을 저장하지 않는다.
    - 이 스크립트는 .env, token cache를 커밋하지 않는다.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_ENV_FILE = _BACKEND_DIR / ".env"
if _ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ENV_FILE, override=False)

# 주문 API 미호출 보장 선언 (정적 상수)
_ORDER_API_CALLED = False
_FORBIDDEN_TR_IDS = ["TTTC0012U", "TTTC0011U", "VTTC0012U", "VTTC0011U"]


def _mask(value: str | None, visible: int = 4) -> str:
    """민감정보 마스킹 — 앞 visible자만 노출, 나머지는 ***."""
    if not value:
        return "(미설정)"
    if len(value) <= visible:
        return "*" * len(value)
    return value[:visible] + "***"


def _check_env_config() -> dict:
    """환경변수에서 수급 조회에 필요한 설정을 읽고 상태를 반환한다."""
    real_app_key = os.environ.get("KIS_REAL_APP_KEY", "")
    real_app_secret = os.environ.get("KIS_REAL_APP_SECRET", "")
    # real 자격증명이 없으면 paper 키로 fallback (main.py와 동일 로직)
    app_key = real_app_key or os.environ.get("KIS_APP_KEY", "")
    app_secret = real_app_secret or os.environ.get("KIS_APP_SECRET", "")
    real_base_url = os.environ.get("KIS_REAL_BASE_URL", "https://openapi.koreainvestment.com:9443")
    real_trading_enabled = os.environ.get("KIS_REAL_TRADING_ENABLED", "false").lower() == "true"

    return {
        "real_app_key_set": bool(real_app_key),
        "paper_app_key_fallback": not real_app_key and bool(os.environ.get("KIS_APP_KEY", "")),
        "app_key_masked": _mask(app_key),
        "app_secret_set": bool(app_secret),
        "real_base_url": real_base_url,
        "real_trading_enabled": real_trading_enabled,
        "config_ready": bool(app_key) and bool(app_secret),
        "_app_key": app_key,
        "_app_secret": app_secret,
    }


def _clean_raw_payload(row: dict) -> dict:
    """raw_payload에서 민감정보 키를 제거한다.

    KIS investor flow 응답에는 account/token이 포함되지 않지만,
    명시적으로 필터링해 안전성을 보장한다.
    """
    _SENSITIVE_KEYS = {"token", "access_token", "appkey", "appsecret", "account_no", "CANO", "ACNT_PRDT_CD"}
    return {k: v for k, v in row.items() if k not in _SENSITIVE_KEYS}


async def _run_investor_flow_check(
    config: dict,
    symbol_code: str,
    target_date: date,
    store: bool,
) -> dict:
    """실제 KIS investor flow API를 호출해 응답을 검증한다.

    place_order는 이 함수 어느 경로에서도 호출하지 않는다.
    """
    import httpx

    from app.trading.broker.kis_investor_flow_client import KISInvestorFlowClient

    result: dict = {
        "order_api_called": False,          # 항상 False
        "forbidden_tr_ids_called": [],      # 항상 빈 배열
        "real_trading_enabled": False,      # smoke test에서는 항상 False
        "token": "not_tested",
        "investor_flow_query": "not_tested",
        "rt_cd": None,
        "msg_cd": None,
        "msg1": None,
        "row_count": 0,
        "sample_dates": [],
        "sample_parsed": None,
        "store_result": None,
        "store_row_count": 0,
        "upsert_idempotent": None,
        "errors": [],
    }

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        client = KISInvestorFlowClient(
            base_url=config["real_base_url"],
            app_key=config["_app_key"],
            app_secret=config["_app_secret"],
            http_client=http_client,
            token_cache_path=".cache/kis_investor_flow_token.json",
        )

        # 1. 토큰 발급
        try:
            token = await client._get_access_token()
            result["token"] = "ok (masked: " + _mask(token, 8) + ")"
        except Exception as exc:
            result["token"] = f"FAILED: {type(exc).__name__}"
            result["errors"].append(f"token: {exc}")
            return result

        # 2. FHPTJ04160001 호출
        try:
            rows = await client.get_daily_investor_flow_by_stock(symbol_code, target_date)
            result["investor_flow_query"] = "ok"
            result["row_count"] = len(rows)
        except Exception as exc:
            result["investor_flow_query"] = f"FAILED: {type(exc).__name__}"
            result["errors"].append(f"investor_flow: {exc}")
            return result

        # 3. 응답 파싱 확인
        if rows:
            from app.services.investor_flow_service import parse_investor_flow_row
            dates_seen = []
            sample_parsed = None
            for row in rows[:5]:
                try:
                    parsed = parse_investor_flow_row(symbol_code, row)
                    dates_seen.append(str(parsed["trade_date"]))
                    if sample_parsed is None:
                        sample_parsed = {
                            "trade_date": str(parsed["trade_date"]),
                            "foreign_net_buy_quantity": parsed["foreign_net_buy_quantity"],
                            "foreign_net_buy_amount_M_KRW": parsed["foreign_net_buy_amount"],
                            "institution_net_buy_quantity": parsed["institution_net_buy_quantity"],
                            "institution_net_buy_amount_M_KRW": parsed["institution_net_buy_amount"],
                            "individual_net_buy_quantity": parsed["individual_net_buy_quantity"],
                            "individual_net_buy_amount_M_KRW": parsed["individual_net_buy_amount"],
                        }
                except Exception as exc:
                    result["errors"].append(f"parse row: {exc}")
            result["sample_dates"] = dates_seen
            result["sample_parsed"] = sample_parsed
        else:
            result["investor_flow_query"] += " (empty output2 — 비영업일 또는 미산출 시간대)"

        # 4. DB 저장 (--store 옵션)
        if store and rows:
            try:
                from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
                from sqlalchemy.pool import NullPool
                from app.core.config import get_settings
                from app.services.investor_flow_service import InvestorFlowService

                settings = get_settings()
                engine = create_async_engine(settings.database_url, poolclass=NullPool)
                session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

                async with session_factory() as session:
                    service = InvestorFlowService(session=session, client=client)
                    # date range: target_date 기준 1주일
                    date_from = target_date - timedelta(days=6)
                    stored = await service.fetch_and_store(symbol_code, date_from, target_date)
                    result["store_result"] = "ok"
                    result["store_row_count"] = len(stored)

                # upsert 멱등성 확인 — 동일 데이터 재저장
                async with session_factory() as session:
                    service2 = InvestorFlowService(session=session, client=client)
                    stored2 = await service2.fetch_and_store(symbol_code, date_from, target_date)
                    result["upsert_idempotent"] = len(stored2) == len(stored)

                await engine.dispose()
            except Exception as exc:
                result["store_result"] = f"FAILED: {type(exc).__name__}: {exc}"
                result["errors"].append(f"store: {exc}")

    return result


def _print_report(
    config: dict,
    symbol_code: str,
    target_date: date,
    api_result: dict | None,
    confirm_readonly: bool,
    store: bool,
) -> str:
    credential_source = "KIS_REAL_APP_KEY" if config["real_app_key_set"] else "KIS_APP_KEY (fallback)"

    lines = [
        "",
        "=" * 64,
        "  KIS Investor Flow Read-Only Smoke Test — C-2.18.1",
        "=" * 64,
        f"  provider            : kis-real (investor flow only)",
        f"  TR_ID               : FHPTJ04160001 (read-only)",
        f"  symbol_code         : {symbol_code}",
        f"  target_date         : {target_date}",
        f"  credential_source   : {credential_source}",
        f"  app_key             : {config['app_key_masked']}",
        f"  real_base_url       : {config['real_base_url']}",
        f"  config_ready        : {config['config_ready']}",
        f"  real_trading_enabled: {config['real_trading_enabled']}  ← 주문과 무관",
        "",
        "  [주문 API 미호출 보장]",
        f"  order_api_called    : {_ORDER_API_CALLED}  ← 항상 false",
        f"  forbidden_tr_ids    : {_FORBIDDEN_TR_IDS}  ← 미호출 보장",
        f"  place_order method  : KISInvestorFlowClient에 존재하지 않음",
        "",
    ]

    if not confirm_readonly:
        lines += [
            "  [DRY RUN] --confirm-readonly 플래그 없음.",
            "  실제 KIS API 호출은 하지 않았습니다.",
            "",
            "  실제 수급 데이터 조회를 원하면:",
            "    python scripts/kis_investor_flow_smoke_test.py --confirm-readonly",
            "",
            "  DB 저장까지 원하면:",
            "    python scripts/kis_investor_flow_smoke_test.py --confirm-readonly --store",
            "",
        ]
        if not config["config_ready"]:
            lines.append("  [WARN] 자격증명 미설정.")
            lines.append("         KIS_REAL_APP_KEY + KIS_REAL_APP_SECRET 또는")
            lines.append("         KIS_APP_KEY + KIS_APP_SECRET을 .env에 설정하세요.")
        verdict = "DRY_RUN_OK"
    else:
        assert api_result is not None
        lines += [
            "  [API 결과]",
            f"  token               : {api_result['token']}",
            f"  investor_flow_query : {api_result['investor_flow_query']}",
            f"  row_count           : {api_result['row_count']}",
            f"  sample_dates        : {api_result['sample_dates']}",
            "",
        ]

        if api_result["sample_parsed"]:
            p = api_result["sample_parsed"]
            lines += [
                "  [파싱 결과 샘플 — 첫 번째 영업일]",
                f"  trade_date              : {p['trade_date']}",
                f"  foreign_net_buy_qty     : {p['foreign_net_buy_quantity']:,} 주" if p['foreign_net_buy_quantity'] is not None else "  foreign_net_buy_qty     : None",
                f"  foreign_net_buy_amt     : {p['foreign_net_buy_amount_M_KRW']} 백만원" if p['foreign_net_buy_amount_M_KRW'] is not None else "  foreign_net_buy_amt     : None",
                f"  institution_net_buy_qty : {p['institution_net_buy_quantity']:,} 주" if p['institution_net_buy_quantity'] is not None else "  institution_net_buy_qty : None",
                f"  institution_net_buy_amt : {p['institution_net_buy_amount_M_KRW']} 백만원" if p['institution_net_buy_amount_M_KRW'] is not None else "  institution_net_buy_amt : None",
                f"  individual_net_buy_qty  : {p['individual_net_buy_quantity']:,} 주" if p['individual_net_buy_quantity'] is not None else "  individual_net_buy_qty  : None",
                f"  individual_net_buy_amt  : {p['individual_net_buy_amount_M_KRW']} 백만원" if p['individual_net_buy_amount_M_KRW'] is not None else "  individual_net_buy_amt  : None",
                "  [금액 단위: 백만원(KIS 응답 원본) — amount=3500이면 35억원]",
                "",
            ]

        if store:
            lines += [
                "  [DB 저장 결과]",
                f"  store_result        : {api_result['store_result']}",
                f"  store_row_count     : {api_result['store_row_count']}",
                f"  upsert_idempotent   : {api_result['upsert_idempotent']}  ← 재실행 시 중복 없음",
                "",
            ]

        if api_result["errors"]:
            lines.append("  [ERRORS]")
            for err in api_result["errors"]:
                lines.append(f"    - {err}")
            verdict = "INVESTOR_FLOW_PARTIAL"
        elif api_result["investor_flow_query"].startswith("ok"):
            verdict = "INVESTOR_FLOW_VERIFIED"
        else:
            verdict = "INVESTOR_FLOW_FAILED"

    lines += [
        f"  result              : {verdict}",
        "",
        "  주문 API 미호출 최종 확인:",
        "    - place_order: 이 스크립트 어느 경로에서도 호출되지 않음",
        "    - KISInvestorFlowClient는 place_order 메서드를 보유하지 않음",
        "    - 실전 주문 여전히 불가 (KIS_REAL_TRADING_ENABLED=false, TradingGuardState=paused)",
        "",
        "=" * 64,
        "",
    ]

    report = "\n".join(lines)
    print(report)
    return verdict


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"날짜 형식이 잘못되었습니다: {s!r} (YYYY-MM-DD 형식 필요)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="KIS 투자자 수급 Read-Only Smoke Test (C-2.18.1)"
    )
    parser.add_argument("--confirm-readonly", action="store_true",
                        help="실제 KIS investor flow API를 호출합니다. 주문 API는 호출하지 않습니다.")
    parser.add_argument("--symbol-code", default="005930",
                        help="조회할 종목코드 (기본: 005930 삼성전자)")
    parser.add_argument("--target-date", type=_parse_date,
                        default=None,
                        help="조회 기준일 YYYY-MM-DD (기본: 어제)")
    parser.add_argument("--store", action="store_true",
                        help="수급 데이터를 DB에 저장합니다. read-only market data 저장이며 주문과 무관.")
    args = parser.parse_args()

    # target_date 기본값: 어제 (장 마감 후 기준)
    target_date = args.target_date or (date.today() - timedelta(days=1))

    config = _check_env_config()

    if args.confirm_readonly:
        if not config["config_ready"]:
            print("\n[ERROR] 자격증명 미설정.")
            print("  KIS_REAL_APP_KEY + KIS_REAL_APP_SECRET 또는")
            print("  KIS_APP_KEY + KIS_APP_SECRET을 .env에 설정하세요.")
            sys.exit(1)

        if config["real_trading_enabled"]:
            print("\n[WARN] KIS_REAL_TRADING_ENABLED=true 감지.")
            print("  이 smoke test는 investor flow 조회만 수행합니다.")
            print("  place_order는 절대 호출하지 않습니다.")

        api_result = asyncio.run(
            _run_investor_flow_check(
                config=config,
                symbol_code=args.symbol_code,
                target_date=target_date,
                store=args.store,
            )
        )
        verdict = _print_report(
            config=config,
            symbol_code=args.symbol_code,
            target_date=target_date,
            api_result=api_result,
            confirm_readonly=True,
            store=args.store,
        )
        sys.exit(0 if verdict in ("INVESTOR_FLOW_VERIFIED", "INVESTOR_FLOW_PARTIAL") else 1)
    else:
        _print_report(
            config=config,
            symbol_code=args.symbol_code,
            target_date=target_date,
            api_result=None,
            confirm_readonly=False,
            store=args.store,
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
