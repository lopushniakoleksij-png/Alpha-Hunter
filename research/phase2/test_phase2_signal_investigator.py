import unittest
from decimal import Decimal as D
from phase2_signal_investigator import Setup, Bar, investigate

def s(direction="LONG", disposition="BLOCKED", entry="100", stop="95", target="110"):
    return Setup("sig1", direction, D(entry), D(stop), D(target), disposition, "S1")

def b(t, low, high):
    return Bar(t, D(low), D(high))

class InvestigatorTests(unittest.TestCase):
    def test_tp_first(self):
        r=investigate(s(),[b("01","99","101"),b("02","101","111")])
        self.assertEqual(r.status,"TP_FIRST")
        self.assertTrue(r.hypothetical)
    def test_stop_first(self):
        self.assertEqual(investigate(s(),[b("01","99","101"),b("02","94","100")]).status,"SL_FIRST")
    def test_both_same_bar(self):
        self.assertEqual(investigate(s(),[b("01","99","101"),b("02","94","111")]).status,"AMBIGUOUS")
    def test_entry_and_exit_same_bar(self):
        self.assertEqual(investigate(s(),[b("01","94","101")]).status,"AMBIGUOUS")
    def test_no_entry(self):
        self.assertEqual(investigate(s(),[b("01","101","109")]).status,"NO_ENTRY")
    def test_missing_levels(self):
        x=Setup("x","LONG",D("100"),None,D("110"),"WATCH")
        self.assertEqual(investigate(x,[]).status,"NOT_EVALUABLE")
    def test_short_tp(self):
        x=s("SHORT","ACCEPTED","100","105","90")
        r=investigate(x,[b("01","99","101"),b("02","89","99")])
        self.assertEqual(r.status,"TP_FIRST")
        self.assertFalse(r.hypothetical)
    def test_out_of_order(self):
        self.assertEqual(investigate(s(),[b("02","99","101"),b("01","100","111")]).status,"UNKNOWN")
if __name__=="__main__":
    unittest.main()
