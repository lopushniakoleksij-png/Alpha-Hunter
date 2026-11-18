"""P0 E8 isolated child-readback acceptance contract (not a production fix)."""
import importlib.util
from pathlib import Path
import pytest

PATH = Path(__file__).resolve().parents[1] / "ops/local/p0_core_child_identity_contract_v01.py"
spec = importlib.util.spec_from_file_location("p0_receipt_contract", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sample():
    return {
        "parent": [("run-1",)],
        "symbols": [("run-1", "BTCUSDT"), ("run-1", "ETHUSDT")],
        "signals": [("signal-1",)],
        "features": [("signal-1", "feature-a")],
        "readiness": [("run-1", "BTCUSDT"), ("run-1", "ETHUSDT")],
    }


def test_exact_independent_readback_passes():
    assert module.verify_core_child_identities(sample(), sample())


@pytest.mark.parametrize("family", ["parent", "symbols", "signals", "features", "readiness"])
def test_missing_family_child_fails_closed(family):
    expected, observed = sample(), sample()
    observed[family] = observed[family][1:]
    assert not module.verify_core_child_identities(expected, observed)


@pytest.mark.parametrize("family", ["parent", "symbols", "signals", "features", "readiness"])
def test_duplicate_child_fails_even_when_present(family):
    expected, observed = sample(), sample()
    observed[family].append(observed[family][0])
    assert not module.verify_core_child_identities(expected, observed)


def test_same_count_wrong_identity_fails():
    expected, observed = sample(), sample()
    observed["symbols"][0] = ("run-1", "SOLUSDT")
    assert not module.verify_core_child_identities(expected, observed)


def test_missing_family_or_malformed_identity_fails():
    expected, observed = sample(), sample()
    del observed["readiness"]
    assert not module.verify_core_child_identities(expected, observed)
    observed = sample()
    observed["signals"] = [("signal-1", None)]
    assert not module.verify_core_child_identities(expected, observed)
