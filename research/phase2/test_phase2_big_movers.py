import unittest
from decimal import Decimal as D
from phase2_big_movers import Snapshot, rank_movers

def s(sym, t, price, market="USDT-M", complete=True):
    return Snapshot(sym,t,D(price),sym+t,market,complete)

A="2026-11-01T00:00:00+00:00"
B="2026-11-02T00:00:00+00:00"
C="2026-11-03T00:00:00+00:00"

class MoversTests(unittest.TestCase):
    def test_gainers_and_losers(self):
        g,l,e=rank_movers([s("A",A,"100"),s("B",A,"100")],
                           [s("A",B,"120"),s("B",B,"80")],24)
        self.assertEqual((g[0].symbol,l[0].symbol),("A","B"))
        self.assertEqual(g[0].return_pct,D("20"))
    def test_no_nearest_timestamp(self):
        g,l,e=rank_movers([s("A",A,"100")],[s("A",C,"120")],24)
        self.assertEqual(e["A"],"WINDOW_MISMATCH")
    def test_duplicate_is_excluded(self):
        _,_,e=rank_movers([s("A",A,"100"),s("A",A,"100")],[s("A",B,"120")],24)
        self.assertEqual(e["A"],"DUPLICATE_SNAPSHOT")
    def test_missing_endpoint(self):
        _,_,e=rank_movers([s("A",A,"100")],[],24)
        self.assertEqual(e["A"],"MISSING_ENDPOINT")
    def test_spot_excluded(self):
        _,_,e=rank_movers([s("A",A,"100","SPOT")],[s("A",B,"120")],24)
        self.assertEqual(e["A"],"WRONG_MARKET")
    def test_invalid_price(self):
        _,_,e=rank_movers([s("A",A,"0")],[s("A",B,"120")],24)
        self.assertEqual(e["A"],"INVALID_PRICE")
    def test_incomplete(self):
        _,_,e=rank_movers([s("A",A,"100",complete=False)],[s("A",B,"120")],24)
        self.assertEqual(e["A"],"INCOMPLETE_PROVENANCE")
    def test_tie_determinism(self):
        g,_,_=rank_movers([s("B",A,"100"),s("A",A,"100")],
                          [s("B",B,"110"),s("A",B,"110")],24)
        self.assertEqual([x.symbol for x in g],["A","B"])
if __name__=="__main__":
    unittest.main()
