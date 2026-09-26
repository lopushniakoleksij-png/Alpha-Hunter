from pathlib import Path


SQL = Path("sealed_scientific_fingerprint_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_scientific_fingerprint_columns_are_versioned_and_optional_for_legacy():
    required = [
        "frozen_scientific_fingerprint_sha256",
        "baseline_scientific_fingerprint_sha256",
        "scientific_fingerprint_enabled",
        "scientific_fingerprint_sha256",
    ]
    for marker in required:
        assert marker in SQL

    assert "add column if not exists frozen_scientific_fingerprint_sha256 text" in LOWER
    assert "add column if not exists baseline_scientific_fingerprint_sha256 text" in LOWER


def test_activation_prefers_scientific_fingerprint_with_legacy_git_fallback():
    assert "v_spec.frozen_scientific_fingerprint_sha256 is not null" in SQL
    assert "v_spec.frozen_scientific_fingerprint_sha256 is null" in SQL
    assert "p.payload->'validation_identity'->>'git_commit'" in SQL
    assert "scientific_fingerprint_ok" in SQL


def test_drift_uses_scientific_fingerprint_for_new_specs():
    drift = LOWER.split("drift as (", 1)[1].split("),\necon as (", 1)[0]
    assert "scientific_fingerprint_sha256" in drift
    assert "frozen_scientific_fingerprint_sha256 is not null" in drift
    assert "frozen_scientific_fingerprint_sha256 is null" in drift
    assert "baseline_git_commit" in drift
    assert "baseline_config_sha256" in drift


def test_paper_economics_are_bound_to_same_scientific_identity():
    economics = LOWER.split(
        "create or replace view public.alpha_hunter_strategy_paper_economics_v01",
        1,
    )[1].split(
        "create or replace view public.alpha_hunter_profitability_validation_status_v01",
        1,
    )[0]
    assert economics.count("scientific_fingerprint_sha256") >= 4
    assert "first_observation_id" in economics
    assert "co.status='shadow_candidate'" in economics


def test_scientific_fingerprint_contract_never_grants_execution_authority():
    required = [
        "true as paper_only",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in LOWER

    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_activation_only_considers_newest_preregistered_spec():
    function_sql = LOWER.split(
        "create or replace function private.alpha_hunter_try_activate_profitability_test_v01()",
        1,
    )[1].split(
        "revoke all on function private.alpha_hunter_try_activate_profitability_test_v01()",
        1,
    )[0]
    selector = function_sql.split("for v_spec in", 1)[1].split("loop", 1)[0]
    assert "order by s.preregistered_at_utc desc" in selector
    assert "limit 1" in selector
    assert "'latest_spec_only',true" in function_sql
    assert "'selected_spec_id',v_spec.spec_id" in function_sql
