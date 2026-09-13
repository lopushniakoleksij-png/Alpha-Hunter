from pathlib import Path

SQL = Path('geometry_diagnostics_v01.sql').read_text()


def test_shadow_only_geometry_diagnostics_contract():
    required = [
        "alpha_hunter_geometry_diagnostics",
        "alpha_hunter_capture_geometry_diagnostics",
        "shadow_only boolean not null default true check (shadow_only=true)",
        "trade_permission boolean not null default false check (trade_permission=false)",
        "research_geometry_is_not_execution_permission",
        "thresholds_invented",
        "alpha_hunter_block_append_only_mutation",
        "enable row level security",
        "revoke all on table public.alpha_hunter_geometry_diagnostics from public, anon, authenticated",
        "set search_path=''",
    ]
    for marker in required:
        assert marker in SQL


def test_diagnostics_do_not_add_execution_path():
    forbidden = [
        "production_execution_enabled=true",
        "trade_permission=true",
        "/api/v3/trade/place-order",
        "/api/v2/mix/order/place-order",
    ]
    for marker in forbidden:
        assert marker not in SQL


def test_research_geometry_is_direction_aware():
    assert "when s.direction='LONG' then s.support_price else s.resistance_price" in SQL
    assert "when s.direction='LONG' then s.resistance_price else s.support_price" in SQL
    assert "RESEARCH_SR_GEOMETRY_RECOVERABLE" in SQL
