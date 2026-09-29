from pathlib import Path

SQL = Path("ops/sql/volume_growth_cadence_forward_v02.sql").read_text(
    encoding="utf-8"
).lower()


def test_v01_is_explicitly_superseded():
    assert "vg-forward-top30-v01" in SQL
    assert "vg-forward-top30-cadence-v02" in SQL
    assert "v01_lag_predecessor_incompatible_with_20_minute_scanner_cadence" in SQL


def test_cadence_aware_prior_is_50_to_70_minutes():
    assert "50,70,60" in SQL
    assert "make_interval(mins=>v_prior_max)" in SQL
    assert "make_interval(mins=>v_prior_min)" in SQL
    assert "make_interval(mins=>v_prior_target)" in SQL


def test_new_forward_boundary_blocks_backfill():
    assert "experiment_started_at_utc" in SQL
    assert "u.observed_at_utc>=v_started_at" in SQL
    assert "no universe observation before the v02 preregistration boundary is admitted" in SQL


def test_forward_candidate_is_sub5_only():
    assert "abs(s.change_24h_pct)<5.0" in SQL
    assert "first_new_5pct_event_after_sub5_capture" in SQL


def test_scorecard_compares_shadow_and_production():
    for marker in [
        "shadow_precision_pct",
        "production_precision_pct",
        "shadow_only_precision_pct",
        "production_only_precision_pct",
    ]:
        assert marker in SQL


def test_v01_cron_is_removed_and_v02_uses_free_minutes():
    assert "alpha-hunter-volume-growth-forward-scorecard-v01" in SQL
    assert "alpha-hunter-volume-growth-forward-scorecard-v02" in SQL
    assert "'9,30,52 * * * *'" in SQL


def test_no_trade_or_selector_authority():
    for marker in [
        "production_selector_changed',false",
        "trade_permission boolean not null default false",
        "threshold_change_permitted boolean not null default false",
        "production_promotion_permitted boolean not null default false",
    ]:
        assert marker in SQL

    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL


def test_ranked_sql_alias_does_not_collide_with_plpgsql_record():
    assert "from ranked ranked_row" in SQL
    assert "md5(ranked_row.observation_id)" in SQL
    assert "from ranked r\n" not in SQL
