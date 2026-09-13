from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import production_guardrails as guard


UTC = timezone.utc
T0 = datetime(
    2026, 8, 15, 20, 34, 0,
    tzinfo=UTC,
)
NOW = T0 + timedelta(minutes=1)


def snapshot(
    *,
    run_id: str = "scan-current",
    collected_at: datetime = T0,
    total_contracts: int = 200,
    ticker_count: int = 200,
    eligible_count: int = 2,
    selected_count: int = 2,
    selected_symbols=None,
    result_rows=None,
    private_status: str = "CONNECTED",
):
    if selected_symbols is None:
        selected_symbols = [
            "AAAUSDT",
            "BBBUSDT",
        ]

    if result_rows is None:
        result_rows = [
            {
                "symbol": "AAAUSDT",
            },
            {
                "symbol": "BBBUSDT",
            },
        ]

    return {
        "run_id":
            run_id,

        "collected_at_utc":
            collected_at.isoformat(),

        "universe": {
            "total_contracts":
                total_contracts,

            "ticker_count":
                ticker_count,

            "eligible_count":
                eligible_count,

            "selected_count":
                selected_count,

            "selected_symbols":
                selected_symbols,
        },

        "symbols":
            result_rows,

        "private_account": {
            "status":
                private_status,
        },
    }


def context_for(
    payload,
    *,
    current_time=NOW,
):
    checks, context = (
        guard.validate_snapshot(
            payload,
            current_time=current_time,
        )
    )

    critical_failures = [
        check
        for check in checks
        if (
            check["critical"]
            and check["status"]
            == "FAIL"
        )
    ]

    if critical_failures:
        raise AssertionError(
            critical_failures
        )

    return context


def ledger_rows(
    *,
    count: int = 200,
    selection_run_id: str = "scan-current",
    observed_at: datetime = T0
        + timedelta(seconds=30),
    bucket: datetime | None = None,
    permission_violation: bool = False,
):
    if bucket is None:
        bucket = guard.hour_bucket(
            T0
        )

    rows = []

    for index in range(count):
        rows.append({
            "observed_at_utc":
                observed_at.isoformat(),

            "hour_bucket_utc":
                bucket.isoformat(),

            "symbol":
                f"SYM{index:03d}USDT",

            "prefilter_eligible":
                index < 2,

            "deep_scan_selected":
                index < 2,

            "selection_snapshot_at_utc":
                T0.isoformat(),

            "selection_run_id":
                selection_run_id,

            "source":
                "BITGET_ALL_TICKERS",

            "measurement_quality":
                "HOURLY_TICKER_SNAPSHOT",

            "trade_permission":
                (
                    True
                    if (
                        permission_violation
                        and index == 0
                    )
                    else False
                ),
        })

    return rows


def check_by_name(
    checks,
    name,
):
    return next(
        check
        for check in checks
        if check["name"] == name
    )


class TestSnapshotGuardrails(
    unittest.TestCase
):

    def test_fresh_snapshot_passes_critical_checks(
        self,
    ):
        checks, _ = guard.validate_snapshot(
            snapshot(),
            current_time=NOW,
        )

        critical_failures = [
            check
            for check in checks
            if (
                check["critical"]
                and check["status"]
                == "FAIL"
            )
        ]

        self.assertEqual(
            critical_failures,
            [],
        )

        self.assertEqual(
            guard.overall_status(
                checks
            ),
            "PASS",
        )

    def test_stale_snapshot_fails(
        self,
    ):
        old = (
            NOW
            - timedelta(
                seconds=
                    guard
                    .SNAPSHOT_MAX_AGE_SECONDS
                    + 1
            )
        )

        checks, _ = guard.validate_snapshot(
            snapshot(
                collected_at=old
            ),
            current_time=NOW,
        )

        freshness = check_by_name(
            checks,
            "snapshot_freshness",
        )

        self.assertEqual(
            freshness["status"],
            "FAIL",
        )

        self.assertEqual(
            guard.overall_status(
                checks
            ),
            "FAIL",
        )

    def test_selected_symbol_mismatch_fails(
        self,
    ):
        payload = snapshot(
            selected_count=2,
            selected_symbols=[
                "AAAUSDT",
            ],
        )

        checks, _ = guard.validate_snapshot(
            payload,
            current_time=NOW,
        )

        consistency = check_by_name(
            checks,
            "selected_symbol_consistency",
        )

        self.assertEqual(
            consistency["status"],
            "FAIL",
        )

    def test_private_api_warning_is_noncritical(
        self,
    ):
        checks, _ = guard.validate_snapshot(
            snapshot(
                private_status=
                    "DISCONNECTED"
            ),
            current_time=NOW,
        )

        private = check_by_name(
            checks,
            "bitget_private_api",
        )

        self.assertEqual(
            private["status"],
            "WARN",
        )

        self.assertFalse(
            private["critical"]
        )

        self.assertEqual(
            guard.overall_status(
                checks
            ),
            "DEGRADED",
        )


class TestUniverseLedgerGuardrails(
    unittest.TestCase
):

    def test_first_capture_matches_current_scan(
        self,
    ):
        context = context_for(
            snapshot()
        )

        checks, metrics = (
            guard.validate_universe_ledger(
                ledger_rows(),
                snapshot_context=
                    context,
                current_time=NOW,
            )
        )

        self.assertEqual(
            metrics["capture_mode"],
            "FIRST_CAPTURE_MATCH",
        )

        self.assertEqual(
            guard.overall_status(
                checks
            ),
            "PASS",
        )

        count_check = check_by_name(
            checks,
            "ledger_scan_count_consistency",
        )

        self.assertEqual(
            count_check["status"],
            "PASS",
        )

    def test_same_hour_immutable_reuse_is_degraded_not_failed(
        self,
    ):
        context = context_for(
            snapshot(
                run_id="scan-new"
            )
        )

        checks, metrics = (
            guard.validate_universe_ledger(
                ledger_rows(
                    selection_run_id=
                        "scan-first-in-hour"
                ),
                snapshot_context=
                    context,
                current_time=NOW,
            )
        )

        self.assertEqual(
            metrics["capture_mode"],
            "SAME_HOUR_IMMUTABLE_REUSE",
        )

        capture = check_by_name(
            checks,
            "ledger_capture_mode",
        )

        self.assertEqual(
            capture["status"],
            "WARN",
        )

        self.assertEqual(
            guard.overall_status(
                checks
            ),
            "DEGRADED",
        )

        critical_failures = [
            check
            for check in checks
            if (
                check["critical"]
                and check["status"]
                == "FAIL"
            )
        ]

        self.assertEqual(
            critical_failures,
            [],
        )

    def test_low_ledger_coverage_fails(
        self,
    ):
        context = context_for(
            snapshot()
        )

        checks, _ = (
            guard.validate_universe_ledger(
                ledger_rows(
                    count=100
                ),
                snapshot_context=
                    context,
                current_time=NOW,
            )
        )

        coverage = check_by_name(
            checks,
            "universe_ledger_coverage",
        )

        self.assertEqual(
            coverage["status"],
            "FAIL",
        )

        self.assertEqual(
            guard.overall_status(
                checks
            ),
            "FAIL",
        )

    def test_duplicate_ledger_symbol_fails(
        self,
    ):
        context = context_for(
            snapshot()
        )

        rows = ledger_rows()

        rows[-1]["symbol"] = (
            rows[0]["symbol"]
        )

        checks, _ = (
            guard.validate_universe_ledger(
                rows,
                snapshot_context=
                    context,
                current_time=NOW,
            )
        )

        unique = check_by_name(
            checks,
            "universe_symbol_uniqueness",
        )

        self.assertEqual(
            unique["status"],
            "FAIL",
        )

    def test_trade_permission_violation_fails(
        self,
    ):
        context = context_for(
            snapshot()
        )

        checks, _ = (
            guard.validate_universe_ledger(
                ledger_rows(
                    permission_violation=
                        True
                ),
                snapshot_context=
                    context,
                current_time=NOW,
            )
        )

        permission = check_by_name(
            checks,
            "v79_trade_permission",
        )

        self.assertEqual(
            permission["status"],
            "FAIL",
        )

        self.assertTrue(
            permission["critical"]
        )

        self.assertEqual(
            guard.overall_status(
                checks
            ),
            "FAIL",
        )

    def test_missing_selection_context_fails(
        self,
    ):
        context = context_for(
            snapshot()
        )

        rows = ledger_rows()

        for row in rows:
            row[
                "selection_run_id"
            ] = None

        checks, metrics = (
            guard.validate_universe_ledger(
                rows,
                snapshot_context=
                    context,
                current_time=NOW,
            )
        )

        selection = check_by_name(
            checks,
            "ledger_selection_context",
        )

        capture = check_by_name(
            checks,
            "ledger_capture_mode",
        )

        self.assertEqual(
            selection["status"],
            "FAIL",
        )

        self.assertEqual(
            capture["status"],
            "FAIL",
        )

        self.assertEqual(
            metrics["capture_mode"],
            "INVALID",
        )

        self.assertEqual(
            guard.overall_status(
                checks
            ),
            "FAIL",
        )


if __name__ == "__main__":
    unittest.main()
