"""maintenance/checks.py 순수 함수 단위 테스트 (DB 없음)."""
import pytest

from app.maintenance.checks import (
    AccountInput,
    Finding,
    NullRiskEventInput,
    PositionMismatchInput,
    Severity,
    StrategyVersionInput,
    detect_null_risk_events,
    detect_orphan_strategy_versions,
    detect_placeholder_accounts,
    detect_position_event_mismatches,
)


# ---------------------------------------------------------------------------
# detect_null_risk_events
# ---------------------------------------------------------------------------


def test_detect_null_risk_events_approved_null_is_auto_fixable() -> None:
    events = [NullRiskEventInput(id=1, result="approved", rule_name=None, reason=None)]
    findings = detect_null_risk_events(events)
    assert len(findings) == 1
    assert findings[0].auto_fixable is True
    assert findings[0].entity_id == "1"
    assert findings[0].check_name == "null_risk_event_fields"


def test_detect_null_risk_events_rejected_null_not_auto_fixable() -> None:
    events = [NullRiskEventInput(id=2, result="rejected", rule_name=None, reason="blocked")]
    findings = detect_null_risk_events(events)
    assert len(findings) == 1
    assert findings[0].auto_fixable is False


def test_detect_null_risk_events_partial_null_detected() -> None:
    # rule_name만 None이어도 탐지해야 한다
    events = [NullRiskEventInput(id=3, result="approved", rule_name=None, reason="ok")]
    findings = detect_null_risk_events(events)
    assert len(findings) == 1


def test_detect_null_risk_events_no_null_returns_empty() -> None:
    events = [
        NullRiskEventInput(id=4, result="approved", rule_name="all_rules_passed", reason="ok")
    ]
    findings = detect_null_risk_events(events)
    assert findings == []


def test_detect_null_risk_events_empty_input_returns_empty() -> None:
    assert detect_null_risk_events([]) == []


def test_detect_null_risk_events_mixed_list() -> None:
    events = [
        NullRiskEventInput(id=10, result="approved", rule_name=None, reason=None),
        NullRiskEventInput(id=11, result="approved", rule_name="r", reason="ok"),
        NullRiskEventInput(id=12, result="rejected", rule_name=None, reason=None),
    ]
    findings = detect_null_risk_events(events)
    assert len(findings) == 2
    ids = {f.entity_id for f in findings}
    assert ids == {"10", "12"}


# ---------------------------------------------------------------------------
# detect_position_event_mismatches
# ---------------------------------------------------------------------------


def test_detect_position_event_mismatches_basic() -> None:
    m = PositionMismatchInput(
        position_id=1, symbol_code="005930", account_id=1,
        position_quantity=2, event_quantity_sum=0,
    )
    findings = detect_position_event_mismatches([m])
    assert len(findings) == 1
    f = findings[0]
    assert f.entity_id == "1"
    assert f.severity == Severity.ERROR
    assert f.auto_fixable is True
    assert f.details["discrepancy"] == 2


def test_detect_position_event_mismatches_empty_returns_empty() -> None:
    assert detect_position_event_mismatches([]) == []


def test_detect_position_event_mismatches_description_contains_symbol() -> None:
    m = PositionMismatchInput(
        position_id=5, symbol_code="035420", account_id=2,
        position_quantity=10, event_quantity_sum=8,
    )
    findings = detect_position_event_mismatches([m])
    assert "035420" in findings[0].description
    assert "+2" in findings[0].description


# ---------------------------------------------------------------------------
# detect_orphan_strategy_versions
# ---------------------------------------------------------------------------


def _make_sv(
    id_: int,
    strategy_name: str,
    symbol_code: str | None,
    status: str = "active",
) -> StrategyVersionInput:
    params = {"symbol_code": symbol_code} if symbol_code else {}
    return StrategyVersionInput(
        id=id_,
        strategy_id=1,
        strategy_name=strategy_name,
        symbol_code=symbol_code,
        status=status,
        parameters=params,
    )


def test_detect_orphan_symbol_not_in_watchlist() -> None:
    versions = [_make_sv(1, "NAVER_MA", "035420")]
    findings = detect_orphan_strategy_versions(versions, watchlist_symbol_codes={"005930"})
    assert len(findings) == 1
    assert findings[0].entity_id == "1"
    assert findings[0].auto_fixable is True


def test_detect_orphan_symbol_in_watchlist_no_finding() -> None:
    versions = [_make_sv(1, "SAMSUNG_MA", "005930")]
    findings = detect_orphan_strategy_versions(versions, watchlist_symbol_codes={"005930"})
    assert findings == []


def test_detect_orphan_no_symbol_code_skipped() -> None:
    versions = [_make_sv(1, "UNKNOWN_MA", symbol_code=None)]
    findings = detect_orphan_strategy_versions(versions, watchlist_symbol_codes=set())
    assert findings == []


def test_detect_orphan_empty_watchlist_returns_findings_for_all_symbols() -> None:
    versions = [
        _make_sv(1, "A_MA", "005930"),
        _make_sv(2, "B_MA", "035420"),
    ]
    findings = detect_orphan_strategy_versions(versions, watchlist_symbol_codes=set())
    assert len(findings) == 2


# ---------------------------------------------------------------------------
# detect_placeholder_accounts
# ---------------------------------------------------------------------------


def _make_account(id_: int, broker_account_no: str) -> AccountInput:
    return AccountInput(
        id=id_,
        alias=None,
        broker_account_no=broker_account_no,
        account_type="paper",
    )


def test_detect_placeholder_known_string() -> None:
    accounts = [_make_account(1, "너의모의계좌번호")]
    findings = detect_placeholder_accounts(accounts)
    assert len(findings) == 1
    assert findings[0].auto_fixable is False


def test_detect_placeholder_real_account_no_finding() -> None:
    accounts = [_make_account(2, "12345678-01")]
    findings = detect_placeholder_accounts(accounts)
    assert findings == []


def test_detect_placeholder_invalid_format() -> None:
    accounts = [_make_account(3, "INVALID_NO")]
    findings = detect_placeholder_accounts(accounts)
    assert len(findings) == 1


def test_detect_placeholder_empty_returns_empty() -> None:
    assert detect_placeholder_accounts([]) == []


def test_detect_placeholder_other_known_strings() -> None:
    for placeholder in ("your_account_no", "PLACEHOLDER"):
        accounts = [_make_account(1, placeholder)]
        findings = detect_placeholder_accounts(accounts)
        assert len(findings) == 1, f"expected finding for {placeholder!r}"
