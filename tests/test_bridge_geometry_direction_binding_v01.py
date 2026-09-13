from pathlib import Path


SQL = Path("bridge_geometry_direction_binding_v01.sql").read_text()


def test_private_fail_closed_trigger_contract():
    lowered = SQL.lower()
    assert "private.alpha_hunter_enforce_bridge_geometry_direction" in SQL
    assert "security definer" in lowered
    assert "set search_path = ''" in lowered
    assert "before insert or update on public.alpha_hunter_big_mover_money_entry_shadow" in lowered
    assert "upper(new.scanner_direction) <> upper(new.direction)" in SQL


def test_mismatched_geometry_is_erased():
    for assignment in (
        "new.candidate_entry := null",
        "new.stop_price := null",
        "new.target_price := null",
        "new.execution_rr := null",
    ):
        assert assignment in SQL
    assert "EXECUTION_GEOMETRY_DIRECTION_MISMATCH" in SQL
    assert "EXECUTION_GEOMETRY_MISSING" in SQL
    assert "new.bridge_status := 'DATA_INSUFFICIENT'" in SQL


def test_blockers_are_idempotently_deduplicated():
    assert "jsonb_agg(distinct value)" in SQL


def test_research_geometry_cannot_be_promoted():
    assert "'research_geometry_promoted', false" in SQL
    assert "'geometry_source', 'SCANNER_EXECUTION_SETUP'" in SQL


def test_shadow_boundary_is_hard():
    lowered = SQL.lower()
    assert "new.shadow_only := true" in lowered
    assert "new.trade_permission := false" in lowered
    assert "trade_permission := true" not in lowered
    for forbidden in ("place-order", "place_order", "cancel-order", "cancel_order", "production_execution_enabled := true"):
        assert forbidden not in lowered


def test_privileged_function_is_not_publicly_callable():
    lowered = SQL.lower()
    assert "revoke all on function private.alpha_hunter_enforce_bridge_geometry_direction() from public, anon, authenticated" in lowered
    assert "grant execute on function private.alpha_hunter_enforce_bridge_geometry_direction() to service_role" in lowered
