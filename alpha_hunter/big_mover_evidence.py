from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import requests


DIRECTION_TO_AUDIT = {
    "LONG": "UP",
    "SHORT": "DOWN",
}

CORE_FEATURE_COLUMNS = (
    "volume_ratio",
    "volatility_pct",
    "compression_score",
    "funding_rate",
    "open_interest_change_pct",
    "relative_strength_btc",
    "rsi_15m",
    "rsi_1h",
    "rsi_4h",
    "distance_to_support_pct",
    "distance_to_resistance_pct",
)


@dataclass(frozen=True)
class EvidenceWindow:
    training_start_utc: str
    training_end_utc: str
    latest_audit_utc: str
    horizon_hours: int
    mover_threshold_pct: float
    control_ceiling_pct: float
    pre_expansion_abs_move_pct: float
    audit_staleness_hours: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "training_start_utc": self.training_start_utc,
            "training_end_utc": self.training_end_utc,
            "latest_audit_utc": self.latest_audit_utc,
            "horizon_hours": self.horizon_hours,
            "mover_threshold_pct": self.mover_threshold_pct,
            "control_ceiling_pct": self.control_ceiling_pct,
            "pre_expansion_abs_move_pct": self.pre_expansion_abs_move_pct,
            "audit_staleness_hours": self.audit_staleness_hours,
        }


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "N/A", "—"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError("timestamp is required")
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _source_payload(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("source_payload")
    return value if isinstance(value, dict) else {}


def _nested_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    return value if isinstance(value, dict) else {}


def current_move_pct(row: dict[str, Any]) -> float | None:
    payload = _source_payload(row)
    return _float(payload.get("change_24h_pct"))


def extract_numeric_features(row: dict[str, Any]) -> dict[str, float]:
    """Map persisted Alpha Hunter feature rows into the mover learner input.

    Only observed numeric evidence is emitted. Missing fields stay missing rather than
    being imputed, so feature coverage remains visible in the similarity score.
    """
    result: dict[str, float] = {}

    embedded = row.get("features")
    if isinstance(embedded, dict):
        for key, value in embedded.items():
            number = _float(value)
            if number is not None:
                result[str(key)] = number

    for name in CORE_FEATURE_COLUMNS:
        number = _float(row.get(name))
        if number is not None:
            result[name] = number

    payload = _source_payload(row)
    behaviour = _nested_dict(payload, "behaviour")
    components = _nested_dict(behaviour, "components")

    extras = {
        "behaviour_score": behaviour.get("score"),
        "spread_pct": behaviour.get("spread_pct"),
        "funding_change_pct": behaviour.get("funding_change_pct"),
        "relative_strength_acceleration": behaviour.get("relative_strength_acceleration"),
        "volume_acceleration_component": components.get("volume_acceleration"),
        "trend_acceleration_component": components.get("trend_acceleration"),
        "volatility_transition_component": components.get("volatility_transition"),
        "liquidity_component": components.get("liquidity"),
    }
    for name, value in extras.items():
        number = _float(value)
        if number is not None:
            result[name] = number

    return result


def _audit_direction(row: dict[str, Any]) -> str:
    return str(row.get("mover_direction") or "").strip().upper()


def _threshold(row: dict[str, Any]) -> float | None:
    return _float(row.get("mover_threshold_pct"))


def build_forward_evidence(
    feature_rows: Iterable[dict[str, Any]],
    audit_rows: Iterable[dict[str, Any]],
    *,
    horizon_hours: int = 24,
    mover_threshold_pct: float = 10.0,
    control_ceiling_pct: float = 5.0,
    pre_expansion_abs_move_pct: float = 5.0,
) -> list[dict[str, Any]]:
    """Create hindsight-safe mover/control labels from persisted forward outcomes.

    A training snapshot is eligible only while its absolute 24h move remains below
    the canonical 5% mover boundary. A MOVER requires a same-direction >=10% audit
    inside the following horizon. A CONTROL requires no same-direction >=5% audit.
    The 5%-to-10% grey zone is deliberately excluded.
    """
    if horizon_hours <= 0:
        raise ValueError("horizon_hours must be positive")
    if mover_threshold_pct < control_ceiling_pct:
        raise ValueError("mover_threshold_pct must be >= control_ceiling_pct")

    audits_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in audit_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or not row.get("audited_at_utc"):
            continue
        audits_by_symbol[symbol].append(row)

    for rows in audits_by_symbol.values():
        rows.sort(key=lambda item: _dt(item.get("audited_at_utc")))

    evidence: list[dict[str, Any]] = []
    horizon = timedelta(hours=horizon_hours)

    for row in feature_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or not row.get("captured_at_utc"):
            continue

        move = current_move_pct(row)
        if move is None or abs(move) >= pre_expansion_abs_move_pct:
            continue

        features = extract_numeric_features(row)
        if not features:
            continue

        captured = _dt(row.get("captured_at_utc"))
        end = captured + horizon
        symbol_audits = audits_by_symbol.get(symbol, [])

        for direction, audit_direction in DIRECTION_TO_AUDIT.items():
            future = [
                audit
                for audit in symbol_audits
                if audit_direction == _audit_direction(audit)
                and captured < _dt(audit.get("audited_at_utc")) <= end
            ]
            major = [
                audit
                for audit in future
                if (_threshold(audit) or 0.0) >= mover_threshold_pct
            ]
            any_mover = [
                audit
                for audit in future
                if (_threshold(audit) or 0.0) >= control_ceiling_pct
            ]

            if major:
                label = "MOVER"
                outcome_at = min(_dt(item.get("audited_at_utc")) for item in major)
            elif not any_mover:
                label = "CONTROL"
                outcome_at = end
            else:
                # Explicit grey zone: informative, but not clean enough to train the
                # big-mover-vs-control signature.
                continue

            evidence.append(
                {
                    "symbol": symbol,
                    "captured_at_utc": captured.isoformat(),
                    "outcome_at_utc": outcome_at.isoformat(),
                    "label": label,
                    "direction": direction,
                    "is_pre_expansion": True,
                    "current_24h_move_pct": move,
                    "scanner_direction": row.get("direction"),
                    "scanner_state": row.get("state"),
                    "features": features,
                }
            )

    return evidence


def build_live_candidates(feature_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score every currently captured symbol in both directions.

    This intentionally does not require the legacy scanner to have declared LONG or
    SHORT first. The old direction is retained only as context; it cannot grant
    permission or remove the opposite-direction research candidate.
    """
    candidates: list[dict[str, Any]] = []
    for row in feature_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        features = extract_numeric_features(row)
        if not features:
            continue
        move = current_move_pct(row)
        for direction in ("LONG", "SHORT"):
            candidates.append(
                {
                    "symbol": symbol,
                    "direction": direction,
                    "change_24h_pct": move,
                    "scanner_direction": row.get("direction"),
                    "scanner_state": row.get("state"),
                    "features": features,
                }
            )
    return candidates


def summarize_evidence(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, dict[str, int]] = {
        "LONG": {"MOVER": 0, "CONTROL": 0},
        "SHORT": {"MOVER": 0, "CONTROL": 0},
    }
    symbols: dict[str, dict[str, set[str]]] = {
        "LONG": {"MOVER": set(), "CONTROL": set()},
        "SHORT": {"MOVER": set(), "CONTROL": set()},
    }
    total = 0
    for row in rows:
        direction = str(row.get("direction") or "").upper()
        label = str(row.get("label") or "").upper()
        if direction not in counts or label not in counts[direction]:
            continue
        total += 1
        counts[direction][label] += 1
        symbol = str(row.get("symbol") or "").upper()
        if symbol:
            symbols[direction][label].add(symbol)

    return {
        "rows": total,
        "counts": counts,
        "unique_symbols": {
            direction: {
                label: len(values)
                for label, values in labels.items()
            }
            for direction, labels in symbols.items()
        },
    }


class SupabaseRestReader:
    """Small read/write adapter using the production service-role Data API.

    The Big-Mover engine remains shadow-only. This adapter never touches order or
    execution endpoints.
    """

    def __init__(self, url: str, key: str, *, timeout_seconds: int = 30) -> None:
        if not url or not key:
            raise ValueError("Supabase URL and key are required")
        self.url = url.rstrip("/")
        self.key = key
        self.timeout_seconds = timeout_seconds

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        result = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            result["Prefer"] = prefer
        return result

    def get_rows(
        self,
        table: str,
        params: dict[str, str],
        *,
        page_size: int = 1000,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        start = 0
        while True:
            end = start + page_size - 1
            response = requests.get(
                f"{self.url}/rest/v1/{table}",
                params=params,
                headers={**self._headers(), "Range": f"{start}-{end}"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, list):
                raise RuntimeError(f"{table} returned a non-list payload")
            rows.extend(item for item in page if isinstance(item, dict))
            if len(page) < page_size:
                break
            start += page_size
        return rows

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        response = requests.post(
            f"{self.url}/rest/v1/{table}",
            params={"on_conflict": "observation_id"},
            headers=self._headers(prefer="resolution=ignore-duplicates,return=minimal"),
            json=rows,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return len(rows)


def load_shadow_inputs(
    reader: SupabaseRestReader,
    *,
    now: datetime | None = None,
    training_days: int = 21,
    horizon_hours: int = 24,
    mover_threshold_pct: float = 10.0,
    control_ceiling_pct: float = 5.0,
    pre_expansion_abs_move_pct: float = 5.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], EvidenceWindow, dict[str, Any]]:
    """Load production evidence and current feature rows without writing anything."""
    latest_audit = reader.get_rows(
        "alpha_hunter_missed_mover_audit",
        {
            "select": "audited_at_utc",
            "order": "audited_at_utc.desc",
            "limit": "1",
        },
    )
    if not latest_audit:
        raise RuntimeError("no missed-mover audit evidence is available")

    latest_audit_at = _dt(latest_audit[0]["audited_at_utc"])
    training_end = latest_audit_at - timedelta(hours=horizon_hours)
    training_start = training_end - timedelta(days=training_days)
    audit_end = training_end + timedelta(hours=horizon_hours)
    reference_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    feature_select = ",".join(
        (
            "signal_id",
            "run_id",
            "symbol",
            "captured_at_utc",
            "state",
            "direction",
            *CORE_FEATURE_COLUMNS,
            "features",
            "source_payload",
        )
    )
    training_features = reader.get_rows(
        "alpha_hunter_signal_features",
        {
            "select": feature_select,
            "captured_at_utc": f"gte.{training_start.isoformat()}",
            "and": f"(captured_at_utc.lte.{training_end.isoformat()})",
            "order": "captured_at_utc.asc",
        },
    )
    audits = reader.get_rows(
        "alpha_hunter_missed_mover_audit",
        {
            "select": (
                "symbol,audited_at_utc,mover_direction,current_24h_move_pct,"
                "mover_threshold_pct,mover_class,measurement_quality"
            ),
            "audited_at_utc": f"gte.{training_start.isoformat()}",
            "and": f"(audited_at_utc.lte.{audit_end.isoformat()})",
            "order": "audited_at_utc.asc",
        },
    )

    evidence = build_forward_evidence(
        training_features,
        audits,
        horizon_hours=horizon_hours,
        mover_threshold_pct=mover_threshold_pct,
        control_ceiling_pct=control_ceiling_pct,
        pre_expansion_abs_move_pct=pre_expansion_abs_move_pct,
    )

    latest_feature = reader.get_rows(
        "alpha_hunter_signal_features",
        {
            "select": "run_id,captured_at_utc",
            "order": "captured_at_utc.desc",
            "limit": "1",
        },
    )
    if not latest_feature:
        raise RuntimeError("no live feature rows are available")
    latest_run_id = str(latest_feature[0].get("run_id") or "")
    if not latest_run_id:
        raise RuntimeError("latest feature row has no run_id")

    live_features = reader.get_rows(
        "alpha_hunter_signal_features",
        {
            "select": feature_select,
            "run_id": f"eq.{latest_run_id}",
            "order": "symbol.asc",
        },
    )
    live_candidates = build_live_candidates(live_features)

    staleness_hours = max(
        0.0,
        (reference_now - latest_audit_at).total_seconds() / 3600.0,
    )
    window = EvidenceWindow(
        training_start_utc=training_start.isoformat(),
        training_end_utc=training_end.isoformat(),
        latest_audit_utc=latest_audit_at.isoformat(),
        horizon_hours=horizon_hours,
        mover_threshold_pct=mover_threshold_pct,
        control_ceiling_pct=control_ceiling_pct,
        pre_expansion_abs_move_pct=pre_expansion_abs_move_pct,
        audit_staleness_hours=round(staleness_hours, 3),
    )
    context = {
        "latest_feature_run_id": latest_run_id,
        "latest_feature_at_utc": str(latest_feature[0].get("captured_at_utc")),
        "training_feature_rows": len(training_features),
        "audit_rows": len(audits),
        "live_feature_rows": len(live_features),
        "live_directional_candidates": len(live_candidates),
    }
    return evidence, live_candidates, window, context
