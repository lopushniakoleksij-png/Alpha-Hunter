import unittest
from decimal import Decimal as D
from phase2_candle_reconciliation import CandleRecord as C,reconcile
def c(**kw):
    x=dict(symbol="BTCUSDT",market="USDT-FUTURES",granularity="1H",
           open_utc="2026-11-08T00:00:00Z",source_exchange="BITGET",
           source_endpoint="/api/v3/market/history-candles",source_row_id="r1",
           episode_id="e1",open_price=D("100"),high=D("110"),
           low=D("90"),close=D("105"),fully_closed=True)
    x.update(kw)
    return C(**x)
class ReconciliationTests(unittest.TestCase):
    def test_unique(self):self.assertEqual(reconcile([c()]).status,"UNIQUE")
    def test_identical_duplicate(self):
        r=reconcile([c(),c(source_row_id="r2",episode_id="e2")])
        self.assertEqual(r.status,"DEDUPED_IDENTICAL")
        self.assertEqual(r.source_ids,("r1","r2"))
        self.assertEqual(r.episodes,("e1","e2"))
    def test_conflict(self):
        self.assertEqual(reconcile([c(),c(source_row_id="r2",close=D("106"))]).status,"CONFLICT")
    def test_mixed_hour(self):
        self.assertEqual(reconcile([c(),c(open_utc="2026-11-08T01:00:00Z")]).status,"MIXED_KEYS")
    def test_bad_ohlc(self):
        self.assertEqual(reconcile([c(low=D("106"))]).status,"INVALID")
    def test_unclosed(self):
        self.assertEqual(reconcile([c(fully_closed=False)]).status,"INVALID")
    def test_missing(self):self.assertEqual(reconcile([]).status,"MISSING")
    def test_no_source(self):self.assertEqual(reconcile([c(source_row_id="")]).status,"INVALID")
if __name__=="__main__":unittest.main()
