"""Pure successor receipt tests: no DB, no P0 scan, no exchange calls."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/reviews/successor_quote_receipts_v01.py"
spec = importlib.util.spec_from_file_location("successor_quote_receipts_v01", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
build = module.build_monitoring_receipts
FINGERPRINT = "50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834"


def sample():
    parent = {"run_id": "run-1", "collected_at_utc": "2026-10-12T10:00:00Z", "symbol_count": 2,
              "validation_identity": {"run_source": "RENDER_CRON", "runtime_role": "RENDER_CRON",
                                      "scientific_fingerprint_sha256": FINGERPRINT}}
    children = [{"run_id": "run-1", "symbol": x} for x in ("QUSDT", "NMRUSDT")]
    positions = [{"entry_order_id": "p1", "symbol": "QUSDT", "direction": "LONG"},
                 {"entry_order_id": "p2", "symbol": "QUSDT", "direction": "LONG"},
                 {"entry_order_id": "p3", "symbol": "NMRUSDT", "direction": "SHORT"}]
    attempts = [{"entry_order_id": p["entry_order_id"], "source_run_id": "run-1",
                 "symbol": p["symbol"], "direction": p["direction"],
                 "attempt_id": "synthetic-" + p["entry_order_id"],
                 "outcome": "NO_TRIGGER", "blockers": [],
                 "observed_at_utc": "2026-10-12T10:00:04Z",
                 "best_bid": "1", "best_ask": "1.01",
                 "best_bid_size": "10", "best_ask_size": "7",
                 "evidence": {"quote_source": "BITGET_PUBLIC_ALL_TICKERS"}}
                for p in positions]
    quotes = [{"source_run_id": "run-1", "symbol": x, "source": "BITGET_PUBLIC_ALL_TICKERS",
               "captured_at_utc": "2026-10-12T10:00:04Z",
               "bid_price": "1", "ask_price": "1.01", "bid_size": "10", "ask_size": "7"}
              for x in ("QUSDT", "NMRUSDT")]
    return parent, children, positions, attempts, quotes


def assess(data=None, inventory=True, offset=30, sources=None):
    return build(*(data if data is not None else sample()),
                 asof_inventory_complete=inventory, maximum_quote_offset_seconds=offset,
                 approved_quote_sources=sources if sources is not None else {"BITGET_PUBLIC_ALL_TICKERS"})


def receipt(result, symbol):
    return next(item for item in result["receipts"] if item["symbol"] == symbol)


def test_clean_two_strategies_are_one_independent_quote_but_two_positions():
    data = sample()
    original = deepcopy(data)
    result = assess(data)
    assert result == assess(data) and data == original
    assert result["run_status"] == "RECEIPTS_OBSERVED_NOT_EXECUTION_PROOF"
    assert result["receipt_count"] == 2 and result["expected_position_count"] == 3
    q = receipt(result, "QUSDT")
    assert q["expected_position_count"] == 2 and q["attempt_count"] == 2
    assert q["exit_side"] == "SELL" and q["observed_exit_top_book_quantity"] == "10"
    nmr = receipt(result, "NMRUSDT")
    assert nmr["exit_side"] == "BUY" and nmr["observed_exit_top_book_quantity"] == "7"
    for permission in ("paper_authority", "exchange_authority", "trade_permission", "production_promotion_permitted"):
        assert result[permission] is False
    assert result["order_path"] == "NONE"
    assert all(row["future_exit_guaranteed"] is False for row in result["receipts"])


def test_canonical_parent_without_symbols_or_attempts_is_incomplete():
    data = list(sample())
    data[1] = []
    data[3] = []
    result = assess(tuple(data))
    assert result["run_status"] == "UNKNOWN_OR_INCOMPLETE"
    assert "SYMBOL_CHILD_COUNT_MISMATCH" in result["run_blockers"]
    assert "SYMBOL_CHILD_MISSING" in receipt(result, "QUSDT")["blockers"]
    assert "EXIT_ATTEMPT_MISSING" in receipt(result, "NMRUSDT")["blockers"]


def test_one_missing_position_attempt_is_not_hidden_by_duplicate_strategies():
    data = list(sample())
    data[3] = data[3][:1] + data[3][2:]
    assert "EXIT_ATTEMPT_MISSING" in receipt(assess(tuple(data)), "QUSDT")["blockers"]


def test_duplicates_and_wrong_run_fail_closed():
    data = list(sample())
    data[3].append(data[3][0].copy())
    assert "EXIT_ATTEMPT_DUPLICATE" in receipt(assess(tuple(data)), "QUSDT")["blockers"]
    data = list(sample())
    data[3][0]["source_run_id"] = "old-run"
    assert "ATTEMPT_RUN_IDENTITY_INVALID" in assess(tuple(data))["run_blockers"]


@pytest.mark.parametrize("bad", [None, "NaN", "Infinity", 0, -1, True])
def test_invalid_bid_size_is_not_executable_depth(bad):
    data = list(sample())
    data[4][0]["bid_size"] = bad
    assert "QUOTE_BOOK_INVALID" in receipt(assess(tuple(data)), "QUSDT")["blockers"]


def test_unlabelled_and_unapproved_provenance_rejected():
    data = list(sample())
    data[4][0]["source"] = ""
    assert "QUOTE_SOURCE_UNLABELLED" in receipt(assess(tuple(data)), "QUSDT")["blockers"]
    data = list(sample())
    data[4][0]["source"] = "UNKNOWN_VENDOR"
    assert "QUOTE_SOURCE_NOT_APPROVED" in receipt(assess(tuple(data)), "QUSDT")["blockers"]


def test_quote_capture_age_and_explicit_policy_both_required():
    data = list(sample())
    data[4][0]["captured_at_utc"] = "2026-10-12T10:01:00Z"
    assert "QUOTE_OUTSIDE_CAPTURE_WINDOW" in receipt(assess(tuple(data)), "QUSDT")["blockers"]
    assert "QUOTE_TIMESTAMP_POLICY_INVALID" in assess(offset=None)["run_blockers"]
    assert "APPROVED_QUOTE_SOURCES_MISSING" in assess(sources=set())["run_blockers"]


def test_asof_position_inventory_unknown_is_never_complete():
    result = assess(inventory=False)
    assert result["run_status"] == "UNKNOWN_OR_INCOMPLETE"
    assert "ASOF_POSITION_INVENTORY_UNVERIFIED" in result["run_blockers"]


def test_conflicting_quote_and_bad_attempt_outcome_not_accepted():
    data = list(sample())
    other = data[4][0].copy()
    other["bid_size"] = "999"
    data[4].append(other)
    assert "QUOTE_CAPTURE_DUPLICATE_OR_CONFLICT" in receipt(assess(tuple(data)), "QUSDT")["blockers"]
    data = list(sample())
    data[3][0]["outcome"] = "INPUT_MISSING"
    assert "EXIT_ATTEMPT_OUTCOME_UNVERIFIED" in receipt(assess(tuple(data)), "QUSDT")["blockers"]
    data = list(sample())
    data[3][0]["outcome"] = "FUTURE_UNKNOWN_STATUS"
    assert "EXIT_ATTEMPT_OUTCOME_UNVERIFIED" in receipt(assess(tuple(data)), "QUSDT")["blockers"]


def test_position_identity_is_bound_to_attempt():
    data = list(sample())
    data[3][0]["symbol"] = "FAKEUSDT"
    assert "ATTEMPT_POSITION_IDENTITY_MISMATCH" in assess(tuple(data))["run_blockers"]


def test_no_positions_with_attested_inventory_is_not_a_trading_success():
    data = list(sample())
    data[2] = []
    data[3] = []
    data[4] = []
    assert assess(tuple(data))["run_status"] == "NO_POSITIONS_CONFIRMED_ASOF_RUN"
    assert assess((data[0], data[1], None, data[3], data[4]))["run_status"] == "UNKNOWN_OR_INCOMPLETE"
    data[0]["symbol_count"] = 0
    assert assess((data[0], "invalid", [], [], []))["run_status"] == "UNKNOWN_OR_INCOMPLETE"


def test_canonical_identity_mismatch_rejected():
    data = list(sample())
    data[0]["validation_identity"]["runtime_role"] = "WEB_ON_DEMAND"
    assert "CANONICAL_RUN_IDENTITY_INVALID" in assess(tuple(data))["run_blockers"]


def test_prototype_has_no_runtime_wiring_or_exchange_dependencies():
    code = SOURCE.read_text(encoding="utf-8")
    assert "supabase" not in code.lower()
    assert "bitget_client" not in code
    for path in ("alpha_hunter/storage.py", "alpha_hunter/paper_execution.py", "alpha_hunter/paper_exit.py",
                 "alpha_hunter/paper_horizon.py", "run.py", "hourly.py"):
        assert "successor_quote_receipts_v01" not in (ROOT / path).read_text(encoding="utf-8")


def test_no_trigger_without_individual_receipt_evidence_fails_closed():
    cases = (
        ("attempt_id", "EXIT_ATTEMPT_ID_MISSING"),
        ("observed_at_utc", "EXIT_ATTEMPT_TIME_MISSING"),
        ("blockers", "EXIT_ATTEMPT_BLOCKERS_PRESENT_OR_UNKNOWN"),
        ("evidence", "EXIT_ATTEMPT_QUOTE_SOURCE_MISMATCH"),
    )
    for missing, expected in cases:
        data = list(sample())
        data[3][0].pop(missing)
        result = assess(tuple(data))
        assert result["run_status"] == "UNKNOWN_OR_INCOMPLETE"
        assert expected in receipt(result, "QUSDT")["blockers"]
        assert result["trade_permission"] is False


def test_quote_and_attempt_must_match_book_source_and_capture_time():
    cases = (
        ("best_bid_size", "9999", "EXIT_ATTEMPT_QUOTE_BOOK_MISMATCH"),
        ("best_ask", "1.5", "EXIT_ATTEMPT_QUOTE_BOOK_MISMATCH"),
        ("observed_at_utc", "2026-10-12T10:00:45Z", "EXIT_ATTEMPT_QUOTE_TIME_MISMATCH"),
    )
    for field, value, expected in cases:
        data = list(sample())
        data[3][0][field] = value
        result = assess(tuple(data))
        assert result["run_status"] == "UNKNOWN_OR_INCOMPLETE"
        assert expected in receipt(result, "QUSDT")["blockers"]
    data = list(sample())
    data[3][0]["evidence"]["quote_source"] = "CLAIMED_DIFFERENT_VENUE"
    result = assess(tuple(data))
    assert "EXIT_ATTEMPT_QUOTE_SOURCE_MISMATCH" in receipt(result, "QUSDT")["blockers"]


def test_zero_symbol_parent_or_malformed_parent_never_claims_completed_monitoring():
    data = list(sample())
    data[0]["symbol_count"] = 0
    assert "EXPECTED_CHILD_COUNT_INVALID" in assess(tuple(data))["run_blockers"]
    data = list(sample())
    data[0] = None
    assert assess(tuple(data))["run_status"] == "UNKNOWN_OR_INCOMPLETE"
    assert assess()["independently_authenticated_source"] is False
