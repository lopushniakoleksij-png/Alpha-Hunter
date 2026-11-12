import unittest
from phase2_evidence_coverage import CandleEvidence as C,validate_hourly_window as v
from datetime import datetime,timedelta,timezone
BASE=datetime(2026,11,1,tzinfo=timezone.utc)
def t(h): return (BASE+timedelta(hours=h)).isoformat()
def c(h, **kw):
    x=dict(symbol="BTCUSDT",open_utc=t(h),known_at_utc=t(h+1),captured_at_utc=t(h+1),source_exchange="BITGET",product_type="USDT-M",granularity="1H",fully_closed=True,high=101.0,low=99.0,source_id=str(h))
    x.update(kw)
    return C(**x)
def run(rows,asof=24):return v("BTCUSDT",t(0),t(24),t(asof),rows)
class CoverageTests(unittest.TestCase):
    def test_complete(self):self.assertEqual(run([c(i) for i in range(24)]).status,"COMPLETE")
    def test_missing_hour(self):self.assertEqual(run([c(i) for i in range(23)]).reason,"INCOMPLETE_HOURLY_WINDOW")
    def test_duplicate(self):self.assertEqual(run([c(i) for i in range(24)]+[c(0)]).reason,"DUPLICATE_HOURLY_CANDLE")
    def test_future_capture(self):self.assertEqual(run([c(i,captured_at_utc=t(25)) for i in range(24)]).reason,"INVALID_OR_FUTURE_EVIDENCE")
    def test_future_known(self):self.assertEqual(run([c(i,known_at_utc=t(25)) for i in range(24)]).reason,"INVALID_OR_FUTURE_EVIDENCE")
    def test_not_closed(self):self.assertEqual(run([c(i,fully_closed=False) for i in range(24)]).reason,"INVALID_OR_FUTURE_EVIDENCE")
    def test_wrong_market(self):self.assertEqual(run([c(i,product_type="SPOT") for i in range(24)]).reason,"INVALID_OR_FUTURE_EVIDENCE")
    def test_no_lookahead(self):self.assertEqual(run([c(i) for i in range(24)],asof=23).reason,"WINDOW_NOT_YET_KNOWN")
    def test_wrong_symbol(self):self.assertEqual(run([c(i,symbol="ETHUSDT") for i in range(24)]).reason,"INCOMPLETE_HOURLY_WINDOW")
if __name__=="__main__":unittest.main()
