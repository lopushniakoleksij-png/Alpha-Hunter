from __future__ import annotations

from typing import Any, Iterable


LANES = (
    "mandatory",
    "pre_move",
    "previous",
    "quiet",
    "movement",
    "liquidity",
)


def _symbol(row: dict[str, Any]) -> str:
    return str(row.get("symbol") or "").upper().strip()


def build_lane_reserved_selection(
    *,
    lane_rows: dict[str, Iterable[dict[str, Any]]],
    lane_quotas: dict[str, int],
    deep_scan_limit: int,
    legacy_order: Iterable[str] = (),
) -> list[str]:
    """Build a bounded V15 shadow selection without starving later lanes.

    This helper is intentionally detached from V14 production selection.
    Quotas must be explicit: no trading threshold or lane allocation is
    invented by the code. The result never exceeds deep_scan_limit.
    """

    if deep_scan_limit <= 0:
        return []

    missing = [lane for lane in LANES if lane not in lane_quotas]
    if missing:
        raise ValueError(
            "lane_quotas missing lanes: " + ",".join(missing)
        )

    quotas: dict[str, int] = {}
    for lane in LANES:
        value = int(lane_quotas[lane])
        if value < 0:
            raise ValueError(f"lane_quotas[{lane}] must be >= 0")
        quotas[lane] = value

    if sum(quotas.values()) > deep_scan_limit:
        raise ValueError("lane_quotas exceed deep_scan_limit")

    selected: list[str] = []

    def add(symbol: str) -> None:
        normalized = str(symbol or "").upper().strip()
        if normalized and normalized not in selected:
            selected.append(normalized)

    for lane in LANES:
        rows = list(lane_rows.get(lane, ()))
        for row in rows[: quotas[lane]]:
            add(_symbol(row))

    for symbol in legacy_order:
        if len(selected) >= deep_scan_limit:
            break
        add(symbol)

    return selected[:deep_scan_limit]
