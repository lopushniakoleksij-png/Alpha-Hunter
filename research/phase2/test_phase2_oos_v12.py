"""Offline regression tests for frozen OOS dates, evidence integrity and safety."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs,urlparse

import phase2_oos_v12_capture as capt
import phase2_oos_v12_export as exporter
import phase2_oos_v12_replay as replay

class FakeResponse:
    def __init__(self,b):self.raw=b
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.raw

def fake_fetch(req,timeout):
    p=parse_qs(urlparse(req.full_url).query)
    start=int(p["startTime"][0]);count=int(p["limit"][0])
    step=capt.DAY_MS if p["granularity"][0]=="1Dutc" else capt.HOUR_MS
    if p["granularity"][0]=="1Dutc":
        closes=["82066","81912.5","82983.9","84054.9","81384.1"]
        if count!=5:raise AssertionError("not pre-entry period")
        rows=[[str(start+i*step),closes[i],"85000","75000",closes[i],"1","1"] for i in range(5)]
    else:
        if count!=48:raise AssertionError("wrong bounded period")
        rows=[[str(start+i*step),"100","105","95","100","1","1"] for i in range(48)]
    return FakeResponse(json.dumps({"code":"00000","requestTime":1794658000000,"data":rows}).encode())

def make_row(day,symbol,suffix="s"):
    return {"signal_id":day+symbol+suffix,
            "symbol":symbol,
            "detected_at_utc":f"{day} 01:15:00.000000+00",
            "created_at":f"{day} 01:15:15.000000+00",
            "direction":"SHORT","trade_permission":"f",
            "entry_price":"100","stop_loss":"110","take_profit":"90",
            "reward_risk":"1",
            "execution_checks_json":json.dumps({"rr_minimum_met":False,
                                                 "participation_confirmed":True,
                                                 "momentum_confirmed":False}),
            "trade_permission_reason":"test"}

class OOSV12Tests(unittest.TestCase):
    def test_frozen_requests_only(self):
        specs=capt.requests()
        self.assertEqual(len(specs),10)
        self.assertEqual(sum(s["count"] for s in specs if s["granularity"]=="1H"),432)
        self.assertEqual(sum(s["count"] for s in specs if s["granularity"]=="1Dutc"),5)
        self.assertEqual({s["day"] for s in specs if s["granularity"]=="1H"},set(capt.DAYS))
    def test_private_capture_and_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/"new-oos"
            with patch.object(capt,"BASE",root):
                result=capt.capture(folder,fetch=fake_fetch)
            self.assertEqual(result["sources"],10)
            self.assertEqual(result["hourly_bars"],432)
            self.assertEqual(result["daily_prior_bars"],5)
            checked,_=replay.checked_archive(folder)
            self.assertEqual(len(checked),10)
            self.assertEqual(len(list(folder.glob("*.json"))),11)
            with patch.object(capt,"BASE",root):
                with self.assertRaises(ValueError):capt.capture(folder,fetch=fake_fetch)
    def test_raw_hash_tamper_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/"new-oos"
            with patch.object(capt,"BASE",root):capt.capture(folder,fetch=fake_fetch)
            m=json.loads((folder/"manifest.json").read_text())
            (folder/m["raw_sources"][0]["filename"]).write_text("CORRUPTED")
            with self.assertRaises(ValueError):replay.checked_archive(folder)
    def test_bad_date_series_fails(self):
        spec=capt.requests()[0]
        p=json.loads(fake_fetch(type("Req",(),{"full_url":spec["url"]})(),20).raw)
        p["data"][6][0]=p["data"][7][0]
        with self.assertRaises(ValueError):
            capt.check_payload(json.dumps(p).encode(),spec)
    def test_regimes_pre_day_only(self):
        spec=capt.requests()[-1]
        data=fake_fetch(type("Req",(),{"full_url":spec["url"]})(),20).raw
        reg=replay.preday_regimes(data)
        self.assertEqual([reg[d]["regime"] for d in capt.DAYS],
                         ["SIDEWAYS","RISING","FALLING"])
    def test_first_complete_per_symbol_day_ignores_later_trade_quality(self):
        rows=[make_row(d,s) for d in capt.DAYS for s in capt.SYMBOLS]
        better=make_row("2026-10-20","BTCUSDT","later")
        better["detected_at_utc"]="2026-10-20 15:15:00.000000+00"
        better["created_at"]="2026-10-20 15:15:25.000000+00"
        better["execution_checks_json"]=json.dumps({"rr_minimum_met":True,
                                                     "participation_confirmed":True,
                                                     "momentum_confirmed":True})
        chosen=replay.select_first([better]+rows)
        self.assertEqual(len(chosen),9)
        self.assertEqual(chosen[("2026-10-20","BTCUSDT")]["signal_id"],
                         make_row("2026-10-20","BTCUSDT")["signal_id"])
    def test_missing_candidate_fails_no_cherry_pick(self):
        rows=[make_row(d,s) for d in capt.DAYS for s in capt.SYMBOLS]
        with self.assertRaises(ValueError):replay.select_first(rows[:-1])
    def test_filter_checks_do_not_infer_permission(self):
        row=make_row("2026-10-20","BTCUSDT")
        checks=replay.classify_gates(row)
        self.assertEqual(checks,{"reward_risk":"FAIL","participation":"PASS","momentum":"FAIL"})
        row["execution_checks_json"]="{}"
        self.assertEqual(replay.classify_gates(row)["reward_risk"],"MISSING")
    def test_exact_frozen_readonly_signal_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/"cohort.csv"
            fields=list(exporter.FIELDS)
            with dest.open("w",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
                for day,n in exporter.EXPECTED.items():
                    for i in range(n):
                        row=make_row(day,capt.SYMBOLS[i%3],str(i))
                        writer.writerow(row)
            info=exporter.inspect_export(dest)
            self.assertEqual(info["records"],450)
            self.assertEqual(info["by_day"],exporter.EXPECTED)
            self.assertEqual(len(info["sha256"]),64)
    def test_replay_cannot_overwrite_existing_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            with patch.object(replay,"BASE",d):
                with self.assertRaises(ValueError):
                    replay.certify(d/"unused",d/"unused.csv",d)
if __name__=="__main__":
    unittest.main()
