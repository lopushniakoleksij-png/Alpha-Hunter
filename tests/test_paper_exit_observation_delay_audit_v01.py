from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "ops/sql/paper_exit_observation_delay_audit_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_observation_delay_audit_sql_parses():
    assert parse_sql(SQL)


def test_audit_reads_only_valid_completed_lifecycle_evidence():
    assert "alpha_hunter_paper_completed_trades_valid_v05" in LOWER
    assert "alpha_hunter_paper_exit_fills_v04" in LOWER
    assert "alpha_hunter_paper_protective_orders_v03" in LOWER
    assert "alpha_hunter_paper_exit_attempts_v04" in LOWER
    assert "stop_triggered" in LOWER
    assert "target_triggered" in LOWER


def test_counterfactual_is_trigger_anchored_and_preserves_modeled_slippage():
    assert "protective_trigger_price" in LOWER
    assert "trigger_anchored_exit_price" in LOWER
    assert "x.side='sell'" in LOWER
    assert "x.side='buy'" in LOWER
    assert "x.slippage_bps/10000.0" in LOWER
    assert "trigger_anchored_net_r_ex_funding" in LOWER
    assert "observation_delay_tax_r" in LOWER


def test_counterfactual_is_explicitly_non_claim_and_conservative():
    assert "observed_spread_cost_reused_conservatively" in LOWER
    assert "counterfactual_only" in LOWER
    assert "profitability_claim_permitted" in LOWER
    assert "false as profitability_claim_permitted" in LOWER


def test_existing_paper_evidence_is_not_mutated():
    forbidden = (
        "delete from public.alpha_hunter_paper",
        "update public.alpha_hunter_paper",
        "truncate",
        "insert into public.alpha_hunter_paper_fills",
        "insert into public.alpha_hunter_paper_exit_fills",
        "insert into public.alpha_hunter_paper_completed",
    )
    for marker in forbidden:
        assert marker not in LOWER


def test_audit_has_no_exchange_or_promotion_authority():
    assert "false as exchange_authority" in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER
    for forbidden in (
        "place_order(",
        "cancel_order(",
        "modify_order(",
        "set_leverage(",
    ):
        assert forbidden not in LOWER


def test_summary_reports_observed_and_trigger_anchored_r_separately():
    assert "alpha_hunter_paper_exit_observation_delay_summary_v01" in LOWER
    assert "average_observed_net_r" in LOWER
    assert "average_trigger_anchored_net_r" in LOWER
    assert "total_observation_delay_tax_r" in LOWER
    assert "maximum_absolute_observation_delay_tax_r" in LOWER
