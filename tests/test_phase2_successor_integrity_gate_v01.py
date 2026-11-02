"""No network, exchange, production database or secret access."""
import importlib.util
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'ops/reviews/phase2_successor_integrity_gate_v01.py'
spec = importlib.util.spec_from_file_location('phase2_gate', SRC)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def sample():
    p = {'entry_order_id':'p1','decision_id':'d1','symbol':'BTCUSDT',
         'direction':'LONG','prior_observed_at_utc':'2026-11-02T08:43:00Z'}
    receipt = {'entry_order_id':'p1','decision_id':'d1','symbol':'BTCUSDT',
               'direction':'LONG','source_run_id':'run-100',
               'observed_at_utc':'2026-11-02T09:03:00Z',
               'outcome':'NO_TRIGGER','blockers':[], 'paper_only':True,
               'exchange_authority':False,'trade_permission':False,'order_path':'NONE'}
    return {'run_id':'run-100','collected_at_utc':'2026-11-02T09:04:00Z',
            'expected_symbols':['BTCUSDT','ETHUSDT'],
            'persisted_symbols':['BTCUSDT','ETHUSDT'],
            'positions':[p],'receipts':[receipt],
            'expected_fingerprint':'fp-r11','observed_fingerprint':'fp-r11',
            'expected_source':'RENDER_CRON','observed_source':'RENDER_CRON',
            'monitoring_limit_minutes':35}


class Phase2GateTests(unittest.TestCase):
    def evaluate(self, **changes):
        s=sample();s.update(changes)
        return gate.evaluate_scan(**s)

    def assert_rejects(self, code, **changes):
        r=self.evaluate(**changes)
        self.assertIn(code,r['blockers'])
        self.assertFalse(r['scientific_eligible'])
        self.assertFalse(r['trade_permission'])
        self.assertFalse(r['production_promotion_permitted'])

    def test_complete_two_symbol_scan_and_monitoring(self):
        r=self.evaluate()
        self.assertTrue(r['operational_evidence_complete'])
        self.assertTrue(r['scientific_eligible'])
        self.assertFalse(r['trade_permission'])

    def test_actual_61_expected_zero_children(self):
        self.assert_rejects('CANONICAL_CHILD_IDENTITY_INCOMPLETE',expected_symbols=[f'S{i}' for i in range(61)],persisted_symbols=[])

    def test_partial_child_write_and_repeated_children(self):
        self.assert_rejects('CANONICAL_CHILD_IDENTITY_INCOMPLETE',persisted_symbols=['BTCUSDT'])
        self.assert_rejects('PERSISTED_SYMBOL_INVENTORY_INVALID',persisted_symbols=['BTCUSDT','BTCUSDT'])

    def test_mismatched_cohort_fingerprint(self):
        self.assert_rejects('SCIENTIFIC_FINGERPRINT_MISMATCH',observed_fingerprint='fp-r10')

    def test_wrong_source(self):
        self.assert_rejects('RUN_SOURCE_MISMATCH',observed_source='GITHUB')

    def test_no_receipt_not_empty_monitoring(self):
        self.assert_rejects('MONITORING_RECEIPT_COVERAGE_FAILED',receipts=[])

    def test_duplicate_receipt(self):
        r=sample()['receipts'][0]
        self.assert_rejects('DUPLICATE_OR_MISSING_RECEIPT_ID',receipts=[r,r])

    def test_late_gap_remains_invalid_even_with_new_receipt(self):
        p=sample()['positions'][0].copy()
        p['prior_observed_at_utc']='2026-11-02T08:22:00Z'
        self.assert_rejects('MONITORING_GAP_OVER_FROZEN_LIMIT',positions=[p])

    def test_exact_35_minute_boundary_allowed(self):
        p=sample()['positions'][0].copy()
        p['prior_observed_at_utc']='2026-11-02T08:28:00Z'
        self.assertTrue(self.evaluate(positions=[p])['operational_evidence_complete'])

    def test_receipt_staleness(self):
        r=sample()['receipts'][0].copy()
        r['observed_at_utc']='2026-11-02T08:25:00Z'
        p=sample()['positions'][0].copy();p['prior_observed_at_utc']='2026-11-02T08:00:00Z'
        self.assert_rejects('MONITORING_RECEIPT_STALE',receipts=[r],positions=[p])

    def test_timestamp_missing_timezone(self):
        self.assert_rejects('SCAN_TIMESTAMP_INVALID',collected_at_utc='2026-11-02T09:04:00')

    def test_no_prior_receipt_cannot_fake_first_touch(self):
        p=sample()['positions'][0].copy();p.pop('prior_observed_at_utc')
        self.assert_rejects('MONITORING_TIME_EVIDENCE_MISSING',positions=[p])

    def test_unusable_and_mismatched_receipt(self):
        r=sample()['receipts'][0].copy();r['outcome']='INPUT_MISSING'
        self.assert_rejects('RECEIPT_UNUSABLE',receipts=[r])
        r=sample()['receipts'][0].copy();r['symbol']='ETHUSDT'
        self.assert_rejects('RECEIPT_IDENTITY_MISMATCH',receipts=[r])

    def test_historical_bad_cohort_never_rehabilitated(self):
        r=self.evaluate(prior_cohort_failure=True)
        self.assertTrue(r['operational_evidence_complete'])
        self.assertFalse(r['scientific_eligible'])
        self.assertTrue(r['historical_failure_preserved'])

    def test_long_and_short_use_opposite_close_book(self):
        f=gate.check_exit_capacity
        self.assertEqual(f(direction='LONG',quantity=143,best_bid=1,best_ask=1.01,bid_size=40,ask_size=300),'INSUFFICIENT_CLOSE_SIDE_TOP_OF_BOOK')
        self.assertEqual(f(direction='SHORT',quantity=892,best_bid=1,best_ask=1.01,bid_size=1000,ask_size=13),'INSUFFICIENT_CLOSE_SIDE_TOP_OF_BOOK')
        self.assertEqual(f(direction='SHORT',quantity=10,best_bid=1,best_ask=1.01,bid_size=1,ask_size=15),'CAPACITY_OBSERVED_NOT_EXECUTION_PROVEN')

    def test_prior_stop_wins_over_later_horizon(self):
        result=gate.check_exit_capacity(direction='LONG',quantity=10,best_bid=1,best_ask=1.01,bid_size=20,ask_size=20,prior_stop_unresolved=True)
        self.assertEqual(result,'UNRESOLVED_PRIOR_STOP_PRECEDENCE')

    def test_no_fabricated_fill_for_missing_quotes(self):
        self.assertEqual(gate.check_exit_capacity(direction='LONG',quantity=10,best_bid=None,best_ask=1.01,bid_size=20,ask_size=20),'EXECUTABLE_QUOTE_OR_QUANTITY_MISSING')

if __name__ == '__main__':
    unittest.main()
