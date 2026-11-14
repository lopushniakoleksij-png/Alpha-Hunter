import unittest
from phase2_backfill_planner import plan
A="2026-11-02T00:00:00Z"
B="2026-11-09T00:00:00Z"
class PlannerTests(unittest.TestCase):
    def test_seven_days_split(self):
        a=plan(["BTCUSDT"],A,B)
        self.assertEqual([x.expected_hours for x in a],[84,84])
        self.assertEqual(a[0].end_ms,a[1].start_ms)
    def test_deterministic(self):
        self.assertEqual(plan(["SOLUSDT","BTCUSDT"],A,B),plan(["BTCUSDT","SOLUSDT"],A,B))
    def test_reject_unknown(self):
        with self.assertRaises(ValueError):plan(["FAKEUSDT"],A,B)
    def test_reject_duplicate(self):
        with self.assertRaises(ValueError):plan(["BTCUSDT","BTCUSDT"],A,B)
    def test_reject_too_long(self):
        with self.assertRaises(ValueError):plan(["BTCUSDT"],"2026-11-01T00:00:00Z","2026-11-09T00:00:00Z")
    def test_reject_non_utc(self):
        with self.assertRaises(ValueError):plan(["BTCUSDT"],"2026-11-02T00:00:00+01:00",B)
    def test_reject_unaligned(self):
        with self.assertRaises(ValueError):plan(["BTCUSDT"],"2026-11-02T00:01:00Z",B)
    def test_url_is_public_read_only(self):
        x=plan(["BTCUSDT"],A,B)[0]
        self.assertIn("productType=USDT-FUTURES",x.url)
        self.assertIn("/market/history-candles?",x.url)
if __name__=="__main__":unittest.main()
