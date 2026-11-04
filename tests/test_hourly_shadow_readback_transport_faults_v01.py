"""P0 readback transport/shape fault-injection regression; synthetic, GET-only.

These checks ensure a partially successful four-GET read cannot be returned as
canonical evidence after an uncertain HTTP response or unstable latest head.
No production credentials, network requests, SQL writes, or scanner invocations.
"""
from __future__ import annotations

import copy
import pytest

from alpha_hunter.hourly_shadow_readback import (
    TABLE_CHILD, TABLE_FEATURE, TABLE_PARENT, read_latest_canonical_run,
)
from alpha_hunter.hourly_shadow_score import HourlyScoringBlocked

RUN = "a" * 32


def fixture_rows():
    parent = {
        "run_id": RUN, "symbol_count": 2, "error_count": 0,
        "collected_at_utc": "2026-11-04T19:43:25+00:00",
        "payload": {
            "run_id": RUN, "_storage_contract": "snapshot-parent-v0.2",
            "validation_identity": {"run_source": "RENDER_CRON"},
            "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
        },
    }
    children = [{"run_id": RUN, "symbol": s, "payload": {"symbol": s}}
                for s in ("BTCUSDT", "ETHUSDT")]
    features = [{"run_id": RUN, "symbol": s, "features": {}, "source_payload": {}}
                for s in ("BTCUSDT", "ETHUSDT")]
    return parent, children, features


@pytest.mark.parametrize("failed_call", [1, 2, 3, 4])
@pytest.mark.parametrize("error", [TimeoutError("read timed out"), ConnectionError("connection reset")])
def test_any_transport_failure_aborts_entire_readback(failed_call, error):
    parent, children, features = fixture_rows()
    calls = []
    def get_rows(table, params):
        calls.append((table, dict(params)))
        if len(calls) == failed_call:
            raise type(error)(str(error))
        return copy.deepcopy({
            TABLE_PARENT: [parent], TABLE_CHILD: children, TABLE_FEATURE: features
        }[table])

    with pytest.raises(type(error), match=str(error)):
        read_latest_canonical_run(get_rows)
    assert len(calls) == failed_call
    assert all(method in (TABLE_PARENT, TABLE_CHILD, TABLE_FEATURE) for method, _ in calls)
    assert all(params.get("run_id", "eq." + RUN) == "eq." + RUN for _, params in calls)


@pytest.mark.parametrize("failed_call", [1, 2, 3, 4])
@pytest.mark.parametrize("malformed", [None, {}, "error", [None], [1]])
def test_malformed_postgrest_shape_fails_closed_at_every_stage(failed_call, malformed):
    parent, children, features = fixture_rows()
    calls = []
    def get_rows(table, params):
        calls.append(table)
        if len(calls) == failed_call:
            return copy.deepcopy(malformed)
        return copy.deepcopy({
            TABLE_PARENT: [parent], TABLE_CHILD: children, TABLE_FEATURE: features
        }[table])

    with pytest.raises(HourlyScoringBlocked, match="malformed or truncated"):
        read_latest_canonical_run(get_rows)
    assert len(calls) == failed_call


@pytest.mark.parametrize("field, replacement", [
    ("symbol_count", 1), ("collected_at_utc", "2026-11-04T19:44:00+00:00"),
    ("payload", {"run_id": RUN, "validation_identity": {"run_source": "RENDER_CRON"},
                 "symbols": [{"symbol": "BTCUSDT"}]}),
])
def test_same_run_id_but_mutated_parent_recheck_blocks(field, replacement):
    parent, children, features = fixture_rows()
    changed = copy.deepcopy(parent)
    changed[field] = replacement
    count = 0
    def get_rows(table, params):
        nonlocal count
        if table == TABLE_PARENT:
            count += 1
            return [copy.deepcopy(changed if count == 2 else parent)]
        return copy.deepcopy({TABLE_CHILD: children, TABLE_FEATURE: features}[table])
    with pytest.raises(HourlyScoringBlocked, match="changed during readback"):
        read_latest_canonical_run(get_rows)
    assert count == 2
