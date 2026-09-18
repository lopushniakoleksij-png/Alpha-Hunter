from __future__ import annotations

import hashlib
import json
from typing import Any

import requests

from .storage import SupabaseConfig

ACCOUNT_TABLE = "alpha_hunter_account_state_snapshots"
POSITION_TABLE = "alpha_hunter_open_position_snapshots"
MODEL_VERSION = "canonical-account-ledger-v0.2-permission-evidence"
SOURCE = "CANONICAL_SCANNER_PRIVATE_ACCOUNT_CACHE"


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _account_snapshot_id(run_id: str) -> str:
    raw = f"{MODEL_VERSION}|{run_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _position_snapshot_id(account_snapshot_id: str, symbol: str, direction: str) -> str:
    raw = f"{MODEL_VERSION}|{account_snapshot_id}|{symbol}|{direction}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _connected_account(private_account: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    accounts = private_account.get("accounts")
    missing: list[str] = []
    if not isinstance(accounts, list):
        return None, ["ACCOUNTS_NOT_LIST"]

    usdt = next(
        (
            row
            for row in accounts
            if isinstance(row, dict) and str(row.get("margin_coin") or "").upper() == "USDT"
        ),
        None,
    )
    if usdt is None:
        return None, ["USDT_ACCOUNT_MISSING"]

    for key in ("account_equity", "available", "unrealized_pl"):
        if _optional_float(usdt.get(key)) is None:
            missing.append(f"ACCOUNT_{key.upper()}_INVALID")
    return usdt, missing


def _normalize_positions(
    private_account: dict[str, Any], account_snapshot_id: str, captured_at_utc: str
) -> tuple[list[dict[str, Any]], list[str]]:
    source_positions = private_account.get("open_positions")
    if not isinstance(source_positions, list):
        return [], ["OPEN_POSITIONS_NOT_LIST"]

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()

    for index, raw in enumerate(source_positions):
        if not isinstance(raw, dict):
            errors.append(f"POSITION_{index}_NOT_OBJECT")
            continue

        symbol = str(raw.get("symbol") or "").upper()
        hold_side = str(raw.get("hold_side") or "").lower()
        direction = {"long": "LONG", "short": "SHORT"}.get(hold_side)
        quantity = _optional_float(raw.get("total"))

        if not symbol:
            errors.append(f"POSITION_{index}_SYMBOL_MISSING")
        if direction is None:
            errors.append(f"POSITION_{index}_DIRECTION_INVALID")
        if quantity is None or quantity == 0:
            errors.append(f"POSITION_{index}_QUANTITY_INVALID")
        if not symbol or direction is None or quantity is None or quantity == 0:
            continue

        identity = (symbol, direction)
        if identity in seen:
            errors.append(f"POSITION_{index}_DUPLICATE_SYMBOL_DIRECTION")
            continue
        seen.add(identity)

        rows.append(
            {
                "position_snapshot_id": _position_snapshot_id(
                    account_snapshot_id, symbol, direction
                ),
                "account_snapshot_id": account_snapshot_id,
                "captured_at_utc": captured_at_utc,
                "symbol": symbol,
                "direction": direction,
                "quantity": abs(quantity),
                "average_entry": _optional_float(raw.get("open_price_avg")),
                "mark_price": _optional_float(raw.get("mark_price")),
                "liquidation_price": _optional_float(raw.get("liquidation_price")),
                "notional_usdt": None,
                "unrealized_pnl_usdt": _optional_float(raw.get("unrealized_pl")),
                "source_position_id": None,
                # The exchange's stop-loss field is not Alpha Hunter's independently
                # validated structural invalidation and must never be promoted here.
                "structural_stop_price": None,
                "planned_risk_usdt": None,
                "strategy_event_id": None,
                "source_order_intent_id": None,
                "evidence": {
                    "source": SOURCE,
                    "margin_mode": raw.get("margin_mode"),
                    "leverage": raw.get("leverage"),
                    "available_quantity": raw.get("available"),
                    "break_even_price": raw.get("break_even_price"),
                    "exchange_take_profit_observed": raw.get("take_profit"),
                    "exchange_stop_loss_observed": raw.get("stop_loss"),
                    "structural_stop_inferred_from_exchange_stop": False,
                    "planned_risk_invented": False,
                    "notional_invented": False,
                    "no_extra_bitget_request": True,
                },
                "shadow_only": True,
                "trade_permission": False,
            }
        )

    return rows, errors


def build_account_ledger_rows(
    snapshot: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Translate the scanner's already-fetched private-account cache into evidence rows.

    This function never calls Bitget. Missing credentials and malformed payloads are
    persisted as explicit non-eligible account evidence, not interpreted as an empty
    verified position ledger.
    """

    run_id = str(snapshot.get("run_id") or "")
    captured_at_utc = str(snapshot.get("collected_at_utc") or "")
    if not run_id or not captured_at_utc:
        raise ValueError("canonical snapshot lacks immutable run identity")

    account_snapshot_id = _account_snapshot_id(run_id)
    private_account = snapshot.get("private_account")
    if not isinstance(private_account, dict):
        private_account = {}

    scanner_status = str(private_account.get("status") or "MISSING").upper()
    errors: list[str] = []
    positions: list[dict[str, Any]] = []
    usdt_account: dict[str, Any] | None = None

    if scanner_status == "CONNECTED":
        usdt_account, account_errors = _connected_account(private_account)
        positions, position_errors = _normalize_positions(
            private_account, account_snapshot_id, captured_at_utc
        )
        errors.extend(account_errors)
        errors.extend(position_errors)
        schema_validated = not errors
        complete = schema_validated
        connection_status = (
            "CONNECTED_READ_ONLY" if schema_validated else "DATA_INSUFFICIENT"
        )
    elif scanner_status == "NOT_CONFIGURED":
        schema_validated = False
        complete = False
        connection_status = "DISCONNECTED"
        errors.append("PRIVATE_API_NOT_CONFIGURED")
    else:
        schema_validated = False
        complete = False
        connection_status = "DATA_INSUFFICIENT"
        errors.append(f"SCANNER_PRIVATE_ACCOUNT_STATUS_{scanner_status}")

    claimed_count = private_account.get("open_position_count")
    if scanner_status == "CONNECTED" and isinstance(claimed_count, int):
        if claimed_count != len(private_account.get("open_positions") or []):
            errors.append("OPEN_POSITION_COUNT_CLAIM_MISMATCH")
            schema_validated = False
            complete = False
            connection_status = "DATA_INSUFFICIENT"

    if not complete:
        # Incomplete account evidence must never emit apparently verified positions.
        positions = []

    account_row = {
        "account_snapshot_id": account_snapshot_id,
        "captured_at_utc": captured_at_utc,
        "equity_usdt": _optional_float(
            usdt_account.get("account_equity") if usdt_account else None
        ),
        "available_usdt": _optional_float(
            usdt_account.get("available") if usdt_account else None
        ),
        # `locked` is retained only in evidence; it is not assumed to equal margin used.
        "margin_used_usdt": None,
        "unrealized_pnl_usdt": _optional_float(
            usdt_account.get("unrealized_pl") if usdt_account else None
        ),
        "daily_realized_pnl_usdt": None,
        "source": SOURCE,
        "connection_status": connection_status,
        "schema_validated": schema_validated,
        "complete": complete,
        "evidence": {
            "model_version": MODEL_VERSION,
            "canonical_run_id": run_id,
            "scanner_private_account_status": scanner_status,
            "account_count": len(private_account.get("accounts") or [])
            if isinstance(private_account.get("accounts"), list)
            else None,
            "scanner_open_position_count": private_account.get("open_position_count"),
            "persisted_open_position_count": len(positions),
            "api_permission_probe_status": private_account.get("api_permission_probe_status"),
            "api_permission_probe_error": private_account.get("api_permission_probe_error"),
            "api_permission_type": private_account.get("api_permission_type"),
            "api_permissions": private_account.get("api_permissions")
            if isinstance(private_account.get("api_permissions"), list)
            else [],
            "permission_metadata_is_trade_authority": False,
            "locked_observed": usdt_account.get("locked") if usdt_account else None,
            "margin_used_inferred_from_locked": False,
            "daily_realized_pnl_invented": False,
            "schema_errors": errors,
            "no_extra_bitget_request": True,
            "cached_payload_only": True,
        },
        "shadow_only": True,
        "trade_permission": False,
    }
    return account_row, positions


def _insert_ignore(
    settings: SupabaseConfig,
    table: str,
    rows: list[dict[str, Any]],
    on_conflict: str,
) -> int:
    if not rows:
        return 0
    headers = {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=minimal",
    }
    response = requests.post(
        f"{settings.url}/rest/v1/{table}",
        params={"on_conflict": on_conflict},
        headers=headers,
        data=json.dumps(rows, separators=(",", ":")),
        timeout=settings.timeout_seconds,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(
            f"Account ledger persistence failed for {table}: "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )
    return len(rows)


def persist_account_ledger(
    settings: SupabaseConfig,
    account_row: dict[str, Any],
    position_rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """Persist append-only account evidence followed by its position children."""
    accounts = _insert_ignore(
        settings, ACCOUNT_TABLE, [account_row], "account_snapshot_id"
    )
    positions = _insert_ignore(
        settings, POSITION_TABLE, position_rows, "position_snapshot_id"
    )
    return accounts, positions
