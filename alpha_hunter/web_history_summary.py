"""Public, read-only archive-status summary for a degraded Alpha Hunter dashboard.

Never supplies pair names, prices, setups, directions or order instructions.
The most recent canonical parent is never silently replaced as current source.
A separately labelled older storage-complete run is allowed for operational
history only. All HTTP/network access is injected by the Flask web application.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

PARENT_TABLE = "alpha_hunter_snapshots"
CHILD_TABLE = "alpha_hunter_symbol_snapshots"
FEATURE_TABLE = "alpha_hunter_signal_features"
MAX_PARENTS = 6
MAX_SYMBOLS = 2000


class ArchiveEvidenceUnavailable(ValueError):
    """No bounded, trustworthy historical storage summary is available."""


def _utc(text: Any) -> datetime:
    if not isinstance(text, str) or not text:
        raise ArchiveEvidenceUnavailable("missing evidence timestamp")
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArchiveEvidenceUnavailable("malformed evidence timestamp") from exc
    if value.tzinfo is None:
        raise ArchiveEvidenceUnavailable("evidence timestamp lacks timezone")
    return value.astimezone(timezone.utc)


def _head_valid(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return False
    identity = payload.get("validation_identity")
    if not isinstance(identity, dict) or identity.get("run_source") != "RENDER_CRON":
        return False
    rid, n = row.get("run_id"), row.get("symbol_count")
    if not isinstance(rid, str) or not rid or payload.get("run_id") != rid:
        return False
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_SYMBOLS:
        return False
    if row.get("error_count") != 0 or payload.get("_storage_contract") != "snapshot-parent-v0.2":
        return False
    stubs = payload.get("symbols")
    if not isinstance(stubs, list) or len(stubs) != n:
        return False
    symbols = [s.get("symbol") if isinstance(s, dict) else None for s in stubs]
    if any(not isinstance(s, str) or not s for s in symbols) or len(set(symbols)) != n:
        return False
    try:
        _utc(row.get("collected_at_utc"))
    except ArchiveEvidenceUnavailable:
        return False
    return True


def archived_storage_summary(
    read_rows: Callable[[str, dict[str, str]], list[dict[str, Any]]],
    *,
    now_utc: datetime,
) -> dict[str, Any]:
    """Give only aggregate historical storage status, never a live signal.

    The exact latest RENDER_CRON parent is retained as a separate header even
    when its children are absent; do not return its older sibling as current.
    """
    if now_utc.tzinfo is None:
        raise ArchiveEvidenceUnavailable("evaluation clock lacks timezone")
    now = now_utc.astimezone(timezone.utc)
    params = {
        "select": "run_id,collected_at_utc,symbol_count,error_count,payload",
        "payload->validation_identity->>run_source": "eq.RENDER_CRON",
        "order": "collected_at_utc.desc",
        "limit": str(MAX_PARENTS),
    }
    heads = read_rows(PARENT_TABLE, dict(params))
    if not isinstance(heads, list) or not heads or len(heads) > MAX_PARENTS:
        raise ArchiveEvidenceUnavailable("missing or malformed canonical source history")
    latest = heads[0]
    if not isinstance(latest, dict) or not isinstance(latest.get("run_id"), str):
        raise ArchiveEvidenceUnavailable("newest canonical source malformed")
    latest_id = latest["run_id"]
    latest_collected = _utc(latest.get("collected_at_utc"))
    if latest_collected > now:
        raise ArchiveEvidenceUnavailable("future-dated canonical source")

    completed = None
    for row in heads:
        if not _head_valid(row):
            continue
        rid, n = row["run_id"], row["symbol_count"]
        expected_symbols = {s["symbol"] for s in row["payload"]["symbols"]}
        children = read_rows(CHILD_TABLE, {
            "select": "run_id,symbol,error,state,trade_permission",
            "run_id": f"eq.{rid}", "order": "symbol.asc", "limit": str(n + 1),
        })
        if not isinstance(children, list) or len(children) != n:
            continue
        child_symbols = set()
        states = Counter()
        bad_child = False
        for child in children:
            if not isinstance(child, dict) or child.get("run_id") != rid:
                bad_child = True
                break
            symbol = child.get("symbol")
            if (not isinstance(symbol, str) or symbol not in expected_symbols
                    or symbol in child_symbols or child.get("error") not in (None, "")
                    or child.get("trade_permission") is True):
                bad_child = True
                break
            child_symbols.add(symbol)
            state = child.get("state")
            if isinstance(state, str) and state:
                states[state] += 1
        if bad_child or child_symbols != expected_symbols:
            continue

        feature_rows = read_rows(FEATURE_TABLE, {
            "select": "run_id,symbol,captured_at_utc",
            "run_id": f"eq.{rid}", "order": "symbol.asc", "limit": str(n + 1),
        })
        if not isinstance(feature_rows, list) or len(feature_rows) != n:
            continue
        features = set()
        collected = _utc(row["collected_at_utc"])
        bad_feature = False
        for f in feature_rows:
            if not isinstance(f, dict) or f.get("run_id") != rid:
                bad_feature = True
                break
            symbol = f.get("symbol")
            if not isinstance(symbol, str) or symbol not in expected_symbols or symbol in features:
                bad_feature = True
                break
            try:
                timestamp = _utc(f.get("captured_at_utc"))
            except ArchiveEvidenceUnavailable:
                bad_feature = True
                break
            if timestamp != collected:
                bad_feature = True
                break
            features.add(symbol)
        if bad_feature or features != expected_symbols or collected > now:
            continue

        completed = {
            "collected_at_utc": collected.isoformat(),
            "age_minutes": round((now - collected).total_seconds() / 60, 1),
            "declared_symbols": n,
            "persisted_symbols": n,
            "persisted_features": n,
            "aggregate_states": dict(sorted(states.items())),
            "storage_integrity": "MATCHING_PARENT_CHILD_FEATURE_COUNTS",
        }
        break

    # The newest run may have changed during the multi-request read. Treat
    # that as an inconclusive historical probe rather than asserting currency.
    reread = read_rows(PARENT_TABLE, {
        "select": "run_id,collected_at_utc", 
        "payload->validation_identity->>run_source": "eq.RENDER_CRON",
        "order": "collected_at_utc.desc",
        "limit": "1",
    })
    if not isinstance(reread, list) or len(reread) != 1 or reread[0].get("run_id") != latest_id:
        raise ArchiveEvidenceUnavailable("canonical source advanced during archive read")
    if _utc(reread[0].get("collected_at_utc")) != latest_collected:
        raise ArchiveEvidenceUnavailable("canonical source timestamp changed during archive read")

    return {
        "mode": "HISTORICAL_STORAGE_STATUS_ONLY",
        "latest_reported_scan_at_utc": latest_collected.isoformat(),
        "latest_reported_declared_symbols": latest.get("symbol_count"),
        "historical_completed_scan": completed,
        "historical_only": True,
        "this_is_not_a_live_trading_signal": True,
        "verified_live_trade_signal": False,
        "trade_permission": False,
        "exchange_authority": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
        "source_run_not_substituted": True,
    }
