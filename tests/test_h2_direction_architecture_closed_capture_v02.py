from pathlib import Path

from alpha_hunter.analysis import ema

SQL = Path("h2_direction_architecture_closed_capture_v02.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_new_forward_only_closed_candle_cohort_is_separate_from_v01():
    assert "ah-direction-architecture-h2-closed-capture-v02" in LOWER
    assert "h2-direction-architecture-closed-capture-v0.2" in LOWER
    assert "v0.1 rows remain immutable" in LOWER
    assert "does not update/delete/import any v0.1" in LOWER


def test_trigger_uses_canonical_exact_run_symbol_snapshot():
    assert "public.alpha_hunter_symbol_snapshots" in LOWER
    assert "s.run_id=g.run_id" in LOWER
    assert "s.symbol=g.symbol" in LOWER
    assert "last_closed_candle" in LOWER
    assert "canonical_symbol_snapshot_exact_run_symbol_last_closed_candle" in LOWER


def test_trigger_does_not_use_compact_signal_feature_candle_or_ema():
    assert "join public.alpha_hunter_signal_features" not in LOWER
    assert "source_payload#>>'{timeframes,15m,latest_candle,close}'" not in LOWER


def test_closed_candle_is_proven_closed_and_exactly_precedes_forming_bar():
    assert "trigger_candle_confirmed_closed" in LOWER
    assert "forming_candle_started_at_utc" in LOWER
    assert "=sr.trigger_candle_started_at_utc+interval '15 minutes'" in LOWER
    assert "snapshot_collected_at_utc" in LOWER
    assert "excluded_closed_15m_trigger_source_invalid" in LOWER


def test_reverse_one_forming_bar_ema9_is_mathematically_exact():
    closes = [float(x) for x in range(1, 21)]
    current = ema(closes, 9)
    closed = ema(closes[:-1], 9)
    assert current is not None and closed is not None
    derived = (current - 0.2 * closes[-1]) / 0.8
    assert abs(derived - closed) < 1e-12
    assert "(sr.forming_ema9_15m-0.2*sr.forming_candle_close)/0.8" in LOWER
    assert "reversed_one_forming_bar_standard_ema9" in LOWER


def test_existing_h2_science_gates_remain_frozen():
    for marker in [
        "candidate_cooldown_hours integer not null check(candidate_cooldown_hours=24)",
        "check(maximum_source_age_minutes=15)",
        "check(minimum_anchor_observations=100)",
        "minimum_symbols integer not null check(minimum_symbols=30)",
        "minimum_utc_days integer not null check(minimum_utc_days=20)",
        "check(minimum_anchors_per_direction=25)",
        "maximum_collection_days integer not null check(maximum_collection_days=60)",
        "opportunity_timing='early'",
        "parent_aligned",
        "timing_1h_aligned",
        "geometry_valid_at_source",
    ]:
        assert marker in LOWER


def test_outcomes_thresholds_and_trading_remain_locked():
    for forbidden in [
        "trade_permission=true",
        "threshold_change_permitted=true",
        "production_promotion_permitted=true",
        "t0_authorized=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "alpha_hunter_signal_outcomes",
    ]:
        assert forbidden not in LOWER
    assert "outcome_access_permitted boolean not null default false" in LOWER
    assert "confirmatory_analysis_permitted boolean not null default false" in LOWER
    assert "'none'::text as order_path" in LOWER or "'none'" in LOWER


def test_new_collector_has_distinct_six_hour_schedule_and_does_not_unschedule_v01():
    assert "alpha-hunter-h2-direction-closed-capture-v02" in LOWER
    assert "'22 */6 * * *'" in SQL
    assert "does not unschedule v0.1" in LOWER


def test_canonical_source_binding_requires_exact_same_timestamp():
    assert "s.collected_at_utc=g.captured_at_utc" in LOWER


def test_anchor_collection_serves_only_preregistered_independent_h2_cohort():
    assert "with recursive" in LOWER
    assert "and c.h2_triggered=true" in LOWER
    assert "select distinct on(symbol,direction)" in LOWER
    assert "make_interval(hours=>v_spec.candidate_cooldown_hours)" in LOWER
    assert "h2_triggered_24h_symbol_direction_independent_only" in LOWER
    assert "'legacy_only_anchor_admission',false" in LOWER


def test_legacy_alignment_is_overlap_tag_not_anchor_admission_path():
    assert "legacy-only rows do not consume anchor collection capacity" in LOWER
    assert "future standalone legacy-control sampler/evaluator must be separately preregistered" in LOWER
    assert "and (c.h2_triggered or c.legacy_scanner_aligned)" not in LOWER
