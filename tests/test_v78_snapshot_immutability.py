import json
import unittest

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import v78_timing_rr_decay_shadow as v78


class FakeResponse:
    def __init__(
        self,
        status_code=200,
        payload=None,
        text="",
    ):
        self.status_code = status_code
        self._payload = (
            payload
            if payload is not None
            else []
        )
        self.text = text

    def json(self):
        return self._payload


def settings():
    return SimpleNamespace(
        url="https://example.supabase.co",
        key="test-key",
        timeout_seconds=5,
    )


class TestImmutableCompleteSnapshots(
    unittest.TestCase
):
    def test_complete_snapshot_cannot_be_downgraded(
        self,
    ):
        existing = {
            "snapshot_id": "snapshot-1",
            "episode_id": "episode-1",
            "phase": "EMERGING",
            "measurement_quality": "COMPLETE",
            "stop_distance_pct": 1.25,
        }

        incoming = {
            "snapshot_id": "snapshot-1",
            "episode_id": "episode-1",
            "phase": "EMERGING",
            "measurement_quality":
                "INSUFFICIENT_CANDLE_HISTORY",
            "stop_distance_pct": None,
        }

        with (
            patch(
                "v78_timing_rr_decay_shadow."
                "requests.get"
            ) as get_mock,
            patch(
                "v78_timing_rr_decay_shadow."
                "requests.post"
            ) as post_mock,
        ):
            get_mock.return_value = FakeResponse(
                200,
                [existing],
            )

            post_mock.return_value = FakeResponse(
                204,
            )

            saved = v78.upsert_rows(
                settings(),
                [incoming],
            )

        self.assertEqual(
            saved,
            0,
            (
                "A later incomplete calculation "
                "must not replace an existing "
                "COMPLETE snapshot"
            ),
        )

        post_mock.assert_not_called()

    def test_incomplete_snapshot_can_be_upgraded_to_complete(
        self,
    ):
        existing = {
            "snapshot_id": "snapshot-2",
            "episode_id": "episode-2",
            "phase": "EMERGING",
            "measurement_quality":
                "INSUFFICIENT_CANDLE_HISTORY",
        }

        incoming = {
            "snapshot_id": "snapshot-2",
            "episode_id": "episode-2",
            "phase": "EMERGING",
            "measurement_quality": "COMPLETE",
            "stop_distance_pct": 1.10,
        }

        with (
            patch(
                "v78_timing_rr_decay_shadow."
                "requests.get"
            ) as get_mock,
            patch(
                "v78_timing_rr_decay_shadow."
                "requests.post"
            ) as post_mock,
        ):
            get_mock.return_value = FakeResponse(
                200,
                [existing],
            )

            post_mock.return_value = FakeResponse(
                204,
            )

            saved = v78.upsert_rows(
                settings(),
                [incoming],
            )

        self.assertEqual(
            saved,
            1,
        )

        post_mock.assert_called_once()

        payload = json.loads(
            post_mock.call_args.kwargs["data"]
        )

        self.assertEqual(
            payload[0][
                "measurement_quality"
            ],
            "COMPLETE",
        )

    def test_reconstruction_writes_only_allowed_complete_rows(
        self,
    ):
        rows = [
            {
                "snapshot_id": "allowed-complete",
                "measurement_quality": "COMPLETE",
            },
            {
                "snapshot_id": "allowed-incomplete",
                "measurement_quality":
                    "INSUFFICIENT_CANDLE_HISTORY",
            },
            {
                "snapshot_id": "not-allowed",
                "measurement_quality": "COMPLETE",
            },
        ]

        existing = [
            {
                "snapshot_id": row["snapshot_id"],
                "measurement_quality":
                    "INSUFFICIENT_CANDLE_HISTORY",
            }
            for row in rows
        ]

        with (
            patch(
                "v78_timing_rr_decay_shadow."
                "requests.get"
            ) as get_mock,
            patch(
                "v78_timing_rr_decay_shadow."
                "requests.post"
            ) as post_mock,
        ):
            get_mock.return_value = FakeResponse(
                200,
                existing,
            )
            post_mock.return_value = FakeResponse(204)

            saved = v78.upsert_rows(
                settings(),
                rows,
                allowed_snapshot_ids={
                    "allowed-complete",
                    "allowed-incomplete",
                },
                require_complete=True,
            )

        self.assertEqual(saved, 1)
        payload = json.loads(
            post_mock.call_args.kwargs["data"]
        )
        self.assertEqual(
            [row["snapshot_id"] for row in payload],
            ["allowed-complete"],
        )


class FakeBitgetClient:
    def __init__(self):
        self.calls = []

    def _get(
        self,
        path,
        params,
    ):
        self.calls.append(
            (
                path,
                params,
            )
        )

        return []


class TestPhaseAnchoredHistory(
    unittest.TestCase
):
    def test_historical_loader_is_anchored_to_phase_time(
        self,
    ):
        loader = getattr(
            v78,
            "load_phase_candles",
            None,
        )

        self.assertTrue(
            callable(loader),
            (
                "V7.8 must provide a "
                "phase-time historical "
                "candle loader"
            ),
        )

        client = FakeBitgetClient()

        phase_at = datetime(
            2026,
            8,
            15,
            17,
            8,
            21,
            tzinfo=timezone.utc,
        )

        loader(
            client,
            "CYSUSDT",
            "usdt-futures",
            "15m",
            phase_at,
            15,
            120,
        )

        self.assertTrue(
            client.calls
        )

        path, params = (
            client.calls[0]
        )

        self.assertEqual(
            path,
            (
                "/api/v2/mix/market/"
                "history-candles"
            ),
        )

        self.assertEqual(
            params["symbol"],
            "CYSUSDT",
        )

        self.assertEqual(
            params["productType"],
            "usdt-futures",
        )

        self.assertEqual(
            params["granularity"],
            "15m",
        )

        phase_ms = int(
            phase_at.timestamp()
            * 1000
        )

        start_ms = int(
            params["startTime"]
        )

        end_ms = int(
            params["endTime"]
        )

        self.assertLessEqual(
            end_ms,
            phase_ms,
            (
                "Historical retrieval must "
                "not request candles after "
                "the phase timestamp"
            ),
        )

        required_history_ms = (
            120
            * 15
            * 60
            * 1000
        )

        self.assertGreaterEqual(
            phase_ms - start_ms,
            required_history_ms,
            (
                "Historical request must reach "
                "far enough behind phase_at "
                "to reconstruct the requested "
                "candle history"
            ),
        )


if __name__ == "__main__":
    unittest.main()
