import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from phase2_scientific_v11 import (D, frozen_candidates,
                                   model_return, run, valid_price_geometry)

def row(sym="BTCUSDT", id="s1", at="2026-11-08T02:04:00Z",
        created="2026-11-08T02:04:20Z",ep="100",sl="110",tp="90"):
    return {"signal_id":id,"symbol":sym,
            "detected_at_utc":at,"created_at":created,"direction":"SHORT",
            "trade_permission":False,"entry_price":ep,
            "stop_loss":sl,"take_profit":tp}

class UniqueOpportunityTests(unittest.TestCase):
    def test_asof_first_complete_is_selected_even_if_later_score_better(self):
        signals=[row("BTCUSDT","btc_late","2026-11-08T18:00:00Z",
                     "2026-11-08T18:00:20Z","102","107","89"),
                 row("BTCUSDT","btc_first"),
                 row("ETHUSDT","eth_first"),
                 row("SOLUSDT","sol_first")]
        chosen=frozen_candidates(signals)
        self.assertEqual(len(chosen),3)
        self.assertEqual(chosen["BTCUSDT"]["signal_id"],"btc_first")
    def test_absent_symbol_fails_closed(self):
        with self.assertRaises(ValueError):frozen_candidates([row()])
    def test_no_trade_permission_ever(self):
        signals=[row("BTCUSDT"),row("ETHUSDT"),row("SOLUSDT")]
        signals[1]["trade_permission"]=True
        with self.assertRaises(ValueError):frozen_candidates(signals)
    def test_geometry(self):
        self.assertTrue(valid_price_geometry(row()))
        self.assertFalse(valid_price_geometry(row(ep=None)))
        self.assertFalse(valid_price_geometry(row(ep="100",sl="95",tp="90")))
    def test_created_after_evaluation_hour_is_skipped(self):
        signals=[row("BTCUSDT",id="late_stored",
                     created="2026-11-08T03:01:00Z"),
                 row("BTCUSDT",id="valid_later",
                     at="2026-11-08T04:00:00Z",
                     created="2026-11-08T04:00:15Z"),
                 row("ETHUSDT",id="eth"),row("SOLUSDT",id="sol")]
        self.assertEqual(frozen_candidates(signals)["BTCUSDT"]["signal_id"],"valid_later")
    def test_shorts_fee_slippage_reduce_return(self):
        fee=D("0.0006")
        base=model_return("100","110","99","SHORT","TP_FIRST",fee,D("0.0005"))
        no_cost=model_return("100","110","99","SHORT","TP_FIRST",D("0"),D("0"))
        self.assertGreater(D(base["gross_usdt"]),D(base["net_ex_funding_usdt"]))
        self.assertLess(D(base["net_ex_funding_usdt"]),D(no_cost["net_ex_funding_usdt"]))
        self.assertEqual(D(no_cost["net_ex_funding_usdt"]),D("10"))
    def test_stop_loss_negative_and_adverse_execution(self):
        out=model_return("100","110","90","SHORT","SL_FIRST",D("0.0006"),D("0.0005"))
        self.assertLess(D(out["net_ex_funding_usdt"]),D("-100"))
    def test_no_entry_does_not_invent_pnl(self):
        self.assertIsNone(model_return("100","110","90","SHORT","NO_ENTRY",D("0.0006"),D("0.0005")))
        self.assertIsNone(model_return("100","110","90","SHORT","AMBIGUOUS",D("0.0006"),D("0.0005")))
    def test_blocked_certificate_is_read_without_modification(self):
        with tempfile.TemporaryDirectory() as root:
            d=Path(root)
            archive=d/"pilot-original-archive"
            cert_dir=d/"pilot-original-certificate"
            archive.mkdir()
            cert_dir.mkdir()
            original=cert_dir/"certificate.json"
            snapshot=b"private test cohort"
            sha=hashlib.sha256(snapshot).hexdigest()
            source={"BTCUSDT":"a"*64,"ETHUSDT":"b"*64,"SOLUSDT":"c"*64}
            cert={"status":"REPLAY_MATCH_PRELIMINARY_COUNTS","signals":175,
                  "signals_sha256":sha,
                  "source_sha256":source,
                  "outcomes":{"TP_FIRST":29,"AMBIGUOUS":3,"NO_ENTRY":11,"NOT_EVALUABLE":132},
                  "zero_verified_fills":True}
            original.write_text(json.dumps(cert))
            before=original.read_bytes()
            manifest={"sources":[{"symbol":k,"sha256":v} for k,v in source.items()]}
            pretend={"source_signal_instances":175,
                     "complete_signal_instances":43,
                     "distinct_symbol_candidates":3,
                     "hypothetical_outcomes":{"TP_FIRST":3},
                     "scenario_net_totals":{"baseline":"19.750000"}}
            out=d/"new-research"
            with (patch("phase2_scientific_v11.validate_sources",return_value=({},manifest)),
                  patch("phase2_scientific_v11.validate_signals",return_value=([{"signal_id":"any"}]*175,sha)),
                  patch("phase2_scientific_v11.inspect_independent_opportunities",return_value=pretend)):
                result=run(archive,d/"signals.csv",original,out)
            self.assertTrue((out/"v11_independent_research.json").is_file())
            self.assertEqual(original.read_bytes(),before)
            self.assertEqual(result["original_private_certificate_sha256"],hashlib.sha256(before).hexdigest())
            with (patch("phase2_scientific_v11.validate_sources",return_value=({},manifest)),
                  patch("phase2_scientific_v11.validate_signals",return_value=([{"signal_id":"any"}]*175,sha)),
                  patch("phase2_scientific_v11.inspect_independent_opportunities",return_value=pretend)):
                with self.assertRaises(ValueError):run(archive,d/"signals.csv",original,out)
if __name__=="__main__": unittest.main()
