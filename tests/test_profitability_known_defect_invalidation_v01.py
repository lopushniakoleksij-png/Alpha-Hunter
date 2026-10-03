from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "ops/sql/profitability_known_defect_invalidation_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_known_defect_invalidation_sql_parses():
    assert parse_sql(SQL)


def test_r7_invalidation_is_append_only_and_explicit():
    assert "alpha_hunter_profitability_test_invalidations_v01" in LOWER
    assert "trg_ah_profitability_invalidations_append_only_v01" in LOWER
    assert "before update or delete" in LOWER
    assert "seaLED-arch-v14r7-fp-20m-20261003".lower() in LOWER
    assert "paper_lifecycle_integrity_defect" in LOWER
    assert "560.224" in LOWER
    assert "eigenusdt" in LOWER
    assert "ondousdt" in LOWER
    assert "pythusdt" in LOWER


def test_historical_evidence_is_not_mutated():
    forbidden = [
        "update public.alpha_hunter_paper_",
        "delete from public.alpha_hunter_paper_",
        "update public.alpha_hunter_profitability_test_specs_v01",
        "delete from public.alpha_hunter_profitability_test_specs_v01",
        "update public.alpha_hunter_profitability_test_activations_v01",
        "delete from public.alpha_hunter_profitability_test_activations_v01",
    ]
    for marker in forbidden:
        assert marker not in LOWER

    assert "'historical_evidence_mutated',false" in LOWER


def test_test_engine_fails_closed_for_invalidated_spec():
    required = [
        "alpha_hunter_refresh_test_engine_v05",
        "invalidated_by_known_production_defect",
        "scientific_test_invalidated_known_defect",
        "paper_lifecycle_integrity_defect",
        "scientific_cohort_valid',false",
        "final_profitability_claim_permitted',false",
        "not_proven",
    ]
    for marker in required:
        assert marker in LOWER


def test_test_engine_keeps_all_money_permissions_disabled():
    required = [
        "'live_money_claim_permitted',false",
        "'trade_permission',false",
        "'threshold_change_permitted',false",
        "'production_promotion_permitted',false",
        "'order_path','none'",
    ]
    for marker in required:
        assert marker in LOWER


def test_cron_moves_to_v05_refresh():
    assert "alpha-hunter-test-engine-db-refresh-v02" in LOWER
    assert "alpha_hunter_refresh_test_engine_v05()" in LOWER
