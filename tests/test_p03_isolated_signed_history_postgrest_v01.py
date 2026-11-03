"""Real isolated PostgreSQL 16/17 + PostgREST history validator tests.

All data is synthetic; no production URLs, keys, provider access, real orders
or real signer credentials. An ephemeral Ed25519 key is created only in memory.
"""
import base64
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
pytest.importorskip('cryptography')

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_canonical_snapshot_postgrest_http_20261017 import real_http_db

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ops/reviews/p03_isolated_signed_history_postgrest_v01.py"
spec = spec_from_file_location("p03_verified_history_postgrest", SRC)
validator = module_from_spec(spec)
spec.loader.exec_module(validator)

SCANS = [("r1", "2026-11-03T08:02:00Z", "2026-11-03T08:03:00Z"),
         ("r2", "2026-11-03T08:22:00Z", "2026-11-03T08:23:00Z"),
         ("r3", "2026-11-03T08:42:00Z", "2026-11-03T08:43:00Z")]
SYMS = ("SOONUSDT", "NIGHTUSDT")


def seed(conn, scans=SCANS):
    for rid, scan, observed in scans:
        payload = json.dumps({
            "validation_identity": {"run_source": "RENDER_CRON"},
            "_canonical_publication_state": "VERIFIED",
        })
        conn.execute(
            "INSERT INTO public.alpha_hunter_snapshots "
            "(run_id,collected_at_utc,version,product_type,symbol_count,"
            "error_count,payload) VALUES (%s,%s,'synthetic','test',2,0,%s::jsonb)",
            (rid, scan, payload),
        )
        for symbol in SYMS:
            conn.execute(
                "INSERT INTO public.alpha_hunter_symbol_snapshots "
                "(run_id,symbol,payload) VALUES (%s,%s,%s::jsonb)",
                (rid, symbol, json.dumps({"symbol": symbol})),
            )
        conn.execute(
            "INSERT INTO public.alpha_hunter_paper_exit_attempts_v04 "
            "(entry_order_id,source_run_id,decision_id,symbol,direction,"
            "observed_at_utc,outcome,blockers,paper_only,exchange_authority,"
            "trade_permission,order_path) "
            "VALUES ('entry-1',%s,'decision-1','SOONUSDT','SHORT',%s,"
            "'NO_TRIGGER','[]'::jsonb,true,false,false,'NONE')",
            (rid, observed),
        )


def position_manifest():
    return {
        "kind": "SYNTHETIC_ISOLATED",
        "coverage_attested": True,
        "required_run_ids": [x[0] for x in SCANS],
        "expected_symbols_by_run": {x[0]: list(SYMS) for x in SCANS},
        "positions": [{
            "entry_order_id": "entry-1", "decision_id": "decision-1",
            "symbol": "SOONUSDT", "direction": "SHORT",
            "entry_completed_at_utc": "2026-11-03T08:00:00Z",
        }],
        "origin_attestations": {"entry-1": {
            "accepted": True, "artifact_sha256": "a" * 64,
        }},
        "packet_sha256": "0" * 64,
    }


def sealed_fixture():
    """Synthetic signer never leaves memory, is NOT a production trust anchor."""
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    return key, pub


def signed_bundle(manifest, key, *, compute_digest=True):
    if compute_digest:
        manifest["packet_sha256"] = validator.sha256(
            validator.collect_packet(manifest))
    signed = base64.b64encode(
        key.sign(validator.canonical(manifest))).decode("ascii")
    return signed


def run(manifest, signature, pub):
    return validator.evaluate_local_signed_history(
        manifest=manifest,
        signature_b64=signature,
        trusted_ed25519_public_hex=pub,
    )


def test_real_local_postgrest_complete_signed_synthetic_history_passes(real_http_db):
    _, conn = real_http_db
    seed(conn)
    manifest = position_manifest()
    key, pub = sealed_fixture()
    signature = signed_bundle(manifest, key)
    result = run(manifest, signature, pub)
    assert result["status"] == "SYNTHETIC_HISTORY_CONTRACT_PASS_ONLY"
    assert result["historical_evidence_complete"] is True
    assert result["signed_manifest_integrity_checked"] is True
    assert result["scans_checked"] == 3
    assert result["positions_checked"] == 1
    assert result["trade_permission"] is False
    assert result["production_release_authorized"] is False
    assert result["source_market_quotes_authenticated"] is False
    assert conn.execute("SELECT count(*) FROM public.alpha_hunter_snapshots").fetchone()[0] == 3


def test_unsigned_or_wrong_public_key_is_blocked_before_http(real_http_db):
    _, conn = real_http_db
    seed(conn)
    manifest = position_manifest()
    key, pub = sealed_fixture()
    signature = signed_bundle(manifest, key)
    other_key, wrong_pub = sealed_fixture()
    assert "DETACHED_MANIFEST_SIGNATURE_INVALID" in run(
        manifest, signature, wrong_pub)["blockers"]
    assert "TRUSTED_PUBLIC_KEY_MISSING" in run(
        manifest, signature, None)["blockers"]
    altered = json.loads(json.dumps(manifest))
    altered["coverage_attested"] = False
    assert "DETACHED_MANIFEST_SIGNATURE_INVALID" in run(
        altered, signature, pub)["blockers"]
    assert conn.execute("SELECT count(*) FROM public.alpha_hunter_snapshots").fetchone()[0] == 3


def test_signed_replay_fails_on_child_tamper_without_repair(real_http_db):
    _, conn = real_http_db
    seed(conn)
    manifest = position_manifest()
    key, pub = sealed_fixture()
    signature = signed_bundle(manifest, key)
    conn.execute("DELETE FROM public.alpha_hunter_symbol_snapshots "
                 "WHERE run_id='r2' AND symbol='NIGHTUSDT'")
    result = run(manifest, signature, pub)
    assert result["status"] == "EVIDENCE_NO_GO"
    assert "SIGNED_PACKET_DIGEST_MISMATCH" in result["blockers"]
    assert conn.execute("SELECT count(*) FROM public.alpha_hunter_symbol_snapshots "
                        "WHERE run_id='r2'").fetchone()[0] == 1


def test_even_resigned_missing_children_never_passes(real_http_db):
    _, conn = real_http_db
    seed(conn)
    conn.execute("DELETE FROM public.alpha_hunter_symbol_snapshots "
                 "WHERE run_id='r2' AND symbol='NIGHTUSDT'")
    manifest = position_manifest()
    key, pub = sealed_fixture()
    signature = signed_bundle(manifest, key)
    result = run(manifest, signature, pub)
    assert result["status"] == "EVIDENCE_NO_GO"
    assert "HISTORICAL_CHILDREN_INCOMPLETE" in result["blockers"]
    assert result["trade_permission"] is False


def test_older_40m_gap_rejected_despite_recent_healthy_receipt(real_http_db):
    _, conn = real_http_db
    seed(conn, scans=[
        SCANS[0], ("r2", "2026-11-03T08:42:00Z", "2026-11-03T08:43:00Z"),
        ("r3", "2026-11-03T09:02:00Z", "2026-11-03T09:03:00Z")])
    manifest = position_manifest()
    key, pub = sealed_fixture()
    signature = signed_bundle(manifest, key)
    result = run(manifest, signature, pub)
    assert "HISTORICAL_MONITORING_GAP_OVER_35M" in result["blockers"]
    assert result["historical_evidence_complete"] is False
    assert result["original_records_unchanged"] is True


def test_missing_middle_receipt_rejected_and_unmodified(real_http_db):
    _, conn = real_http_db
    seed(conn)
    conn.execute("DELETE FROM public.alpha_hunter_paper_exit_attempts_v04 "
                 "WHERE source_run_id='r2'")
    manifest = position_manifest()
    key, pub = sealed_fixture()
    signature = signed_bundle(manifest, key)
    result = run(manifest, signature, pub)
    assert "HISTORICAL_POSITION_RECEIPT_COVERAGE_FAILED" in result["blockers"]
    assert conn.execute("SELECT count(*) FROM "
                        "public.alpha_hunter_paper_exit_attempts_v04").fetchone()[0] == 2


def test_ambiguous_first_receipt_cannot_be_relabelled(real_http_db):
    _, conn = real_http_db
    seed(conn)
    conn.execute("UPDATE public.alpha_hunter_paper_exit_attempts_v04 "
                 "SET outcome='AMBIGUOUS',observed_at_utc='2026-11-03T08:00:00Z' "
                 "WHERE source_run_id='r1'")
    manifest = position_manifest()
    key, pub = sealed_fixture()
    signature = signed_bundle(manifest, key)
    result = run(manifest, signature, pub)
    assert "UNUSABLE_HISTORICAL_RECEIPT" in result["blockers"]
    assert "AMBIGUOUS_FIRST_ENTRY_ORDERING" in result["blockers"]
    assert conn.execute("SELECT outcome FROM public.alpha_hunter_paper_exit_attempts_v04 "
                        "WHERE source_run_id='r1'").fetchone()[0] == "AMBIGUOUS"


def test_missing_parent_fails_even_if_its_rows_were_deleted(real_http_db):
    _, conn = real_http_db
    seed(conn)
    conn.execute("DELETE FROM public.alpha_hunter_paper_exit_attempts_v04 "
                 "WHERE source_run_id='r2'")
    conn.execute("DELETE FROM public.alpha_hunter_symbol_snapshots "
                 "WHERE run_id='r2'")
    conn.execute("DELETE FROM public.alpha_hunter_snapshots WHERE run_id='r2'")
    manifest = position_manifest()
    key, pub = sealed_fixture()
    signature = signed_bundle(manifest, key)
    result = run(manifest, signature, pub)
    assert "REQUIRED_RUN_MANIFEST_MISMATCH" in result["blockers"]
    assert result["production_release_authorized"] is False


def test_never_accepted_as_production_release_even_with_external_label(real_http_db):
    _, conn = real_http_db
    seed(conn)
    manifest = position_manifest()
    manifest["kind"] = "EXTERNAL_CUSTODY"
    key, pub = sealed_fixture()
    signature = signed_bundle(manifest, key)
    result = run(manifest, signature, pub)
    assert result["status"] == "EXTERNAL_CUSTODY_DIAGNOSTIC_ONLY"
    assert result["production_release_authorized"] is False
    assert result["trade_permission"] is False
    assert result["source_market_quotes_authenticated"] is False


def test_scoped_localhost_only(monkeypatch):
    monkeypatch.delenv("AH_LOCAL_POSTGREST_ONLY", raising=False)
    with pytest.raises(validator.EvidenceRejected, match="ISOLATED_POSTGREST_OPT_IN_MISSING"):
        validator.local_get("alpha_hunter_snapshots", "r1", "run_id", 5)
    monkeypatch.setenv("AH_LOCAL_POSTGREST_ONLY", "1")
    with pytest.raises(validator.EvidenceRejected, match="HTTP_SCOPE_INVALID"):
        validator.local_get("other_table", "r1", "run_id", 5)
    with pytest.raises(validator.EvidenceRejected, match="HTTP_SCOPE_INVALID"):
        validator.local_get("alpha_hunter_snapshots", "../../main", "run_id", 5)
