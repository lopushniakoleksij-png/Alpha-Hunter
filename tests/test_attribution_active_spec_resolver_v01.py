from pathlib import Path

SQL = Path("ops/sql/attribution_active_spec_resolver_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_active_spec_does_not_depend_on_stale_test_engine():
    assert "alpha_hunter_test_engine_latest_v01" not in SQL
    assert "alpha_hunter_profitability_validation_status_v01" in SQL
    assert "profitability_test_status not like 'invalidated_%'" in SQL
    assert "order by v.started_at_utc desc" in SQL


def test_view_remains_read_only_and_service_role_only():
    assert "security_invoker=true" in SQL
    assert "security_barrier=true" in SQL
    assert "from public,anon,authenticated,service_role" in SQL
    assert "to service_role" in SQL


def test_no_execution_authority():
    for marker in [
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]:
        assert marker in SQL
    for forbidden in [
        "insert into public.alpha_hunter_execution_fill_bindings_v01",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]:
        assert forbidden not in SQL
