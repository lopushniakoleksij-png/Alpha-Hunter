from pathlib import Path
from unittest.mock import patch

from ops.recover_roundtrip_fills_readonly import (
    WINDOW_HOURS,
    _classify_trade_side,
)


SCRIPT = Path("ops/recover_roundtrip_fills_readonly.py").read_text(
    encoding="utf-8"
)


def test_window_is_90_days_and_within_three_month_contract():
    assert WINDOW_HOURS == 2160
    assert WINDOW_HOURS // 24 == 90


def test_trade_side_classification_is_conservative():
    assert _classify_trade_side("open") == "OPEN"
    assert _classify_trade_side("open_long") == "OPEN"
    assert _classify_trade_side("close") == "CLOSE"
    assert _classify_trade_side("close_short") == "CLOSE"
    assert _classify_trade_side("buy_single") == "ONE_WAY_UNRESOLVED"
    assert _classify_trade_side("sell_single") == "ONE_WAY_UNRESOLVED"
    assert _classify_trade_side("") == "OTHER"


def test_recovery_calls_existing_canonical_collector_with_90_day_window():
    assert "collect_fill_traceability(" in SCRIPT
    assert "window_hours=WINDOW_HOURS" in SCRIPT
    assert "persist_fill_traceability(" in SCRIPT


def test_recovery_never_claims_execution_or_prints_raw_ids():
    required = [
        '"read_only_get": True',
        '"no_order_write_path": True',
        '"raw_trade_ids_printed": False',
        '"raw_order_ids_printed": False',
        '"shadow_only": True',
        '"trade_permission": False',
        '"OPEN_SIDE_PRESENT"',
        '"OPEN_SIDE_NOT_RECOVERED_WITHIN_90_DAY_WINDOW"',
    ]
    for marker in required:
        assert marker in SCRIPT

    lower = SCRIPT.lower()
    for forbidden in (
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer",
        "trade_permission=true",
        "trade_permission = true",
    ):
        assert forbidden not in lower
