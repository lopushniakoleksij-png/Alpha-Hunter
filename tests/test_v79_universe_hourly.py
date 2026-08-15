from __future__ import annotations

import unittest
from datetime import datetime, timezone

from v79_universe_hourly_collector import (
    MODEL_VERSION,
    build_rows,
    classify_reason,
    hour_bucket,
    observation_id,
    selected_symbols_from_snapshot,
)

UTC = timezone.utc
OBSERVED_AT = datetime(
    2026, 8, 15, 18, 6, 21,
    tzinfo=UTC,
)


def config():
    return {
        "universe_scan": {
            "crypto_only": True,
            "reject_rwa": True,
            "reject_reality": True,
            "minimum_quote_volume": 100000,
            "maximum_24h_extension_pct": 25,
        }
    }


def contract(symbol: str):
    return {
        "symbol": symbol,
        "symbolType": "crypto",
        "isRwa": False,
        "isReality": False,
    }


def ticker(
    symbol: str,
    *,
    price: float = 1.0,
    change_pct: float = 10.0,
    volume: float = 1_000_000,
):
    return {
        "symbol": symbol,
        "lastPr": str(price),
        "change24h": str(
            change_pct / 100.0
        ),
        "quoteVolume": str(volume),
    }


class TestV79Identity(unittest.TestCase):

    def test_hour_bucket(self):
        bucket = hour_bucket(
            OBSERVED_AT
        )

        self.assertEqual(
            bucket.isoformat(),
            "2026-08-15T18:00:00+00:00",
        )

    def test_observation_id_is_same_hour_idempotent(self):
        first = observation_id(
            "TESTUSDT",
            hour_bucket(
                OBSERVED_AT
            ),
        )

        second = observation_id(
            "TESTUSDT",
            hour_bucket(
                OBSERVED_AT
            ),
        )

        self.assertEqual(
            first,
            second,
        )

    def test_model_is_shadow_audit(self):
        self.assertEqual(
            MODEL_VERSION,
            "7.9-universe-ledger-v1",
        )


class TestV79SelectionContext(unittest.TestCase):

    def test_reads_selected_symbols_from_universe(self):
        snapshot = {
            "universe": {
                "selected_symbols": [
                    "AAAUSDT",
                    "BBBUSDT",
                ]
            }
        }

        self.assertEqual(
            selected_symbols_from_snapshot(
                snapshot
            ),
            {
                "AAAUSDT",
                "BBBUSDT",
            },
        )

    def test_falls_back_to_snapshot_symbol_rows(self):
        snapshot = {
            "symbols": [
                {
                    "symbol":
                        "AAAUSDT"
                },
                {
                    "symbol":
                        "BBBUSDT"
                },
            ]
        }

        self.assertEqual(
            selected_symbols_from_snapshot(
                snapshot
            ),
            {
                "AAAUSDT",
                "BBBUSDT",
            },
        )


class TestV79CurrentStatus(unittest.TestCase):

    def test_selected_but_currently_overextended_is_overextended(self):
        reason = classify_reason(
            deep_scan_selected=True,
            crypto_allowed=True,
            liquidity_pass=True,
            extension_pass=False,
        )

        self.assertEqual(
            reason,
            "OVER_EXTENDED",
        )

    def test_selected_and_currently_eligible_is_selected(self):
        reason = classify_reason(
            deep_scan_selected=True,
            crypto_allowed=True,
            liquidity_pass=True,
            extension_pass=True,
        )

        self.assertEqual(
            reason,
            "DEEP_SCAN_SELECTED",
        )

    def test_eligible_not_selected(self):
        reason = classify_reason(
            deep_scan_selected=False,
            crypto_allowed=True,
            liquidity_pass=True,
            extension_pass=True,
        )

        self.assertEqual(
            reason,
            "ELIGIBLE_NOT_SELECTED",
        )


class TestV79Rows(unittest.TestCase):

    def test_selection_snapshot_context_is_preserved(self):
        rows, stats = build_rows(
            contracts=[
                contract(
                    "TESTUSDT"
                )
            ],
            instruments=[],
            tickers=[
                ticker(
                    "TESTUSDT"
                )
            ],
            selected_symbols={
                "TESTUSDT"
            },
            selection_snapshot_at_utc=
                "2026-08-15T17:53:46+00:00",
            selection_run_id=
                "run-123",
            product_type=
                "usdt-futures",
            config=config(),
            observed_at=
                OBSERVED_AT,
        )

        self.assertEqual(
            len(rows),
            1,
        )

        row = rows[0]

        self.assertEqual(
            row[
                "selection_snapshot_at_utc"
            ],
            "2026-08-15T17:53:46+00:00",
        )

        self.assertEqual(
            row[
                "selection_run_id"
            ],
            "run-123",
        )

        self.assertTrue(
            row[
                "deep_scan_selected"
            ]
        )

        self.assertEqual(
            row[
                "rejection_reason"
            ],
            "DEEP_SCAN_SELECTED",
        )

        self.assertFalse(
            row[
                "trade_permission"
            ]
        )

        self.assertEqual(
            stats["selected"],
            1,
        )

    def test_selected_symbol_can_be_currently_overextended(self):
        rows, _ = build_rows(
            contracts=[
                contract(
                    "DOLOUSDT"
                )
            ],
            instruments=[],
            tickers=[
                ticker(
                    "DOLOUSDT",
                    change_pct=-31.85,
                )
            ],
            selected_symbols={
                "DOLOUSDT"
            },
            selection_snapshot_at_utc=
                "2026-08-15T17:53:46+00:00",
            selection_run_id=
                "run-dolo",
            product_type=
                "usdt-futures",
            config=config(),
            observed_at=
                OBSERVED_AT,
        )

        row = rows[0]

        self.assertTrue(
            row[
                "deep_scan_selected"
            ]
        )

        self.assertFalse(
            row[
                "prefilter_eligible"
            ]
        )

        self.assertEqual(
            row[
                "rejection_reason"
            ],
            "OVER_EXTENDED",
        )

    def test_large_eligible_mover_can_be_not_selected(self):
        rows, stats = build_rows(
            contracts=[
                contract(
                    "ENSOUSDT"
                )
            ],
            instruments=[],
            tickers=[
                ticker(
                    "ENSOUSDT",
                    change_pct=23.06,
                )
            ],
            selected_symbols=set(),
            selection_snapshot_at_utc=
                "2026-08-15T17:53:46+00:00",
            selection_run_id=
                "run-enso",
            product_type=
                "usdt-futures",
            config=config(),
            observed_at=
                OBSERVED_AT,
        )

        row = rows[0]

        self.assertTrue(
            row[
                "prefilter_eligible"
            ]
        )

        self.assertFalse(
            row[
                "deep_scan_selected"
            ]
        )

        self.assertEqual(
            row[
                "rejection_reason"
            ],
            "ELIGIBLE_NOT_SELECTED",
        )

        self.assertEqual(
            stats[
                "eligible_not_selected"
            ],
            1,
        )


if __name__ == "__main__":
    unittest.main()
