"""M2.15G-2 — LeaderTrendCandidateEvent model + migration (schema only) 검증.

model/table metadata · forbidden FK 부재 · unique/check constraint · migration 파일 구조 ·
service/API/repository 미존재 · record 생성 없음.
"""
from pathlib import Path

from app.domain.models.leader_trend_candidate_event import LeaderTrendCandidateEvent

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "r1s2t3u4v5w6_add_leader_trend_candidate_events.py"

REQUIRED_COLUMNS = {
    "id", "symbol", "detected_at", "reference_date", "timeframe", "universe_scope",
    "scanner_name", "scanner_version", "candidate_bucket", "is_operational_candidate",
    "strategy_extreme", "current_price", "low_52w", "high_52w", "low_52w_gain_pct",
    "drawdown_from_52w_high_pct", "window_basis", "data_source", "validation_source",
    "validation_status", "validation_report_path", "research_only", "not_buy_signal",
    "created_at", "notes", "source_basis_note", "provenance_warning", "safety_warning",
}


def test_table_name_and_columns():
    tbl = LeaderTrendCandidateEvent.__table__
    assert tbl.name == "leader_trend_candidate_events"  # 기존 candidate_events와 별도
    cols = set(tbl.columns.keys())
    assert REQUIRED_COLUMNS <= cols


def test_no_forbidden_foreign_keys():
    tbl = LeaderTrendCandidateEvent.__table__
    # research observation record → 어떤 FK도 없어야 함
    assert len(tbl.foreign_keys) == 0
    src = MIGRATION.read_text(encoding="utf-8")
    assert "ForeignKeyConstraint" not in src
    for forbidden in ("orders", "trades", "signal_logs", "strategy_versions",
                      "accounts", "portfolio", "broker"):
        # FK 참조 형태(["...id"], ["table.id"])가 없어야 함
        assert f'["{forbidden}.' not in src and f"'{forbidden}." not in src


def test_unique_constraint_present():
    tbl = LeaderTrendCandidateEvent.__table__
    uqs = [c for c in tbl.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any(c.name == "uq_ltce_symbol_scanner_reference_window_scope" for c in uqs)
    uq = next(c for c in uqs if c.name == "uq_ltce_symbol_scanner_reference_window_scope")
    assert {col.name for col in uq.columns} == {
        "symbol", "scanner_name", "scanner_version", "reference_date",
        "timeframe", "window_basis", "universe_scope",
    }


def test_check_constraints_present():
    tbl = LeaderTrendCandidateEvent.__table__
    names = {c.name for c in tbl.constraints if c.__class__.__name__ == "CheckConstraint"}
    assert {"ck_ltce_candidate_bucket", "ck_ltce_window_basis", "ck_ltce_validation_status",
            "ck_ltce_research_only_true", "ck_ltce_not_buy_signal_true"} <= names


def test_research_only_and_not_buy_signal_defaults_true():
    tbl = LeaderTrendCandidateEvent.__table__
    for col in ("research_only", "not_buy_signal"):
        c = tbl.columns[col]
        assert c.nullable is False
        assert c.server_default is not None


def test_migration_file_creates_and_drops_table():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "r1s2t3u4v5w6"' in src
    assert 'down_revision: str | None = "q1r2s3t4u5v6"' in src
    assert 'op.create_table(\n        "leader_trend_candidate_events"' in src
    assert 'op.drop_table("leader_trend_candidate_events")' in src


def test_migration_has_no_data_mutation():
    src = MIGRATION.read_text(encoding="utf-8")
    for token in ("op.execute(", "op.bulk_insert(", "INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert token not in src, f"unexpected data mutation: {token}"


def test_migration_does_not_alter_existing_tables():
    src = MIGRATION.read_text(encoding="utf-8")
    for token in ("op.add_column(", "op.alter_column(", "op.drop_column(",
                  "candidate_events"):  # 기존 candidate_events 테이블 미수정/미참조
        # 단, 주석/문서 내 'candidate_events' 언급은 leader_trend_candidate_events의 substring 아님 확인
        if token == "candidate_events":
            # leader_trend_candidate_events는 candidate_events를 substring으로 포함 → 정확 매칭만 차단
            assert ' "candidate_events"' not in src and "'candidate_events'" not in src
        else:
            assert token not in src


def test_no_leader_trend_candidate_event_service_or_repository():
    # G-2는 model/migration only — service/repository/API 미존재
    assert not (BACKEND / "app" / "services" / "leader_trend_candidate_event_service.py").exists()
    assert not (BACKEND / "app" / "domain" / "repositories" / "leader_trend_candidate_event.py").exists()
    # API route에 candidate-events 생성 경로 미존재
    api_dir = BACKEND / "app" / "api" / "v1"
    for p in api_dir.glob("*.py"):
        assert "leader_trend_candidate_events" not in p.read_text(encoding="utf-8")
