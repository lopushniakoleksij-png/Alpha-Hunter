"""R11 one-shot PUBLIC market-data witness + disposable local PG/PostgREST custody.

Research only: one BTCUSDT futures observation, zero positions, zero trading.
Never accesses Alpha Hunter production DB, protected scanner or live order API.
GitHub-hosted HTTPS capture is independent of Render scanner runtime but NOT
independent human control, exchange signature, or continuous monitoring.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import ssl
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

EXCHANGE = "https://api.bitget.com"
SYMBOL = "BTCUSDT"
CATEGORY = "USDT-FUTURES"
COHORT = "R11-PUBLIC-OBSERVATION-ONLY"
PATHS = {
    "ticker": ("/api/v3/market/tickers", {"category": CATEGORY, "symbol": SYMBOL}),
    "orderbook": ("/api/v3/market/orderbook", {"category": CATEGORY, "symbol": SYMBOL, "limit": "5"}),
}
LOCAL_POSTGREST = "http://127.0.0.1:3000"
LOCAL_DSN = "host=127.0.0.1 port=5432 dbname=postgres user=postgres password=isolated-only"
MAX_BODY = 200_000
MAX_AGE_MS = 90_000


class WitnessRejected(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WitnessRejected("HTTP_REDIRECT_NOT_ALLOWED")


def _ms():
    return int(time.time() * 1000)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _positive(value, label):
    try:
        v = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise WitnessRejected(label + "_NON_NUMERIC") from None
    if not v.is_finite() or v <= 0:
        raise WitnessRejected(label + "_NOT_POSITIVE")
    return v


def _timestamp(value, *, start, end, label):
    try:
        timestamp = int(str(value))
    except (TypeError, ValueError):
        raise WitnessRejected(label + "_INVALID") from None
    if not 1_000_000_000_000 <= timestamp < 10_000_000_000_000:
        raise WitnessRejected(label + "_INVALID")
    if timestamp < start - MAX_AGE_MS or timestamp > end + 5_000:
        raise WitnessRejected(label + "_OUT_OF_WINDOW")
    return timestamp


def _quotes(raw, *, kind, start, end):
    try:
        doc = json.loads(raw)
        if doc.get("code") != "00000":
            raise WitnessRejected("PROVIDER_REJECTED_" + kind)
        _timestamp(doc.get("requestTime"), start=start, end=end, label="PROVIDER_REQUEST_TIME")
        data = doc["data"]
        if kind == "ticker":
            if not isinstance(data, list) or len(data) != 1:
                raise WitnessRejected("TICKER_NOT_EXACTLY_ONE")
            row = data[0]
            if row.get("symbol") != SYMBOL or row.get("category") != CATEGORY:
                raise WitnessRejected("TICKER_SYMBOL_CATEGORY_MISMATCH")
            ts = _timestamp(row.get("ts"), start=start, end=end, label="TICKER_SOURCE_TIME")
            bid = _positive(row.get("bid1Price"), "TICKER_BID")
            ask = _positive(row.get("ask1Price"), "TICKER_ASK")
            _positive(row.get("bid1Size"), "TICKER_BID_SIZE")
            _positive(row.get("ask1Size"), "TICKER_ASK_SIZE")
            _positive(row.get("lastPrice"), "TICKER_LAST")
        elif kind == "orderbook":
            if not isinstance(data, dict):
                raise WitnessRejected("ORDERBOOK_SHAPE_INVALID")
            bids, asks = data["b"], data["a"]
            if (not isinstance(bids, list) or not bids
                    or not isinstance(asks, list) or not asks):
                raise WitnessRejected("ORDERBOOK_LEVELS_MISSING")
            ts = _timestamp(data.get("ts"), start=start, end=end, label="ORDERBOOK_SOURCE_TIME")
            bid = _positive(bids[0][0], "ORDERBOOK_BID")
            ask = _positive(asks[0][0], "ORDERBOOK_ASK")
            _positive(bids[0][1], "ORDERBOOK_BID_SIZE")
            _positive(asks[0][1], "ORDERBOOK_ASK_SIZE")
        else:
            raise WitnessRejected("ENDPOINT_NOT_ALLOWLISTED")
        if bid > ask:
            raise WitnessRejected("CROSSED_MARKET")
        return {"source_timestamp_ms": ts, "bid": str(bid), "ask": str(ask)}
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        if isinstance(exc, WitnessRejected):
            raise
        raise WitnessRejected(kind.upper() + "_JSON_OR_SCHEMA_INVALID") from exc


def _read_public(kind):
    if kind not in PATHS:
        raise WitnessRejected("ENDPOINT_NOT_ALLOWLISTED")
    path, query = PATHS[kind]
    url = EXCHANGE + path + "?" + urlencode(query)
    start = _ms()
    req = Request(url, headers={"Accept": "application/json",
                                "User-Agent": "AH-R11-Public-ReadOnly-Witness/1.0"}, method="GET")
    opener = build_opener(NoRedirect())
    # Explicit certificate/hostname validation; no exchange/API keys.
    with opener.open(req, timeout=12) as response:
        if response.status != 200 or response.geturl() != url:
            raise WitnessRejected("PUBLIC_ENDPOINT_HTTP_OR_REDIRECT")
        raw = response.read(MAX_BODY + 1)
        end = _ms()
        if not raw or len(raw) > MAX_BODY:
            raise WitnessRejected("PUBLIC_RESPONSE_INVALID_SIZE")
        parsed = _quotes(raw, kind=kind, start=start, end=end)
        return {
            "url": url, "method": "GET", "start_ms": start, "end_ms": end,
            "raw": raw, "sha256": _sha(raw), "parsed": parsed,
            "http_date": response.headers.get("Date"),
        }


def _safe_run_id():
    run = os.getenv("GITHUB_RUN_ID", "")
    attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
    if not run.isdecimal() or not attempt.isdecimal():
        raise WitnessRejected("GITHUB_PROVENANCE_ENV_MISSING")
    return "r11-" + run + "-" + attempt


def _manifest(ticker, depth, run_id):
    if abs(ticker["parsed"]["source_timestamp_ms"] -
           depth["parsed"]["source_timestamp_ms"]) > MAX_AGE_MS:
        raise WitnessRejected("SOURCE_TIMESTAMPS_NOT_COMPARABLE")
    captured = datetime.now(timezone.utc).isoformat()
    records = {}
    for kind, observation in (("ticker", ticker), ("orderbook", depth)):
        records[kind] = {
            "url": observation["url"], "method": "GET",
            "transport": "verified HTTPS/TLS peer + hostname",
            "source_timestamp_ms": observation["parsed"]["source_timestamp_ms"],
            "raw_body_sha256": observation["sha256"],
            "raw_body_bytes": len(observation["raw"]),
            "request_start_ms": observation["start_ms"],
            "request_end_ms": observation["end_ms"],
            "http_date": observation["http_date"],
            "parsed": observation["parsed"],
        }
    return {
        "schema": "ah-r11-external-market-transport-custody-v01",
        "cohort_id": COHORT, "run_id": run_id, "symbol": SYMBOL,
        "category": CATEGORY, "captured_at_utc": captured,
        "github_run_id": os.getenv("GITHUB_RUN_ID"),
        "github_sha": os.getenv("GITHUB_SHA", ""),
        "repo_pr_branch": os.getenv("GITHUB_HEAD_REF", os.getenv("GITHUB_REF_NAME", "")),
        "market_source": EXCHANGE,
        "source_transport_authenticated": True,
        "provider_response_cryptographically_signed": False,
        "independent_human_witness_signed": False,
        "continuous_35m_monitoring_proven": False,
        "scheduled_run_manifest_independently_signed": False,
        "new_paper_positions_created": 0,
        "paper_only": True, "trade_permission": False,
        "order_path": "NONE", "production_release_authorized": False,
        "legacy_history_reclassified": False,
        "legacy_acceptance": "EVIDENCE_NO_GO",
        "records": records,
    }


def _local_roundtrip(manifest):
    """Write only the known disposable local PG and read through local PostgREST."""
    if os.getenv("AH_LOCAL_POSTGREST_ONLY") != "1":
        raise WitnessRejected("DISPOSABLE_DB_OPT_IN_NOT_SET")
    if os.getenv("AH_LOCAL_PG_DSN") != LOCAL_DSN:
        raise WitnessRejected("DISPOSABLE_DB_HOST_NOT_EXACTLY_ALLOWLISTED")
    try:
        import psycopg  # test-only, never production dependency
    except ImportError as exc:
        raise WitnessRejected("LOCAL_POSTGRES_DRIVER_MISSING") from exc
    manifest_raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)
    sha = _sha(manifest_raw.encode("utf-8"))
    with psycopg.connect(LOCAL_DSN, autocommit=True) as connection:
        connection.execute("""
          CREATE TABLE IF NOT EXISTS public.ah_r11_market_witness_only (
            run_id text PRIMARY KEY,
            cohort_id text NOT NULL,
            market_source text NOT NULL,
            manifest_json jsonb NOT NULL,
            manifest_sha256 text NOT NULL,
            paper_only boolean NOT NULL DEFAULT TRUE,
            trade_permission boolean NOT NULL DEFAULT FALSE
          )
        """)
        connection.execute("""
          INSERT INTO public.ah_r11_market_witness_only
            (run_id,cohort_id,market_source,manifest_json,manifest_sha256)
          VALUES (%s,%s,%s,%s::jsonb,%s)
        """, (manifest["run_id"], COHORT, EXCHANGE, manifest_raw, sha))
        connection.execute("NOTIFY pgrst,'reload schema'")
    # Independent local transport read-back; schema cache startup can lag.
    opener = build_opener(NoRedirect())
    url = LOCAL_POSTGREST + "/ah_r11_market_witness_only?" + urlencode({
        "select": "run_id,cohort_id,market_source,manifest_json,manifest_sha256,paper_only,trade_permission",
        "run_id": "eq." + manifest["run_id"],
    })
    for _ in range(40):
        try:
            with opener.open(Request(url, method="GET", headers={"Accept": "application/json"}),
                             timeout=2) as response:
                if response.status != 200 or response.geturl() != url:
                    raise WitnessRejected("LOCAL_POSTGREST_HTTP_FAILURE")
                readback = json.load(response)
            if len(readback) != 1:
                raise WitnessRejected("LOCAL_POSTGREST_ROW_MISSING_OR_DUPLICATE")
            row = readback[0]
            if (row["run_id"] != manifest["run_id"]
                    or row["cohort_id"] != COHORT
                    or row["market_source"] != EXCHANGE
                    or row["paper_only"] is not True
                    or row["trade_permission"] is not False
                    or row["manifest_sha256"] != sha
                    or row["manifest_json"] != manifest):
                raise WitnessRejected("LOCAL_POSTGREST_EVIDENCE_MISMATCH")
            return sha
        except HTTPError as exc:
            if exc.code != 404:
                raise
        time.sleep(.25)
    raise WitnessRejected("LOCAL_POSTGREST_CANNOT_READ_WRITTEN_MANIFEST")


def main():
    if os.getenv("AH_LOCAL_POSTGREST_ONLY") != "1":
        raise WitnessRejected("ISOLATED_RUNNER_ONLY")
    if any(os.getenv(x) for x in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
                                "BITGET_API_KEY", "BITGET_SECRET_KEY",
                                "BITGET_API_PASSPHRASE", "RENDER_API_KEY")):
        raise WitnessRejected("PRODUCTION_CREDENTIAL_PRESENT")
    out = Path(os.getenv("AH_R11_WITNESS_OUTPUT", "r11_public_market_witness"))
    run_id = _safe_run_id()
    ticker = _read_public("ticker")
    depth = _read_public("orderbook")
    manifest = _manifest(ticker, depth, run_id)
    sha = _local_roundtrip(manifest)
    out.mkdir(parents=True, exist_ok=True)
    (out / "bitget_ticker_raw.json").write_bytes(ticker["raw"])
    (out / "bitget_orderbook_raw.json").write_bytes(depth["raw"])
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = {
        "result": "R11_ONE_SHOT_PUBLIC_SOURCE_TRANSPORT_CAPTURE_PASS_ONLY",
        "local_pg_postgrest_roundtrip_pass": True,
        "manifest_sha256": sha,
        "run_id": run_id, "cohort_id": COHORT,
        "market_source": EXCHANGE,
        "ticker_sha256": ticker["sha256"],
        "orderbook_sha256": depth["sha256"],
        "independent_human_witness_signed": False,
        "continuous_historical_evidence_complete": False,
        "exchange_execution_proven": False,
        "paper_only": True, "trade_permission": False,
        "production_release_authorized": False,
        "legacy_acceptance": "EVIDENCE_NO_GO",
    }
    (out / "acceptance_report.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("R11_EXTERNAL_PUBLIC_SOURCE_TRANSPORT_PASS; LOCAL_PG_POSTGREST_READBACK_PASS")
    print("run_id=" + run_id)
    print("ticker_sha256=" + ticker["sha256"])
    print("orderbook_sha256=" + depth["sha256"])
    print("manifest_sha256=" + sha)
    print("NO INDEPENDENT HUMAN/PROVIDER SIGNATURE; NO SCAN CONTINUITY; NO TRADE/RELEASE AUTHORITY")


if __name__ == "__main__":
    try:
        main()
    except (WitnessRejected, URLError, HTTPError, OSError, ValueError, TimeoutError) as exc:
        print("R11_ONE_SHOT_EVIDENCE_NO_GO: " + type(exc).__name__ + ": " + str(exc))
        raise SystemExit(1)
