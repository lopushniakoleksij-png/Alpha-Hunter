from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from alpha_hunter.funding_bills import (
    ENDPOINT,
    FUNDING_BUSINESS_TYPE,
    FundingBillResult,
    _normalize_funding_bill,
    _subwindows,
    collect_funding_bills,
    persist_funding_bills,
)


SQL = Path("funding_bill_evidence_v01.sql").read_text(encoding="utf-8")
MODULE = Path("alpha_hunter/funding_bills.py").read_text(encoding="utf-8")
SCRIPT = Path("ops/collect_funding_bills_readonly.py").read_text(
    encoding="utf-8"
)


class FakeFundingClient:
    private_api_configured = True

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def futures_account_bills(self, **kwargs):
        self.calls.append(kwargs)
        return self.payloads.pop(0)


def _account():
    return {
        "status": "CONNECTED",
        "classic_v2_risk_evidence_accepted": True,
    }


def _raw_bill(
    bill_id: str,
    *,
    ctime: str = "1789862400000",
    amount: str = "-0.25",
    fee: str = "0",
    symbol: str = "BTCUSDT",
):
    return {
        "billId": bill_id,
        "symbol": symbol,
        "amount": amount,
        "fee": fee,
        "feeByCoupon": "",
        "businessType": FUNDING_BUSINESS_TYPE,
        "coin": "USDT",
        "balance": "123.45",
        "cTime": ctime,
    }


def test_subwindows_cover_exactly_90_days_without_overlap():
    end = datetime(2026, 9, 20, 2, 30, tzinfo=timezone.utc)
    windows = _subwindows(end)

    assert len(windows) == 3
    assert windows[0][0] == end - timedelta(days=90)
    assert windows[-1][1] == end

    for index, (start, stop) in enumerate(windows):
        assert stop >= start
        assert stop - start < timedelta(days=30) + timedelta(milliseconds=1)
        if index:
            assert windows[index - 1][1] + timedelta(milliseconds=1) == start


def test_funding_bill_normalization_hashes_raw_identity():
    row, errors = _normalize_funding_bill(_raw_bill("raw-bill-123"))

    assert errors == []
    assert row is not None
    assert row["business_type"] == FUNDING_BUSINESS_TYPE
    assert row["amount"] == -0.25
    assert row["fee"] == 0.0
    assert row["funding_account_effect"] == -0.25
    assert len(row["bill_identity_sha256"]) == 64
    assert row["raw_bill_id_persisted"] is False
    assert "raw-bill-123" not in str(row)


def test_collector_queries_three_windows_and_deduplicates_boundary_bill():
    client = FakeFundingClient(
        [
            {"bills": [_raw_bill("same")], "endId": "same"},
            {"bills": [_raw_bill("same")], "endId": "same"},
            {"bills": [_raw_bill("unique")], "endId": "unique"},
        ]
    )

    result = collect_funding_bills(
        client,
        product_type="usdt-futures",
        observed_at_utc="2026-09-20T02:30:00+00:00",
        private_account=_account(),
    )

    assert result.run_row["status"] == "CONNECTED"
    assert result.run_row["complete"] is True
    assert result.run_row["schema_validated"] is True
    assert result.run_row["pages_fetched"] == 3
    assert result.run_row["funding_bill_count"] == 2
    assert len(result.bill_rows) == 2
    assert len(client.calls) == 3

    for call in client.calls:
        assert call["product_type"] == "usdt-futures"
        assert call["limit"] == 100
        assert call.get("id_less_than") is None
        assert call["end_time_ms"] - call["start_time_ms"] <= (
            30 * 24 * 60 * 60 * 1000
        )


def test_empty_three_window_collection_is_complete_zero_funding():
    client = FakeFundingClient(
        [
            {"bills": [], "endId": ""},
            {"bills": [], "endId": ""},
            {"bills": [], "endId": ""},
        ]
    )

    result = collect_funding_bills(
        client,
        product_type="usdt-futures",
        observed_at_utc="2026-09-20T02:30:00+00:00",
        private_account=_account(),
    )

    assert result.run_row["status"] == "ZERO_FUNDING_BILLS"
    assert result.run_row["complete"] is True
    assert result.run_row["schema_validated"] is True
    assert result.run_row["funding_bill_count"] == 0


def test_incomplete_run_never_persists_partial_bill_rows():
    result = FundingBillResult(
        run_row={
            "funding_run_id": "run-1",
            "complete": False,
            "schema_validated": False,
            "status": "INVALID_SCHEMA",
        },
        bill_rows=[
            {
                "funding_bill_evidence_id": "bill-1",
                "bill_identity_sha256": "a" * 64,
            }
        ],
    )

    calls = []

    def fake_insert(settings, table, rows, on_conflict):
        calls.append((table, rows, on_conflict))
        return len(rows)

    with patch(
        "alpha_hunter.funding_bills._insert_ignore",
        side_effect=fake_insert,
    ):
        attempted = persist_funding_bills(object(), result)

    assert attempted == (1, 0, 0)
    assert len(calls) == 3
    assert calls[0][1] == [result.run_row]
    assert calls[1][1] == []
    assert calls[2][1] == []


def test_client_contract_is_get_only_account_bill_endpoint():
    assert f'ENDPOINT = "{ENDPOINT}"' in MODULE
    assert "self._get(" in MODULE
    assert '"businessType": FUNDING_BUSINESS_TYPE' in MODULE
    assert '"startTime": start_time_ms' in MODULE
    assert '"endTime": end_time_ms' in MODULE
    assert "private=True" in MODULE
    assert "retry_deterministic_4xx=False" in MODULE


def test_sql_binding_requires_exactly_one_episode_candidate():
    required = [
        "candidate_episode_count",
        "when c.candidate_episode_count=1",
        "BOUND_UNAMBIGUOUS",
        "UNMATCHED",
        "AMBIGUOUS_OVERLAP",
        "false as inferred_direction",
    ]
    for marker in required:
        assert marker in SQL


def test_full_economic_pnl_gate_requires_complete_run_and_no_ambiguity():
    required = [
        "r.complete=true",
        "r.schema_validated=true",
        "e.opened_or_first_seen_at_utc>=r.window_start_utc",
        "e.closed_at_utc<=r.window_end_utc",
        "coalesce(a.ambiguous_in_episode_window,0)=0",
        "full_economic_pnl_claim_permitted",
        "ACCOUNT_OUTCOME_WITH_TRADING_FEES_AND_BOUND_FUNDING_ONLY",
    ]
    for marker in required:
        assert marker in SQL


def test_funding_schema_is_append_only_and_service_role_scoped():
    lower = SQL.lower()

    for table in (
        "alpha_hunter_funding_bill_runs_v01",
        "alpha_hunter_funding_bill_evidence_v01",
        "alpha_hunter_funding_bill_links_v01",
    ):
        assert f"alter table public.{table} enable row level security" in lower
        assert f"grant select,insert on table public.{table}" in lower

    assert lower.count("alpha_hunter_block_append_only_mutation") >= 3

    for view in (
        "alpha_hunter_roundtrip_funding_binding_v01",
        "alpha_hunter_roundtrip_funding_summary_v01",
        "alpha_hunter_roundtrip_economic_outcome_v01",
        "alpha_hunter_funding_bill_status_v01",
    ):
        assert f"grant select on public.{view}" in lower


def test_no_write_or_execution_authority_is_added():
    combined = (SQL + MODULE + SCRIPT).lower()

    for marker in (
        "place_order(",
        "cancel_order(",
        "modify_order(",
        "set_leverage(",
        "/api/v2/mix/order/place-order",
        "/api/v2/mix/order/cancel-order",
        "/api/v2/mix/account/set-leverage",
        "/api/v2/spot/wallet/transfer",
        "/api/v2/spot/wallet/withdrawal",
        "trade_permission=true",
        "trade_permission = true",
    ):
        assert marker not in combined

    assert '"raw_bill_ids_printed": False' in SCRIPT
    assert '"full_economic_pnl_claimed": False' in SCRIPT
    assert '"realistic_net_r_claimed": False' in SCRIPT
    assert '"trade_permission": False' in SCRIPT
    assert '"read_only_get": True' in SCRIPT
    assert '"no_order_write_path": True' in SCRIPT
