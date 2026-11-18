"""E8 read-only integration: five-family identity contract consumes GET evidence, never POST receipts.

Synthetic HTTP responses only; no production access or database writes.
"""
import importlib.util
from pathlib import Path
from unittest.mock import Mock
import pytest

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError

PATH = Path(__file__).resolve().parents[1] / "ops/local/p0_core_child_identity_contract_v01.py"
spec = importlib.util.spec_from_file_location("p0_receipt_contract", PATH)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)

FAMILIES = {
    "parent": ("alpha_hunter_snapshots", ("run_id",)),
    "symbols": ("alpha_hunter_symbol_snapshots", ("run_id", "symbol")),
    "signals": ("alpha_hunter_signals", ("signal_id",)),
    "features": ("alpha_hunter_signal_features", ("signal_id", "feature_name")),
    "readiness": ("alpha_hunter_readiness_observations_v01", ("run_id", "symbol")),
}
EXPECTED = {
    "parent": [("r1",)],
    "symbols": [("r1", "BTCUSDT")],
    "signals": [("s1",)],
    "features": [("s1", "f1")],
    "readiness": [("r1", "BTCUSDT")],
}


def read_families(storage):
    observed = {}
    for family, (table, columns) in FAMILIES.items():
        rows = storage._select_json(table, {"select": ",".join(columns), "run_id": "eq.r1"})
        observed[family] = [tuple(row.get(column) for column in columns) for row in rows]
    return observed


def storage_with_responses(data):
    session = Mock()
    responses = []
    for family, (_, columns) in FAMILIES.items():
        response = Mock(status_code=200, text="")
        response.json.return_value = [dict(zip(columns, identity)) for identity in data[family]]
        responses.append(response)
    session.get.side_effect = responses
    return SupabaseStorage(SupabaseConfig(url="https://example.invalid", key="test", max_retries=0), session=session)


def test_independent_get_readback_exact_identity_passes():
    storage = storage_with_responses(EXPECTED)
    assert contract.verify_core_child_identities(EXPECTED, read_families(storage))
    assert storage.session.get.call_count == 5
    storage.session.post.assert_not_called()


@pytest.mark.parametrize("family", list(FAMILIES))
def test_independent_get_readback_missing_family_fails_closed(family):
    data = {key: list(rows) for key, rows in EXPECTED.items()}
    data[family] = []
    storage = storage_with_responses(data)
    assert not contract.verify_core_child_identities(EXPECTED, read_families(storage))
    storage.session.post.assert_not_called()


def test_independent_get_readback_wrong_identity_same_count_fails_closed():
    data = {key: list(rows) for key, rows in EXPECTED.items()}
    data["symbols"] = [("r1", "ETHUSDT")]
    storage = storage_with_responses(data)
    assert not contract.verify_core_child_identities(EXPECTED, read_families(storage))


def test_independent_get_readback_http_error_fails_closed():
    storage = storage_with_responses(EXPECTED)
    responses = list(storage.session.get.side_effect)
    responses[1].status_code = 503
    storage.session.get.side_effect = responses
    with pytest.raises(SupabaseStorageError):
        read_families(storage)
    storage.session.post.assert_not_called()
