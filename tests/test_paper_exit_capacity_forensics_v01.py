"""P0 isolated EVAA legacy-paper exit evidence, frozen historical facts."""
from pathlib import Path

import pytest

from alpha_hunter.paper_exit_capacity_forensics import (
    evaluate_observed_exit_capacity, summarize_historical_observations,
)


def sample(*, bid="0.8053", bid_size="100", ask="0.8078",
           when="2026-10-02T23:03:32.764907Z", source=None):
    return dict(
        direction="LONG", quantity="362", stop="0.6923",
        target="0.7867",best_bid=bid,best_ask=ask,
        best_bid_size=bid_size,best_ask_size="1206",
        observed_at_utc=when,quote_source=source,
    )


def no_authority(row):
    assert row["trade_permission"] is False
    assert row["exchange_authority"] is False
    assert row["production_promotion_permitted"] is False
    assert row["profitability_claim_permitted"] is False
    assert row["partial_fill_permitted"] is False
    assert row["position_adjustment_permitted"] is False
    assert row["paper_fill_verified"] is False
    assert row["counterfactual_only"] is True
    assert row["executable_at_top_of_book"] is False
    assert row["source_authentication"] == "NOT_INDEPENDENTLY_ATTESTED"


@pytest.mark.parametrize("bid,bid_size",[
    ("0.8053","100"), # 2026-10-02 23:03 observed paper case
    ("0.8327","276"), # 2026-10-02 23:23 observed paper case
    ("0.8133","300"), # later strong bid, still too small for 362
    ("0.7877","45"), # 2026-10-05 sampled rebound
])
def test_original_evaa_take_profit_detected_but_full_close_unavailable(bid,bid_size):
    o=evaluate_observed_exit_capacity(**sample(bid=bid,bid_size=bid_size,ask=str(float(bid)+.0025)))
    assert o["status"]=="TRIGGERED_BUT_CAPACITY_INSUFFICIENT"
    assert o["trigger_type"]=="TAKE_PROFIT"
    assert o["blocker"]=="EXIT_TOP_OF_BOOK_CAPACITY_INSUFFICIENT"
    assert o["size_shortfall"]==str(int(362-float(bid_size)))
    no_authority(o)


def test_long_stop_was_also_capacity_blocked():
    o=evaluate_observed_exit_capacity(**sample(bid="0.6746",ask="0.6757",bid_size="141"))
    assert o["status"]=="TRIGGERED_BUT_CAPACITY_INSUFFICIENT"
    assert o["trigger_type"]=="STOP_LOSS"
    no_authority(o)


def test_apparent_top_level_943_can_pass_size_check_without_proving_fill():
    o=evaluate_observed_exit_capacity(**sample(bid="0.6634",ask="0.6641",bid_size="943"))
    assert o["status"]=="SAMPLED_TOP_LEVEL_SIZE_SUFFICIENT_ONLY"
    assert o["trigger_type"]=="STOP_LOSS"
    assert o["blocker"]=="NO_EXECUTION_OR_SOURCE_AUTHENTICATION_PROOF"
    no_authority(o)


def test_top_level_362_exactly_passes_capacity_only_not_execution():
    o=evaluate_observed_exit_capacity(**sample(bid_size="362"))
    assert o["status"]=="SAMPLED_TOP_LEVEL_SIZE_SUFFICIENT_ONLY"
    no_authority(o)


def test_repeated_samples_cannot_aggregate_capacity_into_fake_fill():
    first=sample(bid_size="200")
    second=sample(bid_size="200",when="2026-10-02T23:23:04.269494Z")
    r=summarize_historical_observations([first,second],quantity="362")
    assert r["target_capacity_blocked_observations"]==2
    assert r["max_observed_target_top_book_size"]==200
    assert r["samples_are_not_accumulable"] is True
    assert r["trade_permission"] is False
    assert r["profitability_claim_permitted"] is False


@pytest.mark.parametrize("input_change",[
    dict(best_bid="-1"),
    dict(best_ask="0.7"),
    dict(best_bid_size="-1"),
    dict(best_bid_size="NaN"),
    dict(direction="WAIT"),
    dict(stop="0.9"),
    dict(observed_at_utc="2026-10-02T23:03:32"),
])
def test_incomplete_or_invalid_market_evidence_fails_closed(input_change):
    p=sample()
    p.update(input_change)
    o=evaluate_observed_exit_capacity(**p)
    assert o["status"]=="DATA_INSUFFICIENT"
    no_authority(o)


def test_quote_source_name_is_not_independent_authentication():
    o=evaluate_observed_exit_capacity(**sample(
        source="BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"))
    assert o["quote_source"]=="BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"
    no_authority(o)


def test_research_never_writes_or_authorizes_trade():
    source=Path("alpha_hunter/paper_exit_capacity_forensics.py").read_text()
    for forbidden in ("requests.", "psycopg", "execute_sql", "place_order(",
                      "cancel_order(", "modify_order(", "supabase.", "urllib"):
        assert forbidden not in source
    assert "counterfactual_only" in source
    assert "paper_fill_verified" in source
