from pathlib import Path

SQL = Path("sealed_decision_quote_status_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_sealed_quote_view_excludes_left_censored_rows():
    required = [
        "left_censored_quote_rows",
        "sealed_eligible_quote_rows",
        "coalesce(o.first_seen_at_utc,o.observed_at_utc)>=a.started_at_utc",
        "left_censored_quotes_diagnostic_only",
    ]
    for marker in required:
        assert marker in SQL


def test_sealed_quote_view_is_source_scoped():
    assert "q.run_source=s.required_run_source" in SQL
    assert "sealed_post_baseline_quotes_only" in SQL


def test_sealed_quote_view_cannot_activate_cost_model():
    required = [
        "false as slippage_measured",
        "false as fill_claim_permitted",
        "false as cost_model_activation_permitted",
        "false as realistic_net_r_claim_permitted",
    ]
    for marker in required:
        assert marker in SQL


def test_sealed_quote_view_has_no_trading_authority():
    assert "true as paper_only" in SQL
    assert "false as trade_permission" in SQL
    assert "false as production_promotion_permitted" in SQL
    assert "'none'::text as order_path" in SQL
