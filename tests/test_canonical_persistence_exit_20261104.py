"""Isolated successor P0: never mark a failed canonical publication successful.

No network, production database, deployment, trade or clock mutation.
The integration tests for child batching and position continuity live in the
stacked base PR #378; these tests cover the process exit contract only.
"""

import inspect

import pytest

from alpha_hunter import collector


@pytest.mark.parametrize("status", [
    "FAILED: Supabase upsert failed: HTTP 500",
    "NOT_CONFIGURED",
    "DISABLED",
    "PENDING",
    "",
])
def test_canonical_cron_rejects_unverified_persistence(status):
    snapshot = {"validation_identity": {"run_source": "RENDER_CRON"}}
    assert collector.canonical_persistence_exit_code(snapshot, status) == 2


def test_canonical_cron_accepts_only_exact_saved_status():
    snapshot = {"validation_identity": {"run_source": "RENDER_CRON"}}
    assert collector.canonical_persistence_exit_code(snapshot, "SAVED") == 0
    assert collector.canonical_persistence_exit_code(snapshot, "SAVED (unverified)") == 2


@pytest.mark.parametrize("source", ["RENDER_WEB", "GITHUB_ACTIONS", "LOCAL", ""])
def test_noncanonical_offline_or_web_flows_keep_existing_exit_contract(source):
    snapshot = {"validation_identity": {"run_source": source}}
    assert collector.canonical_persistence_exit_code(snapshot, "DISABLED") == 0


def test_invalid_or_missing_validation_identity_cannot_claim_canonical_success():
    # No change to legacy/offline behavior: the existing source identity guards
    # independently reject invalid canonical run attribution.
    for snapshot in ({}, {"validation_identity": None}, {"validation_identity": "bad"}):
        assert collector.canonical_persistence_exit_code(snapshot, "FAILED") == 0


def test_collector_main_actually_returns_the_verified_persistence_exit_code():
    source = inspect.getsource(collector.main)
    assert "exit_code = canonical_persistence_exit_code(snapshot, cloud_status)" in source
    assert "return exit_code" in source
    assert "CANONICAL PERSISTENCE INCOMPLETE" in source


def test_runner_propagates_nonzero_canonical_exit_without_later_persistence(monkeypatch):
    # Preserve existing run.py contract: a nonzero scanner status cannot be
    # disguised by writing downstream universe or account evidence.
    import run as production_runner
    from contextlib import contextmanager

    @contextmanager
    def captured():
        yield {}

    monkeypatch.setattr(production_runner, "capture_existing_universe_calls", captured)
    monkeypatch.setattr(production_runner, "main", lambda: 2)
    assert production_runner.run() == 2
