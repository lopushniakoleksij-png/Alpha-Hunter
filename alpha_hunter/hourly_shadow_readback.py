"""Read-only PostgREST query contract for the isolated hourly scoring successor.

Accepts an injected GET-only reader, not credentials, a HTTP session or a writer.
Never substitutes an older complete snapshot for a broken latest RENDER_CRON
parent and never triggers a new market scan. Validates newest-head stability.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from alpha_hunter.big_mover_evidence import CORE_FEATURE_COLUMNS
from alpha_hunter.hourly_shadow_score import HourlyScoringBlocked

Parent = dict[str, Any]
ReadRows = Callable[[str, dict[str, str]], list[dict[str, Any]]]

TABLE_PARENT = "alpha_hunter_snapshots"
TABLE_CHILD = "alpha_hunter_symbol_snapshots"
TABLE_FEATURE = "alpha_hunter_signal_features"
EXACT_RUN_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_SYMBOLS = 2000


def _list_of_rows(rows: Any, *, name: str, maximum: int) -> list[dict[str, Any]]:
    if (
        not isinstance(rows, list)
        or len(rows) > maximum
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise HourlyScoringBlocked(f"{name}: malformed or truncated readback")
    return rows


def read_latest_canonical_run(read_get: ReadRows) -> tuple[Parent, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return a stable latest canonical parent with exact-run child and feature rows.

    The caller still MUST pass these values into score_verified_hourly, which
    validates scientific fingerprint, freshness, parent-child-feature parity,
    profile provenance and all no-execution gates. The query adapter alone
    makes no 'verified' or trade-readiness claim.
    """
    params = {
        "select": "run_id,collected_at_utc,symbol_count,error_count,payload",
        "payload->validation_identity->>run_source": "eq.RENDER_CRON",
        "order": "collected_at_utc.desc",
        "limit": "1",
    }
    parents = _list_of_rows(read_get(TABLE_PARENT, dict(params)), name="parent", maximum=1)
    if len(parents) != 1:
        raise HourlyScoringBlocked("canonical latest parent is missing")
    parent = parents[0]
    run_id = parent.get("run_id")
    if not isinstance(run_id, str) or EXACT_RUN_PATTERN.fullmatch(run_id) is None:
        raise HourlyScoringBlocked("canonical run_id must be exact 32-character lowercase hex")
    expected_count = parent.get("symbol_count")
    if not isinstance(expected_count, int) or isinstance(expected_count, bool) or not 1 <= expected_count <= MAX_SYMBOLS:
        raise HourlyScoringBlocked("canonical parent count is invalid")
    child_params = {
        "select": "run_id,symbol,error,payload",
        "run_id": f"eq.{run_id}",
        "order": "symbol.asc",
        "limit": str(expected_count + 1),
    }
    feat_params = {
        "select": ",".join((
            "run_id", "symbol", "captured_at_utc", "features", "source_payload",
            *CORE_FEATURE_COLUMNS,
        )),
        "run_id": f"eq.{run_id}",
        "order": "symbol.asc",
        "limit": str(expected_count + 1),
    }
    children = _list_of_rows(
        read_get(TABLE_CHILD, child_params), name="children", maximum=expected_count + 1,
    )
    features = _list_of_rows(
        read_get(TABLE_FEATURE, feat_params), name="features", maximum=expected_count + 1,
    )
    # If a newer canonical run became visible during readback, the original
    # parent is NOT the latest source. Reevaluate in a separate attempt;
    # never silently fall back to an older complete scan.
    confirmed = _list_of_rows(
        read_get(TABLE_PARENT, dict(params)), name="latest parent recheck", maximum=1,
    )
    if len(confirmed) != 1 or confirmed[0] != parent:
        raise HourlyScoringBlocked("canonical latest parent changed during readback")
    return parent, children, features
