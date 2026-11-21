"""E8: opt-in independent readback failure must abort collector success.

Synthetic storage only. Never contacts production or creates paper admissions.
"""
from unittest.mock import Mock

import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


@pytest.mark.parametrize("atomic", [False, True])
def test_save_snapshot_readback_failure_prevents_downstream_paper_side_effects(atomic):
    settings = SupabaseConfig(
        url="https://isolated.invalid", key="qa-only",
        atomic_core_scan_writes=atomic, verify_core_scan_readback=True,
        max_retries=0, retry_backoff_seconds=0,
    )
    storage = SupabaseStorage(settings, session=Mock(), bitget_client=Mock())
    storage._upsert = Mock()
    storage._commit_core_scan_atomic = Mock()
    storage._verify_core_scan_readback = Mock(
        side_effect=SupabaseStorageError("independent readback mismatch")
    )
    storage._insert_immutable = Mock()
    storage._select_json = Mock()

    snapshot = {
        "run_id": "qa-fail-closed", "collected_at_utc": "2026-11-19T02:00:00Z",
        "product_type": "USDT-FUTURES", "symbols": [],
    }
    with pytest.raises(SupabaseStorageError, match="independent readback mismatch"):
        storage.save_snapshot(snapshot)

    storage._verify_core_scan_readback.assert_called_once()
    if atomic:
        storage._commit_core_scan_atomic.assert_called_once()
        storage._upsert.assert_not_called()
    else:
        storage._commit_core_scan_atomic.assert_not_called()
        assert storage._upsert.call_count == 5
    storage._insert_immutable.assert_not_called()
    storage._select_json.assert_not_called()
