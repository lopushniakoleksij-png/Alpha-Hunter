from __future__ import annotations

import unittest
from unittest.mock import patch

import alpha_hunter.collector as collector


class TestPrefilterDataIntegrity(unittest.TestCase):

    def test_missing_change24h_is_not_eligible(self):
        config = {
            "universe_scan": {
                "deep_scan_limit": 30,
                "minimum_quote_volume": 100000,
                "maximum_24h_extension_pct": 25,
                "preserve_previous_candidates": False,
            }
        }

        contracts = [
            {"symbol": "MISSINGUSDT"},
            {"symbol": "VALIDUSDT"},
        ]

        tickers = [
            {
                "symbol": "MISSINGUSDT",
                "lastPr": "1",
                "quoteVolume": "1000000",
                "change24h": None,
            },
            {
                "symbol": "VALIDUSDT",
                "lastPr": "1",
                "quoteVolume": "1000000",
                "change24h": "0.01",
            },
        ]

        metadata = {
            "MISSINGUSDT": {},
            "VALIDUSDT": {},
        }

        with (
            patch.object(
                collector,
                "build_instrument_map",
                return_value=metadata,
            ),
            patch.object(
                collector,
                "instrument_is_allowed",
                return_value=True,
            ),
        ):
            selected, universe = (
                collector.select_market_universe(
                    contracts,
                    [],
                    tickers,
                    None,
                    config,
                )
            )

        self.assertEqual(
            universe["eligible_count"],
            1,
        )

        self.assertEqual(
            selected,
            ["VALIDUSDT"],
        )


if __name__ == "__main__":
    unittest.main()
