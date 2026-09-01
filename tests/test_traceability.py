from datetime import datetime, timedelta, timezone

from alpha_hunter.traceability import (
    ReadyEpisode,
    attach_fill_matches,
    make_ready_id,
    readiness_diagnostic,
    rolling_summary,
    strict_production_ready,
    update_ready_ledger,
)
from traceability_job import (
    FILL_HISTORY_ENDPOINT,
    FILL_PAGE_LIMIT,
    load_fill_history,
)


class StubFillClient:
    private_api_configured = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _get(self, path, params, *, private=False):
        self.calls.append((path, params, private))
        return self.responses.pop(0)


def fill_record(trade_id: str, timestamp: datetime, **overrides):
    record = {
        "tradeId": trade_id,
        "orderId": f"order-{trade_id}",
        "symbol": "TESTUSDT",
        "price": "1.0",
        "side": "buy",
        "tradeSide": "close",
        "profit": "1.0",
        "cTime": str(int(timestamp.timestamp() * 1000)),
    }
    record.update(overrides)
    return record


def test_strict_production_ready_requires_both_gates():
    assert strict_production_ready({"trade_permission": True, "v7_trade_ready": True}) is True
    assert strict_production_ready({"trade_permission": True, "v7_trade_ready": False}) is False
    assert strict_production_ready({"trade_permission": False, "v7_trade_ready": True}) is False
    assert strict_production_ready({"trade_permission": False, "v7_trade_ready": False}) is False


def test_ready_id_is_deterministic_and_episode_specific():
    when = "2026-08-30T12:00:00+00:00"
    a = make_ready_id("HYPEUSDT", "LONG", when, "episode-a")
    b = make_ready_id("HYPEUSDT", "LONG", when, "episode-a")
    c = make_ready_id("HYPEUSDT", "LONG", when, "episode-b")
    assert a == b
    assert a != c
    assert a.startswith("RDY-")


def test_update_ledger_creates_and_ends_distinct_ready_episode():
    episodes: list[ReadyEpisode] = []
    ready = {
        "symbol": "TESTUSDT",
        "trade_permission": True,
        "v7_trade_ready": True,
        "execution_setup": {"direction": "LONG", "entry": 1.0, "rr": 6.0},
        "last_price": 1.0,
    }
    update_ready_ledger(episodes, [ready], "2026-08-30T10:00:00+00:00")
    assert len(episodes) == 1
    assert episodes[0].ready_status == "READY"
    assert episodes[0].direction == "LONG"

    blocked = dict(ready)
    blocked["v7_trade_ready"] = False
    update_ready_ledger(episodes, [blocked], "2026-08-30T11:00:00+00:00")
    assert episodes[0].ready_status == "READY_ENDED"
    assert episodes[0].ended_at_utc == "2026-08-30T11:00:00+00:00"

    update_ready_ledger(episodes, [ready], "2026-08-30T12:00:00+00:00")
    assert len(episodes) == 2
    assert episodes[1].ready_status == "READY"
    assert episodes[0].ready_id != episodes[1].ready_id


def test_missing_symbol_does_not_terminate_ready_episode():
    episodes: list[ReadyEpisode] = []
    ready = {
        "symbol": "TESTUSDT",
        "trade_permission": True,
        "v7_trade_ready": True,
        "execution_setup": {"direction": "SHORT"},
    }
    update_ready_ledger(episodes, [ready], "2026-08-30T10:00:00+00:00")
    update_ready_ledger(episodes, [{"symbol": "OTHERUSDT"}], "2026-08-30T11:00:00+00:00")
    assert episodes[0].ready_status == "READY"


def test_fill_match_is_heuristic_not_verified():
    episodes: list[ReadyEpisode] = []
    ready = {
        "symbol": "TESTUSDT",
        "trade_permission": True,
        "v7_trade_ready": True,
        "execution_setup": {"direction": "SHORT"},
    }
    update_ready_ledger(episodes, [ready], "2026-08-30T10:00:00+00:00")
    fills = [
        {
            "tradeId": "t1",
            "orderId": "o1",
            "symbol": "TESTUSDT",
            "side": "sell",
            "tradeSide": "sell_single",
            "profit": "0",
            "price": "0.99",
            "cTime": str(int(datetime(2026, 8, 30, 10, 5, tzinfo=timezone.utc).timestamp() * 1000)),
            "enterPointSource": "ios",
        }
    ]
    attach_fill_matches(episodes, fills)
    assert episodes[0].first_execution_at_utc is not None
    assert episodes[0].execution_match_quality == "HEURISTIC_FILL_MATCH"
    assert episodes[0].execution_trade_ids == ["t1"]


def test_fill_history_uses_current_endpoint_and_reports_verified_coverage():
    start = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)
    end = start + timedelta(hours=168)
    client = StubFillClient(
        [
            {
                "fillList": [fill_record("trade-1", end - timedelta(hours=1))],
                "endId": "trade-1",
            }
        ]
    )

    result = load_fill_history(client, "usdt-futures", start, end)

    assert result.status == "CONNECTED"
    assert len(result.fills) == 1
    assert result.coverage["endpoint"] == FILL_HISTORY_ENDPOINT
    assert result.coverage["fill_count"] == 1
    assert result.coverage["pages_fetched"] == 1
    assert result.coverage["complete"] is True
    assert result.coverage["schema_validated"] is True
    path, params, private = client.calls[0]
    assert path == "/api/v2/mix/order/fills"
    assert params["productType"] == "usdt-futures"
    assert params["startTime"] == str(int(start.timestamp() * 1000))
    assert params["endTime"] == str(int(end.timestamp() * 1000))
    assert params["limit"] == "100"
    assert "idLessThan" not in params
    assert private is True


def test_zero_fills_are_valid_schema_but_never_traceability_pass():
    start = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)
    end = start + timedelta(hours=168)
    result = load_fill_history(
        StubFillClient([{"fillList": [], "endId": ""}]),
        "usdt-futures",
        start,
        end,
    )

    assert result.status == "ZERO_FILLS"
    assert result.coverage["complete"] is True
    assert result.coverage["schema_validated"] is True
    assert result.coverage["fill_count"] == 0
    summary = rolling_summary(
        [],
        fills=result.fills,
        now_utc=end,
        fill_history_coverage=result.coverage,
    )
    assert summary["fill_history_pass_eligible"] is False
    assert summary["traceability_status"] == "INCOMPLETE"


def test_malformed_fill_response_is_incomplete_not_pass():
    start = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)
    end = start + timedelta(hours=168)
    result = load_fill_history(
        StubFillClient([{"unexpected": []}]),
        "usdt-futures",
        start,
        end,
    )

    assert result.status == "INVALID_SCHEMA"
    assert result.coverage["complete"] is False
    assert result.coverage["schema_validated"] is False
    summary = rolling_summary(
        [],
        fills=result.fills,
        now_utc=end,
        fill_history_coverage=result.coverage,
    )
    assert summary["traceability_status"] == "INCOMPLETE"


def test_fill_history_paginates_with_end_id_and_reports_all_pages():
    start = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)
    end = start + timedelta(hours=168)
    first_page = [
        fill_record(f"trade-{index:03d}", end - timedelta(minutes=index + 1))
        for index in range(FILL_PAGE_LIMIT)
    ]
    final_fill = fill_record("trade-older", start + timedelta(hours=1))
    client = StubFillClient(
        [
            {"fillList": first_page, "endId": "trade-099"},
            {"fillList": [final_fill], "endId": "trade-older"},
        ]
    )

    result = load_fill_history(client, "usdt-futures", start, end)

    assert result.status == "CONNECTED"
    assert result.coverage["fill_count"] == FILL_PAGE_LIMIT + 1
    assert result.coverage["pages_fetched"] == 2
    assert result.coverage["complete"] is True
    assert "idLessThan" not in client.calls[0][1]
    assert client.calls[1][1]["idLessThan"] == "trade-099"


def test_traceability_pass_requires_positive_complete_fill_coverage():
    start = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)
    end = start + timedelta(hours=168)
    result = load_fill_history(
        StubFillClient(
            [
                {
                    "fillList": [fill_record("trade-1", end - timedelta(hours=1))],
                    "endId": "trade-1",
                }
            ]
        ),
        "usdt-futures",
        start,
        end,
    )
    summary = rolling_summary(
        [],
        fills=result.fills,
        now_utc=end,
        fill_history_coverage=result.coverage,
    )
    assert summary["fill_history_pass_eligible"] is True
    assert summary["traceability_status"] == "PASS"

    opening_fill = fill_record(
        "trade-open",
        end - timedelta(minutes=30),
        tradeSide="open",
        profit="0",
    )
    failed = rolling_summary(
        [],
        fills=[opening_fill],
        now_utc=end,
        fill_history_coverage={
            **result.coverage,
            "fill_count": 1,
        },
    )
    assert failed["unlinked_open_like_fill_count"] == 1
    assert failed["traceability_status"] == "FAIL"


def test_rolling_summary_separates_symbols_from_episodes():
    episodes = [
        ReadyEpisode(
            ready_id="RDY-1",
            symbol="HYPEUSDT",
            direction="LONG",
            first_ready_at_utc="2026-08-29T10:00:00+00:00",
            last_ready_at_utc="2026-08-29T10:00:00+00:00",
        ),
        ReadyEpisode(
            ready_id="RDY-2",
            symbol="HYPEUSDT",
            direction="SHORT",
            first_ready_at_utc="2026-08-30T10:00:00+00:00",
            last_ready_at_utc="2026-08-30T10:00:00+00:00",
        ),
        ReadyEpisode(
            ready_id="RDY-3",
            symbol="ADAUSDT",
            direction="LONG",
            first_ready_at_utc="2026-08-30T11:00:00+00:00",
            last_ready_at_utc="2026-08-30T11:00:00+00:00",
        ),
    ]
    summary = rolling_summary(
        episodes,
        now_utc="2026-08-30T12:00:00+00:00",
        hours=168,
    )
    assert summary["distinct_trade_ready_coins"] == 2
    assert summary["distinct_trade_ready_episodes"] == 3
    assert summary["trade_ready_long"] == 2
    assert summary["trade_ready_short"] == 1
    assert summary["fill_history_status"] == "NOT_EVALUATED"
    assert summary["traceability_status"] == "INCOMPLETE"


def test_readiness_diagnostic_ranks_blockers_and_closest_candidates():
    snapshots = [
        {
            "symbols": [
                {
                    "symbol": "FARUSDT",
                    "trade_permission": False,
                    "v7_trade_ready": False,
                    "behaviour_score": 4.0,
                    "market_phase": "EXPANSION",
                    "opportunity_timing": "LATE",
                    "execution_setup": {
                        "direction": None,
                        "rr": None,
                        "checks": {},
                    },
                    "rejection_reasons": ["PHASE_EXPANSION"],
                },
                {
                    "symbol": "NEARUSDT",
                    "trade_permission": False,
                    "v7_trade_ready": False,
                    "behaviour_score": 8.0,
                    "market_phase": "IGNITION",
                    "opportunity_timing": "EARLY",
                    "execution_setup": {
                        "direction": "LONG",
                        "rr": 6.0,
                        "checks": {
                            "direction_aligned": True,
                            "participation_confirmed": False,
                        },
                    },
                    "rejection_reasons": [],
                },
                {
                    "symbol": "BROKENUSDT",
                    "error": "ticker unavailable",
                },
            ]
        }
    ]

    diagnostic = readiness_diagnostic(snapshots)

    assert diagnostic["classification"] == "AUDIT_ONLY_DOES_NOT_GRANT_PERMISSION"
    assert diagnostic["evaluated_candidate_observations"] == 2
    assert diagnostic["data_error_observations"] == 1
    assert diagnostic["strict_ready_observations"] == 0
    assert diagnostic["ranked_gate_blockers"][0] == {
        "reason": "TRADE_PERMISSION",
        "observations": 2,
        "observation_pct": 100.0,
    }
    assert diagnostic["ranked_execution_check_failures"] == [
        {
            "reason": "PARTICIPATION_CONFIRMED",
            "observations": 1,
            "observation_pct": 50.0,
        }
    ]
    root_blockers = {
        row["reason"]: row
        for row in diagnostic["ranked_root_gate_blockers"]
    }
    assert root_blockers["DIRECTION_AVAILABLE"] == {
        "reason": "DIRECTION_AVAILABLE",
        "failed_observations": 1,
        "eligible_observations": 2,
        "failure_pct_when_eligible": 50.0,
        "observation_pct": 50.0,
    }
    assert "EXECUTION_RR" not in root_blockers
    assert diagnostic["composite_trade_permission_gate"]["classification"] == (
        "COMPOSITE_NOT_INDEPENDENT_ROOT_CAUSE"
    )
    assert diagnostic["gate_dependency_model"]["V7_TRADE_READY"] == [
        "TRADE_PERMISSION",
        "EXECUTION_SCORE",
        "EXECUTION_RR",
        "ELIGIBLE_PHASE",
        "EARLY_TIMING",
    ]
    assert diagnostic["ranked_execution_check_failures_when_evaluated"] == [
        {
            "reason": "PARTICIPATION_CONFIRMED",
            "failed_observations": 1,
            "eligible_observations": 1,
            "failure_pct_when_eligible": 100.0,
            "observation_pct": 50.0,
        }
    ]
    assert diagnostic["behaviour_score_distribution"]["median"] == 6.0
    assert diagnostic["reward_risk_distribution_directional"] == {
        "eligible_observations": 1,
        "observations_with_value": 1,
        "value_coverage_pct": 100.0,
        "minimum_observed": 6.0,
        "p25": 6.0,
        "median": 6.0,
        "p75": 6.0,
        "p90": 6.0,
        "maximum_observed": 6.0,
        "required_minimum": 5.0,
        "meeting_minimum_observations": 1,
        "meeting_minimum_pct_of_eligible": 100.0,
        "meeting_minimum_pct_of_values": 100.0,
    }
    closest = diagnostic["current_closest_candidates"]
    assert closest[0]["symbol"] == "NEARUSDT"
    assert closest[0]["conditions_passed"] == 5
    assert closest[0]["independent_conditions_passed"] == 5
    assert closest[0]["failed_conditions"] == ["TRADE_PERMISSION"]
    assert closest[0]["execution_check_failures"] == [
        "PARTICIPATION_CONFIRMED"
    ]
    assert closest[0]["quality_rejections"] == []
    assert closest[0]["audit_only"] is True


def test_readiness_root_cause_uses_directional_rr_denominator():
    snapshots = [
        {
            "symbols": [
                {
                    "symbol": "NODIRECTIONUSDT",
                    "trade_permission": False,
                    "v7_trade_ready": False,
                    "behaviour_score": 8.0,
                    "market_phase": "IGNITION",
                    "opportunity_timing": "EARLY",
                    "execution_setup": {
                        "direction": None,
                        "rr": None,
                        "checks": {},
                    },
                },
                {
                    "symbol": "LOWRRUSDT",
                    "trade_permission": False,
                    "v7_trade_ready": False,
                    "behaviour_score": 8.0,
                    "market_phase": "IGNITION",
                    "opportunity_timing": "EARLY",
                    "execution_setup": {
                        "direction": "LONG",
                        "entry": 100.0,
                        "stop": 90.0,
                        "target": 105.0,
                        "risk": 10.0,
                        "reward": 5.0,
                        "rr": 0.5,
                        "checks": {
                            "direction_aligned": True,
                            "structure_valid": True,
                            "momentum_confirmed": True,
                            "participation_confirmed": True,
                            "funding_not_extreme": True,
                            "data_integrity_min_88": True,
                            "rr_minimum_met": False,
                        },
                    },
                },
            ]
        }
    ]

    diagnostic = readiness_diagnostic(snapshots)

    legacy = {
        row["reason"]: row
        for row in diagnostic["ranked_gate_blockers"]
    }
    assert legacy["EXECUTION_RR"]["observations"] == 2

    root = {
        row["reason"]: row
        for row in diagnostic["ranked_root_gate_blockers"]
    }
    assert root["EXECUTION_RR"] == {
        "reason": "EXECUTION_RR",
        "failed_observations": 1,
        "eligible_observations": 1,
        "failure_pct_when_eligible": 100.0,
        "observation_pct": 50.0,
    }
    distribution = diagnostic["reward_risk_distribution_directional"]
    assert distribution["eligible_observations"] == 1
    assert distribution["maximum_observed"] == 0.5
    assert distribution["meeting_minimum_observations"] == 0
    assert diagnostic["reachability"]["execution_reward_risk_gate"] == (
        "UNREACHED_IN_OBSERVED_COHORT"
    )
    assert diagnostic["reachability"]["thresholds_changed"] is False

    closest = diagnostic["current_closest_candidates"][0]
    assert closest["symbol"] == "LOWRRUSDT"
    assert closest["reward_risk_shortfall"] == 4.5
    assert closest["execution_geometry"]["risk_pct_of_entry"] == 10.0
    assert closest["execution_geometry"]["reward_pct_of_entry"] == 5.0
