from pathlib import Path
from unittest.mock import patch

from alpha_hunter.fill_ledger import (
    FillTraceabilityResult,
    LINK_TABLE,
    TRACEABILITY_TABLE,
    FILL_TABLE,
    _fill_link_rows,
    persist_fill_traceability,
)


def _result():
    return FillTraceabilityResult(
        run_row={
            "traceability_run_id": "trace-1",
            "source_run_id": "source-1",
            "observed_at_utc": "2026-09-20T01:29:53+00:00",
            "status": "CONNECTED",
            "fill_count": 1,
            "complete": True,
            "schema_validated": True,
            "shadow_only": True,
            "trade_permission": False,
        },
        fill_rows=[
            {
                "fill_evidence_id": "fill-1",
                "trade_id": "trade-1",
                "fill_time_utc": "2026-09-19T12:00:00+00:00",
            }
        ],
    )


def test_fill_link_rows_preserve_run_membership_without_mutating_fill_identity():
    rows = _fill_link_rows(_result())

    assert rows == [
        {
            "traceability_run_id": "trace-1",
            "source_run_id": "source-1",
            "fill_evidence_id": "fill-1",
            "trade_id": "trade-1",
            "observed_at_utc": "2026-09-20T01:29:53+00:00",
            "fill_time_utc": "2026-09-19T12:00:00+00:00",
            "model_version": "canonical-readonly-fill-ledger-v0.3-historical-diagnostic",
            "shadow_only": True,
            "trade_permission": False,
        }
    ]


def test_persistence_orders_run_then_fill_then_membership():
    calls = []

    def fake_insert(settings, table, rows, on_conflict):
        calls.append((table, rows, on_conflict))
        return len(rows)

    with patch("alpha_hunter.fill_ledger._insert_ignore", side_effect=fake_insert):
        result = persist_fill_traceability(object(), _result())

    assert result == (1, 1, 1)
    assert [row[0] for row in calls] == [
        TRACEABILITY_TABLE,
        FILL_TABLE,
        LINK_TABLE,
    ]
    assert calls[2][2] == "traceability_run_id,fill_evidence_id"


def test_membership_schema_is_append_only_and_fail_closed():
    sql = Path("fill_traceability_membership_v01.sql").read_text().lower()

    assert "alpha_hunter_fill_traceability_links" in sql
    assert "primary key (traceability_run_id, fill_evidence_id)" in sql
    assert "unique (traceability_run_id, trade_id)" in sql
    assert "enable row level security" in sql
    assert "alpha_hunter_block_append_only_mutation" in sql
    assert "check (shadow_only = true)" in sql
    assert "check (trade_permission = false)" in sql
    assert "alpha_hunter_fill_traceability_linkage_status" in sql
    assert "linkage_count_match" in sql
    assert "linkage_status" in sql

    for forbidden in (
        "trade_permission = true",
        "production_execution_enabled",
        "place_order",
        "cancel_order",
        "modify_order",
        "set-leverage",
    ):
        assert forbidden not in sql


def test_runtime_reports_membership_attempt_count():
    source = Path("run.py").read_text()
    assert "fill_links_attempted" in source
    assert 'f"links={fill_links_attempted} "' in source
