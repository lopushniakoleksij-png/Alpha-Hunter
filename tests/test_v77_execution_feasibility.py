from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from v77_execution_feasibility_shadow import (
    build_execution_row,
    choose_stop,
    choose_target,
    execution_shadow_id,
    expected_execution_shadow_id,
    feasibility_status,
    reusable_shadow_evidence,
    parse_closed_candles,
    rr,
    stop_distance_pct,
    structural_reward_pct,
)

UTC = timezone.utc
CONFIRMED_AT = datetime(2026, 8, 15, 14, 0, tzinfo=UTC)


def raw_candle(opened_at: datetime, high: float, low: float, close: float | None = None):
    close = close if close is not None else (high + low) / 2.0
    return [
        int(opened_at.timestamp() * 1000),
        str(close),
        str(high),
        str(low),
        str(close),
        "1000",
        "1000",
    ]


def history(
    *,
    count: int,
    timeframe_minutes: int,
    as_of: datetime,
    base: float = 100.0,
    spread: float = 2.0,
):
    rows = []
    start = as_of - timedelta(minutes=timeframe_minutes * count)
    for i in range(count):
        opened = start + timedelta(minutes=timeframe_minutes * i)
        drift = (i % 5) * 0.05
        rows.append(
            raw_candle(
                opened,
                base + spread + drift,
                base - spread + drift,
                base + drift,
            )
        )
    return rows


def state(direction: str = "LONG", price: float = 100.0):
    return {
        "episode_id": "episode-v77-001",
        "symbol": "TESTUSDT",
        "path": "REVERSAL",
        "first_confirmed_at_utc": CONFIRMED_AT.isoformat(),
        "price_at_confirmed": price,
        "move_at_confirmed_pct": 1.25,
        "direction_state": "DIRECTION_CONFIRMED",
    }


def confirmation(direction: str = "LONG"):
    return {
        "direction": direction,
        "confidence": 80.0,
    }


class TestFrozenExecutionReuse(
    unittest.TestCase
):
    def test_expected_shadow_id_matches_frozen_id(
        self,
    ):
        item = state()

        expected = execution_shadow_id(
            item["episode_id"],
            CONFIRMED_AT,
        )

        self.assertEqual(
            expected_execution_shadow_id(
                item
            ),
            expected,
        )

    def test_complete_permission_false_row_is_reusable(
        self,
    ):
        item = state()

        shadow_id = (
            expected_execution_shadow_id(
                item
            )
        )

        self.assertIsNotNone(
            shadow_id
        )

        existing = {
            shadow_id: {
                "shadow_id":
                    shadow_id,
                "trade_permission":
                    False,
                "feasibility_status":
                    "STRUCTURE_RR_5_TO_10",
                "candidate_entry":
                    100.0,
            }
        }

        self.assertTrue(
            reusable_shadow_evidence(
                item,
                existing,
            )
        )

    def test_permission_violation_is_not_reusable(
        self,
    ):
        item = state()

        shadow_id = (
            expected_execution_shadow_id(
                item
            )
        )

        existing = {
            shadow_id: {
                "shadow_id":
                    shadow_id,
                "trade_permission":
                    True,
                "feasibility_status":
                    "STRUCTURE_RR_5_TO_10",
                "candidate_entry":
                    100.0,
            }
        }

        self.assertFalse(
            reusable_shadow_evidence(
                item,
                existing,
            )
        )

    def test_incomplete_existing_row_is_not_reusable(
        self,
    ):
        item = state()

        shadow_id = (
            expected_execution_shadow_id(
                item
            )
        )

        existing = {
            shadow_id: {
                "shadow_id":
                    shadow_id,
                "trade_permission":
                    False,
                "feasibility_status":
                    None,
                "candidate_entry":
                    None,
            }
        }

        self.assertFalse(
            reusable_shadow_evidence(
                item,
                existing,
            )
        )


class TestClosedCandleProtection(unittest.TestCase):
    def test_future_candle_is_excluded(self):
        rows = [
            raw_candle(CONFIRMED_AT - timedelta(minutes=30), 101, 99, 100),
            raw_candle(CONFIRMED_AT + timedelta(minutes=1), 500, 1, 250),
        ]
        parsed = parse_closed_candles(rows, CONFIRMED_AT, 15)
        self.assertEqual(len(parsed), 1)
        self.assertLess(parsed[0]["high"], 500)

    def test_forming_candle_is_excluded(self):
        opened = CONFIRMED_AT - timedelta(minutes=10)
        parsed = parse_closed_candles(
            [raw_candle(opened, 150, 50, 100)],
            CONFIRMED_AT,
            15,
        )
        self.assertEqual(parsed, [])

    def test_exact_close_boundary_is_included(self):
        opened = CONFIRMED_AT - timedelta(minutes=15)
        parsed = parse_closed_candles(
            [raw_candle(opened, 101, 99, 100)],
            CONFIRMED_AT,
            15,
        )
        self.assertEqual(len(parsed), 1)

    def test_parse_sorts_oldest_to_newest(self):
        earlier = CONFIRMED_AT - timedelta(minutes=30)
        later = CONFIRMED_AT - timedelta(minutes=15)
        parsed = parse_closed_candles(
            [
                raw_candle(later, 102, 98, 100),
                raw_candle(earlier, 101, 99, 100),
            ],
            CONFIRMED_AT,
            15,
        )
        self.assertLess(parsed[0]["timestamp"], parsed[1]["timestamp"])


class TestStopSelection(unittest.TestCase):
    def test_long_stop_is_below_entry(self):
        stop, source = choose_stop("LONG", 100, 98, 104, 95, 108, 2)
        self.assertIsNotNone(stop)
        self.assertLess(stop, 100)
        self.assertIsNotNone(source)

    def test_short_stop_is_above_entry(self):
        stop, source = choose_stop("SHORT", 100, 96, 102, 90, 110, 2)
        self.assertIsNotNone(stop)
        self.assertGreater(stop, 100)
        self.assertIsNotNone(source)

    def test_long_uses_nearest_defensible_support(self):
        stop, source = choose_stop("LONG", 100, 98, 104, 95, 108, 0)
        self.assertAlmostEqual(stop, 98.0)
        self.assertTrue(source.startswith("15M_SWING_LOW"))

    def test_short_uses_nearest_defensible_resistance(self):
        stop, source = choose_stop("SHORT", 100, 96, 102, 90, 110, 0)
        self.assertAlmostEqual(stop, 102.0)
        self.assertTrue(source.startswith("15M_SWING_HIGH"))

    def test_missing_valid_stop_returns_none(self):
        stop, source = choose_stop("LONG", 100, 101, 104, 102, 108, 2)
        self.assertIsNone(stop)
        self.assertIsNone(source)


class TestTargetSelection(unittest.TestCase):
    def test_long_target_is_nearest_overhead_structure(self):
        self.assertEqual(choose_target("LONG", 100, 95, 103, 92, 108), 103)

    def test_short_target_is_nearest_lower_structure(self):
        self.assertEqual(choose_target("SHORT", 100, 97, 104, 90, 110), 97)

    def test_no_valid_target_returns_none(self):
        self.assertIsNone(choose_target("LONG", 100, 95, 99, 90, 98))


class TestRiskRewardMath(unittest.TestCase):
    def test_stop_distance_math(self):
        self.assertAlmostEqual(stop_distance_pct(100, 98), 2.0, places=6)

    def test_long_structural_reward_math(self):
        self.assertAlmostEqual(structural_reward_pct("LONG", 100, 106), 6.0, places=6)

    def test_short_structural_reward_math(self):
        self.assertAlmostEqual(structural_reward_pct("SHORT", 100, 94), 6.0, places=6)

    def test_rr_math(self):
        self.assertAlmostEqual(rr(10.0, 2.0), 5.0, places=6)

    def test_zero_risk_returns_none(self):
        self.assertIsNone(rr(10.0, 0.0))


class TestFeasibilityClassification(unittest.TestCase):
    def test_rr_below_three(self):
        self.assertEqual(feasibility_status(True, True, 2.99), "STRUCTURE_RR_LT_3")

    def test_rr_three_to_five(self):
        self.assertEqual(feasibility_status(True, True, 3.0), "STRUCTURE_RR_3_TO_5")

    def test_rr_five_to_ten(self):
        self.assertEqual(feasibility_status(True, True, 5.0), "STRUCTURE_RR_5_TO_10")

    def test_rr_ten_plus(self):
        self.assertEqual(feasibility_status(True, True, 10.0), "STRUCTURE_RR_10_PLUS")

    def test_invalid_stop_overrides_rr(self):
        self.assertEqual(feasibility_status(False, True, 20.0), "NO_VALID_STOP")


class TestFrozenExecutionSnapshot(unittest.TestCase):
    def test_snapshot_is_confirmation_anchored_and_no_trade_permission(self):
        c15 = history(count=30, timeframe_minutes=15, as_of=CONFIRMED_AT, base=100, spread=3)
        c1h = history(count=30, timeframe_minutes=60, as_of=CONFIRMED_AT, base=100, spread=6)

        row = build_execution_row(
            state("LONG", 100.0),
            confirmation("LONG"),
            c15,
            c1h,
            CONFIRMED_AT + timedelta(hours=2),
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["candidate_entry"], 100.0)
        self.assertEqual(row["market_price"], 100.0)
        self.assertEqual(row["evaluated_at_utc"], CONFIRMED_AT.isoformat())
        self.assertFalse(row["trade_permission"])
        self.assertTrue(row["evidence"]["future_candle_leakage_blocked"])

    def test_snapshot_id_is_idempotent_for_same_confirmation(self):
        first = execution_shadow_id("episode-v77-001", CONFIRMED_AT)
        second = execution_shadow_id("episode-v77-001", CONFIRMED_AT)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
