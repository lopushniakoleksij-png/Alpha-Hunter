import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from v710_direction_transition_ledger import (
    build_transition_row,
    build_transition_rows,
    insert_transition_rows,
    score_leader,
    transition_snapshot_id,
)


def source_row(
    *,
    episode_id="ep-1",
    direction="UNKNOWN",
    long_score=3.5,
    short_score=1.5,
):
    return {
        "shadow_id":
            "source-shadow-1",

        "episode_id":
            episode_id,

        "symbol":
            "AAAUSDT",

        "path":
            "REVERSAL",

        "evaluated_at_utc":
            "2026-08-16T08:00:00+00:00",

        "market_price":
            1.25,

        "direction":
            direction,

        "confidence":
            0.0,

        "long_score":
            long_score,

        "short_score":
            short_score,

        "ema_15m_bias":
            "BULLISH",

        "ema_1h_bias":
            "NEUTRAL",

        "momentum_15m":
            1.2,

        "momentum_1h":
            0.4,

        "structure_15m":
            "BULLISH",

        "structure_1h":
            "NEUTRAL",

        "model_version":
            "7.6-direction-shadow-v1",

        "evidence": {
            "signals": [
                "EMA15_BULL"
            ],

            "lifecycle_state":
                "UNDER_SURVEILLANCE",

            "v74_rank":
                2,

            "v74_score":
                7.1,

            "v741_shadow_score":
                7.4,

            "first_detection_price":
                1.20,

            "max_up_excursion_pct":
                2.0,

            "max_down_excursion_pct":
                -0.5,
        },
    }


class TestScoreLeader(unittest.TestCase):
    def test_long_leader(self):
        self.assertEqual(
            score_leader(
                3.0,
                1.0,
            ),
            "LONG",
        )

    def test_short_leader(self):
        self.assertEqual(
            score_leader(
                1.0,
                3.0,
            ),
            "SHORT",
        )

    def test_tie(self):
        self.assertEqual(
            score_leader(
                2.0,
                2.0,
            ),
            "TIE",
        )


class TestTransitionPayload(unittest.TestCase):
    def test_unknown_verdict_preserves_score_leader(self):
        row = build_transition_row(
            source_row(
                direction="UNKNOWN",
                long_score=3.5,
                short_score=1.5,
            ),
            "run-123",
            production_version=
                "production-hardening-v1",
            captured_at=datetime(
                2026,
                8,
                16,
                8,
                1,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            row[
                "direction_verdict"
            ],
            "UNKNOWN",
        )

        self.assertEqual(
            row[
                "score_leader"
            ],
            "LONG",
        )

        self.assertEqual(
            row[
                "score_margin"
            ],
            2.0,
        )

    def test_trade_permission_is_always_false(self):
        row = build_transition_row(
            source_row(),
            "run-123",
        )

        self.assertFalse(
            row[
                "trade_permission"
            ]
        )

        self.assertEqual(
            row[
                "capture_mode"
            ],
            "SHADOW",
        )

    def test_snapshot_id_is_deterministic(self):
        first = (
            transition_snapshot_id(
                "run-123",
                "ep-1",
                "2026-08-16T08:00:00+00:00",
                "shadow-1",
            )
        )

        second = (
            transition_snapshot_id(
                "run-123",
                "ep-1",
                "2026-08-16T08:00:00+00:00",
                "shadow-1",
            )
        )

        self.assertEqual(
            first,
            second,
        )

    def test_missing_production_run_id_fails(self):
        with self.assertRaises(
            ValueError
        ):
            build_transition_row(
                source_row(),
                "",
            )

    def test_duplicate_episode_in_same_run_fails(self):
        rows = [
            source_row(
                episode_id="ep-1"
            ),
            source_row(
                episode_id="ep-1"
            ),
        ]

        with self.assertRaises(
            ValueError
        ):
            build_transition_rows(
                rows,
                "run-123",
            )


class TestInsertSafety(unittest.TestCase):
    @patch(
        "v710_direction_transition_ledger.requests.post"
    )
    def test_insert_is_append_only_post(
        self,
        mocked_post,
    ):
        mocked_post.return_value = (
            SimpleNamespace(
                status_code=201,
                text="",
            )
        )

        settings = (
            SimpleNamespace(
                url=(
                    "https://example.supabase.co"
                ),
                key="test-key",
                timeout_seconds=12,
            )
        )

        rows = [
            build_transition_row(
                source_row(),
                "run-123",
            )
        ]

        saved = (
            insert_transition_rows(
                settings,
                rows,
            )
        )

        self.assertEqual(
            saved,
            1,
        )

        self.assertEqual(
            mocked_post.call_count,
            1,
        )

        kwargs = (
            mocked_post.call_args.kwargs
        )

        self.assertNotIn(
            "params",
            kwargs,
        )

        self.assertEqual(
            kwargs[
                "headers"
            ][
                "Prefer"
            ],
            "return=minimal",
        )

        self.assertNotIn(
            "merge-duplicates",
            kwargs[
                "headers"
            ][
                "Prefer"
            ],
        )
