from pathlib import Path

SQL = Path("ops/sql/participation_endpoint_forward_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_forward_only_boundary_and_no_backfill():
    assert "registered_at_utc" in SQL
    assert "d.captured_at_utc>=v_spec.registered_at_utc" in SQL
    assert "no participation diagnostic observed before registered_at_utc is admitted" in SQL


def test_explicit_direction_conflicts_are_excluded():
    assert "(s.direction is null or s.direction=d.candidate_direction)" in SQL


def test_endpoint_uses_first_canonical_snapshot_after_due():
    assert "ss.collected_at_utc>=d.due_at_utc" in SQL
    assert "order by ss.collected_at_utc" in SQL
    assert "first_canonical_symbol_snapshot_at_or_after_due" in SQL


def test_endpoint_lag_is_bounded():
    assert "endpoint_max_lag_minutes" in SQL
    assert "make_interval(mins=>v_spec.endpoint_max_lag_minutes)" in SQL


def test_no_path_or_threshold_claims():
    assert "'stop_target_path_claim_permitted',false" in SQL
    assert "threshold_derivation_permitted boolean not null default false" in SQL
    assert "false as threshold_derivation_permitted" in SQL


def test_no_trade_or_production_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "threshold_derivation_permitted=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL


def test_hourly_cron_uses_free_minute():
    assert "'14 * * * *'" in SQL
    assert "alpha-hunter-participation-endpoint-forward-v01" in SQL
