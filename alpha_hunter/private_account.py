from __future__ import annotations

from typing import Any

from .bitget import BitgetAPIError, BitgetClient

UTA_ACCOUNT_MODES = {"unified", "hybrid", "upgrading", "switching"}


def collect_private_account_snapshot(
    client: BitgetClient,
    product_type: str,
    margin_coin: str = "USDT",
) -> dict[str, Any]:
    if not client.private_api_configured:
        return {
            "status": "NOT_CONFIGURED",
            "accounts": [],
            "open_positions": [],
            "open_position_count": 0,
            "account_mode_probe_status": "NOT_CONFIGURED",
        }

    account_mode_probe_status = "UNAVAILABLE_CLASSIC_FALLBACK"
    account_mode_probe_error: str | None = None
    account_mode: str | None = None
    account_level: str | None = None
    asset_mode: str | None = None
    hold_mode: str | None = None

    try:
        settings = client.account_settings_v3()
    except BitgetAPIError as exc:
        # Classic accounts may not have UTA-management read permission.
        # Keep the existing Classic read path, but preserve that the mode
        # probe was unavailable rather than silently claiming it succeeded.
        account_mode_probe_error = str(exc)
    else:
        account_mode_probe_status = "CONNECTED"
        account_mode = str(settings.get("accountMode") or "").strip().lower() or None
        account_level = str(settings.get("accountLevel") or "").strip().lower() or None
        asset_mode = str(settings.get("assetMode") or "").strip().lower() or None
        hold_mode = str(settings.get("holdMode") or "").strip().lower() or None

        if account_mode in UTA_ACCOUNT_MODES:
            # Bitget documents v3 account/assets + v3 current-position for UTA.
            # Do not accept Classic v2 balances/positions as risk evidence once
            # UTA/Hybrid/transition mode is explicitly detected.
            return {
                "status": "ACCOUNT_MODE_REQUIRES_V3",
                "accounts": [],
                "open_positions": [],
                "open_position_count": 0,
                "account_mode_probe_status": account_mode_probe_status,
                "account_mode": account_mode,
                "account_level": account_level,
                "asset_mode": asset_mode,
                "hold_mode": hold_mode,
                "classic_v2_risk_evidence_accepted": False,
            }

        # The v3 settings contract currently documents only UTA/Hybrid and
        # transition states. An unexpected successful mode must not be guessed.
        return {
            "status": "ACCOUNT_MODE_UNRECOGNIZED",
            "accounts": [],
            "open_positions": [],
            "open_position_count": 0,
            "account_mode_probe_status": account_mode_probe_status,
            "account_mode": account_mode,
            "account_level": account_level,
            "asset_mode": asset_mode,
            "hold_mode": hold_mode,
            "classic_v2_risk_evidence_accepted": False,
        }

    try:
        accounts = client.futures_accounts(product_type)
        positions = client.futures_positions(product_type, margin_coin)
    except BitgetAPIError as exc:
        return {
            "status": "FAILED",
            "error": str(exc),
            "accounts": [],
            "open_positions": [],
            "open_position_count": 0,
            "account_mode_probe_status": account_mode_probe_status,
            "account_mode_probe_error": account_mode_probe_error,
            "account_source": "BITGET_V2_CLASSIC",
        }

    open_positions = []
    for p in positions:
        try:
            total = float(p.get("total") or 0)
        except (TypeError, ValueError):
            total = 0.0
        if total == 0:
            continue
        open_positions.append({
            "symbol": p.get("symbol"),
            "hold_side": p.get("holdSide"),
            "total": p.get("total"),
            "available": p.get("available"),
            "leverage": p.get("leverage"),
            "margin_mode": p.get("marginMode"),
            "open_price_avg": p.get("openPriceAvg"),
            "mark_price": p.get("markPrice"),
            "unrealized_pl": p.get("unrealizedPL"),
            "break_even_price": p.get("breakEvenPrice"),
            "liquidation_price": p.get("liquidationPrice"),
            "take_profit": p.get("takeProfit"),
            "stop_loss": p.get("stopLoss"),
        })

    safe_accounts = [{
        "margin_coin": a.get("marginCoin"),
        "available": a.get("available"),
        "locked": a.get("locked"),
        "account_equity": a.get("accountEquity"),
        "unrealized_pl": a.get("unrealizedPL"),
    } for a in accounts]

    return {
        "status": "CONNECTED",
        "accounts": safe_accounts,
        "open_positions": open_positions,
        "open_position_count": len(open_positions),
        "account_mode_probe_status": account_mode_probe_status,
        "account_mode_probe_error": account_mode_probe_error,
        "account_source": "BITGET_V2_CLASSIC",
        "classic_v2_risk_evidence_accepted": True,
    }
