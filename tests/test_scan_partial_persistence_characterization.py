"""Characterise the existing sequential scan-write gap without network or DB access.

These passing tests DOCUMENT THE DEFECT; they do NOT certify a repair.
They must be replaced by atomic rollback and completeness assertions when the
isolated replacement transaction is implemented.
"""
import requests
import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


class _OK:
    status_code = 201
    text = ""


class _CommitUntilFailure:
    def __init__(self, fail_table):
        self.fail_table = fail_table
        self.committed = []
        self.attempts = []

    def post(self, url, **kwargs):
        table = url.rsplit("/", 1)[-1]
        self.attempts.append(table)
        if table == self.fail_table:
            raise requests.ReadTimeout("simulated Supabase symbol-write timeout")
        self.committed.append(table)
        return _OK()


def _snapshot():
    return {
        "version": "isolated-characterization",
        "collected_at_utc": "2026-11-07T00:00:00Z",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT",
            "state": "WATCH",
            "trade_permission": False,
            "last_price": 65000,
            "execution_setup": {"direction": None, "rr": None},
        }],
    }


@pytest.mark.parametrize("fail_table,expected_written", [
    ("alpha_hunter_symbol_snapshots", ["alpha_hunter_snapshots"]),
    ("alpha_hunter_readiness_observations_v01", [
        "alpha_hunter_snapshots",
        "alpha_hunter_symbol_snapshots",
        "alpha_hunter_signals",
        "alpha_hunter_signal_features",
    ]),
])
def test_legacy_sequential_writes_can_leave_incomplete_scan(
    fail_table, expected_written
):
    session = _CommitUntilFailure(fail_table)
    storage = SupabaseStorage(
        SupabaseConfig(
            url="https://example.supabase.co",
            key="FAKE_TEST_KEY",
            max_retries=2,
            retry_backoff_seconds=0,
        ),
        session=session,
    )
    with pytest.raises(SupabaseStorageError, match="failed after 3 attempts"):
        storage.save_snapshot(_snapshot())

    assert session.committed == expected_written
    assert session.attempts.count(fail_table) == 3
    # This is the known failure condition: successful earlier REST requests
    # stay committed when a later request exhausts retries.
    assert "alpha_hunter_snapshots" in session.committed
    assert fail_table not in session.committed
