import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from ops import r9_depth_timing as d
from ops.runtime_release_fingerprint import runtime_release_paths
from alpha_hunter.scientific_identity import _scientific_paths


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.order = dict(order_id='o', symbol='TESTUSDT', direction='LONG',
                          limit_price=101, quantity=3,
                          submitted_at_utc=(self.now-timedelta(minutes=1)).isoformat())
        self.book = dict(ts=int(self.now.timestamp()*1000),
                         asks=[[101, 2], [100, 2]], bids=[[99, 2], [98, 3]])

    def test_long_deeper_capacity_sorted(self):
        r = d.classify(self.order, self.book, self.now)
        self.assertEqual(r['verdict'], 'RETURNED_DEPTH_SUFFICIENT_L1_INSUFFICIENT')
        self.assertAlmostEqual(r['displayed_book_vwap'], 301/3)
        self.assertFalse(r['fill_proven'])

    def test_short_parity(self):
        self.order.update(direction='SHORT', limit_price=98)
        r = d.classify(self.order, self.book, self.now)
        self.assertEqual(r['verdict'], 'RETURNED_DEPTH_SUFFICIENT_L1_INSUFFICIENT')
        self.assertAlmostEqual(r['displayed_book_vwap'], 296/3)

    def test_not_crossed(self):
        self.order['limit_price'] = 99
        self.assertEqual(d.classify(self.order,self.book,self.now)['verdict'], 'NOT_CROSSED')

    def test_l1_exact_capacity(self):
        self.order['quantity'] = 2
        self.assertEqual(d.classify(self.order,self.book,self.now)['verdict'], 'L1_SUFFICIENT')

    def test_returned_depth_is_not_entire_market(self):
        self.order['quantity'] = 6
        r = d.classify(self.order,self.book,self.now)
        self.assertEqual(r['verdict'], 'RETURNED_DEPTH_INSUFFICIENT')
        self.assertIsNone(r['displayed_book_vwap'])

    def test_invalid_books_rejected(self):
        for change in ({'ts':0}, {'ts':int((self.now+timedelta(minutes=1)).timestamp()*1000)},
                       {'asks':[[100,float('inf')]]}, {'asks':[[100,2],[100,3]]},
                       {'asks':[]}, {'bids':[[102,2]]}):
            with self.subTest(change=change), self.assertRaises((ValueError,KeyError)):
                d.classify(self.order, {**self.book, **change}, self.now)

    def fixture_get(self, base, key, table, params):
        if table == 'alpha_hunter_paper_admission_open_v09':
            return [dict(spec_id=d.SPEC, scientific_fingerprint_sha256=d.FINGERPRINT,
                         paper_only=True, exchange_authority=False,trade_permission=False,order_path='NONE')]
        if table == 'alpha_hunter_production_deployment_runtime_status_v03':
            return [dict(deployment_status='MATCHED',scientific_fingerprint_sha256=d.FINGERPRINT,
                         latest_canonical_scan_at_utc=self.now.isoformat(),latest_canonical_run_id='scan')]
        return [self.order]

    def test_network_failure_persisted_and_no_execution_writes(self):
        writes=[]
        with patch.object(d,'_rest_get',side_effect=self.fixture_get), \
             patch.object(d,'_fetch_depth',side_effect=TimeoutError('secret')), \
             patch.object(d,'_rest_insert',side_effect=lambda b,k,t,r:writes.append((t,r))):
            result=d.collect('base','key')
        self.assertEqual(result['status'],'DEGRADED')
        self.assertEqual([t for t,r in writes],[d.RUNS,d.CAPTURES,d.RUNS])
        self.assertEqual(writes[1][1]['verdict'],'CAPTURE_FAILED')
        self.assertNotIn('secret',str(writes))

    def test_non_crossed_capture_is_kept(self):
        self.order['limit_price']=99
        writes=[]
        with patch.object(d,'_rest_get',side_effect=self.fixture_get), \
             patch.object(d,'_fetch_depth',return_value=(self.book,None)), \
             patch.object(d,'_rest_insert',side_effect=lambda b,k,t,r:writes.append((t,r))):
            result=d.collect('base','key')
        self.assertEqual(result['captures_saved'],1)
        self.assertEqual(writes[1][1]['verdict'],'NOT_CROSSED')

    def test_gate_failure_does_not_fetch(self):
        with patch.object(d,'_rest_get',return_value=[]), patch.object(d,'_rest_insert'), \
             patch.object(d,'_fetch_depth') as fetch:
            self.assertEqual(d.collect('base','key')['status'],'FAILED')
            fetch.assert_not_called()

    def test_no_frozen_fingerprint_files_changed(self):
        root=Path(__file__).resolve().parents[1]
        for files in (_scientific_paths(root),runtime_release_paths(root)):
            self.assertNotIn(root/'ops/r9_depth_timing.py',files)
            self.assertNotIn(root/'ops/sql/r9_depth_timing_v01.sql',files)


if __name__ == '__main__':
    unittest.main()
