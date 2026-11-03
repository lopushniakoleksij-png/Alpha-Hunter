"""Synthetic successor-only canonical child readback; never contacts production."""
import pytest

from alpha_hunter.canonical_child_readback import (
    CanonicalChildReadbackError,
    readback_canonical_child_run,
    verify_canonical_child_rows,
)


def child(symbol, run_id="run-1", payload_symbol=None):
    return {"run_id": run_id, "symbol": symbol, "payload": {
        "symbol": symbol if payload_symbol is None else payload_symbol,
    }}


def test_complete_readback_accepts_unordered_exact_run():
    result = verify_canonical_child_rows(
        "run-1", ["BTCUSDT", "ETHUSDT"], [child("ETHUSDT"), child("BTCUSDT")]
    )
    assert result == {"run_id": "run-1", "expected": 2, "verified": 2, "status": "PASS"}


@pytest.mark.parametrize("expected,rows,reason", [
    (["BTCUSDT", "ETHUSDT"], [], "count mismatch"),
    (["BTCUSDT", "ETHUSDT"], [child("BTCUSDT")], "count mismatch"),
    (["BTCUSDT"], [child("BTCUSDT"), child("ETHUSDT")], "count mismatch"),
    (["BTCUSDT", "ETHUSDT"], [child("BTCUSDT"), child("BTCUSDT")], "duplicate persisted"),
    (["BTCUSDT"], [child("BTCUSDT", run_id="different")], "run_id mismatch"),
    (["BTCUSDT"], [child("ETHUSDT")], "unexpected"),
    (["BTCUSDT"], [child("BTCUSDT", payload_symbol="ETHUSDT")], "payload symbol mismatch"),
    (["BTCUSDT"], [{"run_id": "run-1", "symbol": "BTCUSDT", "payload": None}], "payload symbol mismatch"),
    (["BTCUSDT"], [None], "invalid canonical child"),
    (["BTCUSDT", "BTCUSDT"], [child("BTCUSDT"), child("BTCUSDT")], "duplicate expected"),
    (["BTCUSDT", ""], [child("BTCUSDT"), child("")], "expected canonical symbols"),
    ([], [], "expected canonical symbols"),
])
def test_fail_closed_on_incomplete_or_corrupt_readback(expected, rows, reason):
    with pytest.raises(CanonicalChildReadbackError, match=reason):
        verify_canonical_child_rows("run-1", expected, rows)


@pytest.mark.parametrize("bad_id", ["", None, "   "])
def test_missing_parent_identity_fails_closed(bad_id):
    with pytest.raises(CanonicalChildReadbackError, match="run_id missing"):
        verify_canonical_child_rows(bad_id, ["BTCUSDT"], [child("BTCUSDT")])


def test_bounded_readback_queries_exact_run_and_one_extra_row():
    calls = []

    def read(table, params):
        calls.append((table, params))
        return [child("ETHUSDT"), child("BTCUSDT")]

    result = readback_canonical_child_run(
        "run-1", ["BTCUSDT", "ETHUSDT"], read
    )
    assert result["status"] == "PASS"
    assert calls == [("alpha_hunter_symbol_snapshots", {
        "select": "run_id,symbol,payload", "run_id": "eq.run-1", "limit": "3",
    })]


def test_invalid_request_never_calls_database():
    def forbidden(*args):
        raise AssertionError("database call forbidden")

    with pytest.raises(CanonicalChildReadbackError, match="invalid expected"):
        readback_canonical_child_run("run-1", ["BTCUSDT", "BTCUSDT"], forbidden)


def test_timeout_cannot_be_mistaken_for_pass():
    def timeout(*args):
        raise TimeoutError("statement timeout")

    with pytest.raises(TimeoutError, match="statement timeout"):
        readback_canonical_child_run("run-1", ["BTCUSDT"], timeout)


def test_truncated_page_never_passes():
    with pytest.raises(CanonicalChildReadbackError, match="count mismatch"):
        readback_canonical_child_run("run-1", ["BTCUSDT", "ETHUSDT"], lambda *_: [child("BTCUSDT")])


def test_bounded_request_rejects_more_than_1000_without_read():
    def forbidden(*args):
        raise AssertionError("database call forbidden")
    with pytest.raises(CanonicalChildReadbackError, match="bounded"):
        readback_canonical_child_run("run-1", [f"SYM{i}" for i in range(1001)], forbidden)
