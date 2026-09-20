from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .bitget import BitgetAPIError, BitgetClient
from .storage import SupabaseConfig


RUN_TABLE = "alpha_hunter_funding_bill_runs_v01"
BILL_TABLE = "alpha_hunter_funding_bill_evidence_v01"
LINK_TABLE = "alpha_hunter_funding_bill_links_v01"
ENDPOINT = "/api/v2/mix/account/bill"
MODEL_VERSION = "funding-bill-evidence-v0.1"
WINDOW_DAYS = 90
SUBWINDOW_DAYS = 30
PAGE_LIMIT = 100
MAX_PAGES_PER_WINDOW = 50
FUNDING_BUSINESS_TYPE = "contract_settle_fee"


@dataclass
class FundingBillResult:
    run_row: dict[str, Any]
    bill_rows: list[dict[str, Any]]


def _optional_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
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
            milliseconds / 1000.0,
            tz=timezone.utc,
        ).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _funding_run_id(start: datetime, end: datetime) -> str:
    return _sha256(
        f"{MODEL_VERSION}|{start.isoformat()}|{end.isoformat()}"
    )[:32]


def _funding_bill_id(raw_bill_id: str) -> tuple[str, str]:
    identity = _sha256(raw_bill_id)
    evidence_id = _sha256(
        f"{MODEL_VERSION}|{raw_bill_id}"
    )[:32]
    return evidence_id, identity


def _normalize_funding_bill(
    raw: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []

    raw_bill_id = str(raw.get("billId") or "").strip()
    business_type = str(
        raw.get("businessType") or ""
    ).strip()
    bill_time_utc = _iso_from_ms(raw.get("cTime"))
    symbol = str(raw.get("symbol") or "").upper().strip() or None
    amount = _optional_float(raw.get("amount"))
    fee = _optional_float(raw.get("fee"))
    fee_by_coupon = _optional_float(raw.get("feeByCoupon"))
    coin = str(raw.get("coin") or "").upper().strip()

    if not raw_bill_id:
        errors.append("BILL_ID_MISSING")
    if business_type != FUNDING_BUSINESS_TYPE:
        errors.append("BUSINESS_TYPE_NOT_FUNDING")
    if bill_time_utc is None:
        errors.append("BILL_TIME_INVALID")
    if amount is None:
        errors.append("AMOUNT_INVALID")
    if not coin:
        errors.append("COIN_MISSING")

    if errors:
        return None, errors

    evidence_id, identity_hash = _funding_bill_id(raw_bill_id)
    signed_fee = fee if fee is not None else 0.0

    return {
        "funding_bill_evidence_id": evidence_id,
        "bill_identity_sha256": identity_hash,
        "bill_time_utc": bill_time_utc,
        "symbol": symbol,
        "business_type": FUNDING_BUSINESS_TYPE,
        "amount": amount,
        "fee": fee,
        "fee_by_coupon": fee_by_coupon,
        "coin": coin,
        "funding_account_effect": amount + signed_fee,
        "source_endpoint": ENDPOINT,
        "raw_bill_id_persisted": False,
        "scientific_role": "ACCOUNT_OBSERVED_FUNDING_CASHFLOW",
        "model_version": MODEL_VERSION,
        "shadow_only": True,
        "trade_permission": False,
    }, []


class ReadOnlyFundingBillClient(BitgetClient):
    """GET-only Bitget funding-bill client."""

    def futures_account_bills(
        self,
        *,
        product_type: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = PAGE_LIMIT,
        id_less_than: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "productType": product_type,
            "businessType": FUNDING_BUSINESS_TYPE,
            "startTime": start_time_ms,
            "endTime": end_time_ms,
            "limit": limit,
        }
        if id_less_than:
            params["idLessThan"] = id_less_than

        data = self._get(
            ENDPOINT,
            params,
            private=True,
            retry_deterministic_4xx=False,
        )
        if not isinstance(data, dict):
            raise BitgetAPIError(
                "Bitget account bill endpoint returned invalid schema"
            )
        return data


def _subwindows(
    end: datetime,
) -> list[tuple[datetime, datetime]]:
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    end = end.astimezone(timezone.utc)
    start = end - timedelta(days=WINDOW_DAYS)

    one_ms = timedelta(milliseconds=1)
    width = timedelta(days=SUBWINDOW_DAYS)
    windows: list[tuple[datetime, datetime]] = []

    cursor = start
    for index in range(3):
        sub_end = (
            end
            if index == 2
            else cursor + width - one_ms
        )
        windows.append((cursor, sub_end))
        cursor = sub_end + one_ms

    return windows


def _run_row(
    *,
    run_id: str,
    observed_at_utc: str,
    start: datetime,
    end: datetime,
    pages_fetched: int,
    funding_bill_count: int,
    status: str,
    complete: bool,
    schema_validated: bool,
    detail: str | None,
) -> dict[str, Any]:
    return {
        "funding_run_id": run_id,
        "observed_at_utc": observed_at_utc,
        "window_start_utc": start.isoformat(),
        "window_end_utc": end.isoformat(),
        "requested_window_days": WINDOW_DAYS,
        "window_count": 3,
        "pages_fetched": pages_fetched,
        "funding_bill_count": funding_bill_count,
        "status": status,
        "complete": complete,
        "schema_validated": schema_validated,
        "source_endpoint": ENDPOINT,
        "read_only_get": True,
        "no_order_write_path": True,
        "detail": detail,
        "model_version": MODEL_VERSION,
        "shadow_only": True,
        "trade_permission": False,
    }


def collect_funding_bills(
    client: ReadOnlyFundingBillClient,
    *,
    product_type: str,
    observed_at_utc: str,
    private_account: dict[str, Any],
) -> FundingBillResult:
    try:
        end = datetime.fromisoformat(
            observed_at_utc.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            "funding bill observed_at_utc is invalid"
        ) from exc

    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    end = end.astimezone(timezone.utc)
    start = end - timedelta(days=WINDOW_DAYS)
    run_id = _funding_run_id(start, end)

    account_status = str(
        private_account.get("status") or "MISSING"
    ).upper()
    classic_accepted = (
        private_account.get("classic_v2_risk_evidence_accepted")
        is True
    )

    if not client.private_api_configured:
        return FundingBillResult(
            _run_row(
                run_id=run_id,
                observed_at_utc=observed_at_utc,
                start=start,
                end=end,
                pages_fetched=0,
                funding_bill_count=0,
                status="NOT_CONFIGURED",
                complete=False,
                schema_validated=False,
                detail="Bitget private API credentials are not configured",
            ),
            [],
        )

    if account_status != "CONNECTED" or not classic_accepted:
        return FundingBillResult(
            _run_row(
                run_id=run_id,
                observed_at_utc=observed_at_utc,
                start=start,
                end=end,
                pages_fetched=0,
                funding_bill_count=0,
                status="BLOCKED_ACCOUNT_API_FAMILY_UNVERIFIED",
                complete=False,
                schema_validated=False,
                detail=(
                    f"private_account_status={account_status}; "
                    f"classic_v2_risk_evidence_accepted={classic_accepted}"
                ),
            ),
            [],
        )

    rows: list[dict[str, Any]] = []
    seen_bill_hashes: set[str] = set()
    pages_fetched = 0
    schema_errors: list[str] = []

    for window_number, (window_start, window_end) in enumerate(
        _subwindows(end),
        start=1,
    ):
        cursor: str | None = None

        for page_number in range(1, MAX_PAGES_PER_WINDOW + 1):
            try:
                data = client.futures_account_bills(
                    product_type=product_type,
                    start_time_ms=int(
                        window_start.timestamp() * 1000
                    ),
                    end_time_ms=int(
                        window_end.timestamp() * 1000
                    ),
                    limit=PAGE_LIMIT,
                    id_less_than=cursor,
                )
            except BitgetAPIError as exc:
                return FundingBillResult(
                    _run_row(
                        run_id=run_id,
                        observed_at_utc=observed_at_utc,
                        start=start,
                        end=end,
                        pages_fetched=pages_fetched,
                        funding_bill_count=len(rows),
                        status="FAILED",
                        complete=False,
                        schema_validated=False,
                        detail=str(exc),
                    ),
                    rows,
                )

            pages_fetched += 1
            bills = data.get("bills")
            if not isinstance(bills, list):
                schema_errors.append(
                    f"WINDOW_{window_number}_PAGE_{page_number}_"
                    "BILLS_NOT_LIST"
                )
                break

            if not bills:
                break

            for row_number, raw in enumerate(bills, start=1):
                if not isinstance(raw, dict):
                    schema_errors.append(
                        f"WINDOW_{window_number}_PAGE_{page_number}_"
                        f"ROW_{row_number}_NOT_OBJECT"
                    )
                    continue

                normalized, errors = _normalize_funding_bill(raw)
                if errors:
                    schema_errors.extend(
                        f"WINDOW_{window_number}_PAGE_{page_number}_"
                        f"ROW_{row_number}_{error}"
                        for error in errors
                    )
                    continue

                if normalized is None:
                    continue

                identity_hash = normalized[
                    "bill_identity_sha256"
                ]
                if identity_hash in seen_bill_hashes:
                    continue

                seen_bill_hashes.add(identity_hash)
                rows.append(normalized)

            if schema_errors:
                break

            if len(bills) < PAGE_LIMIT:
                break

            end_id = str(data.get("endId") or "").strip()
            if not end_id:
                schema_errors.append(
                    f"WINDOW_{window_number}_PAGE_{page_number}_"
                    "END_ID_MISSING"
                )
                break
            if end_id == cursor:
                schema_errors.append(
                    f"WINDOW_{window_number}_PAGE_{page_number}_"
                    "PAGINATION_STALLED"
                )
                break

            cursor = end_id
        else:
            schema_errors.append(
                f"WINDOW_{window_number}_PAGINATION_LIMIT_REACHED"
            )

        if schema_errors:
            break

    if schema_errors:
        return FundingBillResult(
            _run_row(
                run_id=run_id,
                observed_at_utc=observed_at_utc,
                start=start,
                end=end,
                pages_fetched=pages_fetched,
                funding_bill_count=len(rows),
                status="INVALID_SCHEMA",
                complete=False,
                schema_validated=False,
                detail=";".join(schema_errors),
            ),
            rows,
        )

    status = "CONNECTED" if rows else "ZERO_FUNDING_BILLS"
    return FundingBillResult(
        _run_row(
            run_id=run_id,
            observed_at_utc=observed_at_utc,
            start=start,
            end=end,
            pages_fetched=pages_fetched,
            funding_bill_count=len(rows),
            status=status,
            complete=True,
            schema_validated=True,
            detail=None,
        ),
        rows,
    )


def _headers(settings: SupabaseConfig) -> dict[str, str]:
    return {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
    }


def _insert_ignore(
    settings: SupabaseConfig,
    table: str,
    rows: list[dict[str, Any]],
    on_conflict: str,
) -> int:
    if not rows:
        return 0

    headers = _headers(settings)
    headers["Prefer"] = (
        "resolution=ignore-duplicates,return=minimal"
    )

    response = requests.post(
        f"{settings.url}/rest/v1/{table}",
        params={"on_conflict": on_conflict},
        headers=headers,
        data=json.dumps(rows, separators=(",", ":")),
        timeout=settings.timeout_seconds,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(
            f"Funding bill persistence failed for {table}: "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )
    return len(rows)


def _link_rows(result: FundingBillResult) -> list[dict[str, Any]]:
    run_id = str(result.run_row.get("funding_run_id") or "")
    if not run_id:
        return []

    return [
        {
            "funding_run_id": run_id,
            "funding_bill_evidence_id": row[
                "funding_bill_evidence_id"
            ],
            "model_version": MODEL_VERSION,
            "shadow_only": True,
            "trade_permission": False,
        }
        for row in result.bill_rows
        if row.get("funding_bill_evidence_id")
    ]


def persist_funding_bills(
    settings: SupabaseConfig,
    result: FundingBillResult,
) -> tuple[int, int, int]:
    run_attempted = _insert_ignore(
        settings,
        RUN_TABLE,
        [result.run_row],
        "funding_run_id",
    )

    evidence_complete = (
        result.run_row.get("complete") is True
        and result.run_row.get("schema_validated") is True
        and result.run_row.get("status")
        in {"CONNECTED", "ZERO_FUNDING_BILLS"}
    )
    canonical_rows = (
        result.bill_rows
        if evidence_complete
        else []
    )

    bill_attempted = _insert_ignore(
        settings,
        BILL_TABLE,
        canonical_rows,
        "bill_identity_sha256",
    )
    link_rows = (
        _link_rows(result)
        if evidence_complete
        else []
    )
    link_attempted = _insert_ignore(
        settings,
        LINK_TABLE,
        link_rows,
        "funding_run_id,funding_bill_evidence_id",
    )
    return run_attempted, bill_attempted, link_attempted
