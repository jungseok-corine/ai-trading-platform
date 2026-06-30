"""M2.15F-3C — manual non-KIS reference fill workflow 준비 검증.

manual snapshot에 metadata/db_* extra field가 있어도 parser/endpoint가 깨지지 않고, reference_*가 0이면 여전히
placeholder_reference로 분류됨을 확인. 읽기 전용 · DB write 0 · 실제 reference 값 미입력.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timezone import KST
from app.db.session import get_db
from app.main import app
from app.services import leader_trend_validation_service as svc_mod
from app.services.leader_trend_validation_service import LeaderTrendValidationService

DOCS = Path(__file__).resolve().parents[2] / "docs" / "data-validation"


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


def test_manual_snapshot_reference_values_still_placeholder_zero():
    data = json.loads(svc_mod._DEFAULT_REFERENCE_PATH.read_text(encoding="utf-8"))
    assert data.get("manual_fill_required") is True
    assert data.get("do_not_use_for_trading") is True
    assert data.get("manual_fill_status") == "placeholder_only"
    for s in data["symbols"]:
        # reference_*는 0 유지(실제 값 미입력)
        assert s["reference_close"] == 0 and s["high_52w"] == 0 and s["low_52w"] == 0
        # db_* baseline은 존재(참고용)
        assert "db_reference_close" in s and "db_high_52w" in s and "db_low_52w" in s
        assert s["source_close_basis"] == "MANUAL_INPUT_REQUIRED"


def test_parser_tolerates_extra_metadata_and_still_placeholder():
    # extra fields가 잔뜩 있어도 parser는 필요한 필드만 읽고 placeholder로 분류
    ref = {
        "source_name": "x", "manual_fill_required": True, "whatever": 123,
        "symbols": [{
            "symbol": "005930", "reference_close": 0, "high_52w": 0, "low_52w": 0,
            "source_url_or_note": "MANUAL REFERENCE REQUIRED",
            "db_reference_close": 323000, "extra_field": "ignored",
        }],
    }
    svc = LeaderTrendValidationService(session=None, reference=ref)  # type: ignore[arg-type]
    assert svc._reference["symbols"][0]["reference_close"] == 0


async def _seed(session, symbol, hloc):
    base = datetime(2025, 1, 1, tzinfo=KST)
    rows = [{"s": symbol, "ts": base + timedelta(days=i), "o": c, "h": h, "l": lo, "c": c, "v": 1000}
            for i, (h, lo, c) in enumerate(hloc)]
    await session.execute(text(
        "insert into market_data (symbol_code,timeframe,ts,open,high,low,close,volume) "
        "values (:s,'1d',:ts,:o,:h,:l,:c,:v)"), rows)
    await session.flush()


async def test_default_endpoint_returns_placeholder_with_enriched_snapshot(db_session: AsyncSession):
    # 모든 pilot 시드 → 풍부한 metadata manual snapshot 사용해도 5개 placeholder_reference
    for s in ("005930", "000660", "035420", "005380", "051910"):
        await _seed(db_session, s, [(120, 100, 110)])
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            b = (await c.get("/api/v1/leader-trend/validation/non-kis-52w")).json()
    finally:
        app.dependency_overrides.clear()
    assert b["summary"]["placeholder_reference"] == 5
    assert b["summary"]["matched"] == 0 and b["summary"]["major_diff"] == 0


def test_runtime_default_path_is_manual_snapshot_no_tests_dep():
    p = svc_mod._DEFAULT_REFERENCE_PATH
    assert p.parts[-1] == "non_kis_52w_reference_pilot5.manual.json"
    assert "tests" not in p.parts
    assert p.exists()


def test_docs_checklist_and_template_sections_exist():
    checklist = DOCS / "manual-non-kis-reference-fill-checklist.md"
    template = DOCS / "non-kis-52w-validation-report-template.md"
    assert checklist.exists()
    ctext = checklist.read_text(encoding="utf-8")
    assert "Manual Non-KIS Reference Fill Checklist" in ctext
    assert "KIS 출처 사용 금지" in ctext
    ttext = template.read_text(encoding="utf-8")
    assert "Do not proceed if" in ttext
    assert "Manual Reference Fill Evidence" in ttext
