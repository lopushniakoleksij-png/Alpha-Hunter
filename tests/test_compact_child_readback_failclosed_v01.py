"""Synthetic child readback completeness regressions; no network or production data."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import app


def _parent(created_at):
    return {
        "run_id": "synthetic-readback-run",
        "symbol_count": 2,
        "created_at": created_at,
    }


def _payload():
    return {
        "_storage_contract": "snapshot-parent-v0.2",
        "run_id": "synthetic-readback-run",
        "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
    }


@pytest.mark.parametrize(
    "children",
    [
        [{"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}}],
        [],
    ],
)
def test_recent_incomplete_children_are_publishing_not_complete(children):
    now = datetime.now(timezone.utc).isoformat()
    with patch.object(app, "supabase_get_rows", return_value=children) as read:
        with pytest.raises(app.CanonicalSnapshotPublishing):
            app._hydrate_dashboard_snapshot(_parent(now), _payload())
    read.assert_called_once()


def test_old_incomplete_children_fail_closed_not_publishing():
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with patch.object(app, "supabase_get_rows", return_value=[
        {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}},
    ]) as read:
        with pytest.raises(RuntimeError, match="Incomplete compact"):
            app._hydrate_dashboard_snapshot(_parent(old), _payload())
    read.assert_called_once()


@pytest.mark.parametrize(
    "children",
    [
        [
            {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}},
            {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}},
        ],
        [
            {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}},
            {"symbol": "SOLUSDT", "payload": {"symbol": "SOLUSDT"}},
        ],
        [
            {"symbol": "BTCUSDT", "payload": {"symbol": "ETHUSDT"}},
            {"symbol": "ETHUSDT", "payload": {"symbol": "ETHUSDT"}},
        ],
        [
            {"symbol": "BTCUSDT", "payload": {"symbol": "BTCUSDT"}},
            {"symbol": "ETHUSDT", "payload": None},
        ],
    ],
)
def test_count_complete_but_corrupt_child_evidence_never_hydrates(children):
    with patch.object(app, "supabase_get_rows", return_value=children) as read:
        with pytest.raises(RuntimeError, match="child|symbol"):
            app._hydrate_dashboard_snapshot(_parent("2026-11-01T00:00:00+00:00"), _payload())
    read.assert_called_once()
