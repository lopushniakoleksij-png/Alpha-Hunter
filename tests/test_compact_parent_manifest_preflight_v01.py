"""Fail-closed compact canonical parent manifest preflight (synthetic, no network)."""
from unittest.mock import patch

import pytest

import app


@pytest.mark.parametrize(
    "symbols,count",
    [
        ([{"symbol": "BTCUSDT"}, {"symbol": "BTCUSDT"}], 2),
        ([{"symbol": ""}], 1),
        ([{"symbol": "   "}], 1),
        ([{"symbol": None}], 1),
        ([{"symbol": 123}], 1),
        (["BTCUSDT"], 1),
        ([{"symbol": "BTCUSDT"}], 2),
        ([{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}], 1),
    ],
)
def test_compact_parent_invalid_identity_never_reads_children(symbols, count):
    row = {"run_id": "synthetic-run", "symbol_count": count}
    payload = {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": "synthetic-run",
        "symbols": symbols,
    }
    with patch.object(app, "supabase_get_rows", side_effect=AssertionError("child I/O forbidden")) as child_read:
        with pytest.raises(RuntimeError, match="manifest"):
            app._hydrate_dashboard_snapshot(row, payload)
    child_read.assert_not_called()


def test_compact_parent_valid_identity_hydrates_children():
    row = {"run_id": "synthetic-run", "symbol_count": 2}
    payload = {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": "synthetic-run",
        "symbols": [{"symbol": "ETHUSDT"}, {"symbol": "BTCUSDT"}],
    }
    children = [
        {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}},
        {"symbol": "ETHUSDT", "payload": {"symbol": "ETHUSDT"}},
    ]
    with patch.object(app, "supabase_get_rows", return_value=children) as child_read:
        result = app._hydrate_dashboard_snapshot(row, payload)
    child_read.assert_called_once()
    assert [item["symbol"] for item in result["symbols"]] == ["BTCUSDT", "ETHUSDT"]
