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
    assert "Current cohort completions" in APP
    assert "Historical lifecycle exits" in APP
    assert "Current cohort completions, historical lifecycle exits and 24H signal outcomes are separate evidence streams" in APP
    assert "valid_completed_trades" in APP
    assert "invalid_geometry_quarantined" in APP


def test_dashboard_payload_keeps_lifecycle_optional_for_recovery_compatibility():
    assert "paper_lifecycle: dict[str, Any] | None = None" in APP
    assert '"paper_lifecycle": paper_lifecycle or {}' in APP


def test_dashboard_surfaces_unresolved_entry_without_rewriting_scientific_verdict(monkeypatch):
    import app
    original = {'operational_status':'PASS','verdict':'TEST_RUNNING','blockers':[], 'spec_id':'R8'}
    def read(table, params):
        return {
            'alpha_hunter_paper_profitability_status_v09':[],
            'alpha_hunter_test_engine_latest_v01':[original],
            'alpha_hunter_paper_repair_status_v01':[{'unresolved_entry_orders':1,'open_positions_over_24h':0}],
        }[table]
    monkeypatch.setattr(app,'supabase_get_rows',read)
    status=app.latest_test_engine_status()
    assert status['operational_status']=='REVIEW_REQUIRED'
    assert status['verdict']=='TEST_RUNNING'
    assert original['operational_status']=='PASS' and original['blockers']==[]
    assert 'UNRESOLVED_PAPER_ENTRY_REQUIRES_REPAIR' in status['blockers']


def test_missing_diagnostics_never_displays_system_pass(monkeypatch):
    import app
    def read(table,params):
        if table=='alpha_hunter_test_engine_latest_v01':
            return [{'operational_status':'PASS'}]
        raise RuntimeError('unavailable')
    monkeypatch.setattr(app,'supabase_get_rows',read)
    status=app.latest_test_engine_status()
    assert status['operational_status']=='REVIEW_REQUIRED'
    assert 'REPAIR_DIAGNOSTICS_UNAVAILABLE' in status['blockers']


def test_successor_status_takes_priority_over_historical_engine(monkeypatch):
    import app
    def read(table,params):
        assert table!='alpha_hunter_test_engine_latest_v01'
        if table=='alpha_hunter_paper_profitability_status_v09':
            return [{'spec_id':'R9','completed_paper_trades':2,'operational_status':'EVIDENCE_COLLECTION'}]
        return [{'unresolved_entry_orders':0,'open_positions_over_24h':0}]
    monkeypatch.setattr(app,'supabase_get_rows',read)
    assert app.latest_test_engine_status()['spec_id']=='R9'
