"""Isolated P0 hourly scoring-only successor, never an execution engine.

Consumes a complete *already persisted* RENDER_CRON parent, its exact child rows,
the exact-run feature rows, and a versioned offline trained-profile artifact.
No database connection, clock-derived source timestamp, market polling, new
universe scan, SQL write, paper admission or exchange/order API is provided.

An input bundle must be prepared separately from mature training outcomes.
This Python v0.1 scoring path is NOT equivalent to deployed DB model v0.2;
model parity and production profile export remain release blockers.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Iterable

from alpha_hunter.big_mover_evidence import build_live_candidates
from alpha_hunter.big_mover_signature import (
    ENGINE_VERSION,
    DirectionalSignature,
    FeatureProfile,
    rank_candidates,
)

PROFILE_CONTRACT = "alpha-hunter-hourly-profile-v0.1"
PARENT_CONTRACT = "snapshot-parent-v0.2"
MAX_SOURCE_AGE = timedelta(minutes=90)
MAX_PROFILE_AGE = timedelta(hours=8)
MAX_FUTURE_CLOCK_SKEW = timedelta(seconds=5)
MIN_OUTCOME_MATURITY = timedelta(hours=24)


class HourlyScoringBlocked(ValueError):
    """A failed source/profile/persistence gate: no scores may be published."""


def _required_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise HourlyScoringBlocked(f"{label}: missing timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HourlyScoringBlocked(f"{label}: invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise HourlyScoringBlocked(f"{label}: timezone required")
    return parsed.astimezone(timezone.utc)


def _finite_positive(value: Any, label: str, *, signed: bool = False, zero_allowed: bool = False) -> float:
    if isinstance(value, bool):
        raise HourlyScoringBlocked(f"{label}: invalid boolean number")
    try:
        n = float(value)
    except (ValueError, TypeError) as exc:
        raise HourlyScoringBlocked(f"{label}: invalid number") from exc
    if not isfinite(n) or (not signed and n < 0) or (not signed and not zero_allowed and n == 0):
        raise HourlyScoringBlocked(f"{label}: invalid range")
    return n


def _hash_payload(data: dict[str, Any]) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_profile_bundle(
    signatures: Iterable[DirectionalSignature],
    *,
    trained_at_utc: str,
    training_end_utc: str,
    scientific_fingerprint_sha256: str,
) -> dict[str, Any]:
    """Export a digest-checked research artifact from pre-trained signatures.

    This digest detects accidental alteration but does NOT authenticate origin,
    validate training labels or prove equivalence to the SQL v0.2 model.
    """
    data = {
        "contract": PROFILE_CONTRACT,
        "engine_version": ENGINE_VERSION,
        "trained_at_utc": trained_at_utc,
        "training_end_utc": training_end_utc,
        "scientific_fingerprint_sha256": scientific_fingerprint_sha256,
        "signatures": [asdict(s) for s in signatures],
        "shadow_only": True,
        "trade_permission": False,
        "profile_source": "offline_pre_expansion_python_research_v0.1",
    }
    # asdict preserves tuple fields; canonical JSON artifacts contain lists.
    # Validate the wire-format representation, not an in-memory Python tuple.
    data = json.loads(json.dumps(data, allow_nan=False))
    artifact = {**data, "digest_sha256": _hash_payload(data)}
    _parse_profile_bundle(artifact)
    return artifact


def _parse_profile_bundle(bundle: dict[str, Any]) -> tuple[dict[str, DirectionalSignature], datetime, datetime]:
    if not isinstance(bundle, dict) or bundle.get("contract") != PROFILE_CONTRACT:
        raise HourlyScoringBlocked("profile contract is missing or incompatible")
    if bundle.get("engine_version") != ENGINE_VERSION or bundle.get("profile_source") != "offline_pre_expansion_python_research_v0.1":
        raise HourlyScoringBlocked("profile engine provenance is incompatible")
    if bundle.get("shadow_only") is not True or bundle.get("trade_permission") is not False:
        raise HourlyScoringBlocked("profile attempts to grant trade authority")
    digest = bundle.get("digest_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise HourlyScoringBlocked("profile digest is missing")
    payload = {k: v for k, v in bundle.items() if k != "digest_sha256"}
    try:
        computed = _hash_payload(payload)
    except (TypeError, ValueError) as exc:
        raise HourlyScoringBlocked("profile contains non-serializable values") from exc
    if digest != computed:
        raise HourlyScoringBlocked("profile artifact digest mismatch")
    trained = _required_utc(bundle.get("trained_at_utc"), "profile trained")
    training_end = _required_utc(bundle.get("training_end_utc"), "training end")
    if training_end > trained - MIN_OUTCOME_MATURITY:
        raise HourlyScoringBlocked("training outcome horizon is not mature")
    fingerprint = bundle.get("scientific_fingerprint_sha256")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise HourlyScoringBlocked("invalid scientific fingerprint")

    raw_signatures = bundle.get("signatures")
    if not isinstance(raw_signatures, list) or len(raw_signatures) != 2:
        raise HourlyScoringBlocked("one LONG and one SHORT profile are required")
    signatures: dict[str, DirectionalSignature] = {}
    for item in raw_signatures:
        if not isinstance(item, dict):
            raise HourlyScoringBlocked("invalid directional signature")
        direction = item.get("direction")
        if direction not in ("LONG", "SHORT") or direction in signatures:
            raise HourlyScoringBlocked("duplicate or unknown signature direction")
        if item.get("version") != ENGINE_VERSION or item.get("shadow_only") is not True or item.get("trade_permission") is not False:
            raise HourlyScoringBlocked("signature provenance or permissions invalid")
        movers, controls = item.get("mover_examples"), item.get("control_examples")
        if not all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in (movers, controls)):
            raise HourlyScoringBlocked("signature lacks both training classes")
        profiles = item.get("feature_profiles")
        if not isinstance(profiles, list) or not profiles:
            raise HourlyScoringBlocked("signature has no weighted features")
        typed_profiles = []
        names = set()
        for f in profiles:
            if not isinstance(f, dict) or not isinstance(f.get("name"), str) or not f["name"] or f["name"] in names:
                raise HourlyScoringBlocked("malformed or repeated profile feature")
            names.add(f["name"])
            fields = {name: _finite_positive(f.get(name), name, signed=name in ("mover_median","control_median")) for name in (
                "mover_median", "control_median", "mover_scale", "control_scale", "separation", "coverage", "weight"
            )}
            if fields["coverage"] > 1:
                raise HourlyScoringBlocked("feature coverage exceeds 1")
            typed_profiles.append(FeatureProfile(name=f["name"], **fields))
        total_weight = _finite_positive(item.get("total_weight"), "profile total weight")
        if abs(sum(f.weight for f in typed_profiles) - total_weight) > 1e-7 * max(1, total_weight):
            raise HourlyScoringBlocked("profile weight sum mismatch")
        signatures[direction] = DirectionalSignature(
            version=ENGINE_VERSION, direction=direction, mover_examples=movers,
            control_examples=controls, feature_profiles=tuple(typed_profiles),
            total_weight=total_weight,
        )
    return signatures, trained, training_end


def score_verified_hourly(
    *,
    parent: dict[str, Any],
    children: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    profile_bundle: dict[str, Any],
    universe_scan_config: dict[str, Any],
    expected_scientific_fingerprint: str,
    now_utc: datetime,
) -> dict[str, Any]:
    """Build *research-only* scores after strict exact-run persistence verification.

    Does not attempt to repair, backfill, skip, or replace failed canonical runs.
    Caller must pass the newest canonical source; this function cannot prove
    latest-run selection or independent source authenticity by itself.
    """
    if not isinstance(now_utc, datetime) or now_utc.tzinfo is None:
        raise HourlyScoringBlocked("evaluation clock must be timezone-aware")
    now = now_utc.astimezone(timezone.utc)
    if not isinstance(parent, dict) or not isinstance(parent.get("payload"), dict):
        raise HourlyScoringBlocked("canonical parent missing")
    payload = parent["payload"]
    identity = payload.get("validation_identity")
    if not isinstance(identity, dict) or identity.get("run_source") != "RENDER_CRON" or identity.get("runtime_role") != "RENDER_CRON":
        raise HourlyScoringBlocked("source identity is not canonical Render cron")
    fingerprint = identity.get("scientific_fingerprint_sha256")
    if not isinstance(expected_scientific_fingerprint, str) or len(expected_scientific_fingerprint) != 64 or fingerprint != expected_scientific_fingerprint:
        raise HourlyScoringBlocked("frozen scientific fingerprint mismatch")
    if payload.get("_storage_contract") != PARENT_CONTRACT:
        raise HourlyScoringBlocked("cannot validate legacy parent-child publication")
    run_id = parent.get("run_id")
    if not isinstance(run_id, str) or not run_id or payload.get("run_id") != run_id:
        raise HourlyScoringBlocked("parent and payload run identity mismatch")
    expected_count = parent.get("symbol_count")
    if not isinstance(expected_count, int) or isinstance(expected_count, bool) or not (1 <= expected_count <= 2000):
        raise HourlyScoringBlocked("invalid expected symbol count")
    if parent.get("error_count") != 0:
        raise HourlyScoringBlocked("scanner reported errors")
    collected = _required_utc(parent.get("collected_at_utc"), "parent collected")
    age = now - collected
    if age < -MAX_FUTURE_CLOCK_SKEW or age > MAX_SOURCE_AGE:
        raise HourlyScoringBlocked("canonical evidence stale or from future")

    stubs = payload.get("symbols")
    if not isinstance(stubs, list) or len(stubs) != expected_count:
        raise HourlyScoringBlocked("parent symbol stub count mismatch")
    symbols = [x.get("symbol") if isinstance(x, dict) else None for x in stubs]
    if any(not isinstance(s, str) or not s for s in symbols) or len(set(symbols)) != expected_count:
        raise HourlyScoringBlocked("duplicate or invalid parent symbols")
    expected_symbols = set(symbols)
    if not isinstance(children, list) or len(children) != expected_count:
        raise HourlyScoringBlocked("incomplete canonical child persistence")
    child_symbols = set()
    for child in children:
        if not isinstance(child, dict) or child.get("run_id") != run_id:
            raise HourlyScoringBlocked("child run identity mismatch")
        symbol = child.get("symbol")
        detail = child.get("payload")
        if (
            not isinstance(symbol, str) or symbol not in expected_symbols
            or symbol in child_symbols or not isinstance(detail, dict)
            or detail.get("symbol") != symbol
            or child.get("error") not in (None, "")
        ):
            raise HourlyScoringBlocked("invalid or duplicated canonical child evidence")
        child_symbols.add(symbol)
    if child_symbols != expected_symbols:
        raise HourlyScoringBlocked("canonical child set mismatch")

    if not isinstance(feature_rows, list) or len(feature_rows) != expected_count:
        raise HourlyScoringBlocked("incomplete exact-run signal feature persistence")
    seen_features = set()
    for row in feature_rows:
        if not isinstance(row, dict) or row.get("run_id") != run_id:
            raise HourlyScoringBlocked("feature run identity mismatch")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or symbol not in expected_symbols or symbol in seen_features:
            raise HourlyScoringBlocked("missing, unknown or duplicated feature symbol")
        seen_features.add(symbol)
        if _required_utc(row.get("captured_at_utc"), "feature captured") != collected:
            raise HourlyScoringBlocked("feature timestamp is not exact canonical parent time")
        if not isinstance(row.get("source_payload"), dict) or "change_24h_pct" not in row["source_payload"]:
            raise HourlyScoringBlocked("missing observed market move")
    if seen_features != expected_symbols:
        raise HourlyScoringBlocked("feature symbol set mismatch")

    signatures, trained, training_end = _parse_profile_bundle(profile_bundle)
    if profile_bundle.get("scientific_fingerprint_sha256") != expected_scientific_fingerprint:
        raise HourlyScoringBlocked("profile and source scientific identity differ")
    if now - trained > MAX_PROFILE_AGE or trained > collected or trained > now or training_end > collected - MIN_OUTCOME_MATURITY:
        raise HourlyScoringBlocked("profile stale, future-trained or not mature for this source")
    if not isinstance(universe_scan_config, dict):
        raise HourlyScoringBlocked("scoring lifecycle configuration missing")

    candidates = build_live_candidates(feature_rows)
    if len(candidates) != expected_count * 2:
        raise HourlyScoringBlocked("source features could not yield both research directions")
    rankings = rank_candidates(candidates, signatures.values(), universe_scan_config=universe_scan_config)
    if len(rankings) != expected_count * 2:
        raise HourlyScoringBlocked("incomplete research scoring result")

    return {
        "mode": "P0_HOURLY_SCORING_ONLY_ISOLATED_RESEARCH",
        "status": "EXACT_RUN_EVIDENCE_VERIFIED_FOR_RESEARCH",
        "canonical_source": "RENDER_CRON",
        "source_run_id": run_id,
        "source_collected_at_utc": collected.isoformat(),
        "source_age_seconds": round(age.total_seconds(), 3),
        "expected_symbols": expected_count,
        "persisted_child_count": len(children),
        "persisted_feature_count": len(feature_rows),
        "profile_trained_at_utc": trained.isoformat(),
        "profile_training_end_utc": training_end.isoformat(),
        "profile_digest_sha256": profile_bundle["digest_sha256"],
        "scoring_engine_version": ENGINE_VERSION,
        "model_parity_with_deployed_sql_v02": "NOT_VERIFIED",
        "shadow_only": True,
        "trade_permission": False,
        "exchange_authority": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
        "ranked_research_only": [score.to_dict() for score in rankings],
    }
