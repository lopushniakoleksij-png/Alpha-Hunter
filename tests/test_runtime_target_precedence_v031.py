from pathlib import Path

PATH = Path(
    "ops/sql/production_deployment_runtime_target_precedence_v031.sql"
)
SQL = PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_fingerprinted_target_has_priority_over_manual_baseline():
    assert "runtime_fingerprint_sha256 is not null" in LOWER
    assert "order by" in LOWER
    assert (
        "(r.runtime_fingerprint_sha256 is not null) desc"
        in LOWER
    )
    fingerprint_pos = LOWER.index(
        "(r.runtime_fingerprint_sha256 is not null) desc"
    )
    recorded_pos = LOWER.index("r.recorded_at_utc desc", fingerprint_pos)
    assert fingerprint_pos < recorded_pos


def test_runtime_sources_remain_limited():
    assert (
        "where r.source in ('github_runtime_push','manual_runtime_target')"
        in LOWER
    )


def test_public_deployment_view_schema_remains_compatible():
    assert (
        "create or replace view public.alpha_hunter_production_deployment_drift_v01"
        in LOWER
    )
    segment = LOWER.split(
        "create or replace view public.alpha_hunter_production_deployment_drift_v01",
        1,
    )[1]
    public_select = segment.split(
        "from public.alpha_hunter_production_deployment_runtime_status_v03",
        1,
    )[0]
    assert "target_runtime_fingerprint_sha256" not in public_select
    assert "live_runtime_fingerprint_sha256" not in public_select


def test_no_deploy_or_trade_authority_added():
    for forbidden in [
        "deploy hook",
        "render api",
        "place_order",
        "cancel_order",
        "modify_order",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER
