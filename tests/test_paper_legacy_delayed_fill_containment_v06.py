from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "ops/sql/paper_legacy_delayed_fill_containment_v06.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_containment_sql_parses_and_is_append_only():
    assert parse_sql(SQL)
    assert "alpha_hunter_paper_entry_quarantine_v06" in LOWER
    assert "legacy_delayed_limit_fill_pre_deploy" in LOWER
    assert "historical_rows_deleted',false" in LOWER
    assert "historical_rows_rewritten',false" in LOWER
    assert "delete from public.alpha_hunter_paper" not in LOWER
    assert "update public.alpha_hunter_paper" not in LOWER
    assert "truncate" not in LOWER


def test_reconciliation_fails_closed_on_runtime_drift():
    assert "alpha_hunter_paper_reconciliation_gate_v06" in LOWER
    assert "entry_reconciliation_permitted" in LOWER
    assert "d.deployment_status='matched'" in LOWER
    assert "and g.entry_reconciliation_permitted=true" in LOWER
    assert "if v_deployment_status is distinct from 'matched'" in LOWER
    assert "j->>'source_run_id' is distinct from v_latest_canonical_run_id" in LOWER


def test_stale_delayed_limit_fill_quarantine_is_forward_bounded():
    assert "o.order_type='limit'" in LOWER
    assert "f.filled_at_utc>o.submitted_at_utc" in LOWER
    assert "2026-10-03 00:07:44+00" in LOWER
    assert "a69cfb66c070640238d2ff480988c02c7da7f6955b43d4f1a12f10c4fc6095db" in LOWER


def test_valid_completed_trade_view_excludes_entry_and_exit_quarantine():
    assert "alpha_hunter_paper_completed_trades_valid_v05" in LOWER
    assert "left join public.alpha_hunter_paper_exit_quarantine_v04 q" in LOWER
    assert "left join public.alpha_hunter_paper_entry_quarantine_v06 eq" in LOWER
    assert "q.entry_order_id is null" in LOWER
    assert "eq.order_id is null" in LOWER


def test_reconciliation_view_preserves_existing_column_contract():
    start = LOWER.index(
        "create or replace view public.alpha_hunter_paper_reconciliation_open_v03"
    )
    end = LOWER.index(
        "from public.alpha_hunter_paper_orders_v02 o",
        start,
    )
    projection = LOWER[start:end]
    required_order = [
        "o.order_id",
        "o.decision_id",
        "o.symbol",
        "o.direction",
        "o.order_type",
        "o.limit_price",
        "o.quantity as ordered_quantity",
        "coalesce(x.filled_quantity,0) as filled_quantity",
        "o.quantity-coalesce(x.filled_quantity,0) as remaining_quantity",
        "as execution_state",
        "coalesce(x.fill_count,0)::integer as fill_count",
        "coalesce(e.event_sequence,3)::integer as event_sequence",
        "d.stop_price",
        "d.target_price",
        "o.public_maker_fee_bps",
        "o.public_taker_fee_bps",
        "o.paper_only",
        "o.exchange_authority",
        "o.trade_permission",
        "o.order_path",
        "o.submitted_at_utc",
        "x.average_fill_price",
    ]
    positions = [projection.index(marker) for marker in required_order]
    assert positions == sorted(positions)


def test_no_live_exchange_authority_added():
    assert "place_order(" not in LOWER
    assert "cancel_order(" not in LOWER
    assert "modify_order(" not in LOWER
    assert "set_leverage(" not in LOWER
    assert "exchange_authority boolean not null default false" in LOWER
    assert "trade_permission boolean not null default false" in LOWER
