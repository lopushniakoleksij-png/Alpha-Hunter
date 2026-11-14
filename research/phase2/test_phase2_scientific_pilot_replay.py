import json
import unittest
from datetime import datetime,timezone
from phase2_scientific_pilot_replay import replay,SOURCE_START_MS,SYMBOLS

def candle_pack(*,entry=True,target=True,stop=False,ambiguous_entry=False):
    rows=[]
    for i in range(48):
        high="11" if i==3 and entry else "9.5"
        low="9" if i==3 and entry else "8.5"
        if i==3 and ambiguous_entry:low="6"
        if i==4 and target:low="6"
        if i==4 and stop:high="16"
        close="9"
        op="9"
        hi=max(float(high),float(op),float(close))
        lo=min(float(low),float(op),float(close))
        rows.append([str(SOURCE_START_MS+i*3600000),op,str(hi),str(lo),close,"1","1"])
    return json.dumps({"code":"00000","requestTime":1794652927683,"data":rows}).encode()

def signal(**kw):
    data={"signal_id":"s1","symbol":"BTCUSDT",
          "detected_at_utc":"2026-11-08T02:05:00Z",
          "created_at":"2026-11-08T02:05:30Z",
          "direction":"SHORT","trade_permission":False,
          "entry_price":10,"stop_loss":15,"take_profit":7}
    data.update(kw)
    return data

def source(**kw):
    return {s:candle_pack(**kw) for s in SYMBOLS}

class ReplayTests(unittest.TestCase):
    def test_tp_after_entry(self):
        r=replay([signal()],source())
        self.assertEqual(r["outcomes"],{"TP_FIRST":1})
        self.assertEqual(r["verified_executable_fills"],0)
    def test_no_entry(self):
        self.assertEqual(replay([signal()],source(entry=False))["outcomes"],{"NO_ENTRY":1})
    def test_ambiguous_entry_candle(self):
        self.assertEqual(replay([signal()],source(ambiguous_entry=True))["outcomes"],{"AMBIGUOUS":1})
    def test_both_exit_levels_same_candle(self):
        self.assertEqual(replay([signal()],source(stop=True))["outcomes"],{"AMBIGUOUS":1})
    def test_missing_levels(self):
        self.assertEqual(replay([signal(stop_loss=None)],source())["outcomes"],{"NOT_EVALUABLE":1})
    def test_missing_created_at_is_unknown(self):
        self.assertEqual(replay([signal(created_at=None)],source())["outcomes"],{"UNKNOWN":1})
    def test_created_after_hour_is_unknown(self):
        self.assertEqual(replay([signal(created_at="2026-11-08T03:01:00Z")],source())["outcomes"],{"UNKNOWN":1})
    def test_duplicate_signal_id_rejected(self):
        with self.assertRaises(ValueError):replay([signal(),signal()],source())
    def test_trade_permission_rejected(self):
        with self.assertRaises(ValueError):replay([signal(trade_permission=True)],source())
    def test_missing_source_rejected(self):
        with self.assertRaises(ValueError):replay([signal()],{"BTCUSDT":candle_pack()})
    def test_outside_cohort_rejected(self):
        with self.assertRaises(ValueError):
            replay([signal(detected_at_utc="2026-11-09T02:05:00Z")],source())
if __name__=="__main__":unittest.main()
