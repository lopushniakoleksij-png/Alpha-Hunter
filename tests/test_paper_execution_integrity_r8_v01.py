from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "ops/sql/paper_execution_integrity_r8_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_r8_integrity_sql_parses():
    assert parse_sql(SQL)


def test_r8_activation_is_explicit_append_only_and_fail_closed():
    required = [
        "alpha_hunter_paper_execution_integrity_activation_v08",
        "paper_execution_r8",
        "maximum_entry_age_minutes",
        "maximum_monitoring_gap_minutes",
        "required_run_source",
        "render_cron",
        "before update or delete",
        "grant select",
    ]
    for marker in required:
        assert marker in LOWER

    assert "insert into public.alpha_hunter_paper_execution_integrity_activation_v08" not in LOWER


def test_reconciliation_is_scoped_to_post_activation_latest_open_state():
    required = [
        "alpha_hunter_paper_reconciliation_open_v08",
        "o.submitted_at_utc>=a.activated_at_utc",
        "le.state in ('submitted','partially_filled')",
        "alpha_hunter_paper_entry_quarantine_v06",
        "entry_reconciliation_permitted=true",
    ]
    for marker in required:
        assert marker in LOWER


def test_reconciliation_outcome_contract_supports_r8_terminal_states():
    required = [
        "'no_full_capacity'",
        "'expired'",
        "'quarantined_legacy_partial'",
    ]
    for marker in required:
        assert marker in LOWER


def test_active_exposure_key_is_symbol_strategy_direction():
    required = [
        "alpha_hunter_paper_active_exposure_members_v08",
        "alpha_hunter_paper_active_exposure_keys_v08",
        "symbol",
        "strategy_id",
        "direction",
        "'resting_entry'",
        "'filled_protected_position'",
    ]
    for marker in required:
        assert marker in LOWER


def test_clean_trade_quality_requires_source_fingerprint_aon_freshness_and_monitoring():
    required = [
        "alpha_hunter_paper_completed_trade_quality_v08",
        "canonical_paper_authority_source_valid",
        "scientific_fingerprint_match",
        "all_or_none_entry_valid",
        "entry_freshness_valid",
        "monitoring_cadence_valid",
        "partial_fill_state_count",
        "maximum_monitoring_gap_minutes_observed",
    ]
    for marker in required:
        assert marker in LOWER


def test_clean_completed_view_excludes_any_failed_integrity_gate():
    assert "alpha_hunter_paper_completed_trades_valid_v08" in LOWER
    for gate in [
        "canonical_paper_authority_source_valid=true",
        "scientific_fingerprint_match=true",
        "all_or_none_entry_valid=true",
        "entry_freshness_valid=true",
        "monitoring_cadence_valid=true",
    ]:
        assert gate in LOWER


def test_quarantine_is_append_only_projection_not_history_mutation():
    assert "alpha_hunter_paper_completed_trades_quarantine_v08" in LOWER
    for reason in [
        "non_canonical_paper_authority_source",
        "scientific_fingerprint_mismatch",
        "entry_not_all_or_none",
        "entry_stale_over_35m",
        "protective_monitoring_gap_over_35m",
    ]:
        assert reason in LOWER

    forbidden = [
        "delete from public.alpha_hunter_paper_",
        "update public.alpha_hunter_paper_completed",
        "update public.alpha_hunter_paper_orders",
        "update public.alpha_hunter_paper_fills",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_integrity_status_keeps_all_live_authority_disabled():
    required = [
        "one_exposure_guard_integrity_ok",
        "all_or_none_entry_required",
        "canonical_render_cron_required",
        "false as live_money_claim_permitted",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in LOWER
