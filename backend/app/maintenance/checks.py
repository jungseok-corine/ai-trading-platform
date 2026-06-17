"""순수 함수 기반 데이터 정합성 검사.

DB 접근 없음 — 입력 데이터만으로 Finding 목록을 반환한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Finding:
    check_name: str
    severity: Severity
    entity_type: str
    entity_id: str
    description: str
    details: dict
    auto_fixable: bool


@dataclass
class NullRiskEventInput:
    id: int
    result: str  # "approved" | "rejected"
    rule_name: str | None
    reason: str | None


@dataclass
class PositionMismatchInput:
    position_id: int
    symbol_code: str
    account_id: int
    position_quantity: int
    event_quantity_sum: int


@dataclass
class StrategyVersionInput:
    id: int
    strategy_id: int
    strategy_name: str
    symbol_code: str | None  # sv.parameters.get("symbol_code")
    status: str
    parameters: dict


@dataclass
class AccountInput:
    id: int
    alias: str | None
    broker_account_no: str
    account_type: str


_KNOWN_PLACEHOLDERS = {"너의모의계좌번호", "your_account_no", "PLACEHOLDER"}
_REAL_ACCOUNT_PATTERN = re.compile(r"^\d{8}-\d{2}$")


def detect_null_risk_events(events: list[NullRiskEventInput]) -> list[Finding]:
    findings: list[Finding] = []
    for e in events:
        if e.rule_name is None or e.reason is None:
            findings.append(
                Finding(
                    check_name="null_risk_event_fields",
                    severity=Severity.WARNING,
                    entity_type="risk_event",
                    entity_id=str(e.id),
                    description=(
                        f"risk_event #{e.id} has NULL rule_name or reason (result={e.result})"
                    ),
                    details={
                        "result": e.result,
                        "rule_name": e.rule_name,
                        "reason": e.reason,
                    },
                    auto_fixable=(e.result == "approved"),
                )
            )
    return findings


def detect_position_event_mismatches(
    mismatches: list[PositionMismatchInput],
) -> list[Finding]:
    findings: list[Finding] = []
    for m in mismatches:
        discrepancy = m.position_quantity - m.event_quantity_sum
        findings.append(
            Finding(
                check_name="position_event_mismatch",
                severity=Severity.ERROR,
                entity_type="position",
                entity_id=str(m.position_id),
                description=(
                    f"position #{m.position_id} ({m.symbol_code}) qty={m.position_quantity} "
                    f"but event_sum={m.event_quantity_sum} (discrepancy={discrepancy:+d})"
                ),
                details={
                    "symbol_code": m.symbol_code,
                    "account_id": m.account_id,
                    "position_quantity": m.position_quantity,
                    "event_quantity_sum": m.event_quantity_sum,
                    "discrepancy": discrepancy,
                },
                auto_fixable=True,
            )
        )
    return findings


def detect_orphan_strategy_versions(
    versions: list[StrategyVersionInput],
    watchlist_symbol_codes: set[str],
) -> list[Finding]:
    findings: list[Finding] = []
    for v in versions:
        if not v.symbol_code:
            continue
        if v.symbol_code not in watchlist_symbol_codes:
            findings.append(
                Finding(
                    check_name="orphan_strategy_version",
                    severity=Severity.WARNING,
                    entity_type="strategy_version",
                    entity_id=str(v.id),
                    description=(
                        f"strategy_version #{v.id} ({v.strategy_name}, symbol={v.symbol_code}) "
                        f"is {v.status} but not in any watchlist"
                    ),
                    details={
                        "strategy_id": v.strategy_id,
                        "strategy_name": v.strategy_name,
                        "symbol_code": v.symbol_code,
                        "status": v.status,
                    },
                    auto_fixable=True,
                )
            )
    return findings


def detect_placeholder_accounts(accounts: list[AccountInput]) -> list[Finding]:
    findings: list[Finding] = []
    for a in accounts:
        no = a.broker_account_no
        is_placeholder = no in _KNOWN_PLACEHOLDERS or not _REAL_ACCOUNT_PATTERN.match(no)
        if is_placeholder:
            findings.append(
                Finding(
                    check_name="placeholder_account",
                    severity=Severity.WARNING,
                    entity_type="account",
                    entity_id=str(a.id),
                    description=(
                        f"account #{a.id} (alias={a.alias!r}) "
                        f"has placeholder broker_account_no={no!r}"
                    ),
                    details={
                        "alias": a.alias,
                        "broker_account_no": no,
                        "account_type": a.account_type,
                    },
                    auto_fixable=False,
                )
            )
    return findings
