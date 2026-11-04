"""Synthetic readback checks: no HTTP, credentials, SQL writes or scans."""
import copy
import pytest
from alpha_hunter.hourly_shadow_readback import read_latest_canonical_run, TABLE_PARENT, TABLE_CHILD, TABLE_FEATURE
from alpha_hunter.hourly_shadow_score import HourlyScoringBlocked

RUN = "a" * 32

def sample():
    parent = {"run_id": RUN, "symbol_count": 2, "error_count": 0,
      "collected_at_utc": "2026-11-04T19:43:25+00:00",
      "payload": {"run_id": RUN, "_storage_contract": "snapshot-parent-v0.2",
        "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
        "validation_identity": {"run_source": "RENDER_CRON", "runtime_role": "RENDER_CRON",
          "scientific_fingerprint_sha256": "f" * 64}}}
    children = [{"run_id": RUN, "symbol": s, "payload": {"symbol": s}} for s in ("BTCUSDT","ETHUSDT")]
    features = [{"run_id": RUN, "symbol": s, "captured_at_utc": parent["collected_at_utc"],
       "features": {"volume_ratio": 8}, "source_payload": {"change_24h_pct": 0.5}}
       for s in ("BTCUSDT","ETHUSDT")]
    return parent, children, features

def reader(parent, children, features, newer=None):
    calls = []
    def get_rows(table, params):
        calls.append((table, dict(params)))
        if table == TABLE_PARENT:
            count = sum(t == TABLE_PARENT for t, _ in calls)
            return [copy.deepcopy(newer if count == 2 and newer is not None else parent)]
        if table == TABLE_CHILD:
            return copy.deepcopy(children)
        if table == TABLE_FEATURE:
            return copy.deepcopy(features)
        raise AssertionError("unexpected table")
    return get_rows, calls

def test_correct_source_and_table_requests():
    p, c, f = sample()
    get_rows, calls = reader(p,c,f)
    assert read_latest_canonical_run(get_rows) == (p,c,f)
    assert [t for t,_ in calls] == [TABLE_PARENT,TABLE_CHILD,TABLE_FEATURE,TABLE_PARENT]
    assert calls[0][1]["payload->validation_identity->>run_source"] == "eq.RENDER_CRON"
    assert calls[1][1]["run_id"] == "eq."+RUN
    assert calls[2][1]["run_id"] == "eq."+RUN
    assert calls[3][1] == calls[0][1]
    assert calls[1][1]["limit"] == "3"

def test_incomplete_newest_never_replaced_by_old_complete():
    p, _, _ = sample()
    get_rows,_ = reader(p,[],[])
    got = read_latest_canonical_run(get_rows)
    assert got[0]["run_id"] == RUN
    assert got[1] == [] and got[2] == []

def test_new_canonical_parent_during_read_fails():
    p,c,f = sample()
    new = copy.deepcopy(p)
    new["run_id"] = "b"*32
    get_rows,_ = reader(p,c,f,newer=new)
    with pytest.raises(HourlyScoringBlocked,match="changed"):
        read_latest_canonical_run(get_rows)

@pytest.mark.parametrize("bad", ["", "invalid", "A"*32, "a"*31, "a"*33])
def test_invalid_run_id_never_used_as_query(bad):
    p,c,f = sample()
    p["run_id"] = bad
    get_rows,calls = reader(p,c,f)
    with pytest.raises(HourlyScoringBlocked,match="32-character"):
        read_latest_canonical_run(get_rows)
    assert len(calls) == 1

@pytest.mark.parametrize("bad", [None, False, 0, -1, 2001, "61"])
def test_invalid_count_fails_before_child_fetch(bad):
    p,c,f = sample()
    p["symbol_count"] = bad
    get_rows,calls = reader(p,c,f)
    with pytest.raises(HourlyScoringBlocked,match="count is invalid"):
        read_latest_canonical_run(get_rows)
    assert len(calls) == 1

def test_transport_failure_propagates_without_fallback():
    def failing(*_args):
        raise TimeoutError("test read timeout")
    with pytest.raises(TimeoutError):
        read_latest_canonical_run(failing)

def test_missing_latest_parent_blocks():
    with pytest.raises(HourlyScoringBlocked,match="parent is missing"):
        read_latest_canonical_run(lambda *_args: [])
