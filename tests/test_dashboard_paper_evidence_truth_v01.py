from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
SQL = (
    ROOT / "ops/sql/paper_lifecycle_dashboard_truth_v01.sql"
).read_text(encoding="utf-8")


def test_paper_lifecycle_truth_view_is_read_only_and_safe():
    lower = SQL.lower()
    assert parse_sql(SQL)
    assert "alpha_hunter_paper_lifecycle_status_v05" in lower
    assert "alpha_hunter_paper_completed_trades_valid_v05" in lower
    assert "invalid_entry_geometry_pre_fix" in lower
    assert "grant select" in lower
    assert "trade_permission" in lower
    assert "production_promotion_permitted" in lower
    assert "place_order(" not in lower
    assert "cancel_order(" not in lower
    assert "modify_order(" not in lower


def test_dashboard_separates_sealed_sample_from_execution_lifecycle():
    assert "def latest_paper_lifecycle_status()" in APP
    assert "alpha_hunter_paper_lifecycle_status_v05" in APP
    assert "Sealed 24H sample" in APP
    assert "Clean lifecycle exits" in APP
    assert "Sealed 24H sample and execution lifecycle are separate evidence streams" in APP
    assert "valid_completed_trades" in APP
    assert "invalid_geometry_quarantined" in APP


def test_dashboard_payload_keeps_lifecycle_optional_for_recovery_compatibility():
    assert "paper_lifecycle: dict[str, Any] | None = None" in APP
    assert '"paper_lifecycle": paper_lifecycle or {}' in APP
