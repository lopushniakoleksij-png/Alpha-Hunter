"""E8: real storage readback method must fail closed on independent GET mismatch.

Synthetic session only; no production database or private SQL is accessed.
"""
from unittest.mock import Mock

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


def make_storage(responses):
    settings = SupabaseConfig(url="https://isolated.invalid", key="qa-only", max_retries=0, retry_backoff_seconds=0)
    storage = SupabaseStorage(settings, session=Mock(), bitget_client=Mock())
    storage._select_json = Mock(side_effect=responses)
    return storage


def fixture_rows():
    run_id = "qa-run"
    parent = [{"run_id": run_id}]
    symbols = [{"run_id": run_id, "symbol": "BTCUSDT"}]
    signals = [{"run_id": run_id, "signal_id": "sig-1", "symbol": "BTCUSDT"}]
    features = [{"run_id": run_id, "signal_id": "sig-1", "symbol": "BTCUSDT"}]
    readiness = [{"run_id": run_id, "symbol": "BTCUSDT"}]
    return run_id, parent, symbols, signals, features, readiness


def test_exact_five_family_independent_get_readback_passes():
    args = fixture_rows()
    storage = make_storage(list(args[1:]))
    storage._verify_core_scan_readback(*args)
    assert storage._select_json.call_count == 5
    for call in storage._select_json.call_args_list:
        assert call.args[1]["run_id"] == "eq.qa-run"
    storage.session.post.assert_not_called()


@pytest.mark.parametrize("family_index", range(5))
def test_missing_one_persisted_family_fails_closed(family_index):
    args = fixture_rows()
    observed = [list(family) for family in args[1:]]
    observed[family_index] = []
    storage = make_storage(observed)
    with pytest.raises(SupabaseStorageError, match="readback mismatch"):
        storage._verify_core_scan_readback(*args)
    storage.session.post.assert_not_called()


def test_same_count_wrong_symbol_fails_closed():
    args = fixture_rows()
    observed = [list(family) for family in args[1:]]
    observed[1] = [{"run_id": "qa-run", "symbol": "ETHUSDT"}]
    storage = make_storage(observed)
    with pytest.raises(SupabaseStorageError, match="readback mismatch"):
        storage._verify_core_scan_readback(*args)


def test_independent_get_failure_does_not_report_success_or_write():
    args = fixture_rows()
    storage = make_storage([SupabaseStorageError("independent GET unavailable")])
    with pytest.raises(SupabaseStorageError, match="independent GET unavailable"):
        storage._verify_core_scan_readback(*args)
    storage.session.post.assert_not_called()
