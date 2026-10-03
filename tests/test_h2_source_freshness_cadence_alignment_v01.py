from pathlib import Path

SQL = Path("h2_source_freshness_cadence_alignment_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_repair_moves_only_downstream_cadence():
    assert "schedule:='17 * * * *'" in SQL
    assert "schedule:='18 * * * *'" in SQL
    assert "schedule:='20 */6 * * *'" in SQL
    assert "alpha-hunter-big-mover-money-entry-bridge-hourly" in SQL
    assert "alpha-hunter-money-entry-stage-hourly" in SQL
    assert "alpha-hunter-h2-direction-capture-hourly" in SQL


def test_h2_six_hour_frequency_is_preserved():
    assert "'18 */6 * * *'" in SQL
    assert "'20 */6 * * *'" in SQL
    assert "H2 remains a 6-hour capture job" in SQL


def test_upstream_answer_key_and_parent_cadence_are_not_changed():
    assert "ANSWER_KEY and PARENT_DIRECTION unchanged" in SQL
    assert "alpha-hunter-big-mover-shadow-hourly" not in SQL
    assert "jobname='alpha-hunter-big-mover-parent-direction-hourly'" not in SQL


def test_existing_job_contract_is_fail_closed():
    assert "command contract mismatch" in SQL
    assert "unexpected existing schedule" in SQL
    assert "refuses to modify inactive required jobs" in SQL
    assert "v_bridge.command<>" in SQL
    assert "v_stage.command<>" in SQL
    assert "v_h2.command<>" in SQL


def test_frozen_fifteen_minute_contract_is_not_weakened():
    assert "15::integer as frozen_maximum_source_age_minutes" in LOWER
    assert "does not change the h2 15-minute freshness contract" in LOWER
    assert "source_fresh_for_15m_trigger" in LOWER


def test_read_only_freshness_status_exposes_directional_stall():
    assert "alpha_hunter_h2_source_freshness_status_v01" in LOWER
    assert "pre_fresh_context_rows" in LOWER
    assert "fresh_context_rows" in LOWER
    assert "stale_context_rows" in LOWER
    assert "pipeline_freshness_stalled" in LOWER
    assert "group by direction" in LOWER


def test_observability_does_not_read_outcomes_or_change_science():
    forbidden = [
        "alpha_hunter_signal_outcomes",
        "geometry_holdout_outcomes",
        "trade_permission=true",
        "trade_permission = true",
        "threshold_change_permitted=true",
        "production_promotion_permitted=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER

    assert "false as outcome_evidence_used" in LOWER
    assert "false as threshold_change_permitted" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "false as trade_permission" in LOWER
    assert "'NONE'::text as order_path" in SQL


def test_status_view_is_service_role_read_only():
    assert (
        "revoke all on public.alpha_hunter_h2_source_freshness_status_v01"
        in LOWER
    )
    assert (
        "grant select on public.alpha_hunter_h2_source_freshness_status_v01"
        in LOWER
    )
