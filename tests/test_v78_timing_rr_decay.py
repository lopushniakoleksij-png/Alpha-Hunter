from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from v78_timing_rr_decay_shadow import (
    MODEL_VERSION,
    apply_rr_decay,
    build_phase_row,
    phase_snapshot_id,
    rr_decay,
)

UTC = timezone.utc
DETECTED_AT = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)
EMERGING_AT = datetime(2026, 8, 15, 11, 0, tzinfo=UTC)
CONFIRMED_AT = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def candle(
    opened_at: datetime,
    high: float,
    low: float,
    close: float,
):
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
    as_of: datetime,
    timeframe_minutes: int,
    count: int = 30,
):
    start = as_of - timedelta(
        minutes=timeframe_minutes * count
    )

    rows = []

    for i in range(count):
        opened = start + timedelta(
            minutes=timeframe_minutes * i
        )

        drift = (i % 5) * 0.05

        rows.append(
            candle(
                opened,
                103.0 + drift,
                97.0 + drift,
                100.0 + drift,
            )
        )

    return rows


def episode():
    return SimpleNamespace(
        episode_id="v78-episode-001",
        symbol="TESTUSDT",
        path="REVERSAL",
        first_detected_at_utc=DETECTED_AT.isoformat(),
        first_detection_price=100.0,
    )


def state():
    return {
        "episode_id": "v78-episode-001",
        "symbol": "TESTUSDT",
        "path": "REVERSAL",
    }


class TestV78SnapshotIdentity(unittest.TestCase):

    def test_phase_snapshot_id_is_idempotent(self):
        first = phase_snapshot_id(
            "abc",
            "DETECTION",
        )

        second = phase_snapshot_id(
            "abc",
            "DETECTION",
        )

        self.assertEqual(first, second)

    def test_different_phases_have_different_ids(self):
        detection = phase_snapshot_id(
            "abc",
            "DETECTION",
        )

        emerging = phase_snapshot_id(
            "abc",
            "EMERGING",
        )

        self.assertNotEqual(
            detection,
            emerging,
        )


class TestV78RRDecay(unittest.TestCase):

    def test_positive_decay_means_rr_was_lost(self):
        self.assertAlmostEqual(
            rr_decay(5.0, 2.0),
            3.0,
        )

    def test_negative_decay_means_rr_improved(self):
        self.assertAlmostEqual(
            rr_decay(2.0, 5.0),
            -3.0,
        )

    def test_missing_rr_returns_none(self):
        self.assertIsNone(
            rr_decay(None, 5.0)
        )

        self.assertIsNone(
            rr_decay(5.0, None)
        )


class TestV78PhaseSemantics(unittest.TestCase):

    def test_detection_direction_is_retrospective(self):
        row = build_phase_row(
            episode=episode(),
            state=state(),
            phase="DETECTION",
            phase_at=DETECTED_AT,
            phase_price=100.0,
            confirmed_direction="LONG",
            confirmed_confidence=80.0,
            observed_direction_at_phase=None,
            observed_confidence_at_phase=None,
            move_consumed_pct=0.0,
            candles_15m_raw=history(
                DETECTED_AT,
                15,
            ),
            candles_1h_raw=history(
                DETECTED_AT,
                60,
            ),
            processed_at=CONFIRMED_AT,
        )

        self.assertIsNotNone(row)
        assert row is not None

        self.assertEqual(
            row["direction_source"],
            "RETROSPECTIVE_FIRST_CONFIRMED",
        )

        self.assertFalse(
            row["direction_available_at_phase"]
        )

        self.assertIsNone(
            row[
                "direction_consistent_with_confirmed"
            ]
        )

        self.assertFalse(
            row["trade_permission"]
        )

    def test_emerging_matching_direction_is_available(self):
        row = build_phase_row(
            episode=episode(),
            state=state(),
            phase="EMERGING",
            phase_at=EMERGING_AT,
            phase_price=101.0,
            confirmed_direction="LONG",
            confirmed_confidence=80.0,
            observed_direction_at_phase="LONG",
            observed_confidence_at_phase=62.0,
            move_consumed_pct=1.0,
            candles_15m_raw=history(
                EMERGING_AT,
                15,
            ),
            candles_1h_raw=history(
                EMERGING_AT,
                60,
            ),
            processed_at=CONFIRMED_AT,
        )

        self.assertIsNotNone(row)
        assert row is not None

        self.assertTrue(
            row["direction_available_at_phase"]
        )

        self.assertTrue(
            row[
                "direction_consistent_with_confirmed"
            ]
        )

        self.assertEqual(
            row["confidence"],
            62.0,
        )

    def test_emerging_wrong_direction_is_not_available(self):
        row = build_phase_row(
            episode=episode(),
            state=state(),
            phase="EMERGING",
            phase_at=EMERGING_AT,
            phase_price=101.0,
            confirmed_direction="LONG",
            confirmed_confidence=80.0,
            observed_direction_at_phase="SHORT",
            observed_confidence_at_phase=65.0,
            move_consumed_pct=-1.0,
            candles_15m_raw=history(
                EMERGING_AT,
                15,
            ),
            candles_1h_raw=history(
                EMERGING_AT,
                60,
            ),
            processed_at=CONFIRMED_AT,
        )

        self.assertIsNotNone(row)
        assert row is not None

        self.assertFalse(
            row["direction_available_at_phase"]
        )

        self.assertFalse(
            row[
                "direction_consistent_with_confirmed"
            ]
        )

    def test_confirmed_direction_is_live_available(self):
        row = build_phase_row(
            episode=episode(),
            state=state(),
            phase="CONFIRMED",
            phase_at=CONFIRMED_AT,
            phase_price=102.0,
            confirmed_direction="LONG",
            confirmed_confidence=80.0,
            observed_direction_at_phase="LONG",
            observed_confidence_at_phase=80.0,
            move_consumed_pct=2.0,
            candles_15m_raw=history(
                CONFIRMED_AT,
                15,
            ),
            candles_1h_raw=history(
                CONFIRMED_AT,
                60,
            ),
            processed_at=CONFIRMED_AT,
        )

        self.assertIsNotNone(row)
        assert row is not None

        self.assertEqual(
            row["direction_source"],
            "FIRST_CONFIRMED",
        )

        self.assertTrue(
            row["direction_available_at_phase"]
        )

        self.assertTrue(
            row[
                "direction_consistent_with_confirmed"
            ]
        )

    def test_move_consumed_is_preserved(self):
        row = build_phase_row(
            episode=episode(),
            state=state(),
            phase="CONFIRMED",
            phase_at=CONFIRMED_AT,
            phase_price=102.0,
            confirmed_direction="LONG",
            confirmed_confidence=80.0,
            observed_direction_at_phase="LONG",
            observed_confidence_at_phase=80.0,
            move_consumed_pct=2.75,
            candles_15m_raw=history(
                CONFIRMED_AT,
                15,
            ),
            candles_1h_raw=history(
                CONFIRMED_AT,
                60,
            ),
            processed_at=CONFIRMED_AT,
        )

        self.assertIsNotNone(row)
        assert row is not None

        self.assertEqual(
            row["move_consumed_pct"],
            2.75,
        )

    def test_minutes_from_detection_are_exact(self):
        row = build_phase_row(
            episode=episode(),
            state=state(),
            phase="CONFIRMED",
            phase_at=CONFIRMED_AT,
            phase_price=102.0,
            confirmed_direction="LONG",
            confirmed_confidence=80.0,
            observed_direction_at_phase="LONG",
            observed_confidence_at_phase=80.0,
            move_consumed_pct=2.0,
            candles_15m_raw=history(
                CONFIRMED_AT,
                15,
            ),
            candles_1h_raw=history(
                CONFIRMED_AT,
                60,
            ),
            processed_at=CONFIRMED_AT,
        )

        self.assertIsNotNone(row)
        assert row is not None

        self.assertEqual(
            row["minutes_from_detection"],
            120.0,
        )


class TestV78MeasurementQuality(unittest.TestCase):

    def test_insufficient_history_is_explicit(self):
        row = build_phase_row(
            episode=episode(),
            state=state(),
            phase="DETECTION",
            phase_at=DETECTED_AT,
            phase_price=100.0,
            confirmed_direction="LONG",
            confirmed_confidence=80.0,
            observed_direction_at_phase=None,
            observed_confidence_at_phase=None,
            move_consumed_pct=0.0,
            candles_15m_raw=[],
            candles_1h_raw=[],
            processed_at=CONFIRMED_AT,
        )

        self.assertIsNotNone(row)
        assert row is not None

        self.assertEqual(
            row["measurement_quality"],
            "INSUFFICIENT_CANDLE_HISTORY",
        )

        self.assertEqual(
            row["feasibility_status"],
            "INSUFFICIENT_HISTORY",
        )

        self.assertIsNone(
            row["rr_to_structure"]
        )

        self.assertFalse(
            row["rr5_possible"]
        )

    def test_future_candle_cannot_affect_phase_snapshot(self):
        c15 = history(
            DETECTED_AT,
            15,
        )

        c1h = history(
            DETECTED_AT,
            60,
        )

        c15.append(
            candle(
                DETECTED_AT + timedelta(minutes=1),
                500.0,
                1.0,
                250.0,
            )
        )

        c1h.append(
            candle(
                DETECTED_AT + timedelta(minutes=1),
                500.0,
                1.0,
                250.0,
            )
        )

        row = build_phase_row(
            episode=episode(),
            state=state(),
            phase="DETECTION",
            phase_at=DETECTED_AT,
            phase_price=100.0,
            confirmed_direction="LONG",
            confirmed_confidence=80.0,
            observed_direction_at_phase=None,
            observed_confidence_at_phase=None,
            move_consumed_pct=0.0,
            candles_15m_raw=c15,
            candles_1h_raw=c1h,
            processed_at=CONFIRMED_AT,
        )

        self.assertIsNotNone(row)
        assert row is not None

        self.assertLess(
            row["swing_high_15m"],
            500.0,
        )

        self.assertTrue(
            row["evidence"][
                "future_candle_leakage_blocked"
            ]
        )


class TestV78DecayChain(unittest.TestCase):

    def test_apply_rr_decay_orders_phases(self):
        rows = [
            {
                "phase": "CONFIRMED",
                "rr_to_structure": 1.0,
            },
            {
                "phase": "DETECTION",
                "rr_to_structure": 5.0,
            },
            {
                "phase": "EMERGING",
                "rr_to_structure": 3.0,
            },
        ]

        result = apply_rr_decay(rows)

        self.assertEqual(
            [
                row["phase"]
                for row in result
            ],
            [
                "DETECTION",
                "EMERGING",
                "CONFIRMED",
            ],
        )

    def test_confirmed_decay_from_detection(self):
        rows = [
            {
                "phase": "DETECTION",
                "rr_to_structure": 5.0,
            },
            {
                "phase": "EMERGING",
                "rr_to_structure": 3.0,
            },
            {
                "phase": "CONFIRMED",
                "rr_to_structure": 1.0,
            },
        ]

        result = apply_rr_decay(rows)

        confirmed = result[-1]

        self.assertEqual(
            confirmed["previous_phase"],
            "EMERGING",
        )

        self.assertAlmostEqual(
            confirmed[
                "rr_decay_from_previous"
            ],
            2.0,
        )

        self.assertAlmostEqual(
            confirmed[
                "rr_decay_from_detection"
            ],
            4.0,
        )


class TestV78Safety(unittest.TestCase):

    def test_model_version_is_shadow(self):
        self.assertEqual(
            MODEL_VERSION,
            "7.8-timing-rr-decay-v1",
        )


if __name__ == "__main__":
    unittest.main()
