"""C-2.18.1: KIS Investor Flow Smoke Test 스크립트 테스트.

kis_investor_flow_smoke_test.py 스크립트의 동작을 검증한다.
실제 KIS API는 호출하지 않는다 (모두 mock).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ─── smoke test 모듈 import (dotenv 로드 없이) ───────────────────────────────
@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    """dotenv 로드를 막아 테스트 환경 오염 방지."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda **kw: None, raising=False)


def _import_smoke():
    """smoke test 모듈을 매 테스트마다 fresh import한다."""
    import importlib
    import scripts.kis_investor_flow_smoke_test as m
    importlib.reload(m)
    return m


# ─── _mask 함수 ───────────────────────────────────────────────────────────────

class TestMask:
    def test_none_returns_unset(self):
        m = _import_smoke()
        assert m._mask(None) == "(미설정)"

    def test_empty_string_returns_unset(self):
        m = _import_smoke()
        assert m._mask("") == "(미설정)"

    def test_short_value_all_stars(self):
        m = _import_smoke()
        result = m._mask("ab")
        assert "*" in result
        assert "a" not in result
        assert "b" not in result

    def test_long_value_shows_prefix_only(self):
        m = _import_smoke()
        val = "APP_KEY_1234567890"
        result = m._mask(val)
        assert result.startswith("APP_")
        assert "***" in result
        assert "1234567890" not in result

    def test_visible_param(self):
        m = _import_smoke()
        result = m._mask("ABCDEFGH", visible=6)
        assert result.startswith("ABCDEF")
        assert "GH" not in result


# ─── _check_env_config ────────────────────────────────────────────────────────

class TestCheckEnvConfig:
    def test_empty_env_config_not_ready(self, monkeypatch):
        m = _import_smoke()
        monkeypatch.delenv("KIS_REAL_APP_KEY", raising=False)
        monkeypatch.delenv("KIS_REAL_APP_SECRET", raising=False)
        monkeypatch.delenv("KIS_APP_KEY", raising=False)
        monkeypatch.delenv("KIS_APP_SECRET", raising=False)
        monkeypatch.delenv("KIS_REAL_TRADING_ENABLED", raising=False)
        cfg = m._check_env_config()
        assert cfg["config_ready"] is False
        assert cfg["real_app_key_set"] is False

    def test_real_keys_set_config_ready(self, monkeypatch):
        m = _import_smoke()
        monkeypatch.setenv("KIS_REAL_APP_KEY", "REAL_KEY_XXXX")
        monkeypatch.setenv("KIS_REAL_APP_SECRET", "REAL_SECRET_XXXX")
        monkeypatch.delenv("KIS_APP_KEY", raising=False)
        monkeypatch.delenv("KIS_APP_SECRET", raising=False)
        monkeypatch.delenv("KIS_REAL_TRADING_ENABLED", raising=False)
        cfg = m._check_env_config()
        assert cfg["config_ready"] is True
        assert cfg["real_app_key_set"] is True

    def test_fallback_to_paper_keys(self, monkeypatch):
        m = _import_smoke()
        monkeypatch.delenv("KIS_REAL_APP_KEY", raising=False)
        monkeypatch.delenv("KIS_REAL_APP_SECRET", raising=False)
        monkeypatch.setenv("KIS_APP_KEY", "PAPER_KEY")
        monkeypatch.setenv("KIS_APP_SECRET", "PAPER_SECRET")
        monkeypatch.delenv("KIS_REAL_TRADING_ENABLED", raising=False)
        cfg = m._check_env_config()
        assert cfg["paper_app_key_fallback"] is True
        assert cfg["config_ready"] is True

    def test_real_trading_enabled_false_by_default(self, monkeypatch):
        m = _import_smoke()
        monkeypatch.delenv("KIS_REAL_TRADING_ENABLED", raising=False)
        cfg = m._check_env_config()
        assert cfg["real_trading_enabled"] is False

    def test_app_key_masked_in_output(self, monkeypatch):
        m = _import_smoke()
        monkeypatch.setenv("KIS_REAL_APP_KEY", "REAL_KEY_SHOULD_NOT_APPEAR")
        monkeypatch.setenv("KIS_REAL_APP_SECRET", "SECRET_SHOULD_NOT_APPEAR")
        monkeypatch.delenv("KIS_APP_KEY", raising=False)
        monkeypatch.delenv("KIS_APP_SECRET", raising=False)
        monkeypatch.delenv("KIS_REAL_TRADING_ENABLED", raising=False)
        cfg = m._check_env_config()
        # 마스킹 확인: 전체 값이 노출되지 않아야 한다
        assert "REAL_KEY_SHOULD_NOT_APPEAR" not in cfg["app_key_masked"]
        assert "***" in cfg["app_key_masked"]


# ─── _clean_raw_payload ───────────────────────────────────────────────────────

class TestCleanRawPayload:
    def test_sensitive_keys_removed(self):
        m = _import_smoke()
        raw = {
            "stck_bsop_date": "20260617",
            "frgn_ntby_qty": "1000",
            "token": "SECRET_TOKEN",
            "access_token": "ANOTHER_TOKEN",
            "appkey": "MY_APP_KEY",
            "appsecret": "MY_APP_SECRET",
            "CANO": "12345678",
        }
        cleaned = m._clean_raw_payload(raw)
        assert "stck_bsop_date" in cleaned
        assert "frgn_ntby_qty" in cleaned
        assert "token" not in cleaned
        assert "access_token" not in cleaned
        assert "appkey" not in cleaned
        assert "appsecret" not in cleaned
        assert "CANO" not in cleaned

    def test_non_sensitive_keys_preserved(self):
        m = _import_smoke()
        raw = {"stck_bsop_date": "20260617", "frgn_ntby_qty": "1000", "prsn_ntby_qty": "-500"}
        cleaned = m._clean_raw_payload(raw)
        assert cleaned == raw


# ─── dry-run (--confirm-readonly 없음) ────────────────────────────────────────

class TestDryRun:
    def test_dry_run_does_not_call_kis(self, capsys, monkeypatch):
        """--confirm-readonly 없이 실행 시 KIS API를 호출하지 않는다."""
        m = _import_smoke()
        monkeypatch.setenv("KIS_REAL_APP_KEY", "FAKE_KEY")
        monkeypatch.setenv("KIS_REAL_APP_SECRET", "FAKE_SECRET")

        with patch("scripts.kis_investor_flow_smoke_test.asyncio.run") as mock_run:
            config = m._check_env_config()
            verdict = m._print_report(
                config=config,
                symbol_code="005930",
                target_date=date(2026, 6, 17),
                api_result=None,
                confirm_readonly=False,
                store=False,
            )
            mock_run.assert_not_called()

        assert verdict == "DRY_RUN_OK"
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "FAKE_KEY" not in out  # 민감정보 미출력

    def test_dry_run_exits_zero(self, monkeypatch):
        m = _import_smoke()
        monkeypatch.setenv("KIS_REAL_APP_KEY", "FAKE_KEY")
        monkeypatch.setenv("KIS_REAL_APP_SECRET", "FAKE_SECRET")
        monkeypatch.setattr("sys.argv", ["smoke"])  # --confirm-readonly 없음

        with pytest.raises(SystemExit) as exc_info:
            m.main()
        assert exc_info.value.code == 0

    def test_dry_run_shows_order_api_not_called(self, capsys, monkeypatch):
        m = _import_smoke()
        monkeypatch.setenv("KIS_REAL_APP_KEY", "FAKE_KEY")
        monkeypatch.setenv("KIS_REAL_APP_SECRET", "FAKE_SECRET")
        config = m._check_env_config()
        m._print_report(
            config=config,
            symbol_code="005930",
            target_date=date(2026, 6, 17),
            api_result=None,
            confirm_readonly=False,
            store=False,
        )
        out = capsys.readouterr().out
        assert "order_api_called" in out
        assert "False" in out or "false" in out.lower()
        assert "TTTC0012U" in out  # forbidden TR_IDs가 목록에 있어야 한다


# ─── _run_investor_flow_check mock 실행 ──────────────────────────────────────

def _make_fake_rows():
    return [
        {
            "stck_bsop_date": "20260617",
            "frgn_ntby_qty": "123456",
            "frgn_ntby_tr_pbmn": "7890",
            "orgn_ntby_qty": "-50000",
            "orgn_ntby_tr_pbmn": "-3200",
            "prsn_ntby_qty": "-73456",
            "prsn_ntby_tr_pbmn": "-4690",
        },
        {
            "stck_bsop_date": "20260616",
            "frgn_ntby_qty": "200000",
            "frgn_ntby_tr_pbmn": "12000",
            "orgn_ntby_qty": "100000",
            "orgn_ntby_tr_pbmn": "6000",
            "prsn_ntby_qty": "-300000",
            "prsn_ntby_tr_pbmn": "-18000",
        },
    ]


class TestRunInvestorFlowCheckMocked:
    @pytest.mark.asyncio
    async def test_returns_rows_on_success(self, monkeypatch):
        """mock KIS client가 rows를 반환하면 결과에 row_count가 반영된다."""
        m = _import_smoke()
        fake_rows = _make_fake_rows()
        fake_token = "FAKE_TOKEN_ABCDEF"

        mock_client = AsyncMock()
        mock_client._get_access_token = AsyncMock(return_value=fake_token)
        mock_client.get_daily_investor_flow_by_stock = AsyncMock(return_value=fake_rows)

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        config = {
            "real_base_url": "https://fake.kis.kr",
            "_app_key": "FAKE_KEY",
            "_app_secret": "FAKE_SECRET",
        }

        with patch("app.trading.broker.kis_investor_flow_client.KISInvestorFlowClient", return_value=mock_client), \
             patch("httpx.AsyncClient", return_value=mock_http):
            result = await m._run_investor_flow_check(
                config=config,
                symbol_code="005930",
                target_date=date(2026, 6, 17),
                store=False,
            )

        assert result["order_api_called"] is False
        assert result["forbidden_tr_ids_called"] == []
        assert result["investor_flow_query"] == "ok"
        assert result["row_count"] == 2
        assert "2026-06-17" in result["sample_dates"]
        assert result["sample_parsed"] is not None
        assert result["sample_parsed"]["trade_date"] == "2026-06-17"
        # 민감정보 미포함 확인
        assert "FAKE_TOKEN_ABCDEF" not in str(result["token"])

    @pytest.mark.asyncio
    async def test_token_failure_returns_error(self, monkeypatch):
        """토큰 발급 실패 시 token 필드에 FAILED가 들어가고 errors 목록에 추가된다."""
        m = _import_smoke()

        mock_client = AsyncMock()
        mock_client._get_access_token = AsyncMock(side_effect=Exception("auth failed"))

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        config = {
            "real_base_url": "https://fake.kis.kr",
            "_app_key": "FAKE",
            "_app_secret": "FAKE",
        }

        with patch("app.trading.broker.kis_investor_flow_client.KISInvestorFlowClient", return_value=mock_client), \
             patch("httpx.AsyncClient", return_value=mock_http):
            result = await m._run_investor_flow_check(
                config=config,
                symbol_code="005930",
                target_date=date(2026, 6, 17),
                store=False,
            )

        assert "FAILED" in result["token"]
        assert result["investor_flow_query"] == "not_tested"
        assert len(result["errors"]) >= 1

    @pytest.mark.asyncio
    async def test_empty_rows_marks_empty(self, monkeypatch):
        """output2가 빈 배열일 때 empty 메시지가 investor_flow_query에 포함된다."""
        m = _import_smoke()

        mock_client = AsyncMock()
        mock_client._get_access_token = AsyncMock(return_value="TOKEN")
        mock_client.get_daily_investor_flow_by_stock = AsyncMock(return_value=[])

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        config = {
            "real_base_url": "https://fake.kis.kr",
            "_app_key": "FAKE",
            "_app_secret": "FAKE",
        }

        with patch("app.trading.broker.kis_investor_flow_client.KISInvestorFlowClient", return_value=mock_client), \
             patch("httpx.AsyncClient", return_value=mock_http):
            result = await m._run_investor_flow_check(
                config=config,
                symbol_code="005930",
                target_date=date(2026, 6, 17),
                store=False,
            )

        assert "ok" in result["investor_flow_query"]
        assert "empty" in result["investor_flow_query"] or "비영업일" in result["investor_flow_query"]
        assert result["row_count"] == 0

    @pytest.mark.asyncio
    async def test_order_api_never_called(self, monkeypatch):
        """어떤 경로에서도 place_order가 호출되지 않음을 확인한다."""
        m = _import_smoke()
        fake_rows = _make_fake_rows()

        mock_client = AsyncMock()
        mock_client._get_access_token = AsyncMock(return_value="TOKEN")
        mock_client.get_daily_investor_flow_by_stock = AsyncMock(return_value=fake_rows)
        # place_order 메서드가 없음을 시뮬레이션 (spec 없는 AsyncMock은 동적 속성 허용)
        # 명시적으로 spec=[] 설정으로 place_order 접근 시 AttributeError 발생
        mock_client_strict = MagicMock(spec=[
            "_get_access_token",
            "get_daily_investor_flow_by_stock",
        ])
        mock_client_strict._get_access_token = AsyncMock(return_value="TOKEN")
        mock_client_strict.get_daily_investor_flow_by_stock = AsyncMock(return_value=fake_rows)

        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        config = {
            "real_base_url": "https://fake.kis.kr",
            "_app_key": "FAKE",
            "_app_secret": "FAKE",
        }

        with patch("app.trading.broker.kis_investor_flow_client.KISInvestorFlowClient", return_value=mock_client_strict), \
             patch("httpx.AsyncClient", return_value=mock_http):
            result = await m._run_investor_flow_check(
                config=config,
                symbol_code="005930",
                target_date=date(2026, 6, 17),
                store=False,
            )

        # place_order가 없는 client로도 정상 동작
        assert result["order_api_called"] is False
        assert result["investor_flow_query"] == "ok"
        # spec 위반 시 AttributeError가 났다면 errors에 들어갔을 것
        assert not any("place_order" in e for e in result["errors"])


# ─── _print_report 출력 검증 ─────────────────────────────────────────────────

class TestPrintReport:
    def _config(self):
        return {
            "real_app_key_set": True,
            "paper_app_key_fallback": False,
            "app_key_masked": "FAKE***",
            "app_secret_set": True,
            "real_base_url": "https://fake.kis.kr",
            "real_trading_enabled": False,
            "config_ready": True,
            "_app_key": "FAKE_KEY_FULL",
            "_app_secret": "FAKE_SECRET_FULL",
        }

    def test_confirmed_verified_verdict(self, capsys):
        m = _import_smoke()
        api_result = {
            "order_api_called": False,
            "forbidden_tr_ids_called": [],
            "real_trading_enabled": False,
            "token": "ok (masked: FAKE****)",
            "investor_flow_query": "ok",
            "rt_cd": None,
            "msg_cd": None,
            "msg1": None,
            "row_count": 2,
            "sample_dates": ["2026-06-17"],
            "sample_parsed": {
                "trade_date": "2026-06-17",
                "foreign_net_buy_quantity": 123456,
                "foreign_net_buy_amount_M_KRW": "7890",
                "institution_net_buy_quantity": -50000,
                "institution_net_buy_amount_M_KRW": "-3200",
                "individual_net_buy_quantity": -73456,
                "individual_net_buy_amount_M_KRW": "-4690",
            },
            "store_result": None,
            "store_row_count": 0,
            "upsert_idempotent": None,
            "errors": [],
        }
        verdict = m._print_report(
            config=self._config(),
            symbol_code="005930",
            target_date=date(2026, 6, 17),
            api_result=api_result,
            confirm_readonly=True,
            store=False,
        )
        assert verdict == "INVESTOR_FLOW_VERIFIED"
        out = capsys.readouterr().out
        assert "FAKE_KEY_FULL" not in out  # 전체 값 미출력
        assert "FAKE_SECRET_FULL" not in out
        assert "order_api_called" in out
        assert "FHPTJ04160001" in out

    def test_errors_give_partial_verdict(self, capsys):
        m = _import_smoke()
        api_result = {
            "order_api_called": False,
            "forbidden_tr_ids_called": [],
            "real_trading_enabled": False,
            "token": "ok",
            "investor_flow_query": "ok",
            "rt_cd": None, "msg_cd": None, "msg1": None,
            "row_count": 1, "sample_dates": [], "sample_parsed": None,
            "store_result": None, "store_row_count": 0, "upsert_idempotent": None,
            "errors": ["some error occurred"],
        }
        verdict = m._print_report(
            config=self._config(),
            symbol_code="005930",
            target_date=date(2026, 6, 17),
            api_result=api_result,
            confirm_readonly=True,
            store=False,
        )
        assert verdict == "INVESTOR_FLOW_PARTIAL"

    def test_store_info_shown_when_store_flag(self, capsys):
        m = _import_smoke()
        api_result = {
            "order_api_called": False,
            "forbidden_tr_ids_called": [],
            "real_trading_enabled": False,
            "token": "ok",
            "investor_flow_query": "ok",
            "rt_cd": None, "msg_cd": None, "msg1": None,
            "row_count": 2, "sample_dates": ["2026-06-17"], "sample_parsed": None,
            "store_result": "ok",
            "store_row_count": 2,
            "upsert_idempotent": True,
            "errors": [],
        }
        m._print_report(
            config=self._config(),
            symbol_code="005930",
            target_date=date(2026, 6, 17),
            api_result=api_result,
            confirm_readonly=True,
            store=True,
        )
        out = capsys.readouterr().out
        assert "store_result" in out
        assert "upsert_idempotent" in out
        assert "True" in out or "true" in out.lower()

    def test_sensitive_info_not_in_output(self, capsys):
        m = _import_smoke()
        api_result = {
            "order_api_called": False,
            "forbidden_tr_ids_called": [],
            "real_trading_enabled": False,
            "token": "ok (masked: XXXX****)",
            "investor_flow_query": "ok",
            "rt_cd": None, "msg_cd": None, "msg1": None,
            "row_count": 0, "sample_dates": [], "sample_parsed": None,
            "store_result": None, "store_row_count": 0, "upsert_idempotent": None,
            "errors": [],
        }
        m._print_report(
            config=self._config(),
            symbol_code="005930",
            target_date=date(2026, 6, 17),
            api_result=api_result,
            confirm_readonly=True,
            store=False,
        )
        out = capsys.readouterr().out
        assert "FAKE_KEY_FULL" not in out
        assert "FAKE_SECRET_FULL" not in out


# ─── main() 진입점 ────────────────────────────────────────────────────────────

class TestMain:
    def test_missing_credentials_exits_nonzero_when_confirm_readonly(self, monkeypatch):
        m = _import_smoke()
        monkeypatch.delenv("KIS_REAL_APP_KEY", raising=False)
        monkeypatch.delenv("KIS_REAL_APP_SECRET", raising=False)
        monkeypatch.delenv("KIS_APP_KEY", raising=False)
        monkeypatch.delenv("KIS_APP_SECRET", raising=False)
        monkeypatch.setattr("sys.argv", ["smoke", "--confirm-readonly"])

        with pytest.raises(SystemExit) as exc_info:
            m.main()
        assert exc_info.value.code != 0

    def test_default_target_date_is_yesterday(self, monkeypatch):
        """target_date 미지정 시 어제 날짜가 사용된다."""
        m = _import_smoke()
        yesterday = date.today() - timedelta(days=1)
        captured = {}

        def fake_print_report(**kwargs):
            captured.update(kwargs)
            return "DRY_RUN_OK"

        monkeypatch.setattr("sys.argv", ["smoke"])
        monkeypatch.setattr(m, "_print_report", fake_print_report)

        with pytest.raises(SystemExit):
            m.main()

        assert captured.get("target_date") == yesterday

    def test_custom_symbol_passed_to_report(self, monkeypatch):
        m = _import_smoke()
        captured = {}

        def fake_print_report(**kwargs):
            captured.update(kwargs)
            return "DRY_RUN_OK"

        monkeypatch.setattr("sys.argv", ["smoke", "--symbol-code", "000660"])
        monkeypatch.setattr(m, "_print_report", fake_print_report)

        with pytest.raises(SystemExit):
            m.main()

        assert captured.get("symbol_code") == "000660"

    def test_confirm_readonly_calls_api_mock(self, monkeypatch):
        """--confirm-readonly 시 _run_investor_flow_check가 호출된다."""
        m = _import_smoke()
        monkeypatch.setenv("KIS_REAL_APP_KEY", "FAKE_KEY")
        monkeypatch.setenv("KIS_REAL_APP_SECRET", "FAKE_SECRET")
        monkeypatch.delenv("KIS_REAL_TRADING_ENABLED", raising=False)

        fake_result = {
            "order_api_called": False,
            "forbidden_tr_ids_called": [],
            "real_trading_enabled": False,
            "token": "ok",
            "investor_flow_query": "ok",
            "rt_cd": None, "msg_cd": None, "msg1": None,
            "row_count": 1,
            "sample_dates": ["2026-06-17"],
            "sample_parsed": None,
            "store_result": None, "store_row_count": 0, "upsert_idempotent": None,
            "errors": [],
        }

        with patch("scripts.kis_investor_flow_smoke_test.asyncio.run", return_value=fake_result) as mock_run:
            monkeypatch.setattr("sys.argv", ["smoke", "--confirm-readonly"])
            with pytest.raises(SystemExit) as exc_info:
                m.main()
            mock_run.assert_called_once()
        assert exc_info.value.code == 0
