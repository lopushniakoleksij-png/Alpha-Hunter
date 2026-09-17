from pathlib import Path


SQL = Path("scorecard_science_priority_and_participation_v02.sql").read_text()
LOWER = SQL.lower()


def test_keeps_single_evaluator_and_existing_request_cap():
    assert "alpha_hunter_run_big_mover_money_scorecard" in SQL
    assert "limit 80" in LOWER
    assert "limit 81" not in LOWER
    assert "limit 160" not in LOWER
    assert "http_get(" not in LOWER
    assert "http_post(" not in LOWER
    assert "cron.schedule" not in LOWER


def test_current_clean_science_cohorts_are_prioritized_without_trade_authority():
    assert "prospective-early-mover-cohort-v0.2" in SQL
    assert "geometry-diagnostics-v0.2.2-money-entry-scope-aligned" in SQL
    assert "participation-diagnostics-v0.1" in SQL
    assert "scorecard queue contract drifted; refusing patch" in SQL
    assert "trade_permission=true" not in LOWER
    assert "production_execution_enabled=true" not in LOWER


def test_participation_v02_reuses_money_scorecard_exact_bridge_lineage():
    assert "alpha_hunter_participation_forward_observations_v02" in SQL
    assert "alpha_hunter_participation_forward_status_v02" in SQL
    assert "c.source_bridge_id=d.source_bridge_id" in LOWER
    assert "c.run_id=d.run_id" in LOWER
    assert "c.symbol=d.symbol" in LOWER
    assert "c.direction=d.candidate_direction" in LOWER
    assert "alpha_hunter_big_mover_money_scorecard_outcomes" in SQL
    assert "alpha_hunter_signal_outcomes" not in SQL


def test_science_authority_remains_fail_closed():
    assert "false as confirmatory_claim_permitted" in LOWER
    assert "false as threshold_derivation_permitted" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "true as shadow_only" in LOWER
    assert "false as trade_permission" in LOWER
    assert "exploratory_prospective" in LOWER


def test_v01_views_are_not_replaced_or_dropped():
    assert "create or replace view public.alpha_hunter_participation_forward_observations_v01" not in LOWER
    assert "create or replace view public.alpha_hunter_participation_forward_status_v01" not in LOWER
    assert "drop view" not in LOWER
