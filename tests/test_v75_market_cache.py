import unittest

from v75_episode_market_tracker import (
    cached_1m_candles,
    cached_ticker,
)


class FakeClient:
    def __init__(self):
        self.candle_calls = []
        self.ticker_calls = []

    def candles(
        self,
        symbol,
        product_type,
        granularity,
        limit,
    ):
        self.candle_calls.append(
            (
                symbol,
                product_type,
                granularity,
                limit,
            )
        )
        return [
            [1, "1", "1", "1", "1"]
        ]

    def ticker(
        self,
        symbol,
        product_type,
    ):
        self.ticker_calls.append(
            (
                symbol,
                product_type,
            )
        )
        return {
            "lastPr": "1.0",
        }


class TestMarketSampleCache(
    unittest.TestCase
):
    def test_duplicate_symbol_reuses_candles(
        self,
    ):
        client = FakeClient()
        cache = {}

        first = cached_1m_candles(
            client,
            cache,
            "SUIUSDT",
            "usdt-futures",
        )

        second = cached_1m_candles(
            client,
            cache,
            "SUIUSDT",
            "usdt-futures",
        )

        self.assertIs(
            first,
            second,
        )
        self.assertEqual(
            len(client.candle_calls),
            1,
        )

    def test_duplicate_symbol_reuses_ticker(
        self,
    ):
        client = FakeClient()
        cache = {}

        first = cached_ticker(
            client,
            cache,
            "SUIUSDT",
            "usdt-futures",
        )

        second = cached_ticker(
            client,
            cache,
            "SUIUSDT",
            "usdt-futures",
        )

        self.assertIs(
            first,
            second,
        )
        self.assertEqual(
            len(client.ticker_calls),
            1,
        )

    def test_different_symbols_are_independent(
        self,
    ):
        client = FakeClient()
        cache = {}

        cached_1m_candles(
            client,
            cache,
            "SUIUSDT",
            "usdt-futures",
        )

        cached_1m_candles(
            client,
            cache,
            "BTCUSDT",
            "usdt-futures",
        )

        self.assertEqual(
            len(client.candle_calls),
            2,
        )


if __name__ == "__main__":
    unittest.main()
