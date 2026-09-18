from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .bitget import BitgetAPIError, BitgetClient
from .storage import SupabaseConfig

TRACEABILITY_TABLE = "alpha_hunter_fill_traceability_runs"
FILL_TABLE = "alpha_hunter_fill_evidence"
MODEL_VERSION = "canonical-readonly-fill-ledger-v0.2-permission-blocker"
ENDPOINT = "/api/v2/mix/order/fills"
WINDOW_HOURS = 168
PAGE_LIMIT = 100
MAX_PAGES = 20


@dataclass
class FillTraceabilityResult:
    run_row: dict[str, Any]
    fill_rows: list[dict[str, Any]]


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_from_ms(value: Any) -> str | None:
    try:
        milliseconds = int(str(value))
    except (TypeError, ValueError):
        return None
    if milliseconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(
            milliseconds / 1000.0, tz=timezone.utc
        ).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _traceability_run_id(source_run_id: str, start: datetime, end: datetime) -> str:
    raw = (
        f"{MODEL_VERSION}|{source_run_id}|{start.isoformat()}|{end.isoformat()}"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _fill_evidence_id(trade_id: str) -> str:
    raw = f"{MODEL_VERSION}|{trade_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _single_fee(fee_detail: Any) -> tuple[float | None, str | None, bool]:
    if not isinstance(fee_detail, list) or not fee_detail:
        return None, None, False

    normalized: list[tuple[float, str]] = []
    for row in fee_detail:
        if not isinstance(row, dict):
            return None, None, False
        fee = _optional_float(row.get("totalFee"))
        coin = str(row.get("feeCoin") or "").upper()
        if fee is None or not coin:
            return None, None, False
        normalized.append((fee, coin))

    coins = {coin for _, coin in normalized}
    if len(coins) != 1:
        return None, None, False
    coin = next(iter(coins))
    return sum(value for value, _ in normalized), coin, True


def _normalize_fill(
    raw: dict[str, Any],
    *,
    traceability_run_id: str,
    source_run_id: str,
    observed_at_utc: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    trade_id = str(raw.get("tradeId") or "").strip()
    order_id = str(raw.get("orderId") or "").strip()
    symbol = str(raw.get("symbol") or "").upper().strip()
    side = str(raw.get("side") or "").lower().strip()
    trade_scope = str(raw.get("tradeScope") or "").lower().strip()
    fill_time_utc = _iso_from_ms(raw.get("cTime"))
    price = _optional_float(raw.get("price"))
    base_volume = _optional_float(raw.get("baseVolume"))
    quote_volume = _optional_float(raw.get("quoteVolume"))

    if not trade_id:
        errors.append("TRADE_ID_MISSING")
    if not order_id:
        errors.append("ORDER_ID_MISSING")
    if not symbol:
        errors.append("SYMBOL_MISSING")
    if side not in {"buy", "sell"}:
        errors.append("SIDE_INVALID")
    if trade_scope not in {"maker", "taker"}:
        errors.append("TRADE_SCOPE_INVALID")
    if fill_time_utc is None:
        errors.append("FILL_TIME_INVALID")
    if price is None or price <= 0:
        errors.append("PRICE_INVALID")
    if base_volume is None or base_volume <= 0:
        errors.append("BASE_VOLUME_INVALID")

    if errors:
        return None, errors

    fee_amount, fee_coin, fee_schema_valid = _single_fee(raw.get("feeDetail"))
    fill_row = {
        "fill_evidence_id": _fill_evidence_id(trade_id),
        "traceability_run_id": traceability_run_id,
        "source_run_id": source_run_id,
        "observed_at_utc": observed_at_utc,
        "fill_time_utc": fill_time_utc,
        "trade_id": trade_id,
        "order_id": order_id,
        "symbol": symbol,
        "side": side.upper(),
        "trade_side": str(raw.get("tradeSide") or "").upper() or None,
        "position_mode": str(raw.get("posMode") or "") or None,
        "trade_scope": trade_scope.upper(),
        "price": price,
        "base_volume": base_volume,
        "quote_volume": quote_volume,
        "profit": _optional_float(raw.get("profit")),
        "fee_amount": fee_amount,
        "fee_coin": fee_coin,
        "enter_point_source": str(raw.get("enterPointSource") or "") or None,
        "cost_fields_complete": bool(
            quote_volume is not None and fee_schema_valid and fee_amount is not None
        ),
        "evidence": {
            "source": "BITGET_CLASSIC_READ_ONLY_FILL_API",
            "endpoint": ENDPOINT,
            "fee_detail": raw.get("feeDetail") if isinstance(raw.get("feeDetail"), list) else None,
            "fee_schema_valid": fee_schema_valid,
            "documented_trade_scope": trade_scope,
            "slippage_claim_permitted": False,
            "realistic_net_r_claim_permitted": False,
            "order_write_path_present": False,
        },
        "model_version": MODEL_VERSION,
        "shadow_only": True,
        "trade_permission": False,
    }
    return fill_row, []


def _run_row(
    *,
    traceability_run_id: str,
    source_run_id: str,
    observed_at_utc: str,
    start: datetime,
    end: datetime,
    status: str,
    complete: bool,
    schema_validated: bool,
    pages_fetched: int,
    fill_count: int,
    oldest_fill_at_utc: str | None,
    newest_fill_at_utc: str | None,
    detail: str | None,
    account_probe_status: str | None,
) -> dict[str, Any]:
    return {
        "traceability_run_id": traceability_run_id,
        "source_run_id": source_run_id,
        "observed_at_utc": observed_at_utc,
        "window_start_utc": start.isoformat(),
        "window_end_utc": end.isoformat(),
        "endpoint": ENDPOINT,
        "status": status,
        "complete": complete,
        "schema_validated": schema_validated,
        "pages_fetched": pages_fetched,
        "fill_count": fill_count,
        "oldest_fill_at_utc": oldest_fill_at_utc,
        "newest_fill_at_utc": newest_fill_at_utc,
        "detail": detail,
        "evidence": {
            "account_mode_probe_status": account_probe_status,
            "classic_v2_api_family_required": True,
            "read_only_get": True,
            "maximum_pages": MAX_PAGES,
            "page_limit": PAGE_LIMIT,
            "window_hours": WINDOW_HOURS,
            "no_order_write_path": True,
            "zero_fills_do_not_pass_traceability": True,
        },
        "model_version": MODEL_VERSION,
        "shadow_only": True,
        "trade_permission": False,
    }


def collect_fill_traceability(
    client: BitgetClient,
    *,
    product_type: str,
    source_run_id: str,
    observed_at_utc: str,
    private_account: dict[str, Any],
) -> FillTraceabilityResult:
    """Read recent Classic futures fills after the canonical market scan.

    This function is evidence-only. It never places, amends, or cancels an order.
    The Classic fill endpoint is called only when the contemporaneous private-account
    snapshot has already accepted Classic-v2 account evidence.
    """

    try:
        end = datetime.fromisoformat(observed_at_utc.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("fill traceability observed_at_utc is invalid") from exc
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = end - timedelta(hours=WINDOW_HOURS)
    trace_id = _traceability_run_id(source_run_id, start, end)

    account_status = str(private_account.get("status") or "MISSING").upper()
    account_probe_status = str(
        private_account.get("account_mode_probe_status") or ""
    ) or None
    classic_accepted = private_account.get("classic_v2_risk_evidence_accepted") is True

    if not client.private_api_configured:
        return FillTraceabilityResult(
            _run_row(
                traceability_run_id=trace_id,
                source_run_id=source_run_id,
                observed_at_utc=observed_at_utc,
                start=start,
                end=end,
                status="NOT_CONFIGURED",
                complete=False,
                schema_validated=False,
                pages_fetched=0,
                fill_count=0,
                oldest_fill_at_utc=None,
                newest_fill_at_utc=None,
                detail="Bitget private API credentials are not configured",
                account_probe_status=account_probe_status,
            ),
            [],
        )

    if account_status != "CONNECTED" or not classic_accepted:
        return FillTraceabilityResult(
            _run_row(
                traceability_run_id=trace_id,
                source_run_id=source_run_id,
                observed_at_utc=observed_at_utc,
                start=start,
                end=end,
                status="BLOCKED_ACCOUNT_API_FAMILY_UNVERIFIED",
                complete=False,
                schema_validated=False,
                pages_fetched=0,
                fill_count=0,
                oldest_fill_at_utc=None,
                newest_fill_at_utc=None,
                detail=(
                    f"private_account_status={account_status}; "
                    f"classic_v2_risk_evidence_accepted={classic_accepted}"
                ),
                account_probe_status=account_probe_status,
            ),
            [],
        )

    fills: list[dict[str, Any]] = []
    seen_trade_ids: set[str] = set()
    cursor: str | None = None
    pages_fetched = 0
    schema_errors: list[str] = []

    for page_number in range(1, MAX_PAGES + 1):
        try:
            data = client.futures_fills(
                product_type,
                start_time_ms=int(start.timestamp() * 1000),
                end_time_ms=int(end.timestamp() * 1000),
                limit=PAGE_LIMIT,
                id_less_than=cursor,
            )
        except BitgetFillPermissionError as exc:
            return FillTraceabilityResult(
                _run_row(
                    traceability_run_id=trace_id,
                    source_run_id=source_run_id,
                    observed_at_utc=observed_at_utc,
                    start=start,
                    end=end,
                    status="BLOCKED_BITGET_FUTURES_ORDER_PERMISSION",
                    complete=False,
                    schema_validated=False,
                    pages_fetched=pages_fetched,
                    fill_count=len(fills),
                    oldest_fill_at_utc=min((row["fill_time_utc"] for row in fills), default=None),
                    newest_fill_at_utc=max((row["fill_time_utc"] for row in fills), default=None),
                    detail=str(exc),
                    account_probe_status=account_probe_status,
                    blocker_code="BITGET_FUTURES_ORDER_READ_PERMISSION_REQUIRED",
                    required_permission=exc.required_permission,
                    bitget_error_code=exc.bitget_code,
                ),
                fills,
            )
        except BitgetAPIError as exc:
            return FillTraceabilityResult(
                _run_row(
                    traceability_run_id=trace_id,
                    source_run_id=source_run_id,
                    observed_at_utc=observed_at_utc,
                    start=start,
                    end=end,
                    status="FAILED",
                    complete=False,
                    schema_validated=False,
                    pages_fetched=pages_fetched,
                    fill_count=len(fills),
                    oldest_fill_at_utc=min((row["fill_time_utc"] for row in fills), default=None),
                    newest_fill_at_utc=max((row["fill_time_utc"] for row in fills), default=None),
                    detail=str(exc),
                    account_probe_status=account_probe_status,
                ),
                fills,
            )

        pages_fetched = page_number
        if not isinstance(data, dict):
            schema_errors.append(f"PAGE_{page_number}_DATA_NOT_OBJECT")
            break
        page = data.get("fillList")
        if not isinstance(page, list):
            schema_errors.append(f"PAGE_{page_number}_FILL_LIST_NOT_LIST")
            break
        if not page:
            status = "CONNECTED" if fills else "ZERO_FILLS"
            return FillTraceabilityResult(
                _run_row(
                    traceability_run_id=trace_id,
                    source_run_id=source_run_id,
                    observed_at_utc=observed_at_utc,
                    start=start,
                    end=end,
                    status=status,
                    complete=True,
                    schema_validated=True,
                    pages_fetched=pages_fetched,
                    fill_count=len(fills),
                    oldest_fill_at_utc=min((row["fill_time_utc"] for row in fills), default=None),
                    newest_fill_at_utc=max((row["fill_time_utc"] for row in fills), default=None),
                    detail=(None if fills else "Validated 7-day window returned zero fills"),
                    account_probe_status=account_probe_status,
                ),
                fills,
            )

        end_id = str(data.get("endId") or "").strip()
        if not end_id:
            schema_errors.append(f"PAGE_{page_number}_END_ID_MISSING")
            break

        for row_number, raw in enumerate(page, start=1):
            if not isinstance(raw, dict):
                schema_errors.append(f"PAGE_{page_number}_ROW_{row_number}_NOT_OBJECT")
                continue
            trade_id = str(raw.get("tradeId") or "").strip()
            if trade_id and trade_id in seen_trade_ids:
                continue
            normalized, errors = _normalize_fill(
                raw,
                traceability_run_id=trace_id,
                source_run_id=source_run_id,
                observed_at_utc=observed_at_utc,
            )
            if errors:
                schema_errors.extend(
                    f"PAGE_{page_number}_ROW_{row_number}_{error}" for error in errors
                )
                continue
            if normalized is not None:
                seen_trade_ids.add(normalized["trade_id"])
                fills.append(normalized)

        if schema_errors:
            break
        if len(page) < PAGE_LIMIT:
            return FillTraceabilityResult(
                _run_row(
                    traceability_run_id=trace_id,
                    source_run_id=source_run_id,
                    observed_at_utc=observed_at_utc,
                    start=start,
                    end=end,
                    status="CONNECTED",
                    complete=True,
                    schema_validated=True,
                    pages_fetched=pages_fetched,
                    fill_count=len(fills),
                    oldest_fill_at_utc=min((row["fill_time_utc"] for row in fills), default=None),
                    newest_fill_at_utc=max((row["fill_time_utc"] for row in fills), default=None),
                    detail=None,
                    account_probe_status=account_probe_status,
                ),
                fills,
            )
        if end_id == cursor:
            schema_errors.append(f"PAGE_{page_number}_PAGINATION_STALLED")
            break
        cursor = end_id

    status = "INVALID_SCHEMA" if schema_errors else "PAGINATION_LIMIT_REACHED"
    detail = ";".join(schema_errors) if schema_errors else (
        f"Fill retrieval reached safety limit of {MAX_PAGES} pages"
    )
    return FillTraceabilityResult(
        _run_row(
            traceability_run_id=trace_id,
            source_run_id=source_run_id,
            observed_at_utc=observed_at_utc,
            start=start,
            end=end,
            status=status,
            complete=False,
            schema_validated=False if schema_errors else True,
            pages_fetched=pages_fetched,
            fill_count=len(fills),
            oldest_fill_at_utc=min((row["fill_time_utc"] for row in fills), default=None),
            newest_fill_at_utc=max((row["fill_time_utc"] for row in fills), default=None),
            detail=detail,
            account_probe_status=account_probe_status,
        ),
        fills,
    )


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
            f"Fill ledger persistence failed for {table}: "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )
    return len(rows)


def persist_fill_traceability(
    settings: SupabaseConfig,
    result: FillTraceabilityResult,
) -> tuple[int, int]:
    run_attempted = _insert_ignore(
        settings,
        TRACEABILITY_TABLE,
        [result.run_row],
        "traceability_run_id",
    )
    fill_attempted = _insert_ignore(
        settings,
        FILL_TABLE,
        result.fill_rows,
        "trade_id",
    )
    return run_attempted, fill_attempted
