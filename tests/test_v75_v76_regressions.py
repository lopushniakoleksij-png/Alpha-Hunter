from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from alpha_hunter.lifecycle import LifecycleEpisode
from v75_episode_finalizer import classify_ground_truth, dominant_direction, finalization_ready
from v76_direction_shadow import directional_move_pct, shadow_id, update_direction_state


def make_episode(first_detected_at=None, price=100.0, quality="FORWARD_COMPLETE"):
    if first_detected_at is None:
        first_detected_at = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
    timestamp = first_detected_at.isoformat()
    return LifecycleEpisode(
        episode_id="test-episode-001",
        symbol="TESTUSDT",
        path="REVERSAL",
        first_detected_at_utc=timestamp,
        last_detected_at_utc=timestamp,
        first_detection_price=price,
        latest_price=price,
        measurement_quality=quality,
    )


class TestV76Persistence(unittest.TestCase):
    def test_same_hour_rerun_does_not_increment(self):
        episode = make_episode()
        first = update_direction_state(
            episode, None, "SHORT", 80.0, 99.0,
            datetime(2026, 8, 15, 12, 5, tzinfo=timezone.utc),
        )
        second = update_direction_state(
            episode, first, "SHORT", 90.0, 98.0,
            datetime(2026, 8, 15, 12, 55, tzinfo=timezone.utc),
        )
        self.assertEqual(first["consecutive_direction_count"], 1)
        self.assertEqual(second["consecutive_direction_count"], 1)
        self.assertEqual(second["direction_state"], "DIRECTION_EMERGING")
        self.assertEqual(second["confirmation_count"], 0)

    def test_next_hour_can_confirm(self):
        episode = make_episode()
        first = update_direction_state(
            episode, None, "SHORT", 80.0, 99.0,
            datetime(2026, 8, 15, 12, 5, tzinfo=timezone.utc),
        )
        second = update_direction_state(
            episode, first, "SHORT", 80.0, 98.0,
            datetime(2026, 8, 15, 13, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(second["consecutive_direction_count"], 2)
        self.assertEqual(second["direction_state"], "DIRECTION_CONFIRMED")
        self.assertEqual(second["confirmation_count"], 1)
        self.assertIsNotNone(second["first_confirmed_at_utc"])

    def test_low_confidence_does_not_confirm(self):
        episode = make_episode()
        first = update_direction_state(
            episode, None, "LONG", 44.0, 101.0,
            datetime(2026, 8, 15, 12, 5, tzinfo=timezone.utc),
        )
        second = update_direction_state(
            episode, first, "LONG", 44.0, 102.0,
            datetime(2026, 8, 15, 13, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(second["consecutive_direction_count"], 2)
        self.assertEqual(second["direction_state"], "DIRECTION_EMERGING")
        self.assertEqual(second["confirmation_count"], 0)

    def test_confirmed_direction_can_be_lost(self):
        episode = make_episode()
        first = update_direction_state(
            episode, None, "SHORT", 80.0, 99.0,
            datetime(2026, 8, 15, 12, 5, tzinfo=timezone.utc),
        )
        confirmed = update_direction_state(
            episode, first, "SHORT", 80.0, 98.0,
            datetime(2026, 8, 15, 13, 5, tzinfo=timezone.utc),
        )
        lost = update_direction_state(
            episode, confirmed, "LONG", 75.0, 101.0,
            datetime(2026, 8, 15, 14, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(lost["direction_state"], "LOST_CONFIRMATION")
        self.assertEqual(lost["lost_confirmation_count"], 1)

    def test_shadow_id_is_hourly_idempotent(self):
        first = shadow_id(
            "episode-123",
            datetime(2026, 8, 15, 12, 1, tzinfo=timezone.utc),
        )
        same_hour = shadow_id(
            "episode-123",
            datetime(2026, 8, 15, 12, 59, tzinfo=timezone.utc),
        )
        next_hour = shadow_id(
            "episode-123",
            datetime(2026, 8, 15, 13, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(first, same_hour)
        self.assertNotEqual(first, next_hour)

    def test_v76_never_changes_trade_permission(self):
        episode = make_episode()
        self.assertFalse(episode.trade_permission)
        update_direction_state(
            episode, None, "LONG", 90.0, 101.0,
            datetime(2026, 8, 15, 12, 5, tzinfo=timezone.utc),
        )
        self.assertFalse(episode.trade_permission)


class TestV76Timing(unittest.TestCase):
    def test_long_directional_move(self):
        self.assertAlmostEqual(
            directional_move_pct(make_episode(price=100.0), "LONG", 105.0),
            5.0,
            places=6,
        )

    def test_short_directional_move(self):
        self.assertAlmostEqual(
            directional_move_pct(make_episode(price=100.0), "SHORT", 95.0),
            5.0,
            places=6,
        )


class TestV75Finalization(unittest.TestCase):
    def test_forward_episode_ready_at_24h(self):
        now = datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc)
        episode = make_episode(now - timedelta(hours=24))
        self.assertTrue(finalization_ready(episode, now))

    def test_episode_not_ready_before_24h(self):
        now = datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc)
        episode = make_episode(now - timedelta(hours=23, minutes=59))
        self.assertFalse(finalization_ready(episode, now))

    def test_legacy_episode_never_clean_finalizes(self):
        now = datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc)
        episode = make_episode(
            now - timedelta(hours=48),
            quality="LEGACY_PARTIAL",
        )
        self.assertFalse(finalization_ready(episode, now))

    def test_finalized_episode_is_not_ready_again(self):
        now = datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc)
        episode = make_episode(now - timedelta(hours=48))
        episode.is_finalized = True
        self.assertFalse(finalization_ready(episode, now))

    def test_dominant_downside_ground_truth(self):
        episode = make_episode()
        episode.max_up_excursion_pct = 6.0
        episode.max_down_excursion_pct = -11.0
        self.assertEqual(dominant_direction(episode), "DOWN")
        self.assertEqual(classify_ground_truth(episode), "HUGE_EXPANSION_DOWN")

    def test_dominant_upside_ground_truth(self):
        episode = make_episode()
        episode.max_up_excursion_pct = 8.0
        episode.max_down_excursion_pct = -5.0
        self.assertEqual(dominant_direction(episode), "UP")
        self.assertEqual(classify_ground_truth(episode), "MAJOR_EXPANSION_UP")

    def test_no_expansion_below_three_percent(self):
        episode = make_episode()
        episode.max_up_excursion_pct = 2.9
        episode.max_down_excursion_pct = -2.9
        self.assertIsNone(dominant_direction(episode))
        self.assertEqual(classify_ground_truth(episode), "NO_EXPANSION")


if __name__ == "__main__":
    unittest.main()
