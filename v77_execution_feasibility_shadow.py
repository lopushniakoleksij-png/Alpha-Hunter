from __future__ import annotations

import hashlib, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import requests

from alpha_hunter.bitget import BitgetAPIError, BitgetClient
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig
from v76_direction_shadow import load_direction_states
from v76_post_confirmation_tracker import confirmation_shadow

ROOT = Path(__file__).resolve().parent
TABLE = "alpha_hunter_execution_shadow"
MODEL_VERSION = "7.7-execution-shadow-v1"
CANDLE_LIMIT = 120
STRUCTURE_WINDOW = 12
STOP_BUFFER_ATR_FRACTION = 0.25

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)

def f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def headers(settings: SupabaseConfig, merge: bool = False) -> dict[str, str]:
    result = {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
    }
    if merge:
        result["Prefer"] = "resolution=merge-duplicates,return=minimal"
    return result

def execution_shadow_id(episode_id: str, confirmed_at: datetime) -> str:
    raw = f"{episode_id}|{MODEL_VERSION}|{confirmed_at.isoformat()}".encode()
    return hashlib.sha256(raw).hexdigest()[:24]

def expected_execution_shadow_id(
    state: dict[str, Any],
) -> str | None:
    episode_id = str(
        state.get("episode_id")
        or ""
    ).strip()

    confirmed_at = dt(
        state.get(
            "first_confirmed_at_utc"
        )
    )

    if (
        not episode_id
        or confirmed_at is None
    ):
        return None

    return execution_shadow_id(
        episode_id,
        confirmed_at,
    )


def reusable_shadow_evidence(
    state: dict[str, Any],
    existing: dict[
        str,
        dict[str, Any],
    ],
) -> bool:
    shadow_id = (
        expected_execution_shadow_id(
            state
        )
    )

    if shadow_id is None:
        return False

    row = existing.get(
        shadow_id
    )

    if row is None:
        return False

    return (
        row.get("trade_permission")
        is False
        and bool(
            row.get(
                "feasibility_status"
            )
        )
        and row.get(
            "candidate_entry"
        )
        not in (None, "")
    )


def load_existing_shadow_rows(
    settings: SupabaseConfig,
    shadow_ids: list[str],
) -> dict[str, dict[str, Any]]:
    ids = sorted({
        str(value)
        for value in shadow_ids
        if value
    })

    if not ids:
        return {}

    response = requests.get(
        f"{settings.url}/rest/v1/{TABLE}",
        params={
            "select": (
                "shadow_id,"
                "trade_permission,"
                "feasibility_status,"
                "candidate_entry"
            ),
            "shadow_id": (
                "in.("
                + ",".join(ids)
                + ")"
            ),
        },
        headers=headers(settings),
        timeout=settings.timeout_seconds,
    )

    if response.status_code != 200:
        raise RuntimeError(
            "V7.7 existing shadow load failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    payload = response.json()

    if not isinstance(payload, list):
        raise RuntimeError(
            "V7.7 existing shadow response "
            "is not a list"
        )

    result = {}

    for row in payload:
        if not isinstance(row, dict):
            continue

        shadow_id = str(
            row.get("shadow_id")
            or ""
        )

        if shadow_id:
            result[shadow_id] = row

    return result


def parse_closed_candles(candles: list[Any], as_of: datetime, timeframe_minutes: int) -> list[dict[str, float | int]]:
    rows = []
    duration = timedelta(minutes=timeframe_minutes)
    for candle in candles:
        if not isinstance(candle, list):
            continue
        try:
            ts = int(candle[0])
            opened = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            high, low, close = float(candle[2]), float(candle[3]), float(candle[4])
        except (TypeError, ValueError, IndexError):
            continue
        if opened + duration > as_of:
            continue
        rows.append({"timestamp": ts, "high": high, "low": low, "close": close})
    rows.sort(key=lambda row: int(row["timestamp"]))
    return rows

def atr(candles: list[dict[str, float | int]], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    ranges = []
    for i in range(1, len(candles)):
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        previous_close = float(candles[i - 1]["close"])
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    value = sum(ranges[:period]) / period
    for current in ranges[period:]:
        value = (value * (period - 1) + current) / period
    return value

def swing_levels(candles: list[dict[str, float | int]], window: int = STRUCTURE_WINDOW) -> tuple[float | None, float | None]:
    if not candles:
        return None, None
    sample = candles[-window:]
    return min(float(c["low"]) for c in sample), max(float(c["high"]) for c in sample)

def choose_stop(direction: str, entry: float, low15: float | None, high15: float | None, low1h: float | None, high1h: float | None, atr15: float | None) -> tuple[float | None, str | None]:
    buffer = (atr15 or 0.0) * STOP_BUFFER_ATR_FRACTION
    if direction == "LONG":
        candidates = [(s, x) for s, x in (("15M_SWING_LOW", low15), ("1H_SWING_LOW", low1h)) if x is not None and x < entry]
        if not candidates:
            return None, None
        source, level = max(candidates, key=lambda item: item[1])
        return level - buffer, f"{source}+0.25ATR15_BUFFER"
    if direction == "SHORT":
        candidates = [(s, x) for s, x in (("15M_SWING_HIGH", high15), ("1H_SWING_HIGH", high1h)) if x is not None and x > entry]
        if not candidates:
            return None, None
        source, level = min(candidates, key=lambda item: item[1])
        return level + buffer, f"{source}+0.25ATR15_BUFFER"
    return None, None

def choose_target(direction: str, entry: float, low15: float | None, high15: float | None, low1h: float | None, high1h: float | None) -> float | None:
    if direction == "LONG":
        levels = [x for x in (high15, high1h) if x is not None and x > entry]
        return min(levels) if levels else None
    if direction == "SHORT":
        levels = [x for x in (low15, low1h) if x is not None and x < entry]
        return max(levels) if levels else None
    return None

def stop_distance_pct(entry: float, stop: float | None) -> float | None:
    return abs(entry - stop) / entry * 100.0 if entry > 0 and stop is not None else None

def structural_reward_pct(direction: str, entry: float, target: float | None) -> float | None:
    if entry <= 0 or target is None:
        return None
    if direction == "LONG" and target > entry:
        return (target - entry) / entry * 100.0
    if direction == "SHORT" and target < entry:
        return (entry - target) / entry * 100.0
    return None

def rr(reward_pct: float | None, risk_pct: float | None) -> float | None:
    return reward_pct / risk_pct if reward_pct is not None and risk_pct not in (None, 0) else None

def stop_quality(distance_atr: float | None) -> str:
    if distance_atr is None:
        return "ATR_UNAVAILABLE"
    if distance_atr < 0.75:
        return "TIGHT"
    if distance_atr <= 3.0:
        return "NORMAL"
    return "WIDE"

def feasibility_status(stop_valid: bool, structure_valid: bool, structure_rr: float | None) -> str:
    if not stop_valid:
        return "NO_VALID_STOP"
    if not structure_valid or structure_rr is None:
        return "NO_STRUCTURAL_TARGET"
    if structure_rr >= 10:
        return "STRUCTURE_RR_10_PLUS"
    if structure_rr >= 5:
        return "STRUCTURE_RR_5_TO_10"
    if structure_rr >= 3:
        return "STRUCTURE_RR_3_TO_5"
    return "STRUCTURE_RR_LT_3"

def build_execution_row(state: dict[str, Any], confirmation: dict[str, Any], candles_15m_raw: list[Any], candles_1h_raw: list[Any], processed_at: datetime) -> dict[str, Any] | None:
    episode_id = str(state.get("episode_id") or "")
    confirmed_at = dt(state.get("first_confirmed_at_utc"))
    entry = f(state.get("price_at_confirmed"))
    direction = str(confirmation.get("direction") or "").upper()
    confidence = f(confirmation.get("confidence"))
    if not episode_id or confirmed_at is None or entry in (None, 0) or direction not in {"LONG", "SHORT"}:
        return None

    c15 = parse_closed_candles(candles_15m_raw, confirmed_at, 15)
    c1h = parse_closed_candles(candles_1h_raw, confirmed_at, 60)
    if len(c15) < 15 or len(c1h) < 15:
        return None

    atr15, atr1h = atr(c15), atr(c1h)
    low15, high15 = swing_levels(c15)
    low1h, high1h = swing_levels(c1h)
    stop, stop_source = choose_stop(direction, entry, low15, high15, low1h, high1h, atr15)
    target = choose_target(direction, entry, low15, high15, low1h, high1h)
    risk_pct = stop_distance_pct(entry, stop)
    reward_pct = structural_reward_pct(direction, entry, target)
    structure_rr = rr(reward_pct, risk_pct)
    risk_abs = abs(entry - stop) if stop is not None else None
    distance_atr = risk_abs / atr15 if risk_abs is not None and atr15 not in (None, 0) else None

    stop_valid = bool(stop is not None and risk_pct not in (None, 0) and ((direction == "LONG" and stop < entry) or (direction == "SHORT" and stop > entry)))
    structure_valid = bool(stop_valid and target is not None and reward_pct not in (None, 0) and ((direction == "LONG" and target > entry) or (direction == "SHORT" and target < entry)))
    status = feasibility_status(stop_valid, structure_valid, structure_rr)

    return {
        "shadow_id": execution_shadow_id(episode_id, confirmed_at),
        "episode_id": episode_id,
        "symbol": str(state.get("symbol") or ""),
        "path": state.get("path"),
        "model_version": MODEL_VERSION,
        "evaluated_at_utc": confirmed_at.isoformat(),
        "confirmed_direction": direction,
        "confirmed_at_utc": confirmed_at.isoformat(),
        "confirmation_price": entry,
        "confirmation_confidence": confidence,
        "market_price": entry,
        "move_consumed_pct": f(state.get("move_at_confirmed_pct")),
        "candidate_entry": entry,
        "stop_price": stop,
        "stop_source": stop_source,
        "stop_distance_pct": risk_pct,
        "atr_15m": atr15,
        "atr_1h": atr1h,
        "stop_distance_atr": distance_atr,
        "swing_low_15m": low15,
        "swing_high_15m": high15,
        "swing_low_1h": low1h,
        "swing_high_1h": high1h,
        "structural_target": target,
        "structural_reward_pct": reward_pct,
        "rr_to_structure": structure_rr,
        "rr_to_3pct": rr(3.0, risk_pct),
        "rr_to_5pct": rr(5.0, risk_pct),
        "rr_to_10pct": rr(10.0, risk_pct),
        "rr3_possible": bool(structure_valid and structure_rr is not None and structure_rr >= 3),
        "rr5_possible": bool(structure_valid and structure_rr is not None and structure_rr >= 5),
        "rr10_possible": bool(structure_valid and structure_rr is not None and structure_rr >= 10),
        "structure_valid": structure_valid,
        "stop_valid": stop_valid,
        "feasibility_status": status,
        "evidence": {
            "snapshot_basis": "FIRST_DIRECTION_CONFIRMATION",
            "future_candle_leakage_blocked": True,
            "closed_15m_bars_used": len(c15),
            "closed_1h_bars_used": len(c1h),
            "structure_window_bars": STRUCTURE_WINDOW,
            "stop_buffer_atr_fraction": STOP_BUFFER_ATR_FRACTION,
            "stop_distance_quality": stop_quality(distance_atr),
            "scenario_note": "3pct/5pct/10pct are reward-distance scenarios, not predicted targets",
            "direction_state_at_processing": state.get("direction_state"),
            "processed_at_utc": processed_at.isoformat(),
        },
        "trade_permission": False,
        "updated_at": processed_at.isoformat(),
    }

def upsert_rows(settings: SupabaseConfig, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    response = requests.post(
        f"{settings.url}/rest/v1/{TABLE}",
        params={"on_conflict": "shadow_id"},
        headers=headers(settings, True),
        data=json.dumps(rows, separators=(",", ":")),
        timeout=settings.timeout_seconds,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(f"V7.7 execution shadow save failed: HTTP {response.status_code}: {response.text[:800]}")
    return len(rows)

def main() -> int:
    load_env_file(ROOT / ".env")
    config = load_config(ROOT / "config.json")
    settings = SupabaseConfig.from_environment(config)
    if settings is None:
        raise SystemExit("Supabase is not configured")

    product_type = str(config.get("product_type", "usdt-futures"))
    states = load_direction_states(settings)
    confirmed = [
        state for state in states.values()
        if state.get("first_confirmed_at_utc")
        and f(state.get("price_at_confirmed")) not in (None, 0)
    ]
    confirmed.sort(key=lambda s: (str(s.get("first_confirmed_at_utc") or ""), str(s.get("symbol") or "")))

    expected_shadow_ids = [
        shadow_id
        for state in confirmed
        for shadow_id in [
            expected_execution_shadow_id(
                state
            )
        ]
        if shadow_id is not None
    ]

    existing_shadow_rows = {}

    for offset in range(
        0,
        len(expected_shadow_ids),
        75,
    ):
        existing_shadow_rows.update(
            load_existing_shadow_rows(
                settings,
                expected_shadow_ids[
                    offset:offset + 75
                ],
            )
        )

    client = BitgetClient.from_environment(
        timeout=int(config.get("request_timeout_seconds", 12)),
        max_retries=int(config.get("max_retries", 3)),
    )
    processed_at = utc_now()
    rows, skipped, failures = [], 0, 0

    print()
    print("=" * 118)
    print("ALPHA HUNTER V7.7 HUGE-RR EXECUTION FEASIBILITY — SHADOW")
    print("=" * 118)
    print("Confirmed direction states:", len(confirmed))
    print()

    for state in confirmed:
        episode_id = str(state.get("episode_id") or "")
        symbol = str(state.get("symbol") or "")
        confirmed_at = dt(state.get("first_confirmed_at_utc"))
        try:
            if not episode_id or not symbol or confirmed_at is None:
                skipped += 1
                continue
            shadow_id = (
                expected_execution_shadow_id(
                    state
                )
            )

            existing_row = (
                existing_shadow_rows.get(
                    shadow_id
                )
                if shadow_id is not None
                else None
            )

            if existing_row is not None:
                if reusable_shadow_evidence(
                    state,
                    existing_shadow_rows,
                ):
                    print(
                        f"SKIP   {symbol:<15}"
                        "frozen execution evidence "
                        "already stored"
                    )
                    skipped += 1
                    continue

                raise RuntimeError(
                    "existing V7.7 shadow is "
                    "not safe for reuse: "
                    f"{shadow_id}"
                )

            confirmation = confirmation_shadow(settings, episode_id, confirmed_at)
            if not confirmation:
                print(f"SKIP   {symbol:<15}confirmation shadow unavailable")
                skipped += 1
                continue
            candles_15m = client.candles(symbol, product_type, "15m", CANDLE_LIMIT) or []
            candles_1h = client.candles(symbol, product_type, "1H", CANDLE_LIMIT) or []
            row = build_execution_row(state, confirmation, candles_15m, candles_1h, processed_at)
            if row is None:
                print(f"SKIP   {symbol:<15}insufficient closed history at confirmation")
                skipped += 1
                continue
            rows.append(row)
            rr_text = f"{row['rr_to_structure']:.2f}" if row["rr_to_structure"] is not None else "—"
            risk_text = f"{row['stop_distance_pct']:.2f}" if row["stop_distance_pct"] is not None else "—"
            stop_text = f"{row['stop_price']:.8g}" if row["stop_price"] is not None else "—"
            print(f"{symbol:<15}{row['confirmed_direction']:<7} entry={row['candidate_entry']:<12.8g} stop={stop_text:<12} risk={risk_text:>6}% structRR={rr_text:<6} status={row['feasibility_status']}")
        except (BitgetAPIError, RuntimeError, ValueError, TypeError) as exc:
            failures += 1
            print(f"FAILED {symbol:<15}{exc}")

    saved = upsert_rows(settings, rows)
    print()
    print("=" * 118)
    print("V7.7 EXECUTION SHADOW SUMMARY")
    print("=" * 118)
    print("Confirmed direction states:", len(confirmed))
    print("Execution snapshots:", len(rows))
    print("Skipped:", skipped)
    print("Failures:", failures)
    print("Supabase rows upserted:", saved)
    print("Structure >=1:3:", sum(bool(row["rr3_possible"]) for row in rows))
    print("Structure >=1:5:", sum(bool(row["rr5_possible"]) for row in rows))
    print("Structure >=1:10:", sum(bool(row["rr10_possible"]) for row in rows))
    print()
    print("IMPORTANT: V7.7 IS EXECUTION FEASIBILITY SHADOW ONLY.")
    print("3% / 5% / 10% are scenarios, not predicted targets.")
    print("No trade permission was generated.")

    if failures:
        raise SystemExit(f"V7.7 EXECUTION SHADOW FAILED FOR {failures} STATES")

    print()
    print("V7.7 EXECUTION FEASIBILITY: PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
