import unittest

from v710_entry_location_matrix import (
    limit_entry,
    replay_limit_entry,
)


class TestEntryLocation(unittest.TestCase):
    def test_long_pullback_entry(self):
        self.assertEqual(
            limit_entry(
                "LONG",
                100.0,
                90.0,
                0.5,
            ),
            95.0,
        )

    def test_short_pullback_entry(self):
        self.assertEqual(
            limit_entry(
                "SHORT",
                100.0,
                110.0,
                0.5,
            ),
            105.0,
        )

    def test_target_before_fill(self):
        setup = {
            "entry": 95.0,
            "stop": 90.0,
            "target": 110.0,
            "fraction": 0.5,
        }

        outcome = replay_limit_entry(
            "LONG",
            setup,
            [
                {
                    "timestamp": 1,
                    "high": 111.0,
                    "low": 99.0,
                }
            ],
        )

        self.assertEqual(
            outcome,
            "TARGET_BEFORE_FILL",
        )

    def test_fill_then_target(self):
        setup = {
            "entry": 95.0,
            "stop": 90.0,
            "target": 110.0,
            "fraction": 0.5,
        }

        outcome = replay_limit_entry(
            "LONG",
            setup,
            [
                {
                    "timestamp": 1,
                    "high": 100.0,
                    "low": 94.0,
                },
                {
                    "timestamp": 2,
                    "high": 111.0,
                    "low": 96.0,
                },
            ],
        )

        self.assertEqual(
            outcome,
            "TARGET_FIRST",
        )

    def test_fill_stop_same_bar_is_not_optimistic(self):
        setup = {
            "entry": 95.0,
            "stop": 90.0,
            "target": 110.0,
            "fraction": 0.5,
        }

        outcome = replay_limit_entry(
            "LONG",
            setup,
            [
                {
                    "timestamp": 1,
                    "high": 100.0,
                    "low": 89.0,
                }
            ],
        )

        self.assertEqual(
            outcome,
            "FILL_AND_STOP_SAME_BAR",
        )


if __name__ == "__main__":
    unittest.main()
