from pathlib import Path

SQL = Path("ops/sql/participation_emerging_forward_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_rule_is_preexisting_partial_concept():
    assert "preexisting_alpha_hunter_analysis_partial_classification" in SQL
    assert "volume_state_1h_in_elevated_high or open_interest_change_pct_gt_0" in SQL


def test_confirmed_rows_are_separate():
    assert "scanner_confirmed" in SQL
    assert "when s.scanner_participation_confirmed is true" in SQL


def test_forward_boundary_and_no_backfill():
    assert "ep.captured_at_utc>=v_spec.registered_at_utc" in SQL
    assert "no endpoint candidate observed before registered_at_utc is admitted" in SQL


def test_no_t1_mapping_or_threshold_claim():
    assert "t1_stage_mapping_permitted boolean not null default false" in SQL
    assert "threshold_derivation_permitted boolean not null default false" in SQL
    assert "false as t1_stage_mapping_permitted" in SQL


def test_uses_timestamp_correct_endpoint_ledger():
    assert "private.alpha_hunter_participation_endpoint_outcomes_v01" in SQL


def test_no_trade_or_production_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "t1_stage_mapping_permitted=true",
        "threshold_derivation_permitted=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL


def test_hourly_cron_after_endpoint_capture():
    assert "'15 * * * *'" in SQL
    assert "alpha-hunter-participation-emerging-forward-v01" in SQL
