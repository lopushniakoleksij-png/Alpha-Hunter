import unittest

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import v78_timing_rr_decay_shadow as v78


class FakeBitgetClient:
    def candles(
        self,
        *args,
        **kwargs,
    ):
        # Existing V7.8 rolling path.
        # This keeps the current implementation runnable
        # while the test proves phase loader wiring is absent.
        return []


class TestPhaseHistoryWiring(unittest.TestCase):
    def test_each_phase_uses_its_own_phase_timestamp(self):
        detection_at = datetime(
            2026, 8, 15, 12, 0,
            tzinfo=timezone.utc,
        )

        emerging_at = datetime(
            2026, 8, 15, 13, 0,
            tzinfo=timezone.utc,
        )

        confirmed_at = datetime(
            2026, 8, 15, 14, 0,
            tzinfo=timezone.utc,
        )

        episode = SimpleNamespace(
            episode_id="episode-1",
            symbol="TESTUSDT",
            first_detected_at_utc=
                detection_at.isoformat(),
            first_detection_price=100.0,
            path="test",
        )

        state = {
            "episode_id": "episode-1",
            "symbol": "TESTUSDT",
            "first_emerging_at_utc":
                emerging_at.isoformat(),
            "price_at_emerging": 101.0,
            "first_confirmed_at_utc":
                confirmed_at.isoformat(),
            "price_at_confirmed": 102.0,
            "move_at_emerging_pct": 1.0,
            "move_at_confirmed_pct": 2.0,
            "path": "test",
        }

        settings = SimpleNamespace(
            url="https://example.supabase.co",
            key="test-key",
            timeout_seconds=5,
        )

        config = {
            "product_type": "usdt-futures",
            "request_timeout_seconds": 12,
            "max_retries": 3,
        }

        def confirmation(
            _settings,
            _episode_id,
            at,
        ):
            return {
                "direction": "LONG",
                "confidence": 90.0,
                "at": at.isoformat(),
            }

        def phase_row(**kwargs):
            return {
                "snapshot_id":
                    f"snapshot-{kwargs['phase']}",
                "episode_id": "episode-1",
                "symbol": "TESTUSDT",
                "phase": kwargs["phase"],
                "rr_to_structure": 5.0,
                "rr3_possible": True,
                "rr5_possible": True,
                "rr10_possible": False,
                "direction_available_at_phase":
                    kwargs["phase"] != "DETECTION",
            }

        with (
            patch.object(
                v78,
                "load_env_file",
            ),
            patch.object(
                v78,
                "load_config",
                return_value=config,
            ),
            patch.object(
                v78.SupabaseConfig,
                "from_environment",
                return_value=settings,
            ),
            patch.object(
                v78,
                "load_direction_states",
                return_value={
                    "episode-1": state,
                },
            ),
            patch.object(
                v78,
                "load_state",
                return_value=[episode],
            ),
            patch.object(
                v78,
                "load_existing_snapshot_rows",
                return_value={},
            ),
            patch.object(
                v78,
                "confirmation_shadow",
                side_effect=confirmation,
            ),
            patch.object(
                v78.BitgetClient,
                "from_environment",
                return_value=FakeBitgetClient(),
            ),
            patch.object(
                v78,
                "build_phase_row",
                side_effect=phase_row,
            ),
            patch.object(
                v78,
                "upsert_rows",
                return_value=0,
            ),
            patch.object(
                v78,
                "load_phase_candles",
                return_value=[],
            ) as history_mock,
        ):
            result = v78.main()

        self.assertEqual(
            result,
            0,
        )

        # Two timeframes for each of three phases.
        self.assertEqual(
            history_mock.call_count,
            6,
            (
                "V7.8 must load independent phase-at "
                "history for DETECTION, EMERGING "
                "and CONFIRMED"
            ),
        )

        calls = history_mock.call_args_list

        expected = [
            ("15m", detection_at, 15),
            ("1H", detection_at, 60),
            ("15m", emerging_at, 15),
            ("1H", emerging_at, 60),
            ("15m", confirmed_at, 15),
            ("1H", confirmed_at, 60),
        ]

        actual = [
            (
                call.args[3],
                call.args[4],
                call.args[5],
            )
            for call in calls
        ]

        self.assertEqual(
            actual,
            expected,
            (
                "Each timeframe must be anchored "
                "to the timestamp of the phase "
                "being reconstructed"
            ),
        )


if __name__ == "__main__":
    unittest.main()
