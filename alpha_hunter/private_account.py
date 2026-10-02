from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

from .bitget import BitgetAPIError, BitgetClient, BitgetDeterministicAPIError

CLASSIC_ACCOUNT_V3_ERROR_CODE = "40084"
UTA_ACCOUNT_MODES = {"unified", "hybrid", "upgrading", "switching"}
EXPECTED_ACCOUNT_FINGERPRINT_ENV = "BITGET_EXPECTED_ACCOUNT_FINGERPRINT"


def _fingerprint_account_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()


def _classic_account_identity_probe(client: BitgetClient) -> dict[str, Any]:
    """Bind Classic API credentials to one pinned Bitget account without storing UID."""
    expected = str(os.getenv(EXPECTED_ACCOUNT_FINGERPRINT_ENV) or "").strip().lower()
    result: dict[str, Any] = {
        "account_identity_probe_status": "UNAVAILABLE",
        "account_identity_fingerprint": None,
        "account_identity_expected_configured": bool(expected),
        "account_identity_match": False,
        "account_identity_error": None,
        "account_is_subaccount": None,
    }
    try:
        info = client.spot_account_info_v2()
    except BitgetAPIError as exc:
        result["account_identity_error"] = str(exc)
        return result

    user_id = str(info.get("userId") or "").strip()
    if not user_id:
        result["account_identity_probe_status"] = "INVALID_SCHEMA"
        result["account_identity_error"] = "Classic account info returned no userId"
        return result

    fingerprint = _fingerprint_account_id(user_id)
    parent_id = str(info.get("parentId") or "").strip()
    result["account_identity_fingerprint"] = fingerprint
    result["account_is_subaccount"] = bool(parent_id and parent_id != "0")

    if not expected:
        result["account_identity_probe_status"] = "UNPINNED"
        return result

    matched = hmac.compare_digest(fingerprint, expected)
    result["account_identity_match"] = matched
    result["account_identity_probe_status"] = "MATCHED" if matched else "MISMATCH"
    return result


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


TP_PLAN_TYPES = {"profit_plan", "pos_profit"}
SL_PLAN_TYPES = {"loss_plan", "pos_loss"}


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _normalize_pending_protection_order(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_id": raw.get("orderId"),
        "client_oid": raw.get("clientOid"),
        "plan_type": str(raw.get("planType") or "").strip().lower(),
        "symbol": str(raw.get("symbol") or "").strip().upper(),
        "hold_side": str(
            raw.get("posSide") or raw.get("holdSide") or ""
        ).strip().lower(),
        "trigger_price": raw.get("triggerPrice"),
        "trigger_type": raw.get("triggerType"),
        "size": raw.get("size"),
        "plan_status": raw.get("planStatus"),
        "margin_mode": raw.get("marginMode"),
        "created_at_ms": raw.get("cTime"),
        "updated_at_ms": raw.get("uTime"),
    }


def _matching_protection_orders(
    orders: list[dict[str, Any]],
    *,
    symbol: str,
    hold_side: str,
    open_position_count_for_symbol: int,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for order in orders:
        if order.get("symbol") != symbol:
            continue
        order_side = str(order.get("hold_side") or "").lower()
        if order_side in {"long", "short"}:
            if order_side != hold_side:
                continue
        elif open_position_count_for_symbol != 1:
            # A net/blank side is only safe to bind when one open position exists
            # for the symbol. Never guess across simultaneous long/short positions.
            continue
        matched.append(order)
    return matched


def _unique_trigger_price(orders: list[dict[str, Any]]) -> Any:
    values = [
        order.get("trigger_price")
        for order in orders
        if _present(order.get("trigger_price"))
    ]
    unique = {str(value).strip() for value in values}
    if len(unique) != 1:
        return None
    return values[0]


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
            "protection_observation_status": "NOT_CONFIGURED",
            "protection_observation_error": None,
            "pending_tpsl_order_count": 0,
            "api_permission_probe_status": "NOT_CONFIGURED",
            "api_permission_probe_error": None,
            "api_permission_type": None,
            "api_permissions": [],
            "account_identity_probe_status": "NOT_CONFIGURED",
            "account_identity_fingerprint": None,
            "account_identity_expected_configured": bool(
                str(os.getenv(EXPECTED_ACCOUNT_FINGERPRINT_ENV) or "").strip()
            ),
            "account_identity_match": False,
        }

    permission_evidence = _permission_probe(client)

    account_mode_probe_status = "UNAVAILABLE_CLASSIC_FALLBACK"
    account_mode_probe_error: str | None = None
    account_mode: str | None = None
    account_level: str | None = None
    asset_mode: str | None = None
    hold_mode: str | None = None

    identity_evidence: dict[str, Any] = {
        "account_identity_probe_status": "NOT_APPLICABLE",
        "account_identity_fingerprint": None,
        "account_identity_expected_configured": False,
        "account_identity_match": False,
        "account_identity_error": None,
        "account_is_subaccount": None,
    }

    if permission_evidence["api_permission_probe_status"] == "NOT_APPLICABLE_CLASSIC_ACCOUNT":
        # Bitget 40084 explicitly states that the calling account is Classic.
        # Prove which Classic account owns the credentials before accepting
        # balances, positions, fills, or a ZERO_FILLS conclusion.
        account_mode_probe_status = "CLASSIC_CONFIRMED_FROM_V3_40084"
        account_mode_probe_error = permission_evidence["api_permission_probe_error"]
        account_mode = "classic"
        identity_evidence = _classic_account_identity_probe(client)
        identity_status = str(
            identity_evidence.get("account_identity_probe_status") or "UNAVAILABLE"
        )
        if identity_status in {"MISMATCH", "UNAVAILABLE", "INVALID_SCHEMA"}:
            return {
                "status": f"ACCOUNT_IDENTITY_{identity_status}",
                "accounts": [],
                "open_positions": [],
                "open_position_count": 0,
                "account_mode_probe_status": account_mode_probe_status,
                "account_mode_probe_error": account_mode_probe_error,
                "account_mode": account_mode,
                "account_source": "BITGET_V2_CLASSIC",
                "classic_v2_risk_evidence_accepted": False,
                **identity_evidence,
                **permission_evidence,
            }
        # UNPINNED may collect read-only evidence so a repaired credential can be
        # verified and fingerprinted. It must not be allowed to certify a
        # zero-activity account downstream.
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
            "protection_observation_status": "NOT_ATTEMPTED_POSITION_READ_FAILED",
            "protection_observation_error": None,
            "pending_tpsl_order_count": 0,
            "account_source": "BITGET_V2_CLASSIC",
            **identity_evidence,
            **permission_evidence,
        }

    raw_open_positions: list[dict[str, Any]] = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        try:
            total = float(p.get("total") or 0)
        except (TypeError, ValueError):
            total = 0.0
        if total != 0:
            raw_open_positions.append(p)

    protection_status = "NOT_NEEDED_NO_OPEN_POSITIONS"
    protection_error: str | None = None
    pending_protection_orders: list[dict[str, Any]] = []

    if raw_open_positions:
        pending_reader = getattr(client, "pending_tpsl_orders", None)
        if pending_reader is None:
            protection_status = "UNAVAILABLE_CLIENT_METHOD"
        else:
            try:
                pending_rows = pending_reader(product_type)
            except BitgetAPIError as exc:
                # Position truth remains usable, but protection absence must not be
                # inferred while the dedicated TP/SL observer is unavailable.
                protection_status = "FAILED"
                protection_error = str(exc)
            else:
                protection_status = "CONNECTED"
                pending_protection_orders = [
                    _normalize_pending_protection_order(row)
                    for row in pending_rows
                    if isinstance(row, dict)
                ]

    symbol_position_counts: dict[str, int] = {}
    for p in raw_open_positions:
        symbol = str(p.get("symbol") or "").strip().upper()
        if symbol:
            symbol_position_counts[symbol] = symbol_position_counts.get(symbol, 0) + 1

    open_positions = []
    for p in raw_open_positions:
        symbol = str(p.get("symbol") or "").strip().upper()
        hold_side = str(p.get("holdSide") or "").strip().lower()
        matching_orders = _matching_protection_orders(
            pending_protection_orders,
            symbol=symbol,
            hold_side=hold_side,
            open_position_count_for_symbol=symbol_position_counts.get(symbol, 0),
        )
        tp_orders = [
            row
            for row in matching_orders
            if row.get("plan_type") in TP_PLAN_TYPES
        ]
        sl_orders = [
            row
            for row in matching_orders
            if row.get("plan_type") in SL_PLAN_TYPES
        ]

        position_tp = p.get("takeProfit")
        position_sl = p.get("stopLoss")
        pending_tp = _unique_trigger_price(tp_orders)
        pending_sl = _unique_trigger_price(sl_orders)

        resolved_tp = position_tp if _present(position_tp) else pending_tp
        resolved_sl = position_sl if _present(position_sl) else pending_sl
        tp_source = (
            "POSITION_FIELD"
            if _present(position_tp)
            else "PENDING_TPSL"
            if _present(pending_tp)
            else None
        )
        sl_source = (
            "POSITION_FIELD"
            if _present(position_sl)
            else "PENDING_TPSL"
            if _present(pending_sl)
            else None
        )

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
                "take_profit": resolved_tp,
                "stop_loss": resolved_sl,
                "take_profit_source": tp_source,
                "stop_loss_source": sl_source,
                "protection_observation_status": protection_status,
                "protection_observation_error": protection_error,
                "protection_orders": matching_orders,
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
        "protection_observation_status": protection_status,
        "protection_observation_error": protection_error,
        "protection_observation_source": "BITGET_V2_ORDERS_PLAN_PENDING",
        "pending_tpsl_order_count": len(pending_protection_orders),
        "classic_v2_risk_evidence_accepted": True,
        **identity_evidence,
        **permission_evidence,
    }
