import pytest

from v710_money_queue_shadow import (
    build_candidate,
    generate_money_queue,
    required_entry_for_constraints,
)


def test_sol_long_required_entry():
    row = (
        required_entry_for_constraints(
            "LONG",
            92.555,
            102.79,
            0.7070252186246824,
            5.0,
            2.0,
            3.0,
        )
    )

    assert row is not None

    assert row[
        "required_entry"
    ] == pytest.approx(
        94.26083333333334
    )

    assert row[
        "planned_rr"
    ] == pytest.approx(
        5.0
    )

    assert (
        row[
            "planned_risk_pct"
        ]
        <= 2.0
    )

    assert (
        row[
            "planned_atr_x"
        ]
        <= 3.0
    )


def test_velvet_short_required_entry():
    row = (
        required_entry_for_constraints(
            "SHORT",
            0.70676,
            0.47233,
            0.007606732182283812,
            5.0,
            2.0,
            3.0,
        )
    )

    assert row is not None

    assert row[
        "required_entry"
    ] == pytest.approx(
        0.6929019607843138
    )

    assert (
        row[
            "planned_risk_pct"
        ]
        == pytest.approx(
            2.0
        )
    )

    assert (
        row[
            "planned_rr"
        ]
        > 5.0
    )


def test_lower_target_horizon_is_rejected():
    row = {
        "symbol":
            "TESTUSDT",

        "last_price":
            100.0,

        "market_phase":
            "RECOVERY",

        "opportunity_timing":
            "EARLY",

        "behaviour_score":
            8.0,

        "trade_permission":
            False,

        "v7_trade_ready":
            False,

        "execution_setup": {
            "direction":
                "LONG",

            "checks": {
                "direction_aligned":
                    True,

                "structure_valid":
                    True,

                "momentum_confirmed":
                    True,

                "participation_confirmed":
                    True,

                "funding_not_extreme":
                    True,

                "data_integrity_min_88":
                    True,
            },
        },

        "timeframes": {
            "15m": {
                "support":
                    98.0,

                "resistance":
                    110.0,

                "indicators": {
                    "atr_14":
                        1.0,
                },
            },

            "1H": {
                "support":
                    95.0,

                "resistance":
                    120.0,

                "indicators": {
                    "atr_14":
                        2.0,
                },
            },

            "4H": {
                "support":
                    90.0,

                "resistance":
                    140.0,

                "indicators": {
                    "atr_14":
                        4.0,
                },
            },
        },
    }

    candidate = build_candidate(
        row,
        "1H",
        "15m",
    )

    assert candidate is None


def test_shadow_never_grants_permission():
    snapshot = {
        "symbols": [
            {
                "symbol":
                    "TESTUSDT",

                "last_price":
                    100.0,

                "market_phase":
                    "RECOVERY",

                "opportunity_timing":
                    "EARLY",

                "behaviour_score":
                    8.0,

                "trade_permission":
                    True,

                "v7_trade_ready":
                    True,

                "execution_setup": {
                    "direction":
                        "LONG",

                    "checks": {
                        "direction_aligned":
                            True,

                        "structure_valid":
                            True,

                        "momentum_confirmed":
                            True,

                        "participation_confirmed":
                            True,

                        "funding_not_extreme":
                            True,

                        "data_integrity_min_88":
                            True,
                    },
                },

                "timeframes": {
                    "15m": {
                        "support":
                            98.0,

                        "resistance":
                            104.0,

                        "indicators": {
                            "atr_14":
                                1.0,
                        },
                    },

                    "1H": {
                        "support":
                            95.0,

                        "resistance":
                            115.0,

                        "indicators": {
                            "atr_14":
                                2.0,
                        },
                    },

                    "4H": {
                        "support":
                            90.0,

                        "resistance":
                            130.0,

                        "indicators": {
                            "atr_14":
                                4.0,
                        },
                    },
                },
            }
        ],
    }

    config = {
        "candidate_quality": {
            "minimum_execution_reward_risk":
                5.0,

            "minimum_execution_score":
                7.5,
        }
    }

    queue = (
        generate_money_queue(
            snapshot,
            config,
        )
    )

    assert queue

    assert (
        queue[0][
            "shadow_trade_permission"
        ]
        is False
    )


def test_missing_confirmation_and_phase_blocker():
    row = {
        "symbol":
            "SHORTUSDT",

        "last_price":
            100.0,

        "market_phase":
            "BREAKDOWN",

        "opportunity_timing":
            "FAIR",

        "behaviour_score":
            8.0,

        "trade_permission":
            False,

        "v7_trade_ready":
            False,

        "execution_setup": {
            "direction":
                "SHORT",

            "checks": {
                "direction_aligned":
                    True,

                "structure_valid":
                    True,

                "momentum_confirmed":
                    True,

                "participation_confirmed":
                    False,

                "funding_not_extreme":
                    True,

                "data_integrity_min_88":
                    True,
            },
        },

        "timeframes": {
            "15m": {
                "support":
                    80.0,

                "resistance":
                    102.0,

                "indicators": {
                    "atr_14":
                        1.0,
                },
            },

            "1H": {
                "support":
                    80.0,

                "resistance":
                    110.0,

                "indicators": {
                    "atr_14":
                        2.0,
                },
            },

            "4H": {
                "support":
                    70.0,

                "resistance":
                    120.0,

                "indicators": {
                    "atr_14":
                        4.0,
                },
            },
        },
    }

    candidate = (
        build_candidate(
            row,
            "15m",
            "4H",
        )
    )

    assert candidate is not None

    assert (
        "participation_confirmed"
        in candidate[
            "missing_non_rr_checks"
        ]
    )

    blockers = (
        candidate[
            "production_blockers"
        ]
    )

    assert any(
        "BREAKDOWN"
        in blocker
        for blocker
        in blockers
    )

    assert any(
        "FAIR"
        in blocker
        for blocker
        in blockers
    )

    assert (
        candidate[
            "shadow_trade_permission"
        ]
        is False
    )


def test_long_distribution_risk_is_not_queued():
    row = {
        "symbol":
            "DISTUSDT",

        "last_price":
            100.0,

        "market_phase":
            "DISTRIBUTION_RISK",

        "opportunity_timing":
            "FAIR",

        "behaviour_score":
            8.0,

        "trade_permission":
            False,

        "v7_trade_ready":
            False,

        "execution_setup": {
            "direction":
                "LONG",

            "checks": {
                "direction_aligned":
                    True,

                "structure_valid":
                    True,

                "momentum_confirmed":
                    True,

                "participation_confirmed":
                    True,

                "funding_not_extreme":
                    True,

                "data_integrity_min_88":
                    True,
            },
        },

        "timeframes": {
            "15m": {
                "support":
                    98.0,

                "resistance":
                    105.0,

                "indicators": {
                    "atr_14":
                        1.0,
                },
            },

            "1H": {
                "support":
                    95.0,

                "resistance":
                    115.0,

                "indicators": {
                    "atr_14":
                        2.0,
                },
            },

            "4H": {
                "support":
                    90.0,

                "resistance":
                    130.0,

                "indicators": {
                    "atr_14":
                        4.0,
                },
            },
        },
    }

    assert (
        build_candidate(
            row,
            "15m",
            "4H",
        )
        is None
    )



def test_late_candidate_is_not_queued():
    row = {
        "symbol":
            "LATEUSDT",

        "last_price":
            100.0,

        "market_phase":
            "EXPANSION",

        "opportunity_timing":
            "LATE",

        "behaviour_score":
            9.0,

        "trade_permission":
            False,

        "v7_trade_ready":
            False,

        "execution_setup": {
            "direction":
                "LONG",

            "checks": {
                "direction_aligned":
                    True,

                "structure_valid":
                    True,

                "momentum_confirmed":
                    True,

                "participation_confirmed":
                    True,

                "funding_not_extreme":
                    True,

                "data_integrity_min_88":
                    True,
            },
        },

        "timeframes": {
            "15m": {
                "support":
                    98.0,

                "resistance":
                    110.0,

                "indicators": {
                    "atr_14":
                        1.0,
                },
            },

            "1H": {
                "support":
                    95.0,

                "resistance":
                    120.0,

                "indicators": {
                    "atr_14":
                        2.0,
                },
            },

            "4H": {
                "support":
                    90.0,

                "resistance":
                    140.0,

                "indicators": {
                    "atr_14":
                        4.0,
                },
            },
        },
    }

    assert (
        build_candidate(
            row,
            "15m",
            "4H",
        )
        is None
    )
