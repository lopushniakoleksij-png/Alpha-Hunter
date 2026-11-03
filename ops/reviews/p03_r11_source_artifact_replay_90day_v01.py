"""Verify and preserve exact prior R11 public source bytes from GitHub artifacts.

Only replays the TWO existing 2026-11-03 GitHub-hosted market captures.
No new trades, quotes, requests, databases, credentials, history backfill,
signatures, or permissions. One-shot captures do not prove 35m continuity.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
import sys

# Pinned source-side SHA256 digests from original GitHub Actions run logs.
# These are checked independently of the manifest embedded in the downloaded
# ZIP artifact. They still derive from a single GitHub repository trust domain.
SOURCE_RUN = "41624614011"
SOURCE_SHA = "fbbfda59d2d4343f11d2361c119abc495a5daf34"
SOURCE_COHORT = "R11-PUBLIC-OBSERVATION-ONLY"
SOURCE_ID = "r11-41624614011-1"
SOURCE_MARKET = "https://api.bitget.com"
KNOWN = {
    "16": {
        "artifact_id": 13225157215,
        "original_zip_digest_sha256": "45a1312329d66195743f453375ac31fd6da3098b93090e3b8065e23b37f023e7",
        "ticker_sha256": "bd20dacc79b4cfa9818fe0322d4a4e1cbd16fe52eb54c909f87793507194dcb0",
        "orderbook_sha256": "ebcc5f338088335f3eaee98908167b066ebf6b91fa2f2a576d8d6f19d4b85ee6",
        "manifest_sha256": "bb5c5067f324f8196572830cb4a804afc82c8b40a5c4ac59b91bffe2cf2e4d41",
    },
    "17": {
        "artifact_id": 13225043281,
        "original_zip_digest_sha256": "8fcc0039601520dc69901a354be8ca60189ca01bb156c267f3b1b3966b8e9e83",
        "ticker_sha256": "415963c88c7c0212edd7507f2bc504779fb70c46fc0e9a40a95f61cd9e6bf177",
        "orderbook_sha256": "353fe54a7444aec05b18d083c0ef20dfd394c2230479734b85466278f4d4f987",
        "manifest_sha256": "fcaaf0aada4febf1cafcec4e68b241d787875c9be15ffcc16dae319f9d8cb297",
    },
}
FILES = (
    "bitget_ticker_raw.json", "bitget_orderbook_raw.json",
    "manifest.json", "acceptance_report.json",
)


class ReplayRejected(ValueError):
    pass


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _load_json(path: Path):
    data = path.read_bytes()
    if not data or len(data) > 200_000:
        raise ReplayRejected("ARCHIVE_FILE_MISSING_OR_TOO_LARGE")
    try:
        return data, json.loads(data)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ReplayRejected("ARCHIVE_JSON_MALFORMED") from exc


def _fail_if_wrong(name: str, actual, expected):
    if actual != expected:
        raise ReplayRejected("PINNED_" + name + "_MISMATCH")


def replay_one(directory: Path, pg_version: str):
    """Read-only local file verification, no network, write or import side effects."""
    if pg_version not in KNOWN:
        raise ReplayRejected("POSTGRES_VERSION_NOT_ALLOWLISTED")
    info = KNOWN[pg_version]
    for name in FILES:
        if not (directory / name).is_file():
            raise ReplayRejected("REQUIRED_PUBLIC_SOURCE_FILE_MISSING")
    (tick_raw, tick), (depth_raw, depth), (_, manifest), (_, report) = [
        _load_json(directory / name) for name in FILES
    ]
    if not isinstance(manifest, dict) or not isinstance(report, dict):
        raise ReplayRejected("CUSTODY_MANIFEST_INVALID")
    _fail_if_wrong("TICKER_SHA256", sha(tick_raw), info["ticker_sha256"])
    _fail_if_wrong("ORDERBOOK_SHA256", sha(depth_raw), info["orderbook_sha256"])
    _fail_if_wrong("MANIFEST_SHA256", sha(canonical(manifest)), info["manifest_sha256"])

    for key, expected in (
        ("schema", "ah-r11-external-market-transport-custody-v01"),
        ("github_run_id", SOURCE_RUN), ("github_sha", SOURCE_SHA),
        ("cohort_id", SOURCE_COHORT), ("run_id", SOURCE_ID),
        ("market_source", SOURCE_MARKET), ("symbol", "BTCUSDT"),
        ("category", "USDT-FUTURES"), ("paper_only", True),
        ("trade_permission", False), ("order_path", "NONE"),
        ("production_release_authorized", False),
        ("source_transport_authenticated", True),
        ("provider_response_cryptographically_signed", False),
        ("independent_human_witness_signed", False),
        ("continuous_35m_monitoring_proven", False),
        ("scheduled_run_manifest_independently_signed", False),
        ("legacy_history_reclassified", False),
        ("legacy_acceptance", "EVIDENCE_NO_GO"),
        ("new_paper_positions_created", 0),
    ):
        _fail_if_wrong(key.upper(), manifest.get(key), expected)

    for kind, raw, doc in (("ticker", tick_raw, tick),
                           ("orderbook", depth_raw, depth)):
        record = manifest["records"][kind]
        route = "/api/v3/market/tickers" if kind == "ticker" else "/api/v3/market/orderbook"
        query = {"category": "USDT-FUTURES", "symbol": "BTCUSDT"}
        if kind == "orderbook":
            query["limit"] = "5"
        expected_url = SOURCE_MARKET + route + "?" + urlencode(query)
        _fail_if_wrong("URL_" + kind, record.get("url"), expected_url)
        _fail_if_wrong("METHOD_" + kind, record.get("method"), "GET")
        _fail_if_wrong("RAW_SHA_" + kind, record.get("raw_body_sha256"), sha(raw))
        _fail_if_wrong("RAW_LENGTH_" + kind, record.get("raw_body_bytes"), len(raw))
        if not isinstance(doc, dict) or doc.get("code") != "00000":
            raise ReplayRejected("RAW_PROVIDER_CODE_REJECTED")
        if kind == "ticker":
            entries = doc.get("data")
            if not isinstance(entries, list) or len(entries) != 1:
                raise ReplayRejected("RAW_TICKER_WRONG_SIZE")
            row = entries[0]
            if row.get("symbol") != "BTCUSDT" or row.get("category") != "USDT-FUTURES":
                raise ReplayRejected("RAW_TICKER_WRONG_SYMBOL")
            ts = int(row["ts"])
        else:
            row = doc["data"]
            if not row.get("a") or not row.get("b"):
                raise ReplayRejected("RAW_DEPTH_MISSING_SIDES")
            ts = int(row["ts"])
        _fail_if_wrong("SOURCE_TS_" + kind, record.get("source_timestamp_ms"), ts)
        if not isinstance(record.get("request_start_ms"), int) or not isinstance(record.get("request_end_ms"), int):
            raise ReplayRejected("REQUEST_CAPTURE_WINDOW_MISSING")
        if not (record["request_start_ms"] - 90_000 <= ts <= record["request_end_ms"] + 5000):
            raise ReplayRejected("SOURCE_TIMESTAMP_OUT_OF_CAPTURE_WINDOW")
        if record.get("parsed", {}).get("source_timestamp_ms") != ts:
            raise ReplayRejected("PARSED_TIMESTAMP_MISMATCH")
    for key, expected in (
        ("result", "R11_ONE_SHOT_PUBLIC_SOURCE_TRANSPORT_CAPTURE_PASS_ONLY"),
        ("local_pg_postgrest_roundtrip_pass", True),
        ("manifest_sha256", info["manifest_sha256"]),
        ("ticker_sha256", info["ticker_sha256"]),
        ("orderbook_sha256", info["orderbook_sha256"]),
        ("run_id", SOURCE_ID),
        ("cohort_id", SOURCE_COHORT),
        ("independent_human_witness_signed", False),
        ("continuous_historical_evidence_complete", False),
        ("exchange_execution_proven", False),
        ("production_release_authorized", False),
        ("trade_permission", False),
        ("paper_only", True),
        ("legacy_acceptance", "EVIDENCE_NO_GO"),
    ):
        _fail_if_wrong("ACCEPTANCE_REPORT_" + key.upper(), report.get(key), expected)
    return {
        "source_artifact_id": info["artifact_id"],
        "source_archive_zip_digest_from_github_metadata": info["original_zip_digest_sha256"],
        "pg_version": pg_version,
        "source_github_run": SOURCE_RUN, "source_capture_run_id": SOURCE_ID,
        "ticker_sha256": sha(tick_raw), "orderbook_sha256": sha(depth_raw),
        "manifest_sha256": sha(canonical(manifest)),
        "source_transport_and_local_roundtrip_replay_pass": True,
        "independently_held_original_quote_signatures": False,
        "independent_human_custody_approval": False,
        "continuous_35m_coverage": False,
        "real_position_receipts_observed": 0,
        "production_release_authorized": False,
        "trade_permission": False,
        "legacy_evidence_status": "EVIDENCE_NO_GO",
    }


def replay_pair(pg16_dir: Path, pg17_dir: Path):
    a = replay_one(pg16_dir, "16")
    b = replay_one(pg17_dir, "17")
    if a["manifest_sha256"] == b["manifest_sha256"]:
        raise ReplayRejected("TWO_RUNS_WRONG_IDENTITY_REPLAY")
    return {
        "status": "R11_PUBLIC_SOURCE_REPLAY_AND_RETENTION_PASS_ONLY",
        "source_github_run": SOURCE_RUN,
        "original_artifacts": {"pg16": a, "pg17": b},
        "future_cohort_scheduled_run_manifest_authenticated": False,
        "actual_forward_chain_validator_admission": "PROSPECTIVE_EVIDENCE_NO_GO",
        "reason": "Only one pair of near-simultaneous GitHub public observations, no signed schedule or independent event-signing control.",
        "independent_original_provider_signature": False,
        "sustained_35m_evidence": False,
        "new_positions": 0,
        "trade_permission": False,
        "production_release_authorized": False,
        "legacy_evidence_status": "EVIDENCE_NO_GO",
    }


def main(argv):
    if len(argv) != 4:
        raise ReplayRejected("USE: script <pg16_directory> <pg17_directory> <output_report>")
    report = replay_pair(Path(argv[1]), Path(argv[2]))
    out = Path(argv[3])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("R11_REAL_GITHUB_ARTIFACT_BYTES_REPLAY_PASS")
    print("Original run", report["source_github_run"])
    for version in ("pg16", "pg17"):
        x = report["original_artifacts"][version]
        print(version, x["source_artifact_id"], x["manifest_sha256"])
    print("35M_CONTINUITY_NO_GO; HUMAN_SIGNATURE_NO_GO; OLD_HISTORY_NO_GO; TRADING_DISABLED")


if __name__ == "__main__":
    try:
        main(sys.argv)
    except (ReplayRejected, OSError, KeyError, TypeError, ValueError) as exc:
        print("R11_REAL_ARCHIVE_REPLAY_NO_GO: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
