"""Synthetic compact-parent run identity regression; no production reads."""
from unittest.mock import patch

import pytest

import app


@pytest.mark.parametrize(
    "row_id,payload_id",
    [
        ("parent-run", "other-run"),
        ("parent-run", ""),
        ("parent-run", None),
        ("", "parent-run"),
        (None, "parent-run"),
        (123, "123"),
        ("parent-run", 123),
    ],
)
def test_compact_parent_run_identity_mismatch_fails_before_child_io(row_id, payload_id):
    row = {"run_id": row_id, "symbol_count": 1}
    payload = {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": payload_id,
        "symbols": [{"symbol": "BTCUSDT"}],
    }
    with patch.object(app, "supabase_get_rows", side_effect=AssertionError("unexpected child I/O")) as read:
        with pytest.raises(RuntimeError, match="run_id identity mismatch"):
            app._hydrate_dashboard_snapshot(row, payload)
    read.assert_not_called()


def test_compact_parent_matching_run_identity_reads_only_own_children():
    row = {"run_id": "parent-run", "symbol_count": 1}
    payload = {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": "parent-run",
        "symbols": [{"symbol": "BTCUSDT"}],
    }
    children = [{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}}]
    with patch.object(app, "supabase_get_rows", return_value=children) as read:
        result = app._hydrate_dashboard_snapshot(row, payload)
    assert result["symbols"] == [{"symbol": "BTCUSDT"}]
    assert read.call_args.args[1]["run_id"] == "eq.parent-run"
