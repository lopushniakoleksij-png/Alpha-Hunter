from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


TRACEABILITY_VERSION = "1.2"
ROLLING_WINDOW_HOURS = 168
DEFAULT_MINIMUM_EXECUTION_SCORE = 7.5
DEFAULT_MINIMUM_EXECUTION_RR = 5.0


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError("timestamp is required")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(value: Any) -> str:
    return _dt(value).isoformat()


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "N/A", "—"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def strict_production_ready(record: dict[str, Any]) -> bool:
    """Production readiness requires BOTH protected gates."""
    return bool(
        record.get("trade_permission") is True
        and record.get("v7_trade_ready") is True
    )


def record_direction(record: dict[str, Any]) -> str | None:
    setup = record.get("execution_setup") or {}
    direction = (
        record.get("direction")
        or (setup.get("direction") if isinstance(setup, dict) else None)
    )
    text = str(direction or "").upper().strip()
    if text in {"LONG", "BUY"}:
        return "LONG"
    if text in {"SHORT", "SELL"}:
        return "SHORT"
    return None


def record_price(record: dict[str, Any]) -> float | None:
    setup = record.get("execution_setup") or {}
    if not isinstance(setup, dict):
        setup = {}
    for value in (
        setup.get("entry"),
        setup.get("entry_price"),
        record.get("last_price"),
        record.get("reference_price"),
    ):
        parsed = _float(value)
        if parsed is not None:
            return parsed
    return None


def make_ready_id(
    symbol: str,
    direction: str,
    first_ready_at_utc: Any,
    lifecycle_id: str | None = None,
) -> str:
    raw = "|".join(
        [
            str(symbol).upper(),
            str(direction).upper(),
            _iso(first_ready_at_utc),
            str(lifecycle_id or ""),
        ]
    ).encode("utf-8")
    return "RDY-" + hashlib.sha256(raw).hexdigest()[:20].upper()


@dataclass
class ReadyEpisode:
    ready_id: str
    symbol: str
    direction: str
    first_ready_at_utc: str
    last_ready_at_utc: str
    first_ready_price: float | None = None
    latest_ready_price: float | None = None
    lifecycle_id: str | None = None
    t1_id: str | None = None
    lifecycle_stage: str | None = None
    archetype: str | None = None
    trade_permission: bool = True
    v7_trade_ready: bool = True
    trigger: Any = None
    entry: Any = None
    stop: Any = None
    targets: Any = None
    reward_risk: float | None = None
    capital_risk_status: str | None = None
    readiness_observations: int = 1
    ready_status: str = "READY"
    ended_at_utc: str | None = None
    execution_match_quality: str | None = None
    execution_trade_ids: list[str] = field(default_factory=list)
    execution_order_ids: list[str] = field(default_factory=list)
    first_execution_at_utc: str | None = None
    first_execution_price: float | None = None
    execution_source: str | None = None
    closed_at_utc: str | None = None
    realized_pnl: float | None = None
    realized_roi_pct: float | None = None
    outcome: str | None = None
    failure_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _setup_value(record: dict[str, Any], *keys: str) -> Any:
    setup = record.get("execution_setup") or {}
    if not isinstance(setup, dict):
        setup = {}
    for key in keys:
        if setup.get(key) is not None:
            return setup.get(key)
        if record.get(key) is not None:
            return record.get(key)
    return None


def create_ready_episode(
    record: dict[str, Any],
    ready_at_utc: Any,
) -> ReadyEpisode:
    if not strict_production_ready(record):
        raise ValueError("candidate does not pass both production readiness gates")
    symbol = str(record.get("symbol") or "").upper().strip()
    direction = record_direction(record)
    if not symbol:
        raise ValueError("ready episode requires symbol")
    if direction is None:
        raise ValueError("ready episode requires LONG or SHORT direction")
    timestamp = _iso(ready_at_utc)
    lifecycle_id = record.get("lifecycle_id") or record.get("episode_id")
    price = record_price(record)
    return ReadyEpisode(
        ready_id=make_ready_id(symbol, direction, timestamp, lifecycle_id),
        symbol=symbol,
        direction=direction,
        first_ready_at_utc=timestamp,
        last_ready_at_utc=timestamp,
        first_ready_price=price,
        latest_ready_price=price,
        lifecycle_id=str(lifecycle_id) if lifecycle_id else None,
        t1_id=(str(record.get("t1_id")) if record.get("t1_id") else None),
        lifecycle_stage=(record.get("lifecycle_stage") or record.get("state")),
        archetype=record.get("archetype"),
        trigger=_setup_value(record, "trigger", "entry_trigger"),
        entry=_setup_value(record, "entry", "entry_price", "entry_zone"),
        stop=_setup_value(record, "stop", "stop_loss", "sl"),
        targets=_setup_value(record, "targets", "take_profits", "tp"),
        reward_risk=_float(_setup_value(record, "rr", "reward_risk")),
        capital_risk_status=record.get("capital_risk_status"),
    )


def _active_episode(
    episodes: list[ReadyEpisode],
    symbol: str,
    direction: str,
) -> ReadyEpisode | None:
    active = [
        episode
        for episode in episodes
        if episode.symbol == symbol
        and episode.direction == direction
        and episode.ready_status == "READY"
    ]
    if not active:
        return None
    active.sort(key=lambda item: item.first_ready_at_utc, reverse=True)
    return active[0]


def update_ready_ledger(
    episodes: list[ReadyEpisode],
    records: list[dict[str, Any]],
    observed_at_utc: Any,
) -> list[ReadyEpisode]:
    """Update readiness episodes from one frozen production snapshot.

    An active ready episode ends only when the same symbol was evaluated in the
    current snapshot and no longer passes both gates. Missing symbols do not
    terminate episodes because that may be a data-coverage failure.
    """
    timestamp = _iso(observed_at_utc)
    evaluated_symbols: set[str] = set()
    ready_keys: set[tuple[str, str]] = set()

    for record in records:
        if not isinstance(record, dict):
            continue
        symbol = str(record.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        evaluated_symbols.add(symbol)
        if not strict_production_ready(record):
            continue
        direction = record_direction(record)
        if direction is None:
            continue
        ready_keys.add((symbol, direction))
        episode = _active_episode(episodes, symbol, direction)
        if episode is None:
            episodes.append(create_ready_episode(record, timestamp))
            continue
        episode.last_ready_at_utc = timestamp
        episode.latest_ready_price = record_price(record)
        episode.readiness_observations += 1
        episode.lifecycle_stage = record.get("lifecycle_stage") or record.get("state") or episode.lifecycle_stage
        episode.archetype = record.get("archetype") or episode.archetype
        if record.get("lifecycle_id") or record.get("episode_id"):
            episode.lifecycle_id = str(record.get("lifecycle_id") or record.get("episode_id"))
        if record.get("t1_id"):
            episode.t1_id = str(record.get("t1_id"))

    for episode in episodes:
        if episode.ready_status != "READY":
            continue
        if episode.symbol not in evaluated_symbols:
            continue
        if (episode.symbol, episode.direction) not in ready_keys:
            episode.ready_status = "READY_ENDED"
            episode.ended_at_utc = timestamp

    return episodes


def fill_timestamp(fill: dict[str, Any]) -> datetime | None:
    value = fill.get("cTime") or fill.get("ts") or fill.get("timestamp")
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
        return _dt(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _opening_fill_direction(fill: dict[str, Any]) -> str | None:
    """Conservative open-direction inference for Bitget fills.

    Exact clientOid/READY_ID linkage is preferred. When manual/app orders do not
    carry READY_ID, side + tradeSide + zero/near-zero realized profit is only a
    HEURISTIC match and must never be called VERIFIED.
    """
    side = str(fill.get("side") or "").lower()
    trade_side = str(fill.get("tradeSide") or "").lower()
    profit = abs(_float(fill.get("profit")) or 0.0)

    if "open_long" in trade_side:
        return "LONG"
    if "open_short" in trade_side:
        return "SHORT"
    if trade_side == "open":
        if side == "buy":
            return "LONG"
        if side == "sell":
            return "SHORT"
    if trade_side in {"buy_single", "sell_single"} and profit <= 1e-12:
        return "LONG" if trade_side == "buy_single" else "SHORT"
    return None


def attach_fill_matches(
    episodes: list[ReadyEpisode],
    fills: list[dict[str, Any]],
    max_match_hours: float = 48.0,
) -> None:
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        symbol = str(fill.get("symbol") or "").upper().strip()
        direction = _opening_fill_direction(fill)
        timestamp = fill_timestamp(fill)
        if not symbol or direction is None or timestamp is None:
            continue
        candidates: list[ReadyEpisode] = []
        for episode in episodes:
            if episode.symbol != symbol or episode.direction != direction:
                continue
            ready_at = _dt(episode.first_ready_at_utc)
            if timestamp < ready_at:
                continue
            if timestamp - ready_at > timedelta(hours=max_match_hours):
                continue
            candidates.append(episode)
        if not candidates:
            continue
        candidates.sort(key=lambda item: item.first_ready_at_utc, reverse=True)
        episode = candidates[0]
        trade_id = str(fill.get("tradeId") or "").strip()
        order_id = str(fill.get("orderId") or "").strip()
        if trade_id and trade_id not in episode.execution_trade_ids:
            episode.execution_trade_ids.append(trade_id)
        if order_id and order_id not in episode.execution_order_ids:
            episode.execution_order_ids.append(order_id)
        if episode.first_execution_at_utc is None:
            episode.first_execution_at_utc = timestamp.isoformat()
            episode.first_execution_price = _float(fill.get("price"))
            episode.execution_source = str(fill.get("enterPointSource") or "UNKNOWN").upper()
        episode.execution_match_quality = "HEURISTIC_FILL_MATCH"


def unlinked_open_like_fills(
    episodes: list[ReadyEpisode],
    fills: list[dict[str, Any]],
    start_at_utc: Any,
) -> list[dict[str, Any]]:
    start = _dt(start_at_utc)
    linked_trade_ids = {
        trade_id
        for episode in episodes
        for trade_id in episode.execution_trade_ids
    }
    output = []
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        timestamp = fill_timestamp(fill)
        if timestamp is None or timestamp < start:
            continue
        if _opening_fill_direction(fill) is None:
            continue
        trade_id = str(fill.get("tradeId") or "").strip()
        if trade_id and trade_id in linked_trade_ids:
            continue
        output.append(fill)
    return output


def rolling_summary(
    episodes: list[ReadyEpisode],
    fills: list[dict[str, Any]] | None = None,
    now_utc: Any | None = None,
    hours: int = ROLLING_WINDOW_HOURS,
    fill_history_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _dt(now_utc or datetime.now(timezone.utc))
    start = now - timedelta(hours=hours)
    window = [
        episode
        for episode in episodes
        if _dt(episode.first_ready_at_utc) >= start
        and _dt(episode.first_ready_at_utc) <= now
    ]
    distinct_symbols = sorted({episode.symbol for episode in window})
    long_count = sum(1 for episode in window if episode.direction == "LONG")
    short_count = sum(1 for episode in window if episode.direction == "SHORT")
    executed = [episode for episode in window if episode.first_execution_at_utc]
    ready_to_execution = (
        len(executed) / len(window) * 100.0 if window else None
    )
    fills = fills or []
    unlinked = unlinked_open_like_fills(episodes, fills, start)
    coverage = dict(fill_history_coverage or {})
    coverage_status = str(
        coverage.get("status") or "NOT_EVALUATED"
    ).upper()
    coverage_fill_count = coverage.get("fill_count")
    fill_history_pass_eligible = bool(
        coverage_status == "CONNECTED"
        and coverage.get("complete") is True
        and coverage.get("schema_validated") is True
        and isinstance(coverage_fill_count, int)
        and coverage_fill_count > 0
        and coverage_fill_count == len(fills)
    )
    traceability_status = (
        "FAIL"
        if unlinked
        else (
            "PASS"
            if fill_history_pass_eligible
            else "INCOMPLETE"
        )
    )
    return {
        "window_start_utc": start.isoformat(),
        "window_end_utc": now.isoformat(),
        "distinct_trade_ready_coins": len(distinct_symbols),
        "distinct_trade_ready_episodes": len(window),
        "trade_ready_long": long_count,
        "trade_ready_short": short_count,
        "heuristically_matched_executions": len(executed),
        "ready_to_execution_pct": ready_to_execution,
        "ready_symbols": distinct_symbols,
        "ready_ids": [episode.ready_id for episode in window],
        "unlinked_open_like_fill_count": len(unlinked),
        "fill_history_status": coverage_status,
        "fill_history_pass_eligible": fill_history_pass_eligible,
        "fill_history_coverage": coverage,
        "traceability_status": traceability_status,
    }


def _readiness_conditions(
    record: dict[str, Any],
    minimum_execution_score: float,
    minimum_execution_rr: float,
) -> dict[str, bool]:
    phase = str(record.get("market_phase") or "").upper().strip()
    timing = str(record.get("opportunity_timing") or "").upper().strip()
    score = _float(record.get("behaviour_score"))
    setup = record.get("execution_setup") or {}
    if not isinstance(setup, dict):
        setup = {}
    reward_risk = _float(setup.get("rr"))

    return {
        "DIRECTION_AVAILABLE": record_direction(record) is not None,
        "TRADE_PERMISSION": record.get("trade_permission") is True,
        "EXECUTION_SCORE": (
            score is not None
            and score >= minimum_execution_score
        ),
        "EXECUTION_RR": (
            reward_risk is not None
            and reward_risk >= minimum_execution_rr
        ),
        "ELIGIBLE_PHASE": phase in {"RECOVERY", "IGNITION"},
        "EARLY_TIMING": timing == "EARLY",
    }


def readiness_diagnostic(
    snapshots: list[dict[str, Any]],
    minimum_execution_score: float = DEFAULT_MINIMUM_EXECUTION_SCORE,
    minimum_execution_rr: float = DEFAULT_MINIMUM_EXECUTION_RR,
    closest_limit: int = 5,
) -> dict[str, Any]:
    """Explain why observed candidates did not become strictly trade ready.

    This is audit-only. It ranks failed production conditions and surfaces the
    nearest candidates from the latest snapshot without granting permission or
    changing any execution gate.
    """
    blocker_counts: Counter[str] = Counter()
    execution_check_failures: Counter[str] = Counter()
    quality_rejections: Counter[str] = Counter()
    evaluated_observations = 0
    data_error_observations = 0
    strict_ready_observations = 0
    latest_records: list[dict[str, Any]] = []

    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        symbols = snapshot.get("symbols") or []
        if not isinstance(symbols, list):
            continue
        current_records = [row for row in symbols if isinstance(row, dict)]
        latest_records = current_records

        for record in current_records:
            symbol = str(record.get("symbol") or "").strip()
            if not symbol:
                continue
            if "error" in record:
                data_error_observations += 1
                continue
            evaluated_observations += 1
            if strict_production_ready(record):
                strict_ready_observations += 1

            conditions = _readiness_conditions(
                record,
                minimum_execution_score,
                minimum_execution_rr,
            )
            blocker_counts.update(
                name
                for name, passed in conditions.items()
                if not passed
            )

            setup = record.get("execution_setup") or {}
            if isinstance(setup, dict):
                checks = setup.get("checks") or {}
                if isinstance(checks, dict):
                    execution_check_failures.update(
                        str(name).upper()
                        for name, passed in checks.items()
                        if passed is False
                    )

            reasons = record.get("rejection_reasons") or []
            if isinstance(reasons, (list, tuple, set)):
                quality_rejections.update(
                    str(reason).upper()
                    for reason in reasons
                    if str(reason).strip()
                )

    def ranked(counter: Counter[str]) -> list[dict[str, Any]]:
        return [
            {
                "reason": reason,
                "observations": count,
                "observation_pct": (
                    round(count / evaluated_observations * 100.0, 2)
                    if evaluated_observations
                    else 0.0
                ),
            }
            for reason, count in sorted(
                counter.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]

    closest: list[dict[str, Any]] = []
    for record in latest_records:
        if "error" in record:
            continue
        if strict_production_ready(record):
            continue
        symbol = str(record.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        setup = record.get("execution_setup") or {}
        if not isinstance(setup, dict):
            setup = {}
        conditions = _readiness_conditions(
            record,
            minimum_execution_score,
            minimum_execution_rr,
        )
        checks = setup.get("checks") or {}
        if not isinstance(checks, dict):
            checks = {}
        reasons = record.get("rejection_reasons") or []
        if not isinstance(reasons, (list, tuple, set)):
            reasons = []
        closest.append(
            {
                "symbol": symbol,
                "direction": record_direction(record),
                "conditions_passed": sum(conditions.values()),
                "conditions_total": len(conditions),
                "failed_conditions": [
                    name
                    for name, passed in conditions.items()
                    if not passed
                ],
                "execution_check_failures": [
                    str(name).upper()
                    for name, passed in checks.items()
                    if passed is False
                ],
                "quality_rejections": [
                    str(reason).upper()
                    for reason in reasons
                    if str(reason).strip()
                ],
                "behaviour_score": _float(record.get("behaviour_score")),
                "reward_risk": _float(setup.get("rr")),
                "market_phase": record.get("market_phase"),
                "opportunity_timing": record.get("opportunity_timing"),
                "trade_permission": record.get("trade_permission") is True,
                "v7_trade_ready": record.get("v7_trade_ready") is True,
                "audit_only": True,
            }
        )

    closest.sort(
        key=lambda item: (
            -item["conditions_passed"],
            -(
                item["behaviour_score"]
                if item["behaviour_score"] is not None
                else float("-inf")
            ),
            -(
                item["reward_risk"]
                if item["reward_risk"] is not None
                else float("-inf")
            ),
            item["symbol"],
        )
    )

    return {
        "classification": "AUDIT_ONLY_DOES_NOT_GRANT_PERMISSION",
        "evaluated_candidate_observations": evaluated_observations,
        "data_error_observations": data_error_observations,
        "strict_ready_observations": strict_ready_observations,
        "minimum_execution_score": minimum_execution_score,
        "minimum_execution_reward_risk": minimum_execution_rr,
        "ranked_gate_blockers": ranked(blocker_counts),
        "ranked_execution_check_failures": ranked(execution_check_failures),
        "ranked_quality_rejections": ranked(quality_rejections),
        "current_closest_candidates": closest[:max(0, closest_limit)],
    }
