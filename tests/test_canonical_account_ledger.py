from alpha_hunter.account_ledger import (
    SOURCE,
    build_account_ledger_rows,
)


def snapshot(private_account):
    return {
        "run_id": "run-123",
        "collected_at_utc": "2026-09-17T05:02:05+00:00",
        "private_account": private_account,
    }


def test_connected_empty_positions_is_verified_read_only_evidence():
    account, positions = build_account_ledger_rows(
        snapshot(
            {
                "status": "CONNECTED",
                "accounts": [
                    {
                        "margin_coin": "USDT",
                        "available": "100.5",
                        "locked": "2.0",
                        "account_equity": "102.5",
                        "unrealized_pl": "0.0",
                    }
                ],
                "open_positions": [],
                "open_position_count": 0,
                "api_permission_probe_status": "CONNECTED",
                "api_permission_type": "read-only",
                "api_permissions": ["uta_mgt"],
            }
        )
    )

    assert account["connection_status"] == "CONNECTED_READ_ONLY"
    assert account["schema_validated"] is True
    assert account["complete"] is True
    assert account["source"] == SOURCE
    assert account["trade_permission"] is False
    assert account["shadow_only"] is True
    assert account["margin_used_usdt"] is None
    assert account["daily_realized_pnl_usdt"] is None
    assert account["evidence"]["no_extra_bitget_request"] is True
    assert account["evidence"]["api_permission_probe_status"] == "CONNECTED"
    assert account["evidence"]["api_permission_type"] == "read-only"
    assert account["evidence"]["api_permissions"] == ["uta_mgt"]
    assert account["evidence"]["permission_metadata_is_trade_authority"] is False
    assert positions == []


def test_not_configured_is_persisted_as_disconnected_not_clean_positions():
    account, positions = build_account_ledger_rows(
        snapshot(
            {
                "status": "NOT_CONFIGURED",
                "accounts": [],
                "open_positions": [],
                "open_position_count": 0,
            }
        )
    )

    assert account["connection_status"] == "DISCONNECTED"
    assert account["schema_validated"] is False
    assert account["complete"] is False
    assert "PRIVATE_API_NOT_CONFIGURED" in account["evidence"]["schema_errors"]
    assert positions == []


def test_connected_malformed_account_fails_closed():
    account, positions = build_account_ledger_rows(
        snapshot(
            {
                "status": "CONNECTED",
                "accounts": [{"margin_coin": "USDT", "available": "10"}],
                "open_positions": [],
                "open_position_count": 0,
            }
        )
    )

    assert account["connection_status"] == "DATA_INSUFFICIENT"
    assert account["schema_validated"] is False
    assert account["complete"] is False
    assert positions == []


def test_positions_normalize_direction_without_inventing_strategy_risk():
    account, positions = build_account_ledger_rows(
        snapshot(
            {
                "status": "CONNECTED",
                "accounts": [
                    {
                        "margin_coin": "USDT",
                        "available": "50",
                        "locked": "10",
                        "account_equity": "60",
                        "unrealized_pl": "1",
                    }
                ],
                "open_positions": [
                    {
                        "symbol": "BTCUSDT",
                        "hold_side": "long",
                        "total": "0.01",
                        "available": "0.01",
                        "leverage": "5",
                        "margin_mode": "crossed",
                        "open_price_avg": "50000",
                        "mark_price": "51000",
                        "unrealized_pl": "10",
                        "break_even_price": "50010",
                        "liquidation_price": "42000",
                        "take_profit": "55000",
                        "stop_loss": "48000",
                    },
                    {
                        "symbol": "ETHUSDT",
                        "hold_side": "short",
                        "total": "0.5",
                        "open_price_avg": "2500",
                        "mark_price": "2450",
                        "unrealized_pl": "25",
                        "liquidation_price": "3000",
                    },
                ],
                "open_position_count": 2,
            }
        )
    )

    assert account["connection_status"] == "CONNECTED_READ_ONLY"
    assert [row["direction"] for row in positions] == ["LONG", "SHORT"]
    assert all(row["planned_risk_usdt"] is None for row in positions)
    assert all(row["structural_stop_price"] is None for row in positions)
    assert all(row["notional_usdt"] is None for row in positions)
    assert all(row["trade_permission"] is False for row in positions)
    assert positions[0]["evidence"]["structural_stop_inferred_from_exchange_stop"] is False


def test_invalid_position_schema_makes_whole_account_snapshot_incomplete():
    account, positions = build_account_ledger_rows(
        snapshot(
            {
                "status": "CONNECTED",
                "accounts": [
                    {
                        "margin_coin": "USDT",
                        "available": "50",
                        "account_equity": "50",
                        "unrealized_pl": "0",
                    }
                ],
                "open_positions": [
                    {"symbol": "BTCUSDT", "hold_side": "mystery", "total": "1"}
                ],
                "open_position_count": 1,
            }
        )
    )

    assert account["connection_status"] == "DATA_INSUFFICIENT"
    assert account["complete"] is False
    assert positions == []
    assert any("DIRECTION_INVALID" in item for item in account["evidence"]["schema_errors"])


def test_module_contract_does_not_import_or_call_bitget():
    import inspect
    import alpha_hunter.account_ledger as module

    source = inspect.getsource(module)
    assert "BitgetClient" not in source
    assert "futures_accounts(" not in source
    assert "futures_positions(" not in source
    assert "private_api_configured" not in source
