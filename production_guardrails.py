from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from production_health import ProductionHealthClient


ROOT = Path(__file__).resolve().parent

UNIVERSE_TABLE = "alpha_hunter_universe_hourly"

SNAPSHOT_MAX_AGE_SECONDS = 600
MIN_CONTRACT_COUNT = 100
MIN_TICKER_COVERAGE = 0.95
MIN_SCAN_SUCCESS_RATIO = 0.90
MIN_LEDGER_COVERAGE = 0.98

UTC = timezone.utc


class GuardrailError(RuntimeError):
    pass


def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_time(
    value: Any,
) -> datetime | None:

    if not value:
        return None

    try:
        text = str(value).strip()

        if text.endswith("Z"):
            text = (
                text[:-1]
                + "+00:00"
            )

        parsed = datetime.fromisoformat(
            text
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=UTC
            )

        return parsed.astimezone(
            UTC
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def hour_bucket(
    value: datetime,
) -> datetime:

    return value.astimezone(
        UTC
    ).replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def make_check(
    name: str,
    status: str,
    detail: str,
    *,
    critical: bool,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:

    return {
        "name": name,
        "status": status,
        "critical": critical,
        "detail": detail,
        "metrics": metrics or {},
    }


def load_snapshot(
    path: Path,
) -> dict[str, Any]:

    if not path.exists():
        raise GuardrailError(
            f"Snapshot does not exist: {path}"
        )

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:
        raise GuardrailError(
            f"Snapshot JSON invalid: {exc}"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise GuardrailError(
            "Snapshot root must be an object"
        )

    return payload


def validate_snapshot(
    snapshot: dict[str, Any],
    *,
    current_time: datetime,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:

    checks: list[
        dict[str, Any]
    ] = []

    collected_at = parse_time(
        snapshot.get(
            "collected_at_utc"
        )
    )

    run_id = str(
        snapshot.get(
            "run_id",
            "",
        )
        or ""
    ).strip()

    if collected_at is None:
        checks.append(
            make_check(
                "snapshot_timestamp",
                "FAIL",
                "collected_at_utc missing or invalid",
                critical=True,
            )
        )

        snapshot_age = None

    else:
        snapshot_age = (
            current_time
            - collected_at
        ).total_seconds()

        if snapshot_age < -30:
            status = "FAIL"
            detail = (
                "snapshot timestamp is "
                "in the future"
            )

        elif (
            snapshot_age
            > SNAPSHOT_MAX_AGE_SECONDS
        ):
            status = "FAIL"
            detail = (
                f"snapshot age "
                f"{snapshot_age:.1f}s "
                f"> "
                f"{SNAPSHOT_MAX_AGE_SECONDS}s"
            )

        else:
            status = "PASS"
            detail = (
                f"snapshot age "
                f"{snapshot_age:.1f}s"
            )

        checks.append(
            make_check(
                "snapshot_freshness",
                status,
                detail,
                critical=True,
                metrics={
                    "age_seconds":
                        snapshot_age,
                },
            )
        )

    checks.append(
        make_check(
            "snapshot_run_id",
            (
                "PASS"
                if run_id
                else "FAIL"
            ),
            (
                f"run_id={run_id}"
                if run_id
                else "run_id missing"
            ),
            critical=True,
        )
    )

    universe = snapshot.get(
        "universe",
        {},
    )

    if not isinstance(
        universe,
        dict,
    ):
        universe = {}

    total_contracts = int(
        universe.get(
            "total_contracts",
            0,
        )
        or 0
    )

    ticker_count = int(
        universe.get(
            "ticker_count",
            0,
        )
        or 0
    )

    eligible_count = int(
        universe.get(
            "eligible_count",
            0,
        )
        or 0
    )

    selected_count = int(
        universe.get(
            "selected_count",
            0,
        )
        or 0
    )

    selected_symbols = (
        universe.get(
            "selected_symbols",
            [],
        )
        or []
    )

    symbols = (
        snapshot.get(
            "symbols",
            [],
        )
        or []
    )

    if not isinstance(
        selected_symbols,
        list,
    ):
        selected_symbols = []

    if not isinstance(
        symbols,
        list,
    ):
        symbols = []

    contract_ok = (
        total_contracts
        >= MIN_CONTRACT_COUNT
    )

    checks.append(
        make_check(
            "contract_universe_size",
            (
                "PASS"
                if contract_ok
                else "FAIL"
            ),
            (
                f"contracts="
                f"{total_contracts}"
            ),
            critical=True,
            metrics={
                "total_contracts":
                    total_contracts,
            },
        )
    )

    ticker_coverage = (
        ticker_count
        / total_contracts
        if total_contracts > 0
        else 0.0
    )

    checks.append(
        make_check(
            "ticker_coverage",
            (
                "PASS"
                if ticker_coverage
                >= MIN_TICKER_COVERAGE
                else "FAIL"
            ),
            (
                f"ticker coverage="
                f"{ticker_coverage:.1%}"
            ),
            critical=True,
            metrics={
                "ticker_count":
                    ticker_count,

                "total_contracts":
                    total_contracts,

                "coverage":
                    ticker_coverage,
            },
        )
    )

    selected_consistent = (
        selected_count
        == len(selected_symbols)
        == len(symbols)
    )

    checks.append(
        make_check(
            "selected_symbol_consistency",
            (
                "PASS"
                if selected_consistent
                else "FAIL"
            ),
            (
                f"selected_count="
                f"{selected_count}, "
                f"selected_symbols="
                f"{len(selected_symbols)}, "
                f"result_rows="
                f"{len(symbols)}"
            ),
            critical=True,
        )
    )

    unique_selected = {
        str(symbol).upper()
        for symbol
        in selected_symbols
        if symbol
    }

    checks.append(
        make_check(
            "selected_symbol_uniqueness",
            (
                "PASS"
                if len(unique_selected)
                == len(selected_symbols)
                else "FAIL"
            ),
            (
                f"unique="
                f"{len(unique_selected)}, "
                f"listed="
                f"{len(selected_symbols)}"
            ),
            critical=True,
        )
    )

    successful_rows = [
        row
        for row in symbols
        if (
            isinstance(row, dict)
            and "error" not in row
        )
    ]

    scan_success_ratio = (
        len(successful_rows)
        / len(symbols)
        if symbols
        else 0.0
    )

    checks.append(
        make_check(
            "deep_scan_success_ratio",
            (
                "PASS"
                if scan_success_ratio
                >= MIN_SCAN_SUCCESS_RATIO
                else "FAIL"
            ),
            (
                f"deep-scan success="
                f"{scan_success_ratio:.1%}"
            ),
            critical=True,
            metrics={
                "successful":
                    len(successful_rows),

                "attempted":
                    len(symbols),

                "ratio":
                    scan_success_ratio,
            },
        )
    )

    private_account = snapshot.get(
        "private_account",
        {},
    )

    if not isinstance(
        private_account,
        dict,
    ):
        private_account = {}

    private_status = str(
        private_account.get(
            "status",
            "UNKNOWN",
        )
    ).upper()

    checks.append(
        make_check(
            "bitget_private_api",
            (
                "PASS"
                if private_status
                == "CONNECTED"
                else "WARN"
            ),
            (
                f"private API="
                f"{private_status}"
            ),
            critical=False,
        )
    )

    context = {
        "run_id":
            run_id,

        "collected_at":
            collected_at,

        "snapshot_age_seconds":
            snapshot_age,

        "total_contracts":
            total_contracts,

        "ticker_count":
            ticker_count,

        "eligible_count":
            eligible_count,

        "selected_count":
            selected_count,

        "private_api_status":
            private_status,
    }

    return (
        checks,
        context,
    )


def get_universe_rows(
    client: ProductionHealthClient,
    *,
    bucket: datetime,
) -> list[dict[str, Any]]:

    response = requests.get(
        (
            f"{client.url}"
            f"/rest/v1/"
            f"{UNIVERSE_TABLE}"
        ),
        params={
            "hour_bucket_utc":
                (
                    f"eq."
                    f"{bucket.isoformat()}"
                ),

            "select":
                (
                    "observed_at_utc,"
                    "hour_bucket_utc,"
                    "symbol,"
                    "prefilter_eligible,"
                    "deep_scan_selected,"
                    "selection_snapshot_at_utc,"
                    "selection_run_id,"
                    "source,"
                    "measurement_quality,"
                    "trade_permission"
                ),

            "order":
                "symbol.asc",

            "limit":
                "2000",
        },
        headers={
            "apikey":
                client.key,

            "Authorization":
                f"Bearer {client.key}",
        },
        timeout=
            client.timeout_seconds,
    )

    if response.status_code != 200:
        raise GuardrailError(
            (
                "Universe guardrail query failed: "
                f"HTTP "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )
        )

    payload = response.json()

    if not isinstance(
        payload,
        list,
    ):
        raise GuardrailError(
            "Universe query did not return a list"
        )

    return payload


def validate_universe_ledger(
    rows: list[dict[str, Any]],
    *,
    snapshot_context:
        dict[str, Any],
    current_time: datetime,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:

    checks: list[
        dict[str, Any]
    ] = []

    total_contracts = int(
        snapshot_context.get(
            "total_contracts",
            0,
        )
        or 0
    )

    snapshot_run_id = str(
        snapshot_context.get(
            "run_id",
            "",
        )
        or ""
    )

    collected_at = (
        snapshot_context.get(
            "collected_at"
        )
    )

    expected_bucket = (
        hour_bucket(
            collected_at
        )
        if isinstance(
            collected_at,
            datetime,
        )
        else None
    )

    if not rows:
        checks.append(
            make_check(
                "universe_ledger_presence",
                "FAIL",
                "no universe ledger rows",
                critical=True,
            )
        )

        return (
            checks,
            {
                "ledger_rows": 0,
                "capture_mode":
                    "MISSING",
            },
        )

    checks.append(
        make_check(
            "universe_ledger_presence",
            "PASS",
            f"rows={len(rows)}",
            critical=True,
        )
    )

    coverage = (
        len(rows)
        / total_contracts
        if total_contracts > 0
        else 0.0
    )

    checks.append(
        make_check(
            "universe_ledger_coverage",
            (
                "PASS"
                if coverage
                >= MIN_LEDGER_COVERAGE
                else "FAIL"
            ),
            (
                f"ledger coverage="
                f"{coverage:.1%}"
            ),
            critical=True,
            metrics={
                "rows":
                    len(rows),

                "total_contracts":
                    total_contracts,

                "coverage":
                    coverage,
            },
        )
    )

    symbols = [
        str(
            row.get(
                "symbol",
                "",
            )
        ).upper()
        for row in rows
    ]

    unique_symbols = {
        symbol
        for symbol in symbols
        if symbol
    }

    checks.append(
        make_check(
            "universe_symbol_uniqueness",
            (
                "PASS"
                if len(unique_symbols)
                == len(rows)
                else "FAIL"
            ),
            (
                f"unique="
                f"{len(unique_symbols)}, "
                f"rows="
                f"{len(rows)}"
            ),
            critical=True,
        )
    )

    buckets = {
        str(
            row.get(
                "hour_bucket_utc",
                "",
            )
        )
        for row in rows
    }

    bucket_match = False

    if expected_bucket is not None:
        parsed_buckets = {
            parse_time(value)
            for value in buckets
        }

        bucket_match = (
            parsed_buckets
            == {
                expected_bucket
            }
        )

    checks.append(
        make_check(
            "universe_hour_bucket",
            (
                "PASS"
                if bucket_match
                else "FAIL"
            ),
            (
                f"expected="
                f"{expected_bucket}, "
                f"observed="
                f"{sorted(buckets)}"
            ),
            critical=True,
        )
    )

    ledger_run_ids = {
        str(
            row.get(
                "selection_run_id",
                "",
            )
            or ""
        )
        for row in rows
    }

    ledger_run_ids.discard(
        ""
    )

    single_selection_context = (
        len(ledger_run_ids)
        == 1
    )

    checks.append(
        make_check(
            "ledger_selection_context",
            (
                "PASS"
                if single_selection_context
                else "FAIL"
            ),
            (
                f"selection_run_ids="
                f"{sorted(ledger_run_ids)}"
            ),
            critical=True,
        )
    )

    ledger_run_id = (
        next(
            iter(
                ledger_run_ids
            )
        )
        if single_selection_context
        else None
    )

    if (
        ledger_run_id
        and ledger_run_id
        == snapshot_run_id
    ):
        capture_mode = (
            "FIRST_CAPTURE_MATCH"
        )

        checks.append(
            make_check(
                "ledger_capture_mode",
                "PASS",
                (
                    "ledger selection context "
                    "matches current scan"
                ),
                critical=False,
            )
        )

    elif ledger_run_id:
        capture_mode = (
            "SAME_HOUR_IMMUTABLE_REUSE"
        )

        checks.append(
            make_check(
                "ledger_capture_mode",
                "WARN",
                (
                    "ledger belongs to an "
                    "earlier scan in the same "
                    "hour; immutable first-hour "
                    "evidence preserved"
                ),
                critical=False,
                metrics={
                    "snapshot_run_id":
                        snapshot_run_id,

                    "ledger_run_id":
                        ledger_run_id,
                },
            )
        )

    else:
        capture_mode = "INVALID"

        checks.append(
            make_check(
                "ledger_capture_mode",
                "FAIL",
                "selection_run_id unavailable",
                critical=True,
            )
        )

    observed_times = [
        parsed
        for parsed in (
            parse_time(
                row.get(
                    "observed_at_utc"
                )
            )
            for row in rows
        )
        if parsed is not None
    ]

    if (
        len(observed_times)
        != len(rows)
    ):
        checks.append(
            make_check(
                "ledger_timestamps",
                "FAIL",
                (
                    "one or more ledger "
                    "timestamps invalid"
                ),
                critical=True,
            )
        )

    else:
        earliest = min(
            observed_times
        )

        latest = max(
            observed_times
        )

        spread_seconds = (
            latest
            - earliest
        ).total_seconds()

        same_hour = (
            expected_bucket
            is not None
            and hour_bucket(
                earliest
            )
            == expected_bucket
            and hour_bucket(
                latest
            )
            == expected_bucket
        )

        if capture_mode == (
            "FIRST_CAPTURE_MATCH"
        ):
            age_seconds = (
                current_time
                - latest
            ).total_seconds()

            fresh = (
                -30
                <= age_seconds
                <= SNAPSHOT_MAX_AGE_SECONDS
            )

        else:
            age_seconds = (
                current_time
                - latest
            ).total_seconds()

            fresh = same_hour

        checks.append(
            make_check(
                "ledger_freshness",
                (
                    "PASS"
                    if fresh
                    else "FAIL"
                ),
                (
                    f"ledger age="
                    f"{age_seconds:.1f}s, "
                    f"spread="
                    f"{spread_seconds:.3f}s"
                ),
                critical=True,
                metrics={
                    "age_seconds":
                        age_seconds,

                    "spread_seconds":
                        spread_seconds,
                },
            )
        )

    bad_source = [
        row
        for row in rows
        if row.get(
            "source"
        )
        != "BITGET_ALL_TICKERS"
    ]

    checks.append(
        make_check(
            "ledger_source",
            (
                "PASS"
                if not bad_source
                else "FAIL"
            ),
            (
                "source=BITGET_ALL_TICKERS"
                if not bad_source
                else (
                    f"invalid source rows="
                    f"{len(bad_source)}"
                )
            ),
            critical=True,
        )
    )

    bad_quality = [
        row
        for row in rows
        if row.get(
            "measurement_quality"
        )
        != "HOURLY_TICKER_SNAPSHOT"
    ]

    checks.append(
        make_check(
            "ledger_measurement_quality",
            (
                "PASS"
                if not bad_quality
                else "FAIL"
            ),
            (
                "quality=HOURLY_TICKER_SNAPSHOT"
                if not bad_quality
                else (
                    f"invalid quality rows="
                    f"{len(bad_quality)}"
                )
            ),
            critical=True,
        )
    )

    permission_rows = [
        row
        for row in rows
        if row.get(
            "trade_permission"
        )
        is not False
    ]

    checks.append(
        make_check(
            "v79_trade_permission",
            (
                "PASS"
                if not permission_rows
                else "FAIL"
            ),
            (
                "all V7.9 rows have "
                "trade_permission=false"
                if not permission_rows
                else (
                    "V7.9 permission violation "
                    f"rows="
                    f"{len(permission_rows)}"
                )
            ),
            critical=True,
        )
    )

    selected_rows = sum(
        1
        for row in rows
        if row.get(
            "deep_scan_selected"
        )
        is True
    )

    eligible_rows = sum(
        1
        for row in rows
        if row.get(
            "prefilter_eligible"
        )
        is True
    )

    if capture_mode == (
        "FIRST_CAPTURE_MATCH"
    ):
        expected_selected = int(
            snapshot_context.get(
                "selected_count",
                0,
            )
            or 0
        )

        expected_eligible = int(
            snapshot_context.get(
                "eligible_count",
                0,
            )
            or 0
        )

        selection_counts_ok = (
            selected_rows
            == expected_selected
            and eligible_rows
            == expected_eligible
        )

        checks.append(
            make_check(
                "ledger_scan_count_consistency",
                (
                    "PASS"
                    if selection_counts_ok
                    else "FAIL"
                ),
                (
                    f"selected="
                    f"{selected_rows}/"
                    f"{expected_selected}, "
                    f"eligible="
                    f"{eligible_rows}/"
                    f"{expected_eligible}"
                ),
                critical=True,
            )
        )

    else:
        checks.append(
            make_check(
                "ledger_scan_count_consistency",
                "WARN",
                (
                    "not compared because "
                    "immutable same-hour ledger "
                    "belongs to an earlier scan"
                ),
                critical=False,
            )
        )

    metrics = {
        "ledger_rows":
            len(rows),

        "unique_symbols":
            len(unique_symbols),

        "coverage":
            coverage,

        "capture_mode":
            capture_mode,

        "ledger_selection_run_id":
            ledger_run_id,

        "current_scan_run_id":
            snapshot_run_id,

        "eligible_rows":
            eligible_rows,

        "selected_rows":
            selected_rows,
    }

    return (
        checks,
        metrics,
    )


def overall_status(
    checks: list[dict[str, Any]],
) -> str:

    critical_failures = [
        check
        for check in checks
        if (
            check.get("critical")
            and check.get("status")
            == "FAIL"
        )
    ]

    if critical_failures:
        return "FAIL"

    warnings = [
        check
        for check in checks
        if check.get("status")
        == "WARN"
    ]

    if warnings:
        return "DEGRADED"

    return "PASS"


def evaluate(
    *,
    snapshot_path: Path,
    client: ProductionHealthClient,
    current_time: datetime | None = None,
) -> dict[str, Any]:

    current_time = (
        current_time
        or now_utc()
    )

    snapshot = load_snapshot(
        snapshot_path
    )

    (
        snapshot_checks,
        context,
    ) = validate_snapshot(
        snapshot,
        current_time=current_time,
    )

    collected_at = context.get(
        "collected_at"
    )

    if not isinstance(
        collected_at,
        datetime,
    ):
        return {
            "status":
                overall_status(
                    snapshot_checks
                ),

            "checked_at_utc":
                current_time.isoformat(),

            "snapshot_path":
                str(snapshot_path),

            "checks":
                snapshot_checks,

            "metrics":
                {},
        }

    bucket = hour_bucket(
        collected_at
    )

    rows = get_universe_rows(
        client,
        bucket=bucket,
    )

    (
        ledger_checks,
        ledger_metrics,
    ) = validate_universe_ledger(
        rows,
        snapshot_context=context,
        current_time=current_time,
    )

    checks = (
        snapshot_checks
        + ledger_checks
    )

    return {
        "status":
            overall_status(
                checks
            ),

        "checked_at_utc":
            current_time.isoformat(),

        "snapshot_path":
            str(snapshot_path),

        "scan_run_id":
            context.get(
                "run_id"
            ),

        "hour_bucket_utc":
            bucket.isoformat(),

        "checks":
            checks,

        "metrics":
            {
                **context,
                **ledger_metrics,
            },
    }


def print_report(
    result: dict[str, Any],
) -> None:

    print()
    print("=" * 100)
    print(
        "ALPHA HUNTER P0-3 "
        "PRODUCTION DATA GUARDRAILS"
    )
    print("=" * 100)

    for check in result.get(
        "checks",
        [],
    ):
        print(
            f"{check['status']:<8} "
            f"{check['name']:<34} "
            f"{check['detail']}"
        )

    print()
    print(
        "Overall guardrail status:",
        result.get(
            "status"
        ),
    )

    metrics = result.get(
        "metrics",
        {},
    )

    print(
        "Ledger capture mode:",
        metrics.get(
            "capture_mode",
            "UNKNOWN",
        ),
    )

    print(
        "Current scan run ID:",
        metrics.get(
            "current_scan_run_id",
            result.get(
                "scan_run_id"
            ),
        ),
    )

    print(
        "Ledger selection run ID:",
        metrics.get(
            "ledger_selection_run_id"
        ),
    )

    print("=" * 100)


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--snapshot",
        default=(
            "data/snapshots/"
            "latest.json"
        ),
    )

    args = parser.parse_args()

    client = (
        ProductionHealthClient
        .from_environment(
            ROOT
        )
    )

    if client is None:
        raise SystemExit(
            "Supabase health client "
            "not configured"
        )

    result = evaluate(
        snapshot_path=(
            ROOT
            / args.snapshot
        ),
        client=client,
    )

    print_report(
        result
    )

    if result["status"] == "FAIL":
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
