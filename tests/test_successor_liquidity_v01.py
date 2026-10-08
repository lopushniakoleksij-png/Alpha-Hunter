"""Pure candidate-size science; no frozen-cohort runtime participation."""
from copy import deepcopy
from pathlib import Path

import pytest

from alpha_hunter.successor_liquidity import assess_successor_liquidity


def setup(direction="LONG"):
    c = {
        "successor_cohort_id": "PAPER_EXECUTION_FUTURE_SHADOW",
        "source_run_id": "future-canonical-run-1",
        "symbol": "EXAMPLEUSDT",
        "direction": direction,
        "observed_at_utc": "2026-10-08T03:23:10+00:00",
        "entry_price": "0.22",
        "stop_price": "0.20" if direction == "LONG" else "0.24",
    }
    q = {
        "source_run_id": "future-canonical-run-1",
        "source": "BITGET_PUBLIC_TOP_OF_BOOK_CAPTURE",
        "symbol": "EXAMPLEUSDT",
        "captured_at_utc": "2026-10-08T03:23:09+00:00",
        "best_bid": "0.2199",
        "best_ask": "0.2201",
        "best_bid_size": "40",
        "best_ask_size": "900",
    }
    p = {
        "risk_budget_usdt": "2.5",
        "size_multiplier": "1",
        "minimum_trade_number": "1",
        "minimum_trade_usdt": "5",
        "maximum_book_participation": "1",  # example, NOT production-frozen
        "max_quote_age_seconds": "30",  # example, NOT production-frozen
    }
    return c, q, p


def test_magma_long_caps_to_opposite_bid_rather_than_entry_ask():
    c, q, p = setup()
    result = assess_successor_liquidity(c, q, p)
    assert result["status"] == "SHADOW_FEASIBLE_AT_ENTRY_SNAPSHOT_ONLY"
    assert result["quantity"] == 40
    assert result["risk_only_quantity"] == 125
    assert result["entry_book_quantity"] == 900
    assert result["exit_book_quantity"] == 40
    assert result["entry_side"] == "BUY" and result["exit_side"] == "SELL"
    assert result["risk_used_usdt"] <= 2.5
    assert result["exchange_authority"] is False and result["paper_authority"] is False


def test_super_short_ask_13_cannot_satisfy_minimum_five_usdt():
    c, q, p = setup("SHORT")
    q.update(best_bid_size="266", best_ask_size="13")
    result = assess_successor_liquidity(c, q, p)
    assert result["status"] == "BLOCKED"
    assert result["blockers"] == ["BELOW_MINIMUM_TRADE_NOTIONAL"]
    assert result["quantity"] is None


def test_limited_entry_side_caps_short_sell_as_well():
    c, q, p = setup("SHORT")
    q.update(best_bid_size="30", best_ask_size="500")
    result = assess_successor_liquidity(c, q, p)
    assert result["quantity"] == 30
    assert result["entry_side"] == "SELL" and result["exit_side"] == "BUY"


def test_fraction_is_explicit_and_can_reject_magma_due_to_minimum_notional():
    c, q, p = setup()
    p["maximum_book_participation"] = "0.25"
    assert assess_successor_liquidity(c, q, p)["blockers"] == ["BELOW_MINIMUM_TRADE_NOTIONAL"]


def test_rounds_down_and_never_exceeds_risk_budget():
    c, q, p = setup()
    q.update(best_bid_size="101.9", best_ask_size="110")
    c["stop_price"] = "0.203"
    p.update(size_multiplier="0.3", maximum_book_participation="1")
    result = assess_successor_liquidity(c, q, p)
    assert result["quantity"] == pytest.approx(101.7)
    assert result["risk_used_usdt"] <= 2.5


@pytest.mark.parametrize("field,value", [
    ("best_bid_size", None), ("best_ask_size", 0), ("best_ask_size", "NaN"),
    ("best_bid_size", "Infinity"), ("best_ask", "0.1"),
])
def test_bad_book_is_fail_closed(field, value):
    c, q, p = setup()
    q[field] = value
    result = assess_successor_liquidity(c, q, p)
    assert result["status"] == "BLOCKED" and result["quantity"] is None


@pytest.mark.parametrize("field,value", [
    ("maximum_book_participation", "1.01"),
    ("maximum_book_participation", "0"),
    ("maximum_book_participation", None),
    ("size_multiplier", "NaN"),
    ("risk_budget_usdt", "-1"),
    ("minimum_trade_usdt", None),
    ("max_quote_age_seconds", None),
])
def test_missing_or_unsafe_policy_is_fail_closed(field, value):
    c, q, p = setup()
    p[field] = value
    result = assess_successor_liquidity(c, q, p)
    assert result["status"] == "BLOCKED" and result["quantity"] is None


def test_rejects_frozen_r9_r10_even_with_perfect_depth():
    for cohort in ("PAPER_EXECUTION_R9", "PAPER_EXECUTION_R10", ""):
        c, q, p = setup()
        c["successor_cohort_id"] = cohort
        assert "SUCCESSOR_COHORT_NOT_PREREGISTERED" in assess_successor_liquidity(c, q, p)["blockers"]


def test_rejects_unbound_or_future_quote_and_stale_evidence():
    for field, value, blocker in (
        ("source_run_id", "other", "QUOTE_IDENTITY_MISMATCH"),
        ("captured_at_utc", "2026-10-08T03:23:11+00:00", "QUOTE_AFTER_DECISION_LOOKAHEAD"),
        ("captured_at_utc", "2026-10-08T03:22:00+00:00", "QUOTE_STALE"),
        ("captured_at_utc", "2026-10-08T03:23:09", "QUOTE_CLOCK_INVALID"),
    ):
        c, q, p = setup()
        q[field] = value
        assert blocker in assess_successor_liquidity(c, q, p)["blockers"]


def test_missing_stop_geometry_or_symbol_mismatch_blocks():
    c, q, p = setup()
    c["stop_price"] = "0.221"
    assert "RISK_GEOMETRY_INVALID" in assess_successor_liquidity(c, q, p)["blockers"]
    c, q, p = setup()
    q["symbol"] = "OTHERUSDT"
    assert "QUOTE_IDENTITY_MISMATCH" in assess_successor_liquidity(c, q, p)["blockers"]


def test_deterministic_same_input_and_no_mutation():
    c, q, p = setup()
    before = deepcopy((c, q, p))
    first = assess_successor_liquidity(c, q, p)
    assert first == assess_successor_liquidity(c, q, p)
    assert before == (c, q, p)
    for permission in ("exchange_authority", "trade_permission", "paper_authority", "production_promotion_permitted"):
        assert first[permission] is False
    assert first["order_path"] == "NONE"


def test_successor_module_is_not_imported_by_any_active_runtime_path():
    root = Path(__file__).parents[1]
    protected = (
        "alpha_hunter/storage.py", "alpha_hunter/paper_execution.py",
        "alpha_hunter/paper_exit.py", "alpha_hunter/paper_horizon.py",
        "alpha_hunter/collector.py", "run.py", "hourly.py",
    )
    for file in protected:
        source = (root / file).read_text(encoding="utf-8")
        assert "import successor_liquidity" not in source
        assert "from .successor_liquidity import" not in source


def test_historical_magma_entry_quote_does_not_justify_143_units():
    """Only past admission evidence; NOT an attempt to repair October R10 rows."""
    c, q, p = setup("LONG")
    c.update(entry_price="0.21792", stop_price="0.20051")
    q.update(best_bid="0.21786", best_ask="0.21795",
             best_bid_size="46", best_ask_size="848")
    result = assess_successor_liquidity(c, q, p)
    assert result["risk_only_quantity"] == pytest.approx(143.5956346927)
    assert result["quantity"] == 46  # entry snapshot, NOT future exit bid=40
    p["maximum_book_participation"] = "0.25"  # illustrative only
    assert assess_successor_liquidity(c, q, p)["blockers"] == ["BELOW_MINIMUM_TRADE_NOTIONAL"]


def test_historical_super_entry_quote_still_cannot_guarantee_later_exit():
    """Shows the limitation: later ask=13 was unforeseeable from entry ask=266."""
    c, q, p = setup("SHORT")
    c.update(entry_price="0.2205", stop_price="0.2233")
    q.update(best_bid="0.2205", best_ask="0.2207",
             best_bid_size="2157", best_ask_size="266")
    result = assess_successor_liquidity(c, q, p)
    assert result["risk_only_quantity"] == pytest.approx(892.857142857)
    assert result["quantity"] == 266
    assert result["status"] == "SHADOW_FEASIBLE_AT_ENTRY_SNAPSHOT_ONLY"
    assert result["exit_book_quantity"] == 266
    # No assertion of guaranteed 24h exit capacity: stop-time ask was just 13.
