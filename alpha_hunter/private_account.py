from __future__ import annotations

from typing import Any

from .bitget import BitgetAPIError, BitgetClient, BitgetDeterministicAPIError

CLASSIC_ACCOUNT_V3_ERROR_CODE = "40084"
UTA_ACCOUNT_MODES = {"unified", "hybrid", "upgrading", "switching"}


def _permission_probe(client: BitgetClient) -> dict[str, Any]:
    """Collect API-key permission metadata without using it as trade authority."""
    result: dict[str, Any] = {
        "api_permission_probe_status": "UNAVAILABLE",
        "api_permission_probe_error": None,
        "api_permission_type": None,
        "api_permissions": [],
    }
    try:
        info = client.account_info_v3()
    except BitgetDeterministicAPIError as exc:
        result["api_permission_probe_error"] = str(exc)
        if exc.bitget_code == CLASSIC_ACCOUNT_V3_ERROR_CODE:
            result["api_permission_probe_status"] = "NOT_APPLICABLE_CLASSIC_ACCOUNT"
        return result
    except BitgetAPIError as exc:
        result["api_permission_probe_error"] = str(exc)
        return result

    permission_type = str(info.get("permType") or "").strip().lower() or None
    raw_permissions = info.get("permissions")
    permissions = (
        sorted(
            {
                str(value).strip().lower()
                for value in raw_permissions
                if str(value).strip()
            }
        )
        if isinstance(raw_permissions, list)
        else []
    )
    result.update(
        {
            "api_permission_probe_status": "CONNECTED",
            "api_permission_type": permission_type,
            "api_permissions": permissions,
        }
    )
    return result


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
            "api_permission_probe_status": "NOT_CONFIGURED",
            "api_permission_probe_error": None,
            "api_permission_type": None,
            "api_permissions": [],
        }

    permission_evidence = _permission_probe(client)

    account_mode_probe_status = "UNAVAILABLE_CLASSIC_FALLBACK"
    account_mode_probe_error: str | None = None
    account_mode: str | None = None
    account_level: str | None = None
    asset_mode: str | None = None
    hold_mode: str | None = None

    if permission_evidence["api_permission_probe_status"] == "NOT_APPLICABLE_CLASSIC_ACCOUNT":
        # Bitget 40084 explicitly states that the calling account is Classic and
        # the Unified Account API is unsupported. Treat that as positive mode
        # evidence and do not make a second UTA-only settings request.
        account_mode_probe_status = "CLASSIC_CONFIRMED_FROM_V3_40084"
        account_mode_probe_error = permission_evidence["api_permission_probe_error"]
        account_mode = "classic"
    else:
        try:
            settings = client.account_settings_v3()
        except BitgetAPIError as exc:
            # If the account-info probe did not identify Classic mode, preserve
            # the existing fail-closed fallback behavior.
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
                    **permission_evidence,
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
                **permission_evidence,
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
            **permission_evidence,
        }

    open_positions = []
    for p in positions:
        try:
            total = float(p.get("total") or 0)
        except (TypeError, ValueError):
            total = 0.0
        if total == 0:
            continue
        open_positions.append(
            {
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
            }
        )

    safe_accounts = [
        {
            "margin_coin": a.get("marginCoin"),
            "available": a.get("available"),
            "locked": a.get("locked"),
            "account_equity": a.get("accountEquity"),
            "unrealized_pl": a.get("unrealizedPL"),
        }
        for a in accounts
    ]

    return {
        "status": "CONNECTED",
        "accounts": safe_accounts,
        "open_positions": open_positions,
        "open_position_count": len(open_positions),
        "account_mode_probe_status": account_mode_probe_status,
        "account_mode_probe_error": account_mode_probe_error,
        "account_mode": account_mode,
        "account_source": "BITGET_V2_CLASSIC",
        "classic_v2_risk_evidence_accepted": True,
        **permission_evidence,
    }
