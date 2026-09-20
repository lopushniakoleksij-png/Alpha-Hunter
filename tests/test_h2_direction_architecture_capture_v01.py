from pathlib import Path

SQL = Path("h2_direction_architecture_capture_v01.sql").read_text(
    encoding="utf-8"
)
STATUS = Path("nonstop_production_status_v02.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_h2_architecture_is_frozen_exactly():
    required = [
        "H_PARENT_12H_1D_1H_TIMING_15M_ACCEPTANCE_VS_LEGACY_ALIGNMENT_V1",
        "12H and 1D parent directions must both align with candidate direction",
        "1H trend must align with candidate direction",
        "latest closed 15m close above EMA9 for LONG or below EMA9 for SHORT",
        "15m trend label is not a mandatory direction vote",
        "15m local support/resistance invalidation with 4H structural target",
        "scanner_direction equals candidate direction",
    ]
    for marker in required:
        assert marker in SQL


def test_source_scan_price_cannot_become_decision_anchor():
    required = [
        "source_scan_price_is_decision_anchor boolean not null default false",
        "check(source_scan_price_is_decision_anchor=false)",
        "source scan price is provenance only and never the decision anchor",
        "reference_price_is_fill_claim boolean not null default false",
        "check(reference_price_is_fill_claim=false)",
    ]
    for marker in required:
        assert marker in SQL


def test_decision_anchor_is_exact_public_one_minute_open():
    required = [
        "/api/v3/market/candles",
        "interval=1m",
        "ceil(extract(epoch from r.decision_available_at_utc)/60.0)*60.0",
        "= v_expected",
        "BITGET_PUBLIC_V3_1M_CANDLES",
        "exact_expected_minute_required",
        "public_market_data_only",
    ]
    for marker in required:
        assert marker in SQL


def test_capture_is_strictly_post_registration_and_source_freshness_is_bounded():
    required = [
        "g.created_at>v_spec.registered_at_utc",
        "g.created_at<=v_spec.collection_ends_at_utc",
        "maximum_source_age_minutes=15",
        "<= make_interval(mins=>v_spec.maximum_source_age_minutes)",
        "EXCLUDED_SOURCE_STALE_FOR_15M_TRIGGER",
    ]
    for marker in required:
        assert marker in SQL


def test_h2_trigger_does_not_require_15m_trend_alignment():
    assert "and g.timing_1h_aligned" in SQL
    assert "and g.parent_aligned" in SQL
    assert "and g.geometry_valid_at_source" in SQL
    assert "and g.source_fresh" in SQL
    assert "(x.h2_context and x.accept_fast_value)" in SQL

    # 15m trend is captured for analysis but not required by h2_context.
    h2_context_section = SQL.split(") as h2_context,", 1)[0][-1200:]
    assert "trend_15m" not in h2_context_section



def test_capture_classification_booleans_fail_closed_on_missing_context():
    required = [
        "coalesce(g.scanner_direction=g.direction,false)",
        "coalesce(g.opportunity_timing='EARLY',false)",
        "),false) as parent_aligned",
        "),false) as timing_1h_aligned",
    ]
    for marker in required:
        assert marker in SQL


def test_reclaim_and_structural_trigger_are_secondary_tags():
    required = [
        "trigger_accept_fast_value",
        "trigger_ema9_reclaim",
        "trigger_structural_sweep_reclaim",
        "EMA9_RECLAIM",
    ]
    # Architecture calls EMA9 reclaim the stronger tag rather than primary gate.
    assert "same latest closed 15m candle crosses EMA9 in candidate direction" in SQL
    for marker in required[:3]:
        assert marker in SQL


def test_24h_independence_rule_is_frozen():
    required = [
        "candidate_cooldown_hours integer not null check(candidate_cooldown_hours=24)",
        "interval '24 hours'",
        "first H2-triggered symbol-direction reference after a 24-hour cooldown",
    ]
    for marker in required:
        assert marker in SQL


def test_capture_maturity_gate_is_not_claimed_as_power_calculation():
    required = [
        "minimum_anchor_observations=100",
        "minimum_symbols=30",
        "minimum_utc_days=20",
        "minimum_anchors_per_direction=25",
        "capture_maturity_gate_is_power_calculation=false",
    ]
    for marker in required:
        assert marker in SQL


def test_outcomes_are_locked_and_future_evaluator_is_required():
    required = [
        "CAPTURE ONLY",
        "evaluator_preregistration_required=true",
        "outcome_access_permitted=false",
        "confirmatory_analysis_permitted=false",
        "PREREGISTER SEALED EVALUATOR BEFORE ANY H2 OUTCOME ACCESS",
        "primary_results_exposed",
    ]
    for marker in required:
        assert marker in SQL


def test_h2_sql_does_not_read_any_outcome_table():
    forbidden = [
        "alpha_hunter_geometry_holdout_outcomes_sealed",
        "alpha_hunter_signal_outcomes",
        "alpha_hunter_big_mover_money_scorecard_outcomes",
        "alpha_hunter_direction_outcomes",
        "realistic_net_r)",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_no_execution_authority_or_threshold_mutation():
    required = [
        "t0_authorized boolean not null default false",
        "threshold_change_permitted boolean not null default false",
        "production_promotion_permitted boolean not null default false",
        "trade_permission boolean not null default false",
        "order_path text not null default 'NONE'",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "activate_threshold",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_capture_job_is_database_only_not_duplicate_market_scanner():
    assert "alpha-hunter-h2-direction-capture-hourly" in SQL
    assert "'18 * * * *'" in SQL
    assert "alpha_hunter_geometry_diagnostics" in SQL
    assert "alpha_hunter_signal_features" in SQL


def test_h2_evidence_is_append_only_and_service_role_scoped():
    required_tables = [
        "alpha_hunter_h2_direction_specs_v01",
        "alpha_hunter_h2_direction_captures_v01",
        "alpha_hunter_h2_direction_anchor_prices_v01",
        "alpha_hunter_h2_direction_capture_failures_v01",
    ]
    for table in required_tables:
        assert f"alter table public.{table} enable row level security" in LOWER

    assert LOWER.count("alpha_hunter_block_append_only_mutation") >= 4
    assert "grant select on public.alpha_hunter_h2_direction_capture_status_v01" in LOWER
    assert "to service_role" in LOWER


def test_nonstop_status_v02_integrates_h2_without_replacing_v01():
    assert "alpha_hunter_nonstop_production_status_v02" in STATUS
    assert "alpha_hunter_h2_direction_capture_status_v01" in STATUS
    assert "alpha-hunter-h2-direction-capture-hourly" in STATUS
    assert "h2_capture_failure_events" in STATUS
    assert "h2_capture_maturity_gate_met" in STATUS
    assert "h2_outcome_access_permitted" in STATUS
    assert "h2_t0_authorized" in STATUS
    assert "REPAIR_H2_CAPTURE" in STATUS
    assert "COLLECT_PROSPECTIVE_EVIDENCE" in STATUS


def test_nonstop_status_h2_cannot_promote():
    required = [
        "automatic_threshold_change_permitted",
        "automatic_production_promotion_permitted",
        "live_order_path_permitted",
        "trade_permission",
    ]
    for marker in required:
        assert marker in STATUS
