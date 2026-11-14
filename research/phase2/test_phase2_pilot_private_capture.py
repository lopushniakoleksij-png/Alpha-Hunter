import json
import tempfile
import unittest
from pathlib import Path
from phase2_pilot_private_capture import capture, MAX_RESPONSE
from phase2_scientific_pilot_replay import SOURCE_START_MS

def body():
    rows=[[str(SOURCE_START_MS+i*3600000),"9","10","8","9","1","1"] for i in range(48)]
    return json.dumps({"code":"00000","requestTime":1794652927683,"data":rows}).encode()
class Response:
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n): return self.data
def ok(req,timeout): return Response(body())
class PrivateCaptureTests(unittest.TestCase):
    def test_three_bounded_private_capture_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"pilot"
            result=capture(out,fetch=ok)
            self.assertEqual(result["verified_hourly_candles"],144)
            manifest=json.loads((out/"manifest.json").read_text())
            self.assertEqual(len(manifest["sources"]),3)
            self.assertEqual(sorted(s["symbol"] for s in manifest["sources"]),["BTCUSDT","ETHUSDT","SOLUSDT"])
            self.assertEqual(len(list(out.glob("*.json"))),4)
            self.assertFalse(manifest["historical_universe_certified"])
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):capture(Path(tmp),fetch=ok)
    def test_invalid_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            def bad(req,timeout):return Response(b'{"code":"400","data":[]}')
            with self.assertRaises(ValueError):capture(Path(tmp)/"private",fetch=bad)
    def test_relative_output_rejected(self):
        with self.assertRaises(ValueError):capture(Path("relative"),fetch=ok)
if __name__=="__main__":unittest.main()
