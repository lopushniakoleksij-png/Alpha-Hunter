"""Secret-free tests for one-shot R11 public source custody; all fixtures offline."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

FILE = (Path(__file__).resolve().parents[1] /
        "ops/reviews/p03_r11_live_public_source_local_pg_v01.py")
spec = spec_from_file_location("r11_public_source", FILE)
w = module_from_spec(spec)
spec.loader.exec_module(w)
NOW = 1793700000000


def item(kind, payload):
    path, query = w.PATHS[kind]
    return {
        "url": w.EXCHANGE + path, "method": "GET",
        "start_ms": NOW, "end_ms": NOW + 1000, "raw": json.dumps(payload).encode(),
        "sha256": w._sha(json.dumps(payload).encode()),
        "parsed": w._quotes(json.dumps(payload).encode(), kind=kind,
                            start=NOW, end=NOW + 1000), "http_date": None,
    }


def ticker(**changes):
    row = {"symbol": "BTCUSDT", "category": "USDT-FUTURES",
           "lastPrice": "70000", "bid1Price": "69999", "ask1Price": "70001",
           "bid1Size": "1.5", "ask1Size": "2.1", "ts": str(NOW)}
    row.update(changes)
    return {"code": "00000", "requestTime": NOW,
            "data": [row]}


def book(**changes):
    row = {"ts": str(NOW), "b": [["69999", "1.5"]],
           "a": [["70001", "2.1"]]}
    row.update(changes)
    return {"code": "00000", "requestTime": NOW, "data": row}


class MarketTransportTests(TestCase):
    def fails(self, kind, doc, message):
        with self.assertRaisesRegex(w.WitnessRejected, message):
            w._quotes(json.dumps(doc).encode(), kind=kind,
                      start=NOW, end=NOW + 1000)

    def test_official_v3_shape_parses(self):
        a = w._quotes(json.dumps(ticker()).encode(), kind="ticker", start=NOW,end=NOW+1000)
        b = w._quotes(json.dumps(book()).encode(), kind="orderbook", start=NOW,end=NOW+1000)
        self.assertEqual(a["bid"], "69999")
        self.assertEqual(b["ask"], "70001")
        self.assertEqual(a["source_timestamp_ms"], NOW)

    def test_new_prospective_one_shot_is_never_trading_authority(self):
        t = item("ticker", ticker())
        d = item("orderbook", book())
        with patch.dict("os.environ", {"GITHUB_RUN_ID": "41623456789",
                                        "GITHUB_SHA": "abcd", "GITHUB_HEAD_REF": "branch"},
                        clear=True):
            manifest = w._manifest(t,d,"r11-41623456789-1")
        self.assertEqual(manifest["cohort_id"], "R11-PUBLIC-OBSERVATION-ONLY")
        self.assertTrue(manifest["source_transport_authenticated"])
        self.assertFalse(manifest["provider_response_cryptographically_signed"])
        self.assertFalse(manifest["independent_human_witness_signed"])
        self.assertFalse(manifest["continuous_35m_monitoring_proven"])
        self.assertFalse(manifest["production_release_authorized"])
        self.assertFalse(manifest["trade_permission"])
        self.assertFalse(manifest["legacy_history_reclassified"])
        self.assertEqual(manifest["new_paper_positions_created"],0)

    def test_wrong_category_not_reclassified(self):
        self.fails("ticker",ticker(category="SPOT"),"TICKER_SYMBOL_CATEGORY_MISMATCH")

    def test_wrong_symbol_not_accepted(self):
        self.fails("ticker",ticker(symbol="ETHUSDT"),"TICKER_SYMBOL_CATEGORY_MISMATCH")

    def test_stale_market_timestamp_rejected(self):
        self.fails("ticker",ticker(ts=str(NOW-92000)),"TICKER_SOURCE_TIME_OUT_OF_WINDOW")

    def test_future_market_timestamp_rejected(self):
        self.fails("orderbook",book(ts=str(NOW+6000)),"ORDERBOOK_SOURCE_TIME_OUT_OF_WINDOW")

    def test_stale_request_time_rejected(self):
        d=book()
        d["requestTime"]=NOW-92000
        self.fails("orderbook",d,"PROVIDER_REQUEST_TIME_OUT_OF_WINDOW")

    def test_negative_bid_rejected(self):
        self.fails("ticker",ticker(bid1Price="-1"),"TICKER_BID_NOT_POSITIVE")

    def test_invalid_bid_rejected(self):
        self.fails("ticker",ticker(bid1Price="NaN"),"TICKER_BID_NOT_POSITIVE")

    def test_crossed_book_rejected(self):
        self.fails("orderbook",book(b=[["72000","1"]]),"CROSSED_MARKET")

    def test_empty_orderbook_rejected(self):
        self.fails("orderbook",book(a=[]),"ORDERBOOK_LEVELS_MISSING")

    def test_missing_fields_rejected(self):
        self.fails("ticker",{"code":"00000","requestTime":NOW,"data":[{}]},
                   "TICKER_SYMBOL_CATEGORY_MISMATCH")

    def test_source_error_rejected(self):
        self.fails("orderbook",{"code":"3000","requestTime":NOW,"data":{}},
                   "PROVIDER_REJECTED_orderbook")

    def test_misaligned_independent_source_clock_rejected(self):
        t = item("ticker",ticker())
        d = item("orderbook",book())
        d["parsed"]["source_timestamp_ms"] = NOW - 90001
        with self.assertRaisesRegex(w.WitnessRejected,"SOURCE_TIMESTAMPS_NOT_COMPARABLE"):
            w._manifest(t,d,"r11-1-1")

    def test_local_production_dsn_rejected_before_psycopg_connect(self):
        with patch.dict("os.environ",{"AH_LOCAL_POSTGREST_ONLY":"1",
                                       "AH_LOCAL_PG_DSN":"host=production dbname=postgres"},
                        clear=True):
            with self.assertRaisesRegex(w.WitnessRejected,"DISPOSABLE_DB_HOST_NOT_EXACTLY_ALLOWLISTED"):
                w._local_roundtrip({"run_id":"r11-1-1"})

    def test_no_local_db_opt_in_rejected(self):
        with patch.dict("os.environ",{},clear=True):
            with self.assertRaisesRegex(w.WitnessRejected,"DISPOSABLE_DB_OPT_IN_NOT_SET"):
                w._local_roundtrip({"run_id":"r11-1-1"})

    def test_strict_github_run_provenance_required(self):
        with patch.dict("os.environ",{"GITHUB_RUN_ID":"foobar"},clear=True):
            with self.assertRaisesRegex(w.WitnessRejected,"GITHUB_PROVENANCE_ENV_MISSING"):
                w._safe_run_id()

    def test_no_exchange_order_endpoint_defined(self):
        self.assertNotIn("/api/v3/trade",FILE.read_text(encoding="utf-8"))
        self.assertNotIn("/api/v2/mix/order",FILE.read_text(encoding="utf-8"))
        self.assertTrue(all(k in ("ticker","orderbook") for k in w.PATHS))
        self.assertTrue(all(endpoint.startswith("/api/v3/market/")
                            for endpoint,query in w.PATHS.values()))
