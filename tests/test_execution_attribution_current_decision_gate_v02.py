from pathlib import Path

SOURCE_PATH = Path("ops/sql/execution_attribution_ledger_v01.sql")
MIGRATION_PATH = Path(
    "ops/sql/execution_attribution_current_decision_gate_v02.sql"
)
SOURCE = SOURCE_PATH.read_text(encoding="utf-8").lower()
MIGRATION = MIGRATION_PATH.read_text(encoding="utf-8").lower()


def test_freeze_candidates_bind_to_latest_canonical_run():
    assert "latest_canonical as" in SOURCE
    assert "q.run_id=lc.run_id" in SOURCE.replace(" ", "")
    assert "order by s.collected_at_utc desc" in SOURCE


def test_freeze_candidates_have_cadence_freshness_gate():
    assert "maximum_interval_minutes" in SOURCE
    assert "coalesce(c.maximum_interval_minutes,35)" in SOURCE.replace(" ", "")
    assert "interval '1 minute'" in SOURCE
    assert "q.observed_at_utc<=clock_timestamp()" in SOURCE.replace(" ", "")


def test_historical_quotes_are_preserved_not_deleted():
    for forbidden in [
        "delete from public.alpha_hunter_shadow_decision_quotes_v01",
        "update public.alpha_hunter_shadow_decision_quotes_v01",
        "truncate public.alpha_hunter_shadow_decision_quotes_v01",
    ]:
        assert forbidden not in MIGRATION


def test_migration_replaces_only_candidate_view_contract():
    assert (
        "create or replace view public.alpha_hunter_execution_attribution_candidates_v01"
        in MIGRATION
    )
    assert "create or replace function private.alpha_hunter_freeze_execution_decision_v01" not in MIGRATION


def test_existing_quote_and_geometry_gates_remain():
    for marker in [
        "q.quote_complete=true",
        "q.prospective_capture=true",
        "q.action in ('execute_now','place_limit')",
        "s.geometry_valid=true",
        "s.direction=q.direction",
        "s.action=q.action",
    ]:
        assert marker in SOURCE


def test_no_trade_or_order_authority_added():
    for forbidden in [
        "trade_permission=true",
        "trade_permission = true",
        "production_promotion_permitted=true",
        "production_promotion_permitted = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer",
    ]:
        assert forbidden not in MIGRATION
    assert "false as trade_permission" in MIGRATION
    assert "false as production_promotion_permitted" in MIGRATION
    assert "'none'::text as order_path" in MIGRATION
