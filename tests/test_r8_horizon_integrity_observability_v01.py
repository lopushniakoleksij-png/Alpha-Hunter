from pathlib import Path

from pglast import parse_sql


SQL = Path("ops/sql/r8_horizon_integrity_observability_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_sql_parses():
    assert parse_sql(SQL)


def test_guard_is_bound_to_frozen_r8_spec_and_horizon():
    assert "SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003" in SQL
    assert "evaluation_horizon_hours" in LOWER
    assert "frozen_evaluation_horizon_hours" in LOWER
    assert "over_horizon_from_submission_or_exposure" in LOWER
    assert "over_horizon_from_completed_entry" in LOWER


def test_guard_observes_both_active_and_completed_r8_rows():
    assert "alpha_hunter_paper_active_exposure_members_v08" in LOWER
    assert "alpha_hunter_paper_protection_open_v04" in LOWER
    assert "alpha_hunter_paper_completed_trades_valid_v08" in LOWER
    assert "active_over_horizon_positions" in LOWER
    assert "completed_over_horizon_trades" in LOWER


def test_guard_does_not_retroactively_define_a_terminal_exit():
    assert "does not invent a terminal 24h exit" in LOWER
    assert "exit_model_change_permitted" in LOWER
    assert "false as exit_model_change_permitted" in LOWER


def test_guard_cannot_mutate_r8_sample_or_trade_authority():
    forbidden = [
        "insert into public.alpha_hunter_paper_",
        "update public.alpha_hunter_paper_",
        "delete from public.alpha_hunter_paper_",
        "cron.schedule",
        "cron.alter_job",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]
    for marker in forbidden:
        assert marker not in LOWER

    assert "false as sample_mutation_permitted" in LOWER
    assert "false as profitability_claim_permitted" in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER


def test_views_are_service_role_read_only():
    for view in [
        "alpha_hunter_r8_horizon_position_status_v01",
        "alpha_hunter_r8_horizon_integrity_status_v01",
    ]:
        assert f"revoke all on public.{view}" in LOWER
        assert f"grant select on public.{view}" in LOWER


def test_breach_status_requires_protocol_review_not_automatic_repair():
    assert "completed_horizon_breach_observed_review_protocol" in LOWER
    assert "active_horizon_breach_observed_review_protocol" in LOWER
    assert "observability_only_no_retroactive_sample_or_exit_policy_change" in LOWER
