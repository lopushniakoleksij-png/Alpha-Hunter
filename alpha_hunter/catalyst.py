from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


CATALYST_VERSION = "0.2"


def _int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso_from_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(
        value / 1000,
        tz=timezone.utc,
    ).isoformat()


def _title_matches_symbol(
    title: str,
    symbol: str,
    base_coin: str,
) -> tuple[bool, str | None, str | None]:
    """Match only complete symbol/pair tokens, never embedded substrings.

    Examples that must NOT match:
    - LSKUSDT inside CLSKUSDT
    - MUSDT inside CRMUSDT
    - SUSDT inside GFSUSDT

    Announcement text is not a structured symbol feed, so fail closed rather
    than treating an alphanumeric substring as evidence for another contract.
    """
    upper = title.upper()
    symbol_upper = symbol.upper()
    base_upper = base_coin.upper()

    direct_forms = (
        symbol_upper,
        f"{base_upper}/USDT",
        f"{base_upper}-USDT",
        f"{base_upper}_USDT",
    )
    for form in direct_forms:
        if not form:
            continue
        pattern = rf"(?<![A-Z0-9]){re.escape(form)}(?![A-Z0-9])"
        if re.search(pattern, upper):
            return True, form, "EXACT_SYMBOL_OR_PAIR_TOKEN"

    if len(base_upper) < 3:
        return False, None, None

    pattern = rf"(?<![A-Z0-9]){re.escape(base_upper)}(?![A-Z0-9])"
    if re.search(pattern, upper):
        return True, base_upper, "WHOLE_BASE_TOKEN"

    return False, None, None


def normalize_notice(
    row: dict[str, Any],
) -> dict[str, Any] | None:
    ann_id = row.get("annId")
    title = str(row.get("annTitle") or "").strip()
    published_ms = _int(row.get("cTime"))
    if not ann_id or not title or published_ms is None:
        return None
    return {
        "id": str(ann_id),
        "title": title,
        "url": row.get("annUrl"),
        "ann_type": row.get("annType"),
        "ann_sub_type": row.get("annSubType"),
        "language": row.get("language"),
        "published_at_ms": published_ms,
        "published_at_utc": _iso_from_ms(published_ms),
    }


def bind_official_catalyst(
    *,
    symbol: str,
    base_coin: str,
    notices: list[dict[str, Any]],
    exchange_timestamp_ms: int | None,
    freshness_hours: float = 48.0,
    future_tolerance_ms: int = 300000,
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    freshness_ms = int(freshness_hours * 3600 * 1000)

    for raw in notices:
        notice = normalize_notice(raw)
        if notice is None:
            continue
        matched, matched_on, match_rule = _title_matches_symbol(
            notice["title"],
            symbol,
            base_coin,
        )
        if not matched:
            continue
        published_ms = int(notice["published_at_ms"])
        age_ms = (
            exchange_timestamp_ms - published_ms
            if exchange_timestamp_ms is not None
            else None
        )
        fresh = bool(
            age_ms is not None
            and age_ms >= -future_tolerance_ms
            and age_ms <= freshness_ms
        )
        matches.append({
            **notice,
            "matched_on": matched_on,
            "match_rule": match_rule,
            "age_ms": age_ms,
            "fresh": fresh,
        })

    if not matches:
        return None

    matches.sort(
        key=lambda row: int(row["published_at_ms"]),
        reverse=True,
    )
    selected = matches[0]
    return {
        "version": CATALYST_VERSION,
        "validated": True,
        "source": "BITGET_OFFICIAL_ANNOUNCEMENT_API",
        "source_read_only": True,
        "id": selected["id"],
        "title": selected["title"],
        "url": selected["url"],
        "ann_type": selected["ann_type"],
        "ann_sub_type": selected["ann_sub_type"],
        "published_at": selected["published_at_utc"],
        "published_at_ms": selected["published_at_ms"],
        "age_ms": selected["age_ms"],
        "fresh": selected["fresh"],
        "matched_on": selected["matched_on"],
        "match_rule": selected["match_rule"],
        "matched_notice_count": len(matches),
        "direction": "MARKET_CONFIRMED",
        "trade_permission": False,
    }


def build_catalyst_summary(
    records: list[dict[str, Any]],
    *,
    fetched_notice_count: int,
    fetch_errors: list[str] | None = None,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    eligible = [
        record
        for record in records
        if isinstance(record, dict)
        and "error" not in record
    ]
    bound = 0
    fresh = 0
    for record in eligible:
        catalyst = record.get("catalyst")
        if not isinstance(catalyst, dict):
            continue
        if catalyst.get("validated") is True:
            bound += 1
        if catalyst.get("validated") is True and catalyst.get("fresh") is True:
            fresh += 1
    errors = list(fetch_errors or [])
    return {
        "version": CATALYST_VERSION,
        "source": "BITGET_OFFICIAL_ANNOUNCEMENT_API",
        "source_read_only": True,
        "categories": list(categories or []),
        "fetched_notice_count": int(fetched_notice_count),
        "eligible_symbol_count": len(eligible),
        "bound_symbol_count": bound,
        "fresh_bound_symbol_count": fresh,
        "fetch_status": "COMPLETE" if not errors else "PARTIAL",
        "fetch_errors": errors,
        "trade_permission": False,
    }
