import csv
import unittest
from pathlib import Path
from phase2_historical_interval_gate import validate_intervals, validate_row

PATH = Path(__file__).with_name("HISTORICAL_MISSING_CONTRACT_INTERVALS_V1.csv")
REG = Path(__file__).with_name("HISTORICAL_ELIGIBILITY_20261108.csv")
with PATH.open(newline="",encoding="utf-8") as f:
    EVENTS={r["symbol"]:r for r in csv.DictReader(f)}
with REG.open(newline="",encoding="utf-8") as f:
    ELIGIBILITY={r["symbol"]:r for r in csv.DictReader(f)}

class HistoricalIntervalTests(unittest.TestCase):
    def test_real_ledger(self):
        result=validate_intervals()
        self.assertEqual(result["contracts"],15)
        self.assertEqual(result["with_scanner_evidence"],14)
        self.assertEqual(result["close_only_signals"],6)
        self.assertEqual(result["post_termination_signals"],1)
        self.assertEqual(result["post_termination_snapshots"],2)
        self.assertEqual(result["post_termination_permission_true"],0)
    def test_valid_record(self): validate_row(dict(EVENTS["SCRTUSDT"]),ELIGIBILITY)
    def test_false_source_rejected(self):
        r=dict(EVENTS["STBLUSDT"]);r["official_delisting_source"]="https://fraud.example/support/articles/x"
        with self.assertRaises(ValueError):validate_row(r,ELIGIBILITY)
    def test_wrong_order_rejected(self):
        r=dict(EVENTS["STBLUSDT"]);r["new_positions_block_scheduled_utc"]="2026-08-20T04:00:00Z"
        with self.assertRaises(ValueError):validate_row(r,ELIGIBILITY)
    def test_missing_relisting_evidence_cannot_be_promoted(self):
        r=dict(EVENTS["STBLUSDT"]);r["relisting_evidence"]="VERIFIED"
        with self.assertRaises(ValueError):validate_row(r,ELIGIBILITY)
    def test_no_continuous_tradeability_claim(self):
        r=dict(EVENTS["SCRTUSDT"]);r["continuous_eligibility_certified"]="YES"
        with self.assertRaises(ValueError):validate_row(r,ELIGIBILITY)
    def test_close_only_review_flag(self):
        r=dict(EVENTS["SCRTUSDT"]);r["review_flag"]="NONE"
        with self.assertRaises(ValueError):validate_row(r,ELIGIBILITY)
    def test_post_delist_signal_requires_review(self):
        r=dict(EVENTS["STORJUSDT"]);r["review_flag"]="NONE"
        with self.assertRaises(ValueError):validate_row(r,ELIGIBILITY)
    def test_post_delist_permission_fails(self):
        r=dict(EVENTS["STORJUSDT"]);r["post_termination_signals_with_trade_permission_true"]="1"
        with self.assertRaises(ValueError):validate_row(r,ELIGIBILITY)
    def test_event_register_disagreement(self):
        r=dict(EVENTS["STORJUSDT"]);r["futures_termination_scheduled_utc"]="2026-08-27T07:00:00Z"
        with self.assertRaises(ValueError):validate_row(r,ELIGIBILITY)
    def test_unverified_window_cannot_be_promoted(self):
        r=dict(EVENTS["SCRTUSDT"]);r["nov08_status"]="VERIFIED"
        with self.assertRaises(ValueError):validate_row(r,ELIGIBILITY)
    def test_unknown_registration_rejected(self):
        r=dict(EVENTS["STORJUSDT"]);r["symbol"]="FCHUSDT"
        with self.assertRaises(ValueError):validate_row(r,ELIGIBILITY)
if __name__=="__main__":unittest.main()
