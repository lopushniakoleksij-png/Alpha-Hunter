import inspect

import alpha_hunter.collector as collector
from alpha_hunter.collector import pin_open_position_symbols


def _connected(positions):
    return {
        "status": "CONNECTED",
        "open_positions": positions,
        "open_position_count": len(positions),
    }


def test_open_position_is_pinned_beyond_discovery_limit_without_eviction():
    selected = ["BTCUSDT", "ETHUSDT"]
    universe = {
        "selected_count": 2,
        "selected_symbols": list(selected),
    }

    pinned, updated = pin_open_position_symbols(
        selected,
        universe,
        _connected([
            {"symbol": "QNTUSDT", "hold_side": "long", "total": "0.06"},
        ]),
        {"BTCUSDT", "ETHUSDT", "QNTUSDT"},
    )

    assert pinned == ["BTCUSDT", "ETHUSDT", "QNTUSDT"]
    assert updated["discovery_selected_count_before_position_pin"] == 2
    assert updated["selected_count"] == 3
    assert updated["monitored_open_position_symbols"] == ["QNTUSDT"]
    assert updated["monitored_open_position_count"] == 1
    assert updated["open_position_monitoring_status"] == "COMPLETE"


def test_already_selected_open_position_is_not_duplicated():
    selected = ["QNTUSDT", "BTCUSDT"]

    pinned, updated = pin_open_position_symbols(
        selected,
        {"selected_count": 2, "selected_symbols": list(selected)},
        _connected([
            {"symbol": "QNTUSDT", "hold_side": "long", "total": "0.06"},
        ]),
        {"QNTUSDT", "BTCUSDT"},
    )

    assert pinned == selected
    assert pinned.count("QNTUSDT") == 1
    assert updated["monitored_open_position_symbols"] == ["QNTUSDT"]


def test_dual_side_same_symbol_is_one_monitored_market_symbol():
    pinned, updated = pin_open_position_symbols(
        ["BTCUSDT"],
        {"selected_count": 1, "selected_symbols": ["BTCUSDT"]},
        _connected([
            {"symbol": "QNTUSDT", "hold_side": "long", "total": "0.06"},
            {"symbol": "QNTUSDT", "hold_side": "short", "total": "0.02"},
        ]),
        {"BTCUSDT", "QNTUSDT"},
    )

    assert pinned == ["BTCUSDT", "QNTUSDT"]
    assert updated["monitored_open_position_symbols"] == ["QNTUSDT"]
    assert updated["monitored_open_position_count"] == 1


def test_unlisted_open_position_fails_monitoring_complete_without_inventing_contract():
    pinned, updated = pin_open_position_symbols(
        ["BTCUSDT"],
        {"selected_count": 1, "selected_symbols": ["BTCUSDT"]},
        _connected([
            {"symbol": "DELISTEDUSDT", "hold_side": "long", "total": "1"},
        ]),
        {"BTCUSDT"},
    )

    assert pinned == ["BTCUSDT"]
    assert updated["monitored_open_position_symbols"] == ["DELISTEDUSDT"]
    assert updated["monitored_open_position_missing_contracts"] == ["DELISTEDUSDT"]
    assert updated["open_position_monitoring_status"] == "INCOMPLETE"


def test_disconnected_account_cannot_claim_open_position_monitoring_complete():
    selected = ["BTCUSDT"]

    pinned, updated = pin_open_position_symbols(
        selected,
        {"selected_count": 1, "selected_symbols": list(selected)},
        {
            "status": "FAILED",
            "open_positions": [
                {"symbol": "QNTUSDT", "hold_side": "long", "total": "0.06"}
            ],
        },
        {"BTCUSDT", "QNTUSDT"},
    )

    assert pinned == selected
    assert updated["monitored_open_position_symbols"] == []
    assert updated["open_position_monitoring_status"] == "ACCOUNT_NOT_CONNECTED"


def test_private_account_collection_precedes_position_aware_market_scan():
    source = inspect.getsource(collector.main)
    account_read = source.index("collect_private_account_snapshot(")
    universe_select = source.index("select_market_universe(")
    position_pin = source.index("pin_open_position_symbols(")
    scan_loop = source.index("for symbol in selected_symbols:")

    assert account_read < universe_select < position_pin < scan_loop
