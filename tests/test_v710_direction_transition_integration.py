import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from v76_direction_shadow import (
    persist_direction_outputs,
    transition_run_context,
)


class TestTransitionRunContext(unittest.TestCase):
    def test_production_context_uses_runner_environment(self):
        timestamp = datetime(
            2026,
            8,
            16,
            8,
            0,
            tzinfo=timezone.utc,
        )

        with patch.dict(
            "os.environ",
            {
                "ALPHA_HUNTER_PRODUCTION_RUN_ID":
                    "prod-run-123",

                "ALPHA_HUNTER_PRODUCTION_VERSION":
                    "production-hardening-v1",
            },
            clear=False,
        ):
            run_id, version = (
                transition_run_context(
                    timestamp
                )
            )

        self.assertEqual(
            run_id,
            "prod-run-123",
        )

        self.assertEqual(
            version,
            "production-hardening-v1",
        )

    def test_manual_context_is_still_immutable(self):
        timestamp = datetime(
            2026,
            8,
            16,
            8,
            0,
            1,
            123456,
            tzinfo=timezone.utc,
        )

        with patch.dict(
            "os.environ",
            {},
            clear=True,
        ):
            run_id, version = (
                transition_run_context(
                    timestamp
                )
            )

        self.assertTrue(
            run_id.startswith(
                "manual-v76-"
            )
        )

        self.assertEqual(
            version,
            "manual-v76-shadow",
        )


class TestPersistenceOrdering(unittest.TestCase):
    @patch(
        "v76_direction_shadow.save_direction_states"
    )
    @patch(
        "v76_direction_shadow.save_rows"
    )
    @patch(
        "v76_direction_shadow.insert_transition_rows"
    )
    @patch(
        "v76_direction_shadow.build_transition_rows"
    )
    def test_immutable_ledger_is_saved_first(
        self,
        mocked_build,
        mocked_insert,
        mocked_save_rows,
        mocked_save_states,
    ):
        calls = []

        mocked_build.return_value = [
            {
                "snapshot_id":
                    "snapshot-1",

                "trade_permission":
                    False,
            }
        ]

        mocked_insert.side_effect = (
            lambda *args, **kwargs:
                calls.append(
                    "transition"
                )
                or 1
        )

        mocked_save_rows.side_effect = (
            lambda *args, **kwargs:
                calls.append(
                    "shadow"
                )
                or 1
        )

        mocked_save_states.side_effect = (
            lambda *args, **kwargs:
                calls.append(
                    "state"
                )
                or 1
        )

        settings = SimpleNamespace()

        result = (
            persist_direction_outputs(
                settings,
                [
                    {
                        "episode_id":
                            "ep-1",
                    }
                ],
                [
                    {
                        "episode_id":
                            "ep-1",
                    }
                ],
                production_run_id=
                    "prod-run-123",
                production_version=
                    "production-hardening-v1",
                captured_at=datetime(
                    2026,
                    8,
                    16,
                    8,
                    0,
                    tzinfo=timezone.utc,
                ),
            )
        )

        self.assertEqual(
            calls,
            [
                "transition",
                "shadow",
                "state",
            ],
        )

        self.assertEqual(
            result,
            (
                1,
                1,
                1,
            ),
        )

    @patch(
        "v76_direction_shadow.save_direction_states"
    )
    @patch(
        "v76_direction_shadow.save_rows"
    )
    @patch(
        "v76_direction_shadow.insert_transition_rows"
    )
    @patch(
        "v76_direction_shadow.build_transition_rows"
    )
    def test_ledger_failure_blocks_mutable_overwrite(
        self,
        mocked_build,
        mocked_insert,
        mocked_save_rows,
        mocked_save_states,
    ):
        mocked_build.return_value = [
            {
                "snapshot_id":
                    "snapshot-1",

                "trade_permission":
                    False,
            }
        ]

        mocked_insert.side_effect = (
            RuntimeError(
                "immutable ledger failed"
            )
        )

        with self.assertRaises(
            RuntimeError
        ):
            persist_direction_outputs(
                SimpleNamespace(),
                [
                    {
                        "episode_id":
                            "ep-1",
                    }
                ],
                [
                    {
                        "episode_id":
                            "ep-1",
                    }
                ],
                production_run_id=
                    "prod-run-123",
                production_version=
                    "production-hardening-v1",
                captured_at=datetime(
                    2026,
                    8,
                    16,
                    8,
                    0,
                    tzinfo=timezone.utc,
                ),
            )

        mocked_save_rows.assert_not_called()
        mocked_save_states.assert_not_called()


if __name__ == "__main__":
    unittest.main()
