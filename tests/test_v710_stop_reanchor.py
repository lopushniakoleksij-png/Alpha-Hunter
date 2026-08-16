import unittest
from datetime import datetime, timedelta, timezone

from v710_stop_reanchor_diagnostic import (
    MAX_STOP_ATR,
    MAX_STOP_PCT,
    admissible_stop,
    build_reanchor_candidates,
    closed_before,
)


def candles_15m(
    lows=None,
    highs=None,
):
    count = 20

    lows = lows or [99.5] * count
    highs = highs or [100.5] * count

    rows = []

    for i in range(count):
        rows.append(
            {
                "timestamp": i * 900_000,
                "open": 100.0,
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": 100.0,
            }
        )

    return rows


def candles_1h(
    count=24,
    high=110.0,
    low=90.0,
):
    return [
        {
            "timestamp": i * 3_600_000,
            "open": 100.0,
            "high": float(high),
            "low": float(low),
            "close": 100.0,
        }
        for i in range(count)
    ]


class TestStopAdmissibility(unittest.TestCase):
    def test_accepts_stop_inside_both_limits(self):
        self.assertTrue(
            admissible_stop(
                MAX_STOP_PCT,
                MAX_STOP_ATR,
            )
        )

    def test_rejects_pct_too_wide(self):
        self.assertFalse(
            admissible_stop(
                MAX_STOP_PCT + 0.01,
                1.0,
            )
        )

    def test_rejects_atr_too_wide(self):
        self.assertFalse(
            admissible_stop(
                1.0,
                MAX_STOP_ATR + 0.01,
            )
        )

    def test_requires_both_measurements(self):
        self.assertFalse(
            admissible_stop(
                None,
                1.0,
            )
        )

        self.assertFalse(
            admissible_stop(
                1.0,
                None,
            )
        )


class TestClosedCandleProtection(unittest.TestCase):
    def test_excludes_candle_not_closed_at_checkpoint(self):
        checkpoint = datetime(
            2026,
            8,
            16,
            12,
            0,
            tzinfo=timezone.utc,
        )

        rows = [
            {
                "timestamp": int(
                    (
                        checkpoint
                        - timedelta(minutes=30)
                    ).timestamp()
                    * 1000
                )
            },
            {
                "timestamp": int(
                    (
                        checkpoint
                        - timedelta(minutes=15)
                    ).timestamp()
                    * 1000
                )
            },
            {
                "timestamp": int(
                    checkpoint.timestamp()
                    * 1000
                )
            },
        ]

        result = closed_before(
            rows,
            checkpoint,
            15,
        )

        self.assertEqual(
            len(result),
            2,
        )


class TestReanchorCandidateConstruction(unittest.TestCase):
    def test_builds_admissible_5r_candidate(self):
        candidates = (
            build_reanchor_candidates(
                "LONG",
                100.0,
                candles_15m(),
                candles_1h(),
            )
        )

        self.assertTrue(
            candidates
        )

        first = candidates[0]

        self.assertLessEqual(
            first["stop_pct"],
            MAX_STOP_PCT,
        )

        self.assertLessEqual(
            first["stop_atr"],
            MAX_STOP_ATR,
        )

        self.assertGreaterEqual(
            first["rr"],
            5.0,
        )

    def test_rejects_stop_that_is_too_wide(self):
        lows = [95.0] * 20

        candidates = (
            build_reanchor_candidates(
                "LONG",
                100.0,
                candles_15m(
                    lows=lows,
                ),
                candles_1h(),
            )
        )

        self.assertEqual(
            candidates,
            [],
        )

    def test_prefers_widest_admissible_structure(self):
        lows = [99.5] * 20

        lows[-6] = 97.0
        lows[-4] = 98.6
        lows[-3] = 99.2
        lows[-2] = 99.6
        lows[-1] = 99.6

        candidates = (
            build_reanchor_candidates(
                "LONG",
                100.0,
                candles_15m(
                    lows=lows,
                ),
                candles_1h(
                    high=112.0,
                ),
            )
        )

        self.assertTrue(
            candidates
        )

        self.assertEqual(
            candidates[0]["window"],
            4,
        )

        self.assertLessEqual(
            candidates[0]["stop_pct"],
            MAX_STOP_PCT,
        )

        self.assertGreaterEqual(
            candidates[0]["rr"],
            5.0,
        )


if __name__ == "__main__":
    unittest.main()
