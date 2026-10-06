from pathlib import Path


SQL = Path("ops/sql/r10_non_scientific_descendant_activation_bridge_v01.sql").read_text(
    encoding="utf-8"
)


def test_r10_descendant_bridge_preserves_frozen_science_and_authority():
    assert "alpha_hunter_r10_runtime_commit_approvals_v01" in SQL
    assert "v.git_commit=r.frozen_git_commit" in SQL
    assert "ca.approved_runtime_git_commit=v.git_commit" in SQL
    assert (
        "ca.scientific_fingerprint_sha256="
        "r.frozen_scientific_fingerprint_sha256"
    ) in SQL
    assert (
        "p.payload->'validation_identity'->>'git_commit','')<>v.git_commit"
        in SQL
    )
    assert "or not runtime_commit_approved" in SQL
    assert "if not runtime_commit_approved" in SQL
    assert "v.scientific_fingerprint_sha256" in SQL
    assert "<>r.frozen_scientific_fingerprint_sha256" in SQL
    assert "'runtime_git_commit',v.git_commit" in SQL
    assert "'frozen_git_commit',r.frozen_git_commit" in SQL
    assert "true,false,false,false,'NONE'" in SQL


def test_r10_descendant_bridge_keeps_atomic_profitability_clock():
    assert "alpha_hunter_profitability_cadence_contract_v01" in SQL
    assert "RENDER_CRON_ALIGNED_00_20_40" in SQL
    assert "alpha_hunter_profitability_test_activations_v01" in SQL
    assert "'identity_mode','SCIENTIFIC_FINGERPRINT'" in SQL
    assert "'baseline_observed_git_commit'" in SQL
    assert "'historical_rows_reused',false" in SQL
