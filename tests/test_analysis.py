import unittest

from alpha_hunter.analysis import classify_state, parse_candles, support_resistance, trend_state


class AnalysisTests(unittest.TestCase):
    def make_rows(self, rising=True):
        rows = []
        for i in range(40):
            close = 100 + i if rising else 140 - i
            rows.append([str(1_700_000_000_000 + i * 60_000), str(close - 0.5), str(close + 1), str(close - 1), str(close), "10", "1000"])
        return rows

    def test_parse_and_bullish_trend(self):
        candles = parse_candles(self.make_rows(True))
        self.assertEqual(len(candles), 40)
        self.assertEqual(trend_state(candles), "BULLISH")

    def test_bearish_trend(self):
        candles = parse_candles(self.make_rows(False))
        self.assertEqual(trend_state(candles), "BEARISH")

    def test_levels(self):
        candles = parse_candles(self.make_rows(True))
        levels = support_resistance(candles)
        self.assertEqual(levels["support"], 99.0)
        self.assertEqual(levels["resistance"], 140.0)

    def test_fast_v1_never_grants_trade(self):
        state, permission, reason = classify_state(
            {"15m": "BULLISH", "1H": "BULLISH", "4H": "BULLISH"},
            120.0,
            {"support": 100.0, "resistance": 140.0},
        )
        self.assertEqual(state, "DIRECTION_EMERGING_LONG")
        self.assertFalse(permission)
        self.assertIn("1:5", reason)


if __name__ == "__main__":
    unittest.main()

from alpha_hunter.analysis import calculate_indicators, funding_summary, percentage_change, volume_anomaly


def make_candles(count=120, start=100.0, step=0.5, volume=1000.0):
    rows = []
    for i in range(count):
        close = start + i * step
        rows.append({
            "timestamp": i,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "base_volume": volume / close,
            "quote_volume": volume,
        })
    return rows


def test_indicator_package_is_populated():
    indicators = calculate_indicators(make_candles())
    assert indicators["ema_9"] is not None
    assert indicators["ema_21"] is not None
    assert indicators["ema_50"] is not None
    assert indicators["rsi_14"] is not None
    assert indicators["macd"]["histogram"] is not None
    assert indicators["bollinger"]["width_pct"] is not None
    assert indicators["atr_14"] is not None


def test_volume_anomaly_detects_spike():
    candles = make_candles(volume=1000.0)
    candles[-1]["quote_volume"] = 4000.0
    result = volume_anomaly(candles)
    assert result["state"] == "HIGH"
    assert result["ratio"] == 4.0


def test_funding_summary():
    rows = [{"fundingRate": "0.0001"}, {"fundingRate": "0.0002"}]
    result = funding_summary(rows, 0.0003)
    assert round(result["average"], 6) == 0.00015
    assert result["extreme"] is False


def test_percentage_change():
    assert percentage_change(110.0, 100.0) == 10.0
    assert percentage_change(1.0, None) is None

from alpha_hunter.analysis import validate_trade_setup


def executable_record(direction="LONG", price=101.0, support=100.0, resistance=107.0):
    bullish = direction == "LONG"
    return {
        "state": "DIRECTION_EMERGING_LONG" if bullish else "DIRECTION_EMERGING_SHORT",
        "last_price": price,
        "support": support,
        "resistance": resistance,
        "data_integrity_score": 100,
        "open_interest_change_pct": 2.0,
        "funding_history": {"extreme": False},
        "timeframes": {
            "1H": {"indicators": {
                "rsi_14": 58.0 if bullish else 42.0,
                "macd": {"histogram": 0.2 if bullish else -0.2},
                "volume_anomaly": {"state": "HIGH"},
            }}
        },
    }


def test_long_rr_gate_passes_only_with_five_to_one():
    result = validate_trade_setup(executable_record(), 5.0)
    assert result["permission"] is True
    assert result["rr"] == 6.0


def test_rr_gate_rejects_weak_reward():
    result = validate_trade_setup(executable_record(resistance=104.0), 5.0)
    assert result["permission"] is False
    assert result["checks"]["rr_minimum_met"] is False


def test_rr_gate_rejects_without_participation():
    record = executable_record()
    record["timeframes"]["1H"]["indicators"]["volume_anomaly"]["state"] = "NORMAL"
    result = validate_trade_setup(record, 5.0)
    assert result["permission"] is False
    assert result["checks"]["participation_confirmed"] is False


from alpha_hunter.analysis import build_intelligence_score, compression_score

def test_compression_score_detects_contracting_range():
    candles = make_candles(count=40, step=1.0)
    for i, candle in enumerate(candles[-20:]):
        candle["high"] = candle["close"] + 0.05
        candle["low"] = candle["close"] - 0.05
    result = compression_score(candles)
    assert result["state"] in {"MODERATE", "STRONG"}
    assert result["score"] is not None

def test_intelligence_score_labels_probability_uncalibrated():
    record = executable_record()
    record["execution_setup"] = validate_trade_setup(record, 5.0)
    record["timeframes"]["1H"]["compression"] = {"score": 8.0}
    result = build_intelligence_score(record, 5.0)
    assert result["huge_rr_score"] >= 7.0
    assert result["confidence_is_calibrated"] is False
    assert result["verdict"] == "LONG_READY"
