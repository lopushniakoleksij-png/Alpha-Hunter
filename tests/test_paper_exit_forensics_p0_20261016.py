"""Closed-world P0 forensic regressions: no market requests, DB or trades."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from alpha_hunter.paper_exit_forensics import (
    ENDPOINT, SOURCE, audit_paper_exit_one_minute_path,
)


def bar(minute, *, low="99", high="101", opening="100", close="100"):
    return {
        "minute_utc": minute.isoformat(),
        "open": opening, "high": high, "low": low, "close": close,
    }


def scenario(*, direction="LONG", reason="STOP_LOSS", entry_seconds=20):
    begin = datetime(2026, 10, 2, 9, tzinfo=timezone.utc)
    values = [
        bar(begin),
        bar(begin + timedelta(minutes=1)),
        bar(begin + timedelta(minutes=2), low="94", high="101"),
        bar(begin + timedelta(minutes=3)),
        bar(begin + timedelta(minutes=4)),
    ]
    if direction == "SHORT":
        values[2] = bar(begin + timedelta(minutes=2), low="99", high="106")
    return {
        "entry_at_utc": begin + timedelta(seconds=entry_seconds),
        "observed_exit_at_utc": begin + timedelta(minutes=4,seconds=8),
        "direction": direction,
        "stop_price": "95" if direction=="LONG" else "105",
        "target_price": "110" if direction=="LONG" else "90",
        "observed_exit_reason": reason,
        "candles": values,
        "source": SOURCE,
        "source_endpoint": ENDPOINT,
    }


def check_no_authority(result):
    assert result["trade_permission"] is False
    assert result["exchange_authority"] is False
    assert result["production_promotion_permitted"] is False
    assert result["paper_test_evidence"] is False
    assert result["profitability_claim_permitted"] is False
    assert result["execution_price_verified"] is False
    assert result["counterfactual_only"] is True
    assert result["order_path"] == "NONE"
    assert result["source_authentication"] == "NOT_INDEPENDENTLY_AUTHENTICATED"


@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_valid_full_path_identifies_only_candle_touch(direction):
    params = scenario(direction=direction)
    before = deepcopy(params)
    result = audit_paper_exit_one_minute_path(**params)
    assert params == before
    assert result["status"] == "STOP_LOSS"
    assert result["observed_exit_reason_matches"] is True
    assert result["complete_consecutive_candles"] is True
    assert result["candle_count_checked"] == result["expected_candle_count"] == 5
    assert result["minutes_first_touch_to_observed_exit"] == 2.133333
    assert len(result["local_path_sha256"]) == 64
    assert result["local_path_sha256"] == audit_paper_exit_one_minute_path(**params)["local_path_sha256"]
    check_no_authority(result)


def test_target_first_remains_first_even_if_later_stop():
    p = scenario()
    p["candles"][1] = bar(datetime(2026,10,2,9,1,tzinfo=timezone.utc), high="111")
    p["observed_exit_reason"] = "TAKE_PROFIT"
    r = audit_paper_exit_one_minute_path(**p)
    assert r["status"] == "TAKE_PROFIT"
    assert r["observed_exit_reason_matches"] is True
    check_no_authority(r)


@pytest.mark.parametrize("direction",["LONG","SHORT"])
def test_entry_minute_touch_never_proves_order(direction):
    p = scenario(direction=direction, entry_seconds=0)
    p["candles"][0] = bar(
        datetime(2026,10,2,9,tzinfo=timezone.utc),
        low="94" if direction=="LONG" else "99",
        high="101" if direction=="LONG" else "106",
    )
    r = audit_paper_exit_one_minute_path(**p)
    assert r["status"] == "ENTRY_MINUTE_ORDERING_AMBIGUOUS"
    assert r["observed_exit_reason_matches"] is None
    check_no_authority(r)


def test_same_later_minute_stop_and_target_fails_closed():
    p = scenario()
    p["candles"][2] = bar(datetime(2026,10,2,9,2,tzinfo=timezone.utc),low="94",high="111")
    r = audit_paper_exit_one_minute_path(**p)
    assert r["status"] == "AMBIGUOUS_SAME_MINUTE"
    assert r["observed_exit_reason_matches"] is None
    check_no_authority(r)


def test_observed_reason_mismatch_reported_but_never_rewritten():
    p = scenario()
    p["observed_exit_reason"] = "TAKE_PROFIT"
    r = audit_paper_exit_one_minute_path(**p)
    assert r["status"] == "STOP_LOSS"
    assert r["observed_exit_reason_matches"] is False
    check_no_authority(r)


def test_no_candle_touch_cannot_claim_verified_win():
    p = scenario()
    p["candles"][2] = bar(datetime(2026,10,2,9,2,tzinfo=timezone.utc))
    r = audit_paper_exit_one_minute_path(**p)
    assert r["status"] == "NO_MINUTE_TOUCH_FOUND"
    check_no_authority(r)


@pytest.mark.parametrize("invalid",[
    "missing_middle","missing_last","wrong_order","duplicate",
    "invalid_ohlc","unknown_source","wrong_endpoint",
    "naive_clock","observation_before_entry","bad_direction",
    "invalid_protections","stale_25h","empty_candles",
])
def test_incomplete_corrupt_or_untrusted_path_is_data_insufficient(invalid):
    p = scenario()
    if invalid == "missing_middle":
        p["candles"].pop(2)
    elif invalid == "missing_last":
        p["candles"].pop()
    elif invalid == "wrong_order":
        p["candles"][1],p["candles"][2]=p["candles"][2],p["candles"][1]
    elif invalid == "duplicate":
        p["candles"][1] = p["candles"][0].copy()
    elif invalid == "invalid_ohlc":
        p["candles"][1]["low"] = "102"
    elif invalid == "unknown_source":
        p["source"] = "UNKNOWN"
    elif invalid == "wrong_endpoint":
        p["source_endpoint"] = "/private/place-order"
    elif invalid == "naive_clock":
        p["entry_at_utc"] = "2026-10-02T09:00:20"
    elif invalid == "observation_before_entry":
        p["observed_exit_at_utc"] = "2026-10-02T09:00:01+00:00"
    elif invalid == "bad_direction":
        p["direction"] = "SIDEWAYS"
    elif invalid == "invalid_protections":
        p["stop_price"] = "111"
    elif invalid == "stale_25h":
        p["observed_exit_at_utc"] += timedelta(hours=25)
    elif invalid == "empty_candles":
        p["candles"] = []
    result = audit_paper_exit_one_minute_path(**p)
    assert result["status"] == "DATA_INSUFFICIENT"
    assert result["complete_consecutive_candles"] is False
    assert result["observed_exit_reason_matches"] is None
    check_no_authority(result)


def test_research_module_cannot_rewrite_sealed_test_and_has_no_network_imports():
    from pathlib import Path
    source = Path("alpha_hunter/paper_exit_forensics.py").read_text()
    assert "requests" not in source
    assert "supabase" not in source.lower()
    assert "execute_sql" not in source
    assert "apply_migration" not in source
    assert "POST" not in source
    assert "order_path" in source
    assert "MAX_PATH_MINUTES = 1440" in source
    assert "counterfactual_only" in source


def test_synthetic_eigen_489min_delay_not_an_executable_price():
    entry = datetime(2026,10,2,10,tzinfo=timezone.utc)
    # Synthetic time geometry mirrors the delay scale in EIGEN's historical audit.
    candles = [
        bar(entry + timedelta(minutes=i),low="94" if i==71 else "99")
        for i in range(562)
    ]
    # Later bars can be adverse, but never replace the first-touch candle.
    p = {
        "entry_at_utc": entry + timedelta(seconds=24),
        "observed_exit_at_utc": entry + timedelta(minutes=560,seconds=43),
        "direction": "LONG", "stop_price": "95", "target_price": "110",
        "observed_exit_reason": "STOP_LOSS",
        "candles": candles[:561],
        "source": SOURCE,"source_endpoint":ENDPOINT,
    }
    r = audit_paper_exit_one_minute_path(**p)
    assert r["status"] == "STOP_LOSS"
    assert r["minutes_first_touch_to_observed_exit"] > 489
    assert r["minutes_first_touch_to_observed_exit"] < 490
    check_no_authority(r)
