"""Isolated successor-only canonical child-persistence readback contract.

This module does not perform writes, invoke scanners, or run automatically.
A successful HTTP upsert is NOT proof that every expected canonical child was
durably persisted. Call only with an authorised, independently bounded reader.
"""
from collections.abc import Callable, Iterable, Mapping
from typing import Any


class CanonicalChildReadbackError(RuntimeError):
    """The exact expected canonical child set cannot be independently proven."""


def verify_canonical_child_rows(
    run_id: str,
    expected_symbols: Iterable[str],
    persisted_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Verify identity, count and exact child payload identity, fail closed."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise CanonicalChildReadbackError("canonical run_id missing")
    expected = list(expected_symbols)
    if not expected or any(not isinstance(s, str) or not s.strip() for s in expected):
        raise CanonicalChildReadbackError("expected canonical symbols missing or invalid")
    if len(set(expected)) != len(expected):
        raise CanonicalChildReadbackError("duplicate expected canonical symbol")
    if len(expected) > 1000:
        raise CanonicalChildReadbackError("expected canonical symbol count exceeds bounded readback")

    rows = list(persisted_rows)
    if len(rows) != len(expected):
        raise CanonicalChildReadbackError(
            f"canonical child count mismatch: expected {len(expected)}, found {len(rows)}"
        )
    seen = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise CanonicalChildReadbackError("invalid canonical child row")
        if row.get("run_id") != run_id:
            raise CanonicalChildReadbackError("canonical child run_id mismatch")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or symbol not in expected:
            raise CanonicalChildReadbackError("unexpected canonical child symbol")
        if symbol in seen:
            raise CanonicalChildReadbackError("duplicate persisted canonical child")
        seen.add(symbol)
        payload = row.get("payload")
        if not isinstance(payload, Mapping) or payload.get("symbol") != symbol:
            raise CanonicalChildReadbackError("canonical child payload symbol mismatch")
    if seen != set(expected):
        raise CanonicalChildReadbackError("missing canonical child symbol")
    return {"run_id": run_id, "expected": len(expected), "verified": len(seen), "status": "PASS"}


def readback_canonical_child_run(
    run_id: str,
    expected_symbols: Iterable[str],
    read_rows: Callable[[str, dict[str, str]], list[dict[str, Any]]],
    *,
    table: str = "alpha_hunter_symbol_snapshots",
) -> dict[str, Any]:
    """Read exactly one run using an injected read-only, bounded database client.

    No network call is made until expected identities are validated. A timeout,
    denied access, truncated result or incomplete child batch must never PASS.
    """
    expected = list(expected_symbols)
    # Validate before any database operation, including duplicate identities.
    if not isinstance(run_id, str) or not run_id.strip() or not expected or len(expected) > 1000:
        raise CanonicalChildReadbackError("invalid bounded canonical readback request")
    if any(not isinstance(s, str) or not s.strip() for s in expected) or len(set(expected)) != len(expected):
        raise CanonicalChildReadbackError("invalid expected canonical symbol identities")
    rows = read_rows(table, {
        "select": "run_id,symbol,payload",
        "run_id": f"eq.{run_id}",
        "limit": str(len(expected) + 1),
    })
    return verify_canonical_child_rows(run_id, expected, rows)
