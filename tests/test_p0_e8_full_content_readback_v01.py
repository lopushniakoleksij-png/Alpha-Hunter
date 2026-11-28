"""P0 E8: isolated synthetic exact-content readback; NEVER touches real PostgreSQL.

A successful receipt/identical IDs cannot establish persisted payload fidelity.
This opt-in gate GETs all persisted columns only after matching row identities.
"""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from alpha_hunter.core_child_identity import verify_core_child_content
from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


def fixture():
    run = "QA_CONTENT_ONLY"
    return {
        "parent": [{
            "run_id": run, "symbol_count": 1,
            "collected_at_utc": "2026-11-20T10:00:00+00:00",
            "payload": {"symbols": [{"symbol": "BTCUSDT", "trade_permission": False}]},
        }],
        "symbols": [{
            "run_id": run, "symbol": "BTCUSDT", "trade_permission": False,
            "state": "WATCH", "last_price": 60000.0,
            "payload": {"intelligence": {"score": 12.5}, "state": "WATCH"},
        }],
        "signals": [{
            "run_id": run, "signal_id": "QA_SIGNAL", "symbol": "BTCUSDT",
            "entry_price": 60000.0, "trade_permission": False,
            "payload": {"execution_setup": {"checks": {"rr_minimum_met": False}}},
        }],
        "features": [{
            "run_id": run, "signal_id": "QA_SIGNAL", "symbol": "BTCUSDT",
            "signal_features": {"trend": 1.0, "flag": False},
        }],
        "readiness": [{
            "run_id": run, "symbol": "BTCUSDT", "trade_permission": False,
            "reference_price": 60000.0, "state": "WATCH",
        }],
    }


def make_storage(observed):
    storage = SupabaseStorage(
        SupabaseConfig(
            url="https://qa.invalid", key="NO_REAL_CREDENTIAL",
            verify_core_scan_readback=True,
            verify_core_scan_content_readback=True,
            max_retries=0,
        ),
        session=Mock(), bitget_client=Mock(),
    )
    storage._select_json = Mock(side_effect=[deepcopy(observed[k]) for k in fixture()])
    return storage


def verify(storage, expected):
    storage._verify_core_scan_readback(
        "QA_CONTENT_ONLY", *(expected[k] for k in fixture())
    )


def test_exact_five_family_content_passes_and_uses_independent_select_all():
    f = fixture()
    storage = make_storage(f)
    verify(storage, f)
    assert storage._select_json.call_count == 5
    assert all(call.args[1]["select"] == "*" for call in storage._select_json.call_args_list)
    assert all(call.args[1]["run_id"] == "eq.QA_CONTENT_ONLY"
               for call in storage._select_json.call_args_list)
    storage.session.post.assert_not_called()


@pytest.mark.parametrize("family,field,value", [
    ("parent", "symbol_count", 0),
    ("symbols", "last_price", 61500.0),
    ("symbols", "trade_permission", True),
    ("signals", "entry_price", 62000.0),
    ("signals", "trade_permission", True),
    ("features", "signal_features", {"trend": 1.0, "flag": True}),
    ("readiness", "reference_price", 10000.0),
    ("readiness", "state", "READY"),
])
def test_same_identity_different_stored_content_fails_closed(family, field, value):
    f = fixture()
    observed = deepcopy(f)
    observed[family][0][field] = value
    storage = make_storage(observed)
    with pytest.raises(SupabaseStorageError, match="content readback mismatch"):
        verify(storage, f)
    storage.session.post.assert_not_called()


def test_nested_payload_change_fails_even_when_all_identity_and_counts_match():
    f = fixture()
    observed = deepcopy(f)
    observed["signals"][0]["payload"]["execution_setup"]["checks"]["rr_minimum_met"] = True
    assert not verify_core_child_content(f, observed)


def test_missing_submitted_field_fails_even_if_server_supplies_other_columns():
    f = fixture()
    observed = deepcopy(f)
    del observed["symbols"][0]["payload"]
    observed["symbols"][0]["server_created_at"] = "2026-11-20T10:00:01Z"
    assert not verify_core_child_content(f, observed)


def test_server_only_extra_fields_and_equivalent_utc_timestamp_are_safe():
    f = fixture()
    observed = deepcopy(f)
    observed["parent"][0]["server_created_at"] = "2026-11-20T10:00:01Z"
    observed["parent"][0]["collected_at_utc"] = "2026-11-20T10:00:00Z"
    assert verify_core_child_content(f, observed)


def test_boolean_cannot_masquerade_as_number():
    f = fixture()
    observed = deepcopy(f)
    observed["symbols"][0]["payload"]["intelligence"]["score"] = True
    assert not verify_core_child_content(f, observed)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_invalid_nonfinite_jsonb_value_fails_closed(bad):
    f = fixture()
    observed = deepcopy(f)
    observed["symbols"][0]["payload"]["intelligence"]["score"] = bad
    assert not verify_core_child_content(f, observed)


def test_extra_identity_and_duplicates_fail_closed():
    f = fixture()
    observed = deepcopy(f)
    observed["readiness"].append(deepcopy(observed["readiness"][0]))
    assert not verify_core_child_content(f, observed)


def test_content_mode_without_identity_gate_refuses_before_any_write():
    config = SupabaseConfig(
        url="https://qa.invalid", key="QA_ONLY",
        verify_core_scan_readback=False,
        verify_core_scan_content_readback=True,
    )
    session = Mock()
    storage = SupabaseStorage(config, session=session, bitget_client=Mock())
    with pytest.raises(SupabaseStorageError, match="requires identity readback"):
        storage.save_snapshot({})
    session.post.assert_not_called()


def test_environment_requires_explicit_content_optin(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://qa.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "SYNTHETIC_ONLY")
    base = SupabaseConfig.from_environment({"supabase": {"enabled": True}})
    assert base.verify_core_scan_content_readback is False
    qa = SupabaseConfig.from_environment({"supabase": {
        "enabled": True, "verify_core_scan_readback": True,
        "verify_core_scan_content_readback": True,
    }})
    assert qa.verify_core_scan_readback is True
    assert qa.verify_core_scan_content_readback is True
