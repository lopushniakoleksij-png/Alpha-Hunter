"""Offline R11 artifact replay tests. Never talks to GitHub, Bitget or Supabase."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json

SRC = (Path(__file__).resolve().parents[1] /
       "ops/reviews/p03_r11_source_artifact_replay_90day_v01.py")
spec = spec_from_file_location("r11_artifact_replayer", SRC)
replay = module_from_spec(spec)
spec.loader.exec_module(replay)
TS = 1793700000000


def make_capture(folder, pg, price):
    ticker = {
        "code": "00000", "requestTime": TS,
        "data": [{"symbol": "BTCUSDT", "category": "USDT-FUTURES",
                  "ts": str(TS), "bid1Price": str(price), "ask1Price": str(price+1),
                  "bid1Size": "1", "ask1Size": "1", "lastPrice": str(price)}],
    }
    book = {"code": "00000", "requestTime": TS, "data": {
        "ts": str(TS), "b": [[str(price), "1"]], "a": [[str(price + 1), "1"]]}}
    raw = {"ticker": replay.canonical(ticker), "orderbook": replay.canonical(book)}
    meta = {}
    for kind in ("ticker", "orderbook"):
        route = "/api/v3/market/tickers" if kind == "ticker" else "/api/v3/market/orderbook"
        query = "category=USDT-FUTURES&symbol=BTCUSDT"
        if kind == "orderbook":
            query += "&limit=5"
        meta[kind] = {
            "url": "https://api.bitget.com" + route + "?" + query,
            "method": "GET", "source_timestamp_ms": TS,
            "raw_body_sha256": replay.sha(raw[kind]),
            "raw_body_bytes": len(raw[kind]),
            "request_start_ms": TS, "request_end_ms": TS + 1500,
            "parsed": {"source_timestamp_ms": TS},
        }
    manifest = {
        "schema": "ah-r11-external-market-transport-custody-v01",
        "github_run_id": replay.SOURCE_RUN, "github_sha": replay.SOURCE_SHA,
        "cohort_id": replay.SOURCE_COHORT, "run_id": replay.SOURCE_ID,
        "market_source": replay.SOURCE_MARKET,
        "symbol": "BTCUSDT", "category": "USDT-FUTURES",
        "paper_only": True, "trade_permission": False, "order_path": "NONE",
        "production_release_authorized": False,
        "source_transport_authenticated": True,
        "provider_response_cryptographically_signed": False,
        "independent_human_witness_signed": False,
        "continuous_35m_monitoring_proven": False,
        "scheduled_run_manifest_independently_signed": False,
        "legacy_history_reclassified": False,
        "legacy_acceptance": "EVIDENCE_NO_GO",
        "new_paper_positions_created": 0,
        "records": meta,
    }
    digest = replay.sha(replay.canonical(manifest))
    report = {
        "result": "R11_ONE_SHOT_PUBLIC_SOURCE_TRANSPORT_CAPTURE_PASS_ONLY",
        "local_pg_postgrest_roundtrip_pass": True,
        "manifest_sha256": digest, "ticker_sha256": replay.sha(raw["ticker"]),
        "orderbook_sha256": replay.sha(raw["orderbook"]),
        "run_id": replay.SOURCE_ID, "cohort_id": replay.SOURCE_COHORT,
        "independent_human_witness_signed": False,
        "continuous_historical_evidence_complete": False,
        "exchange_execution_proven": False,
        "production_release_authorized": False, "trade_permission": False,
        "paper_only": True, "legacy_acceptance": "EVIDENCE_NO_GO",
    }
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"bitget_ticker_raw.json").write_bytes(raw["ticker"])
    (folder/"bitget_orderbook_raw.json").write_bytes(raw["orderbook"])
    (folder/"manifest.json").write_text(json.dumps(manifest))
    (folder/"acceptance_report.json").write_text(json.dumps(report))
    pin = {
        "artifact_id": 100 if pg=="16" else 101,
        "original_zip_digest_sha256": "a"*64,
        "ticker_sha256": replay.sha(raw["ticker"]),
        "orderbook_sha256": replay.sha(raw["orderbook"]),
        "manifest_sha256": digest,
    }
    return pin


class R11ArchivedEvidenceReplayTests(TestCase):
    def test_complete_synthetic_pair_passes_scope_only(self):
        with TemporaryDirectory() as base:
            a,b=Path(base)/"16",Path(base)/"17"
            pin_a=make_capture(a,"16",70000)
            pin_b=make_capture(b,"17",70100)
            with patch.dict(replay.KNOWN,{"16":pin_a,"17":pin_b},clear=True):
                report = replay.replay_pair(a,b)
            self.assertEqual(report["status"],"R11_PUBLIC_SOURCE_REPLAY_AND_RETENTION_PASS_ONLY")
            self.assertFalse(report["sustained_35m_evidence"])
            self.assertFalse(report["independent_original_provider_signature"])
            self.assertFalse(report["trade_permission"])
            self.assertFalse(report["production_release_authorized"])
            self.assertEqual(report["legacy_evidence_status"],"EVIDENCE_NO_GO")

    def test_original_source_bytes_tamper_rejected(self):
        with TemporaryDirectory() as base:
            a=Path(base)
            pin=make_capture(a,"16",70000)
            (a/"bitget_ticker_raw.json").write_bytes(b'{"different":"true"}')
            with patch.dict(replay.KNOWN,{"16":pin},clear=True):
                with self.assertRaisesRegex(replay.ReplayRejected,"PINNED_TICKER_SHA256_MISMATCH"):
                    replay.replay_one(a,"16")

    def test_missing_raw_file_rejected(self):
        with TemporaryDirectory() as base:
            a=Path(base)
            pin=make_capture(a,"16",70000)
            (a/"bitget_orderbook_raw.json").unlink()
            with patch.dict(replay.KNOWN,{"16":pin},clear=True):
                with self.assertRaisesRegex(replay.ReplayRejected,"REQUIRED_PUBLIC_SOURCE_FILE_MISSING"):
                    replay.replay_one(a,"16")

    def test_altered_manifest_claim_of_approval_rejected(self):
        with TemporaryDirectory() as base:
            a=Path(base)
            pin=make_capture(a,"16",70000)
            manifest=json.loads((a/"manifest.json").read_text())
            manifest["independent_human_witness_signed"]=True
            (a/"manifest.json").write_text(json.dumps(manifest))
            with patch.dict(replay.KNOWN,{"16":pin},clear=True):
                with self.assertRaisesRegex(replay.ReplayRejected,"PINNED_MANIFEST_SHA256_MISMATCH"):
                    replay.replay_one(a,"16")

    def test_new_zip_without_original_expected_digest_does_not_pass(self):
        with TemporaryDirectory() as base:
            a=Path(base)
            pin=make_capture(a,"16",70000)
            # Caller may not re-sign/alter baseline: SHA pinned separately.
            pin["ticker_sha256"]="0"*64
            with patch.dict(replay.KNOWN,{"16":pin},clear=True):
                with self.assertRaisesRegex(replay.ReplayRejected,"PINNED_TICKER_SHA256_MISMATCH"):
                    replay.replay_one(a,"16")

    def test_changed_acceptance_report_rejected(self):
        with TemporaryDirectory() as base:
            a=Path(base)
            pin=make_capture(a,"16",70000)
            report=json.loads((a/"acceptance_report.json").read_text())
            report["trade_permission"]=True
            (a/"acceptance_report.json").write_text(json.dumps(report))
            with patch.dict(replay.KNOWN,{"16":pin},clear=True):
                with self.assertRaisesRegex(replay.ReplayRejected,"PINNED_ACCEPTANCE_REPORT_TRADE_PERMISSION_MISMATCH"):
                    replay.replay_one(a,"16")

    def test_timestamp_outside_window_rejected(self):
        with TemporaryDirectory() as base:
            a=Path(base)
            pin=make_capture(a,"16",70000)
            manifest=json.loads((a/"manifest.json").read_text())
            manifest["records"]["ticker"]["request_start_ms"]=TS+100000
            pin["manifest_sha256"]=replay.sha(replay.canonical(manifest))
            report=json.loads((a/"acceptance_report.json").read_text())
            report["manifest_sha256"]=pin["manifest_sha256"]
            (a/"manifest.json").write_text(json.dumps(manifest))
            (a/"acceptance_report.json").write_text(json.dumps(report))
            with patch.dict(replay.KNOWN,{"16":pin},clear=True):
                with self.assertRaisesRegex(replay.ReplayRejected,"SOURCE_TIMESTAMP_OUT_OF_CAPTURE_WINDOW"):
                    replay.replay_one(a,"16")

    def test_reject_duplicate_source_capture(self):
        with TemporaryDirectory() as base:
            a,b=Path(base)/"16",Path(base)/"17"
            pin_a=make_capture(a,"16",70000)
            pin_b=make_capture(b,"17",70000)
            with patch.dict(replay.KNOWN,{"16":pin_a,"17":pin_b},clear=True):
                with self.assertRaisesRegex(replay.ReplayRejected,"TWO_RUNS_WRONG_IDENTITY_REPLAY"):
                    replay.replay_pair(a,b)


if __name__=="__main__":
    import unittest
    unittest.main()
