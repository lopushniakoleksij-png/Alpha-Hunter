from pathlib import Path

SQL = Path("direction_confirmation_tax_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_reuses_exact_24h_cooldown_without_new_trade_threshold():
    required = [
        "interval '24 hours'",
        "24::integer as cooldown_hours",
        "GEOMETRY_HOLDOUT_OVERLAP_RULE_REUSED",
    ]
    for marker in required:
        assert marker in SQL


def test_early_reference_requires_parent_alignment_and_early_timing():
    required = [
        "parent_12h_1d_aligned=true",
        "opportunity_timing='EARLY'",
        "scanner_direction is distinct from g.direction",
        "rr_15m_stop_4h_target is not null",
    ]
    for marker in required:
        assert marker in SQL


def test_pairing_uses_first_later_scanner_alignment_within_24h():
    required = [
        "g.scanner_direction=e.direction",
        "g.captured_at_utc>=e.captured_at_utc",
        "g.captured_at_utc<=e.captured_at_utc+interval '24 hours'",
        "order by g.captured_at_utc,g.diagnostic_id",
        "limit 1",
    ]
    for marker in required:
        assert marker in SQL


def test_confirmation_tax_is_direction_normalized():
    required = [
        "(p.scanner_entry/p.early_entry-1.0)*100.0",
        "(p.early_entry/p.scanner_entry-1.0)*100.0",
        "p.early_rr-p.scanner_rr",
        "confirmation_price_tax_pct",
        "confirmation_rr_tax",
    ]
    for marker in required:
        assert marker in SQL


def test_rr5_transition_is_descriptive_only():
    required = [
        "LOST_RR5",
        "RETAINED_RR5",
        "GAINED_RR5",
        "NEVER_RR5",
        "NO_SCANNER_ALIGNMENT_WITHIN_24H",
    ]
    for marker in required:
        assert marker in SQL


def test_no_outcome_or_execution_authority():
    required = [
        "false as outcome_evidence_used",
        "false as sealed_holdout_outcome_read",
        "false as t0_authorized",
        "false as threshold_change_permitted",
        "false as production_promotion_permitted",
        "true as shadow_only",
        "false as trade_permission",
        "DESCRIPTIVE_DECISION_TIME_CONFIRMATION_TAX_ONLY",
    ]
    for marker in required:
        assert marker in SQL


def test_views_are_service_role_only():
    for view in (
        "alpha_hunter_direction_confirmation_tax_pairs_v01",
        "alpha_hunter_direction_confirmation_tax_status_v01",
    ):
        assert f"revoke all on public.{view}" in LOWER
        assert f"grant select on public.{view}" in LOWER


def test_no_sealed_outcome_or_production_mutation():
    forbidden = [
        "geometry_holdout_outcomes_sealed",
        "evaluator_failures",
        "insert into",
        "update public.",
        "delete from",
        "cron.schedule",
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled",
        "place_order",
        "cancel_order",
        "modify_order",
        "set-leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER
