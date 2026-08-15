from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import v79_missed_mover_recall_auditor as audit

UTC = timezone.utc

T0 = datetime(
    2026, 8, 15, 10, 0,
    tzinfo=UTC,
)

T1 = T0 + timedelta(hours=1)
T2 = T0 + timedelta(hours=2)


def ledger_row(
    when: datetime,
    *,
    move: float,
    eligible: bool = False,
    selected: bool = False,
    price: float = 1.0,
):
    return {
        "symbol": "TESTUSDT",
        "hour_bucket_utc":
            when.isoformat(),
        "last_price":
            price,
        "change_24h_pct":
            move,
        "prefilter_eligible":
            eligible,
        "deep_scan_selected":
            selected,
        "selection_run_id":
            "run-1" if selected else None,
    }


class TestV79Pagination(unittest.TestCase):

    def test_paginated_loader_collects_all_pages(self):
        first_page = [
            {"id": i}
            for i in range(500)
        ]

        second_page = [
            {"id": 500 + i}
            for i in range(17)
        ]

        with patch.object(
            audit,
            "get_rows",
            side_effect=[
                first_page,
                second_page,
            ],
        ) as mocked:

            rows = audit.get_rows_paginated(
                settings=SimpleNamespace(),
                table="test_table",
                params={
                    "select": "*",
                    "order": "id.asc",
                },
                page_size=500,
            )

        self.assertEqual(
            len(rows),
            517,
        )

        self.assertEqual(
            mocked.call_count,
            2,
        )

        first_params = (
            mocked.call_args_list[0]
            .args[2]
        )

        second_params = (
            mocked.call_args_list[1]
            .args[2]
        )

        self.assertEqual(
            first_params["offset"],
            "0",
        )

        self.assertEqual(
            second_params["offset"],
            "500",
        )


class TestV79HistorySemantics(unittest.TestCase):

    def test_threshold_first_seen(self):
        history = [
            ledger_row(
                T0,
                move=2.0,
            ),
            ledger_row(
                T1,
                move=5.5,
            ),
            ledger_row(
                T2,
                move=8.0,
            ),
        ]

        self.assertEqual(
            audit.threshold_first_seen(
                history,
                5.0,
            ),
            T1,
        )

    def test_first_true_time(self):
        history = [
            ledger_row(
                T0,
                move=1.0,
                eligible=False,
            ),
            ledger_row(
                T1,
                move=2.0,
                eligible=True,
            ),
        ]

        self.assertEqual(
            audit.first_true_time(
                history,
                "prefilter_eligible",
            ),
            T1,
        )

    def test_short_history_is_partial(self):
        history = [
            ledger_row(
                T0,
                move=1.0,
            )
        ]

        self.assertEqual(
            audit.measurement_quality(
                history
            ),
            "PARTIAL_HISTORY",
        )

    def test_complete_24h_history(self):
        history = [
            ledger_row(
                T0 + timedelta(hours=i),
                move=float(i),
            )
            for i in range(24)
        ]

        self.assertEqual(
            audit.measurement_quality(
                history
            ),
            "FORWARD_24H_COMPLETE",
        )


class TestV79FailureAttribution(unittest.TestCase):

    def test_partial_history_blocks_diagnosis(self):
        stage, reason = (
            audit.determine_failure(
                quality="PARTIAL_HISTORY",
                eligible_before=True,
                selected_before=True,
                episode={"episode_id": "e1"},
                direction_state={
                    "first_confirmed_at_utc":
                        T1.isoformat(),
                },
                frozen_confirmed_direction=
                    "LONG",
                mover_direction="UP",
                rr_confirmed=8.0,
            )
        )

        self.assertEqual(
            stage,
            "DATA",
        )

        self.assertEqual(
            reason,
            "INSUFFICIENT_LEDGER_HISTORY",
        )

    def test_eligible_not_selected(self):
        stage, reason = (
            audit.determine_failure(
                quality=
                    "FORWARD_24H_COMPLETE",
                eligible_before=True,
                selected_before=False,
                episode=None,
                direction_state=None,
                frozen_confirmed_direction=None,
                mover_direction="UP",
                rr_confirmed=None,
            )
        )

        self.assertEqual(
            stage,
            "SELECTION",
        )

        self.assertEqual(
            reason,
            "ELIGIBLE_NOT_DEEP_SCANNED",
        )

    def test_wrong_frozen_direction(self):
        stage, reason = (
            audit.determine_failure(
                quality=
                    "FORWARD_24H_COMPLETE",
                eligible_before=True,
                selected_before=True,
                episode={
                    "episode_id": "e1"
                },
                direction_state={
                    "first_confirmed_at_utc":
                        T1.isoformat(),
                    "current_direction":
                        "LONG",
                },
                frozen_confirmed_direction=
                    "SHORT",
                mover_direction="UP",
                rr_confirmed=8.0,
            )
        )

        self.assertEqual(
            stage,
            "DIRECTION",
        )

        self.assertEqual(
            reason,
            "WRONG_DIRECTION",
        )

    def test_latest_direction_cannot_rewrite_history(self):
        stage, reason = (
            audit.determine_failure(
                quality=
                    "FORWARD_24H_COMPLETE",
                eligible_before=True,
                selected_before=True,
                episode={
                    "episode_id": "e1"
                },
                direction_state={
                    "first_confirmed_at_utc":
                        T1.isoformat(),
                    "current_direction":
                        "SHORT",
                    "last_direction":
                        "SHORT",
                },
                frozen_confirmed_direction=
                    "LONG",
                mover_direction="UP",
                rr_confirmed=8.0,
            )
        )

        self.assertEqual(
            stage,
            "NONE",
        )

        self.assertEqual(
            reason,
            "SHADOW_FEASIBLE_NOT_EXECUTED",
        )

    def test_confirmed_direction_unavailable(self):
        stage, reason = (
            audit.determine_failure(
                quality=
                    "FORWARD_24H_COMPLETE",
                eligible_before=True,
                selected_before=True,
                episode={
                    "episode_id": "e1"
                },
                direction_state={
                    "first_confirmed_at_utc":
                        T1.isoformat(),
                },
                frozen_confirmed_direction=None,
                mover_direction="UP",
                rr_confirmed=8.0,
            )
        )

        self.assertEqual(
            stage,
            "DIRECTION",
        )

        self.assertEqual(
            reason,
            "CONFIRMED_DIRECTION_UNAVAILABLE",
        )

    def test_rr_below_five_is_execution_failure(self):
        stage, reason = (
            audit.determine_failure(
                quality=
                    "FORWARD_24H_COMPLETE",
                eligible_before=True,
                selected_before=True,
                episode={
                    "episode_id": "e1"
                },
                direction_state={
                    "first_confirmed_at_utc":
                        T1.isoformat(),
                },
                frozen_confirmed_direction=
                    "LONG",
                mover_direction="UP",
                rr_confirmed=2.5,
            )
        )

        self.assertEqual(
            stage,
            "EXECUTION",
        )

        self.assertEqual(
            reason,
            "RR_BELOW_5_AT_CONFIRMATION",
        )


class TestV79FrozenDirectionInAuditRow(
    unittest.TestCase
):

    def test_build_row_uses_timing_confirmed_direction(self):

        history = [
            ledger_row(
                T0 + timedelta(hours=i),
                move=(
                    1.0
                    if i < 5
                    else 6.0
                ),
                eligible=True,
                selected=True,
                price=100.0 + i,
            )
            for i in range(24)
        ]

        episode = {
            "episode_id": "episode-1",
            "symbol": "TESTUSDT",
            "first_detected_at_utc":
                T0.isoformat(),
        }

        direction_state = {
            "episode_id": "episode-1",
            "current_direction": "SHORT",
            "last_direction": "SHORT",
            "direction_state":
                "LOST_CONFIRMATION",
            "first_confirmed_at_utc":
                T1.isoformat(),
        }

        timing_index = {
            "episode-1": {
                "DETECTION": {
                    "rr_to_structure": 7.0,
                },
                "EMERGING": {
                    "rr_to_structure": 6.0,
                },
                "CONFIRMED": {
                    "direction": "LONG",
                    "rr_to_structure": 5.5,
                },
            }
        }

        row = audit.build_audit_row(
            symbol="TESTUSDT",
            history=history,
            latest=history[-1],
            threshold=5.0,
            episodes=[episode],
            direction_states={
                "episode-1":
                    direction_state
            },
            timing_index=
                timing_index,
            audited_at=
                T0
                + timedelta(hours=24),
        )

        self.assertIsNotNone(row)
        assert row is not None

        self.assertEqual(
            row["confirmed_direction"],
            "LONG",
        )

        self.assertEqual(
            row["direction_state"],
            "LOST_CONFIRMATION",
        )

        self.assertEqual(
            row["primary_failure_stage"],
            "NONE",
        )

        self.assertEqual(
            row["primary_failure_reason"],
            "SHADOW_FEASIBLE_NOT_EXECUTED",
        )

        self.assertFalse(
            row["trade_permission"]
        )


if __name__ == "__main__":
    unittest.main()
