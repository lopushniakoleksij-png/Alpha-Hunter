from pathlib import Path


SQL = Path("money_entry_calibration_cohort_guard_v01.sql").read_text()


def test_calibration_cohort_is_post_fix_and_direction_bound():
    assert "2026-09-13T16:56:10Z" in SQL
    assert "c.scanner_direction = c.direction" in SQL
    assert "geometry_source' = 'SCANNER_EXECUTION_SETUP'" in SQL
    assert "geometry_direction_bound" in SQL
    assert "research_geometry_promoted" in SQL


def test_calibration_cohort_preserves_shadow_boundary():
    assert "c.shadow_only is true" in SQL
    assert "c.trade_permission is false" in SQL
    assert "o.shadow_only is true" in SQL
    assert "o.trade_permission is false" in SQL
    assert "calibration_eligible" in SQL
    assert "SAFETY_BOUNDARY_VIOLATION" in SQL


def test_view_is_private_and_service_role_only():
    assert "private.alpha_hunter_money_entry_calibration_cohort_v01" in SQL
    assert "security_invoker = true" in SQL
    assert "revoke all" in SQL.lower()
    assert "from public, anon, authenticated" in SQL.lower()
    assert "grant select" in SQL.lower()
    assert "to service_role" in SQL.lower()
