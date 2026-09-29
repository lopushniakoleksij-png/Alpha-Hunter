from pathlib import Path

SQL = Path("ops/sql/auto_prospective_decision_freeze_v02.sql").read_text(
    encoding="utf-8"
).lower()


def test_auto_freeze_is_decision_evidence_only():
    assert "automatic_decision_freeze',true" in SQL
    assert "automatic_fill_binding_permitted',false" in SQL
    assert "symbol_time_proximity_attribution_permitted',false" in SQL
    assert "explicit_exact_fill_binding_required',true" in SQL


def test_auto_freeze_requires_complete_prospective_geometry():
    for marker in [
        "new.quote_complete is not true",
        "new.prospective_capture is not true",
        "new.action not in ('execute_now','place_limit')",
        "s.geometry_valid is not true",
        "s.direction<>new.direction",
        "s.action<>new.action",
    ]:
        assert marker in SQL


def test_auto_freeze_requires_sealed_source_and_identity():
    assert "coalesce(new.run_source,'')<>'render_cron'" in SQL
    assert "frozen_scientific_fingerprint_sha256" in SQL
    assert "baseline_git_commit" in SQL
    assert "baseline_config_sha256" in SQL


def test_auto_freeze_is_unique_and_append_only_compatible():
    assert "exec-auto-" in SQL
    assert "on conflict(decision_observation_id) do nothing" in SQL


def test_activation_seed_is_not_historical_backfill():
    assert "'current_run_activation_seed'" in SQL
    assert "'historical_backfill',false" in SQL
    assert "'prospective_from_frozen_at_utc',true" in SQL
    assert "order by x.collected_at_utc desc" in SQL
    assert "limit 1" in SQL


def test_no_trade_or_exchange_write_authority_added():
    for forbidden in [
        "trade_permission,true",
        "production_promotion_permitted,true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "alpha_hunter_bind_execution_fill",
    ]:
        assert forbidden not in SQL


def test_private_trigger_function_is_not_api_exposed():
    assert "security definer" in SQL
    assert "set search_path=''" in SQL
    assert (
        "revoke all on function "
        "private.alpha_hunter_auto_freeze_execution_decision_v02()"
    ) in SQL
    assert "from public,anon,authenticated,service_role" in SQL


def test_plpgsql_record_assignment_is_valid():
    assert "into sp,a" not in SQL
    assert "select spec.* into sp" in SQL
