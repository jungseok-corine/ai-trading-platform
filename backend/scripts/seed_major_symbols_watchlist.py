"""C-4: 주요종목(대형주) watchlist 시드.

전체 종목 마스터가 없는 현 구조에서, 잘 알려진 KOSPI/KOSDAQ 대형주를 watchlist에
한 번에 적재해 "유니버스"를 넓힌다. 적재 후 기존 universe=watchlist 전략들이
이 종목들까지 자동으로 신호를 낸다(스캐너 파이프라인 대상도 동일).

기본 dry-run. --apply 지정 시에만 실제 적재. 멱등(이미 있는 종목은 skip).

주의:
    - 이 목록은 "스타터"다. 종목/코드는 합병·이전상장 등으로 바뀔 수 있으니
      필요하면 _SYMBOLS를 직접 편집하거나 watchlist 화면에서 추가/삭제하면 된다.
    - 적재만으로 신호가 나지는 않는다. 그 종목들의 시세(market_data) 수집이 별도로
      필요하다(KIS rate limit 때문에 장마감 후 배치 권장).

사용법:
    .venv/bin/python scripts/seed_major_symbols_watchlist.py
    .venv/bin/python scripts/seed_major_symbols_watchlist.py --apply
    .venv/bin/python scripts/seed_major_symbols_watchlist.py --apply --name "주요종목"
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


_DEFAULT_WATCHLIST_NAME = "주요종목 (대형주)"

# 잘 알려진 KOSPI/KOSDAQ 대형주 스타터 목록 (code, name).
_SYMBOLS: list[tuple[str, str]] = [
    # --- KOSPI 대형주 ---
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("373220", "LG에너지솔루션"),
    ("207940", "삼성바이오로직스"), ("005380", "현대차"), ("000270", "기아"),
    ("005490", "POSCO홀딩스"), ("035420", "NAVER"), ("051910", "LG화학"),
    ("006400", "삼성SDI"), ("035720", "카카오"), ("028260", "삼성물산"),
    ("012330", "현대모비스"), ("105560", "KB금융"), ("055550", "신한지주"),
    ("086790", "하나금융지주"), ("015760", "한국전력"), ("033780", "KT&G"),
    ("017670", "SK텔레콤"), ("030200", "KT"), ("032830", "삼성생명"),
    ("009150", "삼성전기"), ("010130", "고려아연"), ("018260", "삼성에스디에스"),
    ("034730", "SK"), ("096770", "SK이노베이션"), ("010950", "S-Oil"),
    ("051900", "LG생활건강"), ("068270", "셀트리온"), ("066570", "LG전자"),
    ("011070", "LG이노텍"), ("036570", "엔씨소프트"), ("259960", "크래프톤"),
    ("352820", "하이브"), ("097950", "CJ제일제당"), ("271560", "오리온"),
    ("003490", "대한항공"), ("086280", "현대글로비스"), ("000810", "삼성화재"),
    ("024110", "기업은행"), ("138040", "메리츠금융지주"), ("329180", "HD현대중공업"),
    ("012450", "한화에어로스페이스"), ("042660", "한화오션"), ("009540", "HD한국조선해양"),
    ("047810", "한국항공우주"), ("064350", "현대로템"), ("010140", "삼성중공업"),
    # --- KOSDAQ 대형주 ---
    ("247540", "에코프로비엠"), ("086520", "에코프로"), ("028300", "HLB"),
    ("196170", "알테오젠"), ("058470", "리노공업"), ("240810", "원익IPS"),
    ("039030", "이오테크닉스"), ("005290", "동진쎄미켐"), ("036930", "주성엔지니어링"),
    ("213420", "덕산네오룩스"), ("145020", "휴젤"), ("214150", "클래시스"),
]


async def _get_or_create_watchlist(session, name: str):
    from sqlalchemy import select

    from app.domain.models.watchlist import Watchlist

    wl = (await session.execute(select(Watchlist).where(Watchlist.name == name))).scalar_one_or_none()
    created = False
    if wl is None:
        wl = Watchlist(name=name, description="C-4 주요종목 유니버스 시드", enabled=True)
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
    to_add = [(c, n) for c, n in _SYMBOLS if c not in existing]

    if apply and to_add:
        for code, sym_name in to_add:
            session.add(WatchlistSymbol(
                watchlist_id=wl.id, symbol_code=code, symbol_name=sym_name,
                enabled=True, note="시드: 주요종목",
            ))
        await session.commit()

    return {
        "watchlist_name": name,
        "watchlist_created": created,
        "total_in_list": len(_SYMBOLS),
        "already_present": len(_SYMBOLS) - len(to_add),
        "to_add": [f"{c} {n}" for c, n in to_add],
    }


def _print(info: dict, *, dry_run: bool) -> None:
    mode = "[DRY-RUN]" if dry_run else "[APPLIED]"
    print(f"\n{'=' * 60}\n주요종목 watchlist 시드 {mode}\n{'=' * 60}")
    print(f"  watchlist: {info['watchlist_name']} ({'신규 생성' if info['watchlist_created'] else '기존'})")
    print(f"  목록 종목 {info['total_in_list']}개 / 이미 있음 {info['already_present']}개 / 추가 {len(info['to_add'])}개")
    if info["to_add"]:
        preview = ", ".join(info["to_add"][:8])
        more = f" 외 {len(info['to_add']) - 8}개" if len(info["to_add"]) > 8 else ""
        print(f"  추가 대상: {preview}{more}")
    print("  ※ 적재 후에도 신호가 나려면 그 종목들 시세 수집(market_data)이 필요합니다.")
    print("=" * 60)
    if dry_run and info["to_add"]:
        print("dry-run 입니다. 실제 적재하려면 --apply 를 붙여 다시 실행하세요.")


async def main(apply: bool, name: str) -> int:
    from app.db.session import async_session_factory, engine

    async with async_session_factory() as session:
        info = await run(session, apply=apply, name=name)
    await engine.dispose()
    _print(info, dry_run=not apply)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C-4: 주요종목(대형주) watchlist 시드")
    parser.add_argument("--apply", action="store_true", default=False, help="실제 적재. 미지정 시 dry-run.")
    parser.add_argument("--name", default=_DEFAULT_WATCHLIST_NAME, help="적재할 watchlist 이름.")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply, name=args.name)))
