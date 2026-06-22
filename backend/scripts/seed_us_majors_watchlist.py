"""C-5.3: 미국 주요종목 watchlist 시드 (멀티마켓 유니버스).

미국 대형주를 watchlist에 market="US" + 거래소 코드(NAS/NYS)와 함께 적재한다.
적재 후 universe=watchlist 전략들이 이 종목까지 자동으로 신호를 낸다 — 단,
KISOverseasClient(해외 시세)가 구성돼 있어야 시세 조회가 가능하다.

KIS 해외 거래소 코드:
    NAS = 나스닥, NYS = 뉴욕증권거래소, AMS = 아멕스(NYSE American).

기본 dry-run. --apply 지정 시에만 실제 적재. 멱등(이미 있는 종목은 skip).

주의:
    - 이 목록은 "스타터"다. 필요하면 _SYMBOLS를 직접 편집하거나 watchlist 화면에서
      추가/삭제하면 된다.
    - 적재만으로 신호가 나지는 않는다. 해외 시세(market_data) 수집과 KIS 해외 시세
      클라이언트 구성이 별도로 필요하다.

사용법:
    .venv/bin/python scripts/seed_us_majors_watchlist.py
    .venv/bin/python scripts/seed_us_majors_watchlist.py --apply
    .venv/bin/python scripts/seed_us_majors_watchlist.py --apply --name "US 주요종목"
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_ENV_FILE = _BACKEND_DIR / ".env"
if _ENV_FILE.exists():
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(dotenv_path=_ENV_FILE, override=False)


_DEFAULT_WATCHLIST_NAME = "US 주요종목 (대형주)"

# 미국 대형주 스타터 목록 (ticker, name, exchange). exchange는 KIS 해외 코드.
_SYMBOLS: list[tuple[str, str, str]] = [
    # --- 메가캡 테크 (나스닥) ---
    ("AAPL", "Apple", "NAS"), ("MSFT", "Microsoft", "NAS"),
    ("NVDA", "NVIDIA", "NAS"), ("AMZN", "Amazon", "NAS"),
    ("GOOGL", "Alphabet A", "NAS"), ("META", "Meta Platforms", "NAS"),
    ("TSLA", "Tesla", "NAS"), ("AVGO", "Broadcom", "NAS"),
    ("NFLX", "Netflix", "NAS"), ("AMD", "Advanced Micro Devices", "NAS"),
    ("ADBE", "Adobe", "NAS"), ("COST", "Costco", "NAS"),
    ("PEP", "PepsiCo", "NAS"), ("INTC", "Intel", "NAS"),
    ("QCOM", "Qualcomm", "NAS"), ("CSCO", "Cisco", "NAS"),
    ("AMAT", "Applied Materials", "NAS"), ("MU", "Micron", "NAS"),
    ("PLTR", "Palantir", "NAS"), ("MRVL", "Marvell", "NAS"),
    # --- NYSE 대형주 ---
    ("BRK.B", "Berkshire Hathaway B", "NYS"), ("JPM", "JPMorgan Chase", "NYS"),
    ("V", "Visa", "NYS"), ("MA", "Mastercard", "NYS"),
    ("JNJ", "Johnson & Johnson", "NYS"), ("WMT", "Walmart", "NYS"),
    ("PG", "Procter & Gamble", "NYS"), ("HD", "Home Depot", "NYS"),
    ("XOM", "Exxon Mobil", "NYS"), ("CVX", "Chevron", "NYS"),
    ("KO", "Coca-Cola", "NYS"), ("BAC", "Bank of America", "NYS"),
    ("ORCL", "Oracle", "NYS"), ("CRM", "Salesforce", "NYS"),
    ("MCD", "McDonald's", "NYS"), ("DIS", "Walt Disney", "NYS"),
    ("ABBV", "AbbVie", "NYS"), ("LLY", "Eli Lilly", "NYS"),
    ("UNH", "UnitedHealth", "NYS"), ("NKE", "Nike", "NYS"),
    ("PFE", "Pfizer", "NYS"), ("WFC", "Wells Fargo", "NYS"),
    ("GS", "Goldman Sachs", "NYS"), ("BA", "Boeing", "NYS"),
    ("CAT", "Caterpillar", "NYS"), ("GE", "GE Aerospace", "NYS"),
    ("T", "AT&T", "NYS"), ("VZ", "Verizon", "NYS"),
    ("IBM", "IBM", "NYS"), ("UBER", "Uber", "NYS"),
]


async def _get_or_create_watchlist(session, name: str):
    from sqlalchemy import select

    from app.domain.models.watchlist import Watchlist

    wl = (await session.execute(select(Watchlist).where(Watchlist.name == name))).scalar_one_or_none()
    created = False
    if wl is None:
        wl = Watchlist(name=name, description="C-5.3 미국 주요종목 유니버스 시드", enabled=True)
        session.add(wl)
        await session.flush()
        created = True
    return wl, created


async def run(session, *, apply: bool, name: str) -> dict:
    from sqlalchemy import select

    from app.domain.models.watchlist import WatchlistSymbol

    wl, created = await _get_or_create_watchlist(session, name)

    existing = set(
        (await session.execute(
            select(WatchlistSymbol.symbol_code).where(WatchlistSymbol.watchlist_id == wl.id)
        )).scalars().all()
    )
    to_add = [(c, n, exc) for c, n, exc in _SYMBOLS if c not in existing]

    if apply and to_add:
        for code, sym_name, exchange in to_add:
            session.add(WatchlistSymbol(
                watchlist_id=wl.id, symbol_code=code, symbol_name=sym_name,
                market="US", exchange=exchange, enabled=True, note="시드: US 주요종목",
            ))
        await session.commit()

    return {
        "watchlist_name": name,
        "watchlist_created": created,
        "total_in_list": len(_SYMBOLS),
        "already_present": len(_SYMBOLS) - len(to_add),
        "to_add": [f"{c} {n} ({exc})" for c, n, exc in to_add],
    }


def _print(info: dict, *, dry_run: bool) -> None:
    mode = "[DRY-RUN]" if dry_run else "[APPLIED]"
    print(f"\n{'=' * 60}\nUS 주요종목 watchlist 시드 {mode}\n{'=' * 60}")
    print(f"  watchlist: {info['watchlist_name']} ({'신규 생성' if info['watchlist_created'] else '기존'})")
    print(f"  목록 종목 {info['total_in_list']}개 / 이미 있음 {info['already_present']}개 / 추가 {len(info['to_add'])}개")
    if info["to_add"]:
        preview = ", ".join(info["to_add"][:8])
        more = f" 외 {len(info['to_add']) - 8}개" if len(info["to_add"]) > 8 else ""
        print(f"  추가 대상: {preview}{more}")
    print("  ※ 적재 후 신호가 나려면 해외 시세 수집 + KIS 해외 시세 클라이언트 구성이 필요합니다.")
    print("=" * 60)
    if dry_run and info["to_add"]:
        print("dry-run 입니다. 실제 적재하려면 --apply 를 붙여 다시 실행하세요.")


async def main(apply: bool, name: str) -> int:
    from scripts._common import db_session

    async with db_session() as session:
        info = await run(session, apply=apply, name=name)
    _print(info, dry_run=not apply)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C-5.3: 미국 주요종목 watchlist 시드")
    parser.add_argument("--apply", action="store_true", default=False, help="실제 적재. 미지정 시 dry-run.")
    parser.add_argument("--name", default=_DEFAULT_WATCHLIST_NAME, help="적재할 watchlist 이름.")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply, name=args.name)))
