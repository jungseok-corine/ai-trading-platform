"""M2.15F-2 — manual reference snapshot ↔ test fixture 역할 분리 검증.

runtime default reference는 app/data/reference/...manual.json(placeholder)이며 tests 디렉토리에 의존하지 않는다.
읽기 전용 · DB write 0 · KIS/http 0 · SignalLog/Trade/Order/CandidateEvent 0.
"""
import json

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.services import leader_trend_validation_service as svc_mod
from app.services.leader_trend_validation_service import LeaderTrendValidationService


def _override_get_db(session: AsyncSession):
    async def _get_db():
        yield session
    return _get_db


def test_runtime_default_path_is_app_data_reference():
    p = svc_mod._DEFAULT_REFERENCE_PATH
    parts = p.parts
    # app/data/reference/non_kis_52w_reference_pilot5.manual.json
    assert parts[-1] == "non_kis_52w_reference_pilot5.manual.json"
    assert parts[-2] == "reference"
    assert parts[-3] == "data"
    assert parts[-4] == "app"
    assert "tests" not in parts          # runtime은 tests 디렉토리에 의존하지 않는다
    assert p.exists()                    # manual snapshot 파일 존재


def test_runtime_default_snapshot_is_placeholder():
    data = json.loads(svc_mod._DEFAULT_REFERENCE_PATH.read_text(encoding="utf-8"))
    assert data["source_name"] == "manual_non_kis_reference"
    assert "MANUAL REFERENCE REQUIRED" in data["source_note"]
    syms = {s["symbol"] for s in data["symbols"]}
    assert syms == {"005930", "000660", "035420", "005380", "051910"}
    # 전부 placeholder(0) — 실제 값은 사람이 채운다
    for s in data["symbols"]:
        assert s["reference_close"] == 0 and s["high_52w"] == 0 and s["low_52w"] == 0


def test_service_module_does_not_reference_tests_dir():
    src = open(svc_mod.__file__, encoding="utf-8").read()
    assert "tests/fixtures" not in src   # runtime 코드가 tests 디렉토리 경로에 의존하지 않음


async def test_api_default_uses_manual_snapshot_placeholder(db_session: AsyncSession):
    # default(인자 없음) → manual snapshot(placeholder) 사용 → DB 있는 종목은 placeholder_reference
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            body = (await c.get("/api/v1/leader-trend/validation/non-kis-52w")).json()
    finally:
        app.dependency_overrides.clear()
    assert body["total_symbols_checked"] == 5
    assert body["external_reference_auto_fetch"] is False
    assert body["read_only"] is True
    # placeholder snapshot → DB 없는 종목 missing_db_data, 있으면 placeholder_reference; major/minor/matched 없음
    assert body["summary"]["matched"] == 0
    assert body["summary"]["minor_diff"] == 0
    assert body["summary"]["major_diff"] == 0
    assert body["summary"]["placeholder_reference"] + body["summary"]["missing_db_data"] == 5


def test_explicit_reference_injection_still_works(tmp_path):
    # service에 reference dict 주입 시 default 파일과 무관하게 동작(테스트 격리 보장)
    ref = {"source_name": "synthetic", "symbols": [
        {"symbol": "X", "reference_close": 100, "high_52w": 110, "low_52w": 90, "source_url_or_note": "real"}]}
    s = LeaderTrendValidationService(session=None, reference=ref)  # type: ignore[arg-type]
    assert s._reference["source_name"] == "synthetic"
