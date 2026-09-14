from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from v76_post_confirmation_tracker import (
    apply_direction_state,
    apply_lifecycle_truth,
    directional_move,
    freeze_due_horizons,
    inspect_candle,
    inspect_price,
    mark_thresholds,
)


UTC = timezone.utc
CONFIRMED_AT = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)


def make_row(direction="LONG"):
    return {
        "episode_id": "post-confirm-test-001",
        "symbol": "TESTUSDT",
        "path": "REVERSAL",
        "model_version": "V7.6",
        "confirmed_direction": direction,
        "confirmed_at_utc": CONFIRMED_AT.isoformat(),
        "confirmation_price": 100.0,
        "confirmation_confidence": 80.0,
        "move_consumed_pct": 1.5,
        "tracking_started_at_utc": CONFIRMED_AT.isoformat(),
        "measurement_quality": "FORWARD_COMPLETE",
        "last_market_check_at_utc": None,
        "market_checks": 0,
        "current_directional_move_pct": 0.0,
        "max_favorable_after_confirm_pct": 0.0,
        "max_adverse_after_confirm_pct": 0.0,
        "hit_1pct": False,
        "hit_2pct": False,
        "hit_3pct": False,
        "hit_5pct": False,
        "hit_10pct": False,
        "first_1pct_at_utc": None,
        "first_2pct_at_utc": None,
        "first_3pct_at_utc": None,
        "first_5pct_at_utc": None,
        "first_10pct_at_utc": None,
        "h1_mfe_pct": None,
        "h1_mae_pct": None,
        "h1_frozen_at_utc": None,
        "h4_mfe_pct": None,
        "h4_mae_pct": None,
        "h4_frozen_at_utc": None,
        "h12_mfe_pct": None,
        "h12_mae_pct": None,
        "h12_frozen_at_utc": None,
        "h24_mfe_pct": None,
        "h24_mae_pct": None,
        "h24_frozen_at_utc": None,
        "confirmation_lost": False,
        "first_lost_confirmation_at_utc": None,
        "lifecycle_final_classification": None,
        "direction_correct": None,
        "is_complete": False,
        "completed_at_utc": None,
        "trade_permission": False,
    }


def candle(at: datetime, high: float, low: float):
    return [
        int(at.timestamp() * 1000),
        "100",
        str(high),
        str(low),
        "100",
        "0",
        "0",
    ]


class TestPostConfirmationDirectionalMove(unittest.TestCase):

    def test_long_move(self):
        self.assertAlmostEqual(
            directional_move("LONG", 100.0, 105.0),
            5.0,
            places=6,
        )

    def test_short_move(self):
        self.assertAlmostEqual(
            directional_move("SHORT", 100.0, 95.0),
            5.0,
            places=6,
        )

    def test_wrong_way_move_is_negative(self):
        self.assertAlmostEqual(
            directional_move("SHORT", 100.0, 103.0),
            -3.0,
            places=6,
        )


class TestPostConfirmationThresholds(unittest.TestCase):

    def test_positive_move_marks_all_reached_thresholds(self):
        row = make_row()
        observed = CONFIRMED_AT + timedelta(minutes=10)

        mark_thresholds(
            row,
            5.5,
            observed,
        )

        self.assertTrue(row["hit_1pct"])
        self.assertTrue(row["hit_2pct"])
        self.assertTrue(row["hit_3pct"])
        self.assertTrue(row["hit_5pct"])
        self.assertFalse(row["hit_10pct"])
        self.assertEqual(
            row["first_5pct_at_utc"],
            observed.isoformat(),
        )

    def test_negative_move_never_marks_favorable_threshold(self):
        row = make_row()

        mark_thresholds(
            row,
            -10.0,
            CONFIRMED_AT + timedelta(minutes=5),
        )

        self.assertFalse(row["hit_1pct"])
        self.assertFalse(row["hit_10pct"])

    def test_first_threshold_timestamp_is_immutable(self):
        row = make_row()
        first = CONFIRMED_AT + timedelta(minutes=5)
        later = CONFIRMED_AT + timedelta(minutes=30)

        mark_thresholds(row, 3.5, first)
        mark_thresholds(row, 8.0, later)

        self.assertEqual(
            row["first_3pct_at_utc"],
            first.isoformat(),
        )


class TestPostConfirmationPriceTracking(unittest.TestCase):

    def test_long_tracks_favorable_and_adverse(self):
        row = make_row("LONG")

        inspect_price(
            row,
            106.0,
            CONFIRMED_AT + timedelta(minutes=10),
        )
        inspect_price(
            row,
            97.0,
            CONFIRMED_AT + timedelta(minutes=20),
        )

        self.assertAlmostEqual(
            row["max_favorable_after_confirm_pct"],
            6.0,
            places=6,
        )
        self.assertAlmostEqual(
            row["max_adverse_after_confirm_pct"],
            -3.0,
            places=6,
        )
        self.assertTrue(row["hit_5pct"])
        self.assertFalse(row["trade_permission"])

    def test_short_tracks_favorable_and_adverse(self):
        row = make_row("SHORT")

        inspect_price(
            row,
            94.0,
            CONFIRMED_AT + timedelta(minutes=10),
        )
        inspect_price(
            row,
            103.0,
            CONFIRMED_AT + timedelta(minutes=20),
        )

        self.assertAlmostEqual(
            row["max_favorable_after_confirm_pct"],
            6.0,
            places=6,
        )
        self.assertAlmostEqual(
            row["max_adverse_after_confirm_pct"],
            -3.0,
            places=6,
        )
        self.assertTrue(row["hit_5pct"])
        self.assertFalse(row["trade_permission"])


class TestPostConfirmationHorizons(unittest.TestCase):

    def test_one_hour_freeze_is_immutable(self):
        row = make_row()
        row["max_favorable_after_confirm_pct"] = 4.0
        row["max_adverse_after_confirm_pct"] = -2.0

        freeze_due_horizons(
            row,
            CONFIRMED_AT + timedelta(hours=1),
        )

        self.assertEqual(row["h1_mfe_pct"], 4.0)
        self.assertEqual(row["h1_mae_pct"], -2.0)

        row["max_favorable_after_confirm_pct"] = 9.0
        row["max_adverse_after_confirm_pct"] = -5.0

        freeze_due_horizons(
            row,
            CONFIRMED_AT + timedelta(hours=2),
        )

        self.assertEqual(row["h1_mfe_pct"], 4.0)
        self.assertEqual(row["h1_mae_pct"], -2.0)

    def test_twenty_four_hour_freeze_completes_row(self):
        row = make_row()
        row["max_favorable_after_confirm_pct"] = 12.0
        row["max_adverse_after_confirm_pct"] = -4.0

        freeze_due_horizons(
            row,
            CONFIRMED_AT + timedelta(hours=24),
        )

        self.assertTrue(row["is_complete"])
        self.assertEqual(
            row["completed_at_utc"],
            (CONFIRMED_AT + timedelta(hours=24)).isoformat(),
        )
        self.assertEqual(row["h24_mfe_pct"], 12.0)
        self.assertEqual(row["h24_mae_pct"], -4.0)


class TestPostConfirmationCandles(unittest.TestCase):

    def test_candle_before_confirmation_is_ignored(self):
        row = make_row("LONG")

        inspect_candle(
            row,
            candle(
                CONFIRMED_AT - timedelta(minutes=1),
                120.0,
                80.0,
            ),
        )

        self.assertEqual(
            row["max_favorable_after_confirm_pct"],
            0.0,
        )
        self.assertEqual(
            row["max_adverse_after_confirm_pct"],
            0.0,
        )

    def test_candle_after_24h_does_not_change_excursions(self):
        row = make_row("LONG")
        row["max_favorable_after_confirm_pct"] = 5.0
        row["max_adverse_after_confirm_pct"] = -2.0

        inspect_candle(
            row,
            candle(
                CONFIRMED_AT + timedelta(hours=25),
                150.0,
                50.0,
            ),
        )

        self.assertEqual(
            row["max_favorable_after_confirm_pct"],
            5.0,
        )
        self.assertEqual(
            row["max_adverse_after_confirm_pct"],
            -2.0,
        )
        self.assertTrue(row["is_complete"])


class TestPostConfirmationStateAndTruth(unittest.TestCase):

    def test_lost_confirmation_is_frozen_once(self):
        row = make_row()
        first_lost = (
            CONFIRMED_AT + timedelta(hours=2)
        ).isoformat()

        apply_direction_state(
            row,
            {
                "direction_state": "LOST_CONFIRMATION",
                "lost_confirmation_count": 1,
                "last_evaluated_at_utc": first_lost,
            },
        )

        self.assertTrue(row["confirmation_lost"])
        self.assertEqual(
            row["first_lost_confirmation_at_utc"],
            first_lost,
        )

        later = (
            CONFIRMED_AT + timedelta(hours=3)
        ).isoformat()

        apply_direction_state(
            row,
            {
                "direction_state": "LOST_CONFIRMATION",
                "lost_confirmation_count": 2,
                "last_evaluated_at_utc": later,
            },
        )

        self.assertEqual(
            row["first_lost_confirmation_at_utc"],
            first_lost,
        )

    def test_final_long_matches_up_ground_truth(self):
        row = make_row("LONG")
        episode = SimpleNamespace(
            is_finalized=True,
            final_classification="MAJOR_EXPANSION_UP",
        )

        apply_lifecycle_truth(
            row,
            episode,
        )

        self.assertEqual(
            row["lifecycle_final_classification"],
            "MAJOR_EXPANSION_UP",
        )
        self.assertTrue(row["direction_correct"])

    def test_final_short_rejects_up_ground_truth(self):
        row = make_row("SHORT")
        episode = SimpleNamespace(
            is_finalized=True,
            final_classification="HUGE_EXPANSION_UP",
        )

        apply_lifecycle_truth(
            row,
            episode,
        )

        self.assertFalse(row["direction_correct"])

    def test_no_expansion_has_no_direction_verdict(self):
        row = make_row("LONG")
        episode = SimpleNamespace(
            is_finalized=True,
            final_classification="NO_EXPANSION",
        )

        apply_lifecycle_truth(
            row,
            episode,
        )

        self.assertIsNone(row["direction_correct"])

    def test_unfinalized_episode_cannot_write_ground_truth(self):
        row = make_row("LONG")
        episode = SimpleNamespace(
            is_finalized=False,
            final_classification="MAJOR_EXPANSION_UP",
        )

        apply_lifecycle_truth(
            row,
            episode,
        )

        self.assertIsNone(
            row["lifecycle_final_classification"]
        )
        self.assertIsNone(
            row["direction_correct"]
        )


class TestPostConfirmationPersistenceSchema(unittest.TestCase):

    def test_new_outcome_row_contains_created_at(self):
        from unittest.mock import patch
        from v76_post_confirmation_tracker import make_outcome_row

        state = {
            "episode_id": "mixed-row-schema-test",
            "symbol": "TESTUSDT",
            "path": "REVERSAL",
            "model_version": "7.6-shadow",
            "first_confirmed_at_utc": CONFIRMED_AT.isoformat(),
            "price_at_confirmed": 100.0,
            "move_at_confirmed_pct": 1.0,
            "current_direction": "SHORT",
            "direction_state": "DIRECTION_CONFIRMED",
            "last_confidence": 70.0,
        }

        episode = SimpleNamespace(
            symbol="TESTUSDT",
            path="REVERSAL",
        )

        with patch(
            "v76_post_confirmation_tracker.confirmation_shadow",
            return_value={
                "direction": "SHORT",
                "confidence": 70.0,
                "evaluated_at_utc": CONFIRMED_AT.isoformat(),
                "market_price": 100.0,
            },
        ):
            row = make_outcome_row(
                SimpleNamespace(),
                state,
                episode,
                CONFIRMED_AT + timedelta(minutes=10),
            )

        self.assertIsNotNone(row)
        self.assertIn("created_at", row)
        self.assertIn("updated_at", row)
        self.assertFalse(row["trade_permission"])


if __name__ == "__main__":
    unittest.main()
