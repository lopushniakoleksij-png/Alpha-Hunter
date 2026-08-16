import unittest

from v710_execution_replay_diagnostic import (
    replay,
    target_for_5r,
)


class TestReplayOrdering(unittest.TestCase):
    def test_long_target_first(self):
        result, _ = replay(
            "LONG",
            95.0,
            110.0,
            [
                {
                    "timestamp": 1,
                    "high": 111.0,
                    "low": 99.0,
                }
            ],
        )

        self.assertEqual(
            result,
            "TARGET_FIRST",
        )

    def test_long_stop_first(self):
        result, _ = replay(
            "LONG",
            95.0,
            110.0,
            [
                {
                    "timestamp": 1,
                    "high": 102.0,
                    "low": 94.0,
                }
            ],
        )

        self.assertEqual(
            result,
            "STOP_FIRST",
        )

    def test_short_target_first(self):
        result, _ = replay(
            "SHORT",
            105.0,
            90.0,
            [
                {
                    "timestamp": 1,
                    "high": 101.0,
                    "low": 89.0,
                }
            ],
        )

        self.assertEqual(
            result,
            "TARGET_FIRST",
        )

    def test_ambiguous_same_bar(self):
        result, _ = replay(
            "LONG",
            95.0,
            110.0,
            [
                {
                    "timestamp": 1,
                    "high": 111.0,
                    "low": 94.0,
                }
            ],
        )

        self.assertEqual(
            result,
            "AMBIGUOUS_SAME_BAR",
        )

    def test_unresolved(self):
        result, _ = replay(
            "LONG",
            95.0,
            110.0,
            [
                {
                    "timestamp": 1,
                    "high": 103.0,
                    "low": 98.0,
                }
            ],
        )

        self.assertEqual(
            result,
            "UNRESOLVED",
        )


class TestTargetSelection(unittest.TestCase):
    def test_nearest_level_that_reaches_5r(self):
        source, target, value = (
            target_for_5r(
                "LONG",
                100.0,
                1.0,
                [
                    (
                        "1H_12",
                        103.0,
                    ),
                    (
                        "1H_24",
                        106.0,
                    ),
                    (
                        "1H_48",
                        110.0,
                    ),
                ],
            )
        )

        self.assertEqual(
            source,
            "1H_24",
        )

        self.assertEqual(
            target,
            106.0,
        )

        self.assertGreaterEqual(
            value,
            5.0,
        )

    def test_no_fabricated_target(self):
        source, target, value = (
            target_for_5r(
                "LONG",
                100.0,
                2.0,
                [
                    (
                        "1H_12",
                        104.0,
                    ),
                ],
            )
        )

        self.assertIsNone(
            source
        )

        self.assertIsNone(
            target
        )

        self.assertIsNone(
            value
        )


if __name__ == "__main__":
    unittest.main()
