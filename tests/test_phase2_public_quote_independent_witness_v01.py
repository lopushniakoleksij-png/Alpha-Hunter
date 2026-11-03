"""No network; deterministic provider witness parsing and fail-closed regressions."""
import importlib.util
import json
import unittest
from pathlib import Path

src=Path(__file__).resolve().parents[1]/"ops/reviews/phase2_public_quote_independent_witness_v01.py"
spec=importlib.util.spec_from_file_location("public_quote_witness",src)
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
NOW=1793617200000

def fake_ticker(*,ts=NOW,bid="100",ask="100.1",bid_size="3",ask_size="5",symbol="BTCUSDT"):
    return json.dumps({"code":"00000","requestTime":NOW,"data":[{
        "symbol":symbol,"bidPr":bid,"askPr":ask,"bidSz":bid_size,"askSz":ask_size,"ts":str(ts)}]}).encode()

def fake_depth(*,ts=NOW,bid="100",ask="100.1",bid_size="3",ask_size="5"):
    return json.dumps({"code":"00000","requestTime":NOW,"data":{
        "b":[[bid,bid_size]],"a":[[ask,ask_size]],"ts":str(ts)}}).encode()

def item(raw,path):
    return {"raw":raw,"url":w.BASE+path+"?test_only=true",
            "start_ms":NOW,"end_ms":NOW+1500,"headers":{"date":"Mon, 02 Nov 2026 11:20:00 GMT"}}

class PublicQuoteWitnessTests(unittest.TestCase):
    def test_positive_quote_is_research_only(self):
        data=w.build_manifest(item(fake_ticker(),w.TICKER_PATH),item(fake_depth(),w.DEPTH_PATH))
        self.assertEqual(data["status"],"PUBLIC_PROVIDER_TRANSPORT_CUSTODY_CAPTURED_NOT_SIGNED")
        self.assertFalse(data["provider_response_signed"])
        self.assertFalse(data["executable_fill_proven"])
        self.assertFalse(data["trade_permission"])
        self.assertEqual(data["artifacts"]["ticker"]["raw_body_length"],len(fake_ticker()))
        self.assertEqual(data["artifacts"]["ticker"]["parsed"]["symbol"],"BTCUSDT")

    def test_mismatched_symbol_rejected(self):
        with self.assertRaises(w.EvidenceInvalid):
            w.validate_ticker(fake_ticker(symbol="OTHERUSDT"),start_ms=NOW,end_ms=NOW+500)

    def test_stale_ticker_rejected(self):
        with self.assertRaises(w.EvidenceInvalid):
            w.validate_ticker(fake_ticker(ts=NOW-91000),start_ms=NOW,end_ms=NOW+500)

    def test_future_depth_rejected(self):
        with self.assertRaises(w.EvidenceInvalid):
            w.validate_depth(fake_depth(ts=NOW+20000),start_ms=NOW,end_ms=NOW+500)

    def test_zero_liquidity_rejected(self):
        with self.assertRaises(w.EvidenceInvalid):
            w.validate_depth(fake_depth(ask_size="0"),start_ms=NOW,end_ms=NOW+500)

    def test_negative_or_nonfinite_quote_rejected(self):
        for bid in ("-1","NaN","Infinity"):
            with self.subTest(bid=bid),self.assertRaises(w.EvidenceInvalid):
                w.validate_ticker(fake_ticker(bid=bid),start_ms=NOW,end_ms=NOW+500)

    def test_crossed_bid_ask_rejected(self):
        with self.assertRaises(w.EvidenceInvalid):
            w.validate_ticker(fake_ticker(bid="101",ask="100"),start_ms=NOW,end_ms=NOW+500)

    def test_missing_provider_json_rejected(self):
        for raw in (b'{"code":"99999"}',b'bad',b'{"code":"00000","data":[]}'):
            with self.subTest(raw=raw),self.assertRaises(w.EvidenceInvalid):
                w.validate_ticker(raw,start_ms=NOW,end_ms=NOW+500)

    def test_out_of_sync_quote_and_depth_rejected(self):
        with self.assertRaises(w.EvidenceInvalid):
            w.build_manifest(item(fake_ticker(),w.TICKER_PATH),
                             item(fake_depth(ts=NOW-91000),w.DEPTH_PATH))

    def test_url_path_allowlist_and_symbol_enforced_before_any_network(self):
        for path,query in (("/api/v2/mix/order/place-order",{"symbol":"BTCUSDT"}),
                           (w.TICKER_PATH,{"symbol":"OTHERUSDT"})):
            with self.subTest(path=path),self.assertRaises(w.EvidenceInvalid):
                w.fetch_public(path,query)

    def test_raw_body_required_not_just_claimed_hash(self):
        t=item(fake_ticker(),w.TICKER_PATH);t["raw"]=None
        with self.assertRaises(w.EvidenceInvalid):
            w.build_manifest(t,item(fake_depth(),w.DEPTH_PATH))

if __name__=="__main__":
    unittest.main()
