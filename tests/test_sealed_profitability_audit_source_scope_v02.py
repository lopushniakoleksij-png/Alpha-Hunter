from pathlib import Path


SQL = Path("sealed_profitability_audit_source_scope_v02.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_cadence_ignores_foreign_scanner_rows():
    assert "alpha_hunter_profitability_cadence_integrity_v01" in SQL
    assert "c.required_run_source" in SQL
    assert "payload->'validation_identity'->>'run_source'" in SQL


def test_sample_integrity_uses_source_scoped_first_observations():
    required = [
        "source_episodes as (",
        "fo.observation_id=e.first_observation_id",
        "p.run_id=fo.run_id",
        "=s.required_run_source",
    ]
    for marker in required:
        assert marker in LOWER


def test_candidate_audit_requires_source_scoped_run_id():
    assert "p.run_id=o.run_id" in LOWER
    assert "o.observation_id is null or p.run_id is not null" in LOWER


def test_audits_remain_non_authoritative():
    required = [
        "true as audit_only",
        "true as paper_only",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in LOWER
