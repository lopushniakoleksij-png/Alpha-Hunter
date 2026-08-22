import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from restore_previous_snapshot import (
    fetch_latest_snapshot,
    main,
    restore,
    snapshot_path,
)


class TestFetchLatestSnapshot(
    unittest.TestCase
):

    @patch(
        "restore_previous_snapshot.requests.get"
    )
    def test_restores_payload(
        self,
        mocked_get,
    ):
        mocked_get.return_value = (
            SimpleNamespace(
                status_code=200,
                text="",
                json=lambda: [
                    {
                        "run_id":
                            "run-123",

                        "collected_at_utc":
                            "2026-08-16T09:00:00+00:00",

                        "payload": {
                            "symbols": [
                                {
                                    "symbol":
                                        "BTCUSDT"
                                }
                            ]
                        },
                    }
                ],
            )
        )

        settings = SimpleNamespace(
            url="https://example.supabase.co",
            key="secret",
            snapshot_table=
                "alpha_hunter_snapshots",
            timeout_seconds=15,
        )

        result = fetch_latest_snapshot(
            settings
        )

        self.assertEqual(
            result["run_id"],
            "run-123",
        )

        self.assertEqual(
            result[
                "collected_at_utc"
            ],
            "2026-08-16T09:00:00+00:00",
        )

        self.assertEqual(
            result["symbols"][0][
                "symbol"
            ],
            "BTCUSDT",
        )

    @patch(
        "restore_previous_snapshot.requests.get"
    )
    def test_empty_database_is_bootstrap(
        self,
        mocked_get,
    ):
        mocked_get.return_value = (
            SimpleNamespace(
                status_code=200,
                text="",
                json=lambda: [],
            )
        )

        settings = SimpleNamespace(
            url="https://example.supabase.co",
            key="secret",
            snapshot_table=
                "alpha_hunter_snapshots",
            timeout_seconds=15,
        )

        self.assertIsNone(
            fetch_latest_snapshot(
                settings
            )
        )

    @patch(
        "restore_previous_snapshot.requests.get"
    )
    def test_invalid_payload_fails(
        self,
        mocked_get,
    ):
        mocked_get.return_value = (
            SimpleNamespace(
                status_code=200,
                text="",
                json=lambda: [
                    {
                        "run_id":
                            "run-123",
                        "payload":
                            None,
                    }
                ],
            )
        )

        settings = SimpleNamespace(
            url="https://example.supabase.co",
            key="secret",
            snapshot_table=
                "alpha_hunter_snapshots",
            timeout_seconds=15,
        )

        with self.assertRaises(
            RuntimeError
        ):
            fetch_latest_snapshot(
                settings
            )


class TestRestoreWrite(
    unittest.TestCase
):

    def test_snapshot_path_uses_config(
        self,
    ):
        root = Path(
            "/tmp/alpha"
        )

        path = snapshot_path(
            {
                "snapshot_directory":
                    "data/snapshots"
            },
            root,
        )

        self.assertEqual(
            path,
            Path(
                "/tmp/alpha/"
                "data/snapshots/"
                "latest.json"
            ),
        )

    @patch(
        "restore_previous_snapshot.fetch_latest_snapshot"
    )
    def test_restore_writes_latest_json(
        self,
        mocked_fetch,
    ):
        mocked_fetch.return_value = {
            "run_id":
                "run-456",

            "collected_at_utc":
                "2026-08-16T10:00:00+00:00",

            "symbols": [
                {
                    "symbol":
                        "ETHUSDT"
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(
                tmp
            )

            path = restore(
                SimpleNamespace(),
                {
                    "snapshot_directory":
                        "data/snapshots"
                },
                root=root,
            )

            self.assertIsNotNone(
                path
            )

            self.assertTrue(
                path.exists()
            )

            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                payload[
                    "run_id"
                ],
                "run-456",
            )

            self.assertEqual(
                payload[
                    "symbols"
                ][0][
                    "symbol"
                ],
                "ETHUSDT",
            )


class TestCliSafety(
    unittest.TestCase
):

    @patch(
        "restore_previous_snapshot.restore"
    )
    @patch(
        "restore_previous_snapshot.load_config"
    )
    @patch(
        "restore_previous_snapshot.load_env_file"
    )
    def test_help_exits_without_side_effects(
        self,
        mocked_load_env_file,
        mocked_load_config,
        mocked_restore,
    ):
        with patch(
            "sys.stdout",
            new_callable=StringIO,
        ) as output:
            with self.assertRaises(
                SystemExit
            ) as raised:
                main([
                    "--help"
                ])

        self.assertEqual(
            raised.exception.code,
            0,
        )

        self.assertIn(
            "usage:",
            output.getvalue(),
        )

        mocked_load_env_file.assert_not_called()
        mocked_load_config.assert_not_called()
        mocked_restore.assert_not_called()


if __name__ == "__main__":
    unittest.main()
