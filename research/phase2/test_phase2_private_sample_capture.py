import io
import json
import tempfile
import unittest
from pathlib import Path
from phase2_private_sample_capture import capture
START=1794096000000
class FakeResponse:
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def read(self,n):return self.data
    def __init__(self,data):self.data=data
def good(req,timeout):
    rows=[[str(START+i*3600000),"100","110","90","105","1","100"] for i in range(24)]
    return FakeResponse(json.dumps({"code":"00000","requestTime":1794475503560,"data":rows}).encode())
class CaptureTests(unittest.TestCase):
    def test_offline_capture_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/"private"
            rows=capture(folder,fetch=good)
            self.assertEqual(rows[0]["status"],"PASS")
            self.assertEqual(rows[0]["observed_hours"],24)
            self.assertTrue((folder/rows[0]["filename"]).exists())
            self.assertTrue((folder/"manifest.json").exists())
    def test_refuse_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/"existing").write_text("x")
            with self.assertRaises(ValueError):capture(folder,fetch=good)
    def test_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            def bad(req,timeout):return FakeResponse(b'{"code":"error","data":[]}')
            with self.assertRaises(ValueError):capture(Path(tmp)/"private",fetch=bad)
if __name__=="__main__":unittest.main()
