import csv
import json
import tempfile
import unittest
from pathlib import Path
from phase2_pilot_private_capture import capture
from phase2_pilot_offline_certify import validate_sources,validate_signals,certify
from phase2_scientific_pilot_replay import SOURCE_START_MS

class Response:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.raw
    def __init__(self,raw):self.raw=raw

def fetch(req,timeout):
    rows=[[str(SOURCE_START_MS+i*3600000),"9","10","8","9","1","1"] for i in range(48)]
    return Response(json.dumps({"code":"00000","requestTime":1794652927683,"data":rows}).encode())

COLUMNS=["signal_id","symbol","detected_at_utc","created_at","state","direction",
"trade_permission","entry_price","stop_loss","take_profit","reference_price",
"huge_rr_score","confidence_estimate_pct","reward_risk"]

def signals(path):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS)
        w.writeheader()
        n=0
        for sym,count in (("BTCUSDT",59),("ETHUSDT",57),("SOLUSDT",59)):
            for i in range(count):
                n+=1
                w.writerow({"signal_id":f"signal-{n}","symbol":sym,
                            "detected_at_utc":"2026-11-08T02:05:00Z",
                            "created_at":"2026-11-08T02:05:20Z",
                            "state":"NEUTRAL","direction":"",
                            "trade_permission":"false","entry_price":"",
                            "stop_loss":"","take_profit":""})
    return path

class OfflineCertificateTests(unittest.TestCase):
    def test_source_archive_verifies_hashes_and_scope(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"evidence"
            capture(folder,fetch=fetch)
            raw,manifest=validate_sources(folder)
            self.assertEqual(len(raw),3)
            self.assertEqual(manifest["source_count"],3)
    def test_corrupt_price_archive_fails(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"evidence"
            capture(folder,fetch=fetch)
            m=json.loads((folder/"manifest.json").read_text())
            (folder/m["sources"][0]["filename"]).write_bytes(b"tamper")
            with self.assertRaises(ValueError):validate_sources(folder)
    def test_wrong_source_url_fails(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"evidence"
            capture(folder,fetch=fetch)
            p=folder/"manifest.json";m=json.loads(p.read_text())
            m["sources"][0]["source_url"]="https://api.bitget.com/api/v2/mix/market/history-candles?symbol=ETHUSDT"
            p.write_text(json.dumps(m))
            with self.assertRaises(ValueError):validate_sources(folder)
    def test_signal_snapshot_175_rows(self):
        with tempfile.TemporaryDirectory() as td:
            rows,sha=validate_signals(signals(Path(td)/"signals.csv"))
            self.assertEqual(len(rows),175)
            self.assertEqual(len(sha),64)
            self.assertTrue(all(x["trade_permission"] is False for x in rows))
    def test_wrong_signal_count_fails(self):
        with tempfile.TemporaryDirectory() as td:
            path=signals(Path(td)/"signals.csv")
            path.write_text("\n".join(path.read_text().splitlines()[:-1])+"\n")
            with self.assertRaises(ValueError):validate_signals(path)
    def test_never_certify_wrong_results(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);archive=root/"evidence";capture(archive,fetch=fetch)
            snapshot=signals(root/"signals.csv")
            target=root/"certificate"
            with self.assertRaises(ValueError):certify(archive,snapshot,target)
            self.assertFalse(target.exists())
if __name__=="__main__":unittest.main()
