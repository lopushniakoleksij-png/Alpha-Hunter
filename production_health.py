from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.env import load_env_file


RUN_TABLE = "alpha_hunter_production_runs"
STEP_TABLE = "alpha_hunter_production_steps"


class ProductionHealthError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProductionHealthClient:
    url: str
    key: str
    timeout_seconds: int = 15

    @classmethod
    def from_environment(
        cls,
        project_root: Path,
    ) -> "ProductionHealthClient | None":

        load_env_file(
            project_root / ".env",
            override=False,
        )

        url = (
            os.getenv(
                "SUPABASE_URL",
                "",
            )
            .strip()
            .rstrip("/")
        )

        key = os.getenv(
            "SUPABASE_SERVICE_ROLE_KEY",
            "",
        ).strip()

        if not url or not key:
            return None

        return cls(
            url=url,
            key=key,
        )

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey":
                self.key,

            "Authorization":
                f"Bearer {self.key}",

            "Content-Type":
                "application/json",

            "Prefer":
                (
                    "resolution=merge-duplicates,"
                    "return=minimal"
                ),
        }

    def upsert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        on_conflict: str,
    ) -> None:

        if not rows:
            return

        response = requests.post(
            (
                f"{self.url}"
                f"/rest/v1/{table}"
            ),
            params={
                "on_conflict":
                    on_conflict,
            },
            headers=self.headers,
            data=json.dumps(
                rows,
                separators=(",", ":"),
            ),
            timeout=
                self.timeout_seconds,
        )

        if response.status_code not in {
            200,
            201,
            204,
        }:
            raise ProductionHealthError(
                (
                    f"Supabase production-health "
                    f"upsert failed for {table}: "
                    f"HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )
            )


def status_counts(
    report: dict[str, Any],
) -> dict[str, int]:

    steps = report.get(
        "steps",
        [],
    )

    counts = {
        "step_count":
            len(steps),

        "passed_steps":
            0,

        "failed_steps":
            0,

        "timeout_steps":
            0,

        "skipped_steps":
            0,
    }

    for step in steps:
        status = str(
            step.get(
                "status",
                "",
            )
        ).upper()

        if status == "PASS":
            counts[
                "passed_steps"
            ] += 1

        elif status == "FAILED":
            counts[
                "failed_steps"
            ] += 1

        elif status == "TIMEOUT":
            counts[
                "timeout_steps"
            ] += 1

        elif status == "SKIPPED":
            counts[
                "skipped_steps"
            ] += 1

    return counts


def build_run_row(
    report: dict[str, Any],
) -> dict[str, Any]:

    counts = status_counts(
        report
    )

    invariants = report.get(
        "invariants",
        {},
    )

    return {
        "production_run_id":
            report.get(
                "production_run_id"
            ),

        "production_version":
            report.get(
                "production_version"
            ),

        "mode":
            report.get(
                "mode"
            ),

        "started_at_utc":
            report.get(
                "started_at_utc"
            ),

        "finished_at_utc":
            report.get(
                "finished_at_utc"
            ),

        "duration_seconds":
            report.get(
                "duration_seconds"
            ),

        "overall_status":
            report.get(
                "overall_status",
                "RUNNING",
            ),

        "code_commit":
            report.get(
                "code_commit"
            ),

        "git_branch":
            report.get(
                "git_branch"
            ),

        "host_name":
            socket.gethostname(),

        "pid":
            report.get(
                "pid"
            ),

        "automatic_trade_execution":
            bool(
                invariants.get(
                    "automatic_trade_execution",
                    False,
                )
            ),

        "shadow_trade_permission":
            bool(
                invariants.get(
                    "shadow_trade_permission",
                    False,
                )
            ),

        **counts,

        "payload":
            report,
    }


def build_step_rows(
    report: dict[str, Any],
) -> list[dict[str, Any]]:

    production_run_id = (
        report.get(
            "production_run_id"
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    for step_order, step in enumerate(
        report.get(
            "steps",
            [],
        ),
        start=1,
    ):
        rows.append({
            "production_run_id":
                production_run_id,

            "step_order":
                step_order,

            "step_name":
                step.get(
                    "name"
                ),

            "script":
                step.get(
                    "script"
                ),

            "status":
                step.get(
                    "status"
                ),

            "exit_code":
                step.get(
                    "exit_code"
                ),

            "timeout_seconds":
                step.get(
                    "timeout_seconds"
                ),

            "started_at_utc":
                step.get(
                    "started_at_utc"
                ),

            "finished_at_utc":
                step.get(
                    "finished_at_utc"
                ),

            "duration_seconds":
                step.get(
                    "duration_seconds"
                ),

            "error":
                step.get(
                    "error"
                ),
        })

    return rows


def persist_report(
    client: ProductionHealthClient,
    report: dict[str, Any],
) -> None:

    run_row = build_run_row(
        report
    )

    client.upsert(
        RUN_TABLE,
        [
            run_row,
        ],
        on_conflict=
            "production_run_id",
    )

    step_rows = build_step_rows(
        report
    )

    if step_rows:
        client.upsert(
            STEP_TABLE,
            step_rows,
            on_conflict=(
                "production_run_id,"
                "step_order"
            ),
        )


def safe_persist_report(
    client: ProductionHealthClient | None,
    report: dict[str, Any],
) -> tuple[bool, str | None]:

    if client is None:
        return (
            False,
            "NOT_CONFIGURED",
        )

    try:
        persist_report(
            client,
            report,
        )

    except Exception as exc:
        return (
            False,
            str(exc),
        )

    return (
        True,
        None,
    )
