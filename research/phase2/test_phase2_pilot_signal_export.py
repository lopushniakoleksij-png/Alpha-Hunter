"""No-network tests for the private read-only pilot signal exporter."""
import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import phase2_pilot_signal_export as export

COLUMNS=["signal_id","symbol","detected_at_utc","created_at","state",
         "direction","trade_permission","entry_price","stop_loss","take_profit",
         "reference_price","huge_rr_score","confidence_estimate_pct","reward_risk"]

def csv_payload():
    out=io.StringIO()
    wr=csv.DictWriter(out,fieldnames=COLUMNS,lineterminator="\n")
    wr.writeheader()
    n=0
    for sym,count in (("BTCUSDT",59),("ETHUSDT",57),("SOLUSDT",59)):
        for k in range(count):
            n+=1
            wr.writerow({"signal_id":f"record-{n}","symbol":sym,
                         "detected_at_utc":"2026-11-08T12:05:00Z",
                         "created_at":"2026-11-08T12:05:15Z",
                         "state":"NEUTRAL","direction":"",
                         "trade_permission":"f"})
    return out.getvalue().encode()

class FakeCopy:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def __iter__(self):yield self.data

class FakeCursor:
    def __init__(self,data):self.data=data;self.commands=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,query):self.commands.append(query)
    def copy(self,query):
        if not query.startswith("COPY (") or "TO STDOUT" not in query:
            raise AssertionError("not safe read-only COPY")
        self.commands.append(query)
        return FakeCopy(self.data)

class FakeConn:
    def __init__(self,data):self.cur=FakeCursor(data)
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return self.cur

class PrivateSignalExportTests(unittest.TestCase):
    def test_verified_175_row_read_only_export(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/"signals.csv";conns=[]
            def connector(**kwargs):
                self.assertEqual(kwargs["sslmode"],"require")
                self.assertTrue(kwargs["autocommit"])
                conn=FakeConn(csv_payload());conns.append(conn);return conn
            with patch.object(export,"PRIVATE_ROOT",root):
                result=export.export_cohort(out,password="test-secret",connector=connector)
            self.assertEqual(result["signals"],175)
            self.assertTrue(result["read_only"])
            self.assertTrue(out.is_file())
            cmds=conns[0].cur.commands
            self.assertIn("READ ONLY",cmds[0])
            self.assertEqual(cmds[1],"SET LOCAL TIME ZONE 'UTC'")
            self.assertIn("TO STDOUT",cmds[2])
            self.assertEqual(cmds[3],"COMMIT")
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/"signals.csv";out.write_text("existing")
            with patch.object(export,"PRIVATE_ROOT",root):
                with self.assertRaises(ValueError):
                    export.export_cohort(out,password="test-secret",connector=lambda **kwargs:None)
    def test_missing_password(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(export,"PRIVATE_ROOT",root):
                with self.assertRaises(ValueError):
                    export.export_cohort(root/"signals.csv",password="",connector=lambda **kwargs:None)
    def test_partial_data_does_not_persist(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/"signals.csv"
            with patch.object(export,"PRIVATE_ROOT",root):
                with self.assertRaises(ValueError):
                    export.export_cohort(out,password="test-secret",
                                         connector=lambda **kwargs:FakeConn(b"signal_id,symbol\n"))
            self.assertFalse(out.exists())
            self.assertEqual(list(root.iterdir()),[])
if __name__=="__main__":
    unittest.main()
