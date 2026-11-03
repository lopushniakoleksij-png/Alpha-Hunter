"""P0 signed evidence -> local PostgREST -> immutable historical gate.

ISOLATED VALIDATION ONLY. HTTP GET is hard-fixed to localhost:3000.
The detached Ed25519 trust key MUST come from a separately trusted source,
never from the evidence packet. A valid signature attests the manifest's
origin under that key, not the truth of market quotes or exchange fills.
No producer, trading, database write, deployment, or credential path.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SOURCE = Path(__file__).with_name("p03_historical_successor_fail_closed_v01.py")
spec = importlib.util.spec_from_file_location("p03_history_contract", SOURCE)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)

LOCAL_ORIGIN = "http://127.0.0.1:3000"
RID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
HEX256 = re.compile(r"[0-9a-f]{64}\Z")


class EvidenceRejected(RuntimeError):
    """Fail closed without modifying any evidence."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EvidenceRejected("HTTP_REDIRECT_FORBIDDEN")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def sha256(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def reject(code, scanned=0, positions=0):
    return {
        "status": "EVIDENCE_NO_GO",
        "blockers": (code,),
        "scans_checked": scanned,
        "positions_checked": positions,
        "signed_manifest_integrity_checked": False,
        "historical_evidence_complete": False,
        "source_market_quotes_authenticated": False,
        "original_records_unchanged": True,
        "paper_only": True,
        "trade_permission": False,
        "exchange_authority": False,
        "production_release_authorized": False,
    }


def verify_manifest(manifest, signature_b64, trusted_ed25519_public_hex):
    """Trusted key is an independent argument; self-declared signer is ignored."""
    if not isinstance(manifest, dict):
        raise EvidenceRejected("SIGNED_MANIFEST_MISSING")
    if not isinstance(trusted_ed25519_public_hex, str):
        raise EvidenceRejected("TRUSTED_PUBLIC_KEY_MISSING")
    try:
        public = bytes.fromhex(trusted_ed25519_public_hex)
        signature = base64.b64decode(signature_b64, validate=True)
        if len(public) != 32 or len(signature) != 64:
            raise ValueError("invalid Ed25519 length")
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature, canonical(manifest))
    except (TypeError, ValueError, InvalidSignature, OverflowError) as exc:
        raise EvidenceRejected("DETACHED_MANIFEST_SIGNATURE_INVALID") from exc
    if (manifest.get("kind") not in ("SYNTHETIC_ISOLATED", "EXTERNAL_CUSTODY")
            or manifest.get("coverage_attested") is not True
            or not isinstance(manifest.get("packet_sha256"), str)
            or not HEX256.fullmatch(manifest["packet_sha256"])):
        raise EvidenceRejected("SIGNED_MANIFEST_COVERAGE_INVALID")
    ids = manifest.get("required_run_ids")
    symbols = manifest.get("expected_symbols_by_run")
    if (not isinstance(ids, list) or not ids or len(ids) > 10000
            or not all(isinstance(rid, str) and RID.fullmatch(rid) for rid in ids)
            or len(set(ids)) != len(ids)
            or not isinstance(symbols, dict) or set(symbols) != set(ids)):
        raise EvidenceRejected("SIGNED_RUN_CENSUS_INVALID")
    for rid, rows in symbols.items():
        if (not isinstance(rows, list) or not rows or len(rows) >= 2000
                or len(set(rows)) != len(rows)
                or not all(isinstance(s, str) and s.strip() for s in rows)):
            raise EvidenceRejected("SIGNED_SYMBOL_CENSUS_INVALID")
    if (not isinstance(manifest.get("positions"), list)
            or not isinstance(manifest.get("origin_attestations"), dict)):
        raise EvidenceRejected("SIGNED_POSITION_CENSUS_INVALID")


def local_get(table, run_id, select, limit):
    """Never any external hostname, credential, redirect or HTTP mutation."""
    if os.getenv("AH_LOCAL_POSTGREST_ONLY") != "1":
        raise EvidenceRejected("ISOLATED_POSTGREST_OPT_IN_MISSING")
    if table not in {
        "alpha_hunter_snapshots", "alpha_hunter_symbol_snapshots",
        "alpha_hunter_paper_exit_attempts_v04",
    } or not RID.fullmatch(run_id):
        raise EvidenceRejected("HTTP_SCOPE_INVALID")
    q = urlencode({"select": select, "run_id" if table !=
                    "alpha_hunter_paper_exit_attempts_v04"
                    else "source_run_id": f"eq.{run_id}", "limit": str(limit)})
    url = LOCAL_ORIGIN + "/" + table + "?" + q
    opener = build_opener(NoRedirect())
    try:
        with opener.open(Request(url, method="GET", headers={
                "Accept": "application/json",
                "User-Agent": "P03-Local-ReadOnly-History/1.0",
        }), timeout=10) as response:
            if response.status != 200:
                raise EvidenceRejected("LOCAL_POSTGREST_READ_FAILED")
            data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise EvidenceRejected("LOCAL_POSTGREST_RESPONSE_TOO_LARGE")
    except EvidenceRejected:
        raise
    except Exception as exc:
        raise EvidenceRejected("LOCAL_POSTGREST_READ_FAILED") from exc
    try:
        rows = json.loads(data)
        if not isinstance(rows, list) or len(rows) >= limit:
            raise EvidenceRejected("LOCAL_POSTGREST_READ_TRUNCATED")
    except (ValueError, TypeError) as exc:
        raise EvidenceRejected("LOCAL_POSTGREST_INVALID_JSON") from exc
    return rows


def collect_packet(manifest):
    """Source values are real isolated PostgREST GET response rows, not mocks."""
    parents, children, receipts = [], [], []
    for rid in manifest["required_run_ids"]:
        p = local_get("alpha_hunter_snapshots", rid,
                      "run_id,collected_at_utc,symbol_count,error_count,payload", 3)
        for row in p:
            payload = row.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            identity = payload.get("validation_identity")
            identity = identity if isinstance(identity, dict) else {}
            parents.append({
                "run_id": row.get("run_id"),
                "collected_at_utc": row.get("collected_at_utc"),
                "symbol_count": row.get("symbol_count"),
                "error_count": row.get("error_count"),
                "publication_state": payload.get("_canonical_publication_state"),
                "run_source": identity.get("run_source"),
                "expected_symbols": manifest["expected_symbols_by_run"][rid],
            })
        for row in local_get("alpha_hunter_symbol_snapshots", rid,
                             "run_id,symbol,payload", 2000):
            payload = row.get("payload")
            children.append({
                "run_id": row.get("run_id"), "symbol": row.get("symbol"),
                "payload": {"symbol": payload.get("symbol")
                            if isinstance(payload, dict) else None},
            })
        receipts.extend(local_get(
            "alpha_hunter_paper_exit_attempts_v04", rid,
            "entry_order_id,source_run_id,decision_id,symbol,direction,"
            "observed_at_utc,outcome,blockers,paper_only,exchange_authority,"
            "trade_permission,order_path", 2000))
    parents.sort(key=lambda r: (str(r.get("run_id")), str(r.get("collected_at_utc"))))
    children.sort(key=lambda r: (str(r.get("run_id")), str(r.get("symbol"))))
    receipts.sort(key=lambda r: (str(r.get("source_run_id")),
                                 str(r.get("entry_order_id")),
                                 str(r.get("observed_at_utc"))))
    return {"parents": parents, "children": children, "receipts": receipts,
            "positions": manifest["positions"]}


def evaluate_local_signed_history(*, manifest, signature_b64,
                                  trusted_ed25519_public_hex):
    """Evaluate only under a pre-approved detached trust anchor."""
    try:
        verify_manifest(manifest, signature_b64, trusted_ed25519_public_hex)
        packet = collect_packet(manifest)
        if sha256(packet) != manifest["packet_sha256"]:
            raise EvidenceRejected("SIGNED_PACKET_DIGEST_MISMATCH")
        verdict = contract.evaluate_history(
            **packet,
            required_run_ids=manifest["required_run_ids"],
            origin_attestations=manifest["origin_attestations"],
            coverage_attested=True,
            max_gap_minutes=35,
        )
        accepted = verdict["successor_historical_evidence_pass"]
        return {
            **verdict,
            "status": ("SYNTHETIC_HISTORY_CONTRACT_PASS_ONLY"
                       if accepted and manifest["kind"] == "SYNTHETIC_ISOLATED"
                       else "EXTERNAL_CUSTODY_DIAGNOSTIC_ONLY"
                       if accepted else "EVIDENCE_NO_GO"),
            "signed_manifest_integrity_checked": True,
            "historical_evidence_complete": accepted,
            "source_market_quotes_authenticated": False,
            "production_release_authorized": False,
            "trade_permission": False,
            "exchange_authority": False,
            "paper_only": True,
        }
    except EvidenceRejected as exc:
        return reject(str(exc))
