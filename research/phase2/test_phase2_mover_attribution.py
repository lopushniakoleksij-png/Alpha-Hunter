import unittest
from phase2_mover_attribution import SignalObservation as S, attribute_mover as a
START="2026-11-01T00:00:00+00:00"
END="2026-11-02T00:00:00+00:00"
def signal(i,t, direction="LONG", blocked=False, permitted=True, complete=True):
    return S(i,"BTCUSDT",f"2026-11-01T{t}:00:00+00:00","DIRECTION_EMERGING_LONG",direction,permitted,blocked,complete)
def run(signals, **kw):
    return a("BTCUSDT","LONG",START,END,signals,universe_complete=kw.pop("universe_complete",True),scan_persistence_complete=kw.pop("scan_persistence_complete",True),**kw)
class AttributionTests(unittest.TestCase):
    def test_early(self): self.assertEqual(run([signal("1","03")]).category,"EARLY")
    def test_late(self): self.assertEqual(run([signal("1","10")]).category,"LATE")
    def test_blocked(self): self.assertEqual(run([signal("1","02",blocked=True)]).category,"BLOCKED")
    def test_missed(self): self.assertEqual(run([]).category,"MISSED")
    def test_missing_scan(self): self.assertEqual(run([],scan_persistence_complete=False).category,"UNKNOWN")
    def test_incomplete_universe(self): self.assertEqual(run([],universe_complete=False).category,"UNKNOWN")
    def test_future_signal_ignored(self):
        self.assertEqual(run([S("future","BTCUSDT","2026-11-03T00:00:00+00:00","X","LONG",True,False)]).category,"MISSED")
    def test_wrong_direction(self): self.assertEqual(run([signal("1","02",direction="SHORT")]).category,"MISSED")
    def test_earliest_deterministic(self):
        self.assertEqual(run([signal("b","03"),signal("a","03")]).first_signal_id,"a")
    def test_incomplete_signal(self): self.assertEqual(run([signal("1","02",complete=False)]).category,"UNKNOWN")
if __name__=="__main__":
    unittest.main()
