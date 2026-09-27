from pathlib import Path

SQL_PATH = Path("ops/sql/execution_attribution_ledger_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_attribution_ledger_is_outside_v14_scientific_fingerprint():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert SQL_PATH.name not in [p.name for p in Path(".").glob("*.sql")]


def test_attribution_requires_pretrade_freeze_and_exact_fill_binding():
    for marker in [
        "alpha_hunter_execution_decision_freezes_v01",
        "alpha_hunter_execution_fill_bindings_v01",
        "decision_observation_id",
        "explicit_user_confirmation",
        "exact_fill_id_only",
        "retrospective_attribution_permitted",
        "fill_time_utc<d.frozen_at_utc",
        "retrospective attribution prohibited",
    ]:
        assert marker in LOWER


def test_symbol_time_proximity_is_explicitly_prohibited():
    assert "symbol_time_proximity_attribution_permitted" in LOWER
    assert "'symbol_time_proximity_attribution_permitted',false" in LOWER


def test_verified_attribution_requires_order_and_fill_integrity():
    required = [
        "tr.complete=true",
        "tr.schema_validated=true",
        "o.order_evidence_id is not null",
        "o.order_identity_sha256 is not null",
        "o.order_created_at_utc>=d.frozen_at_utc",
        "f.fill_time_utc>=o.order_created_at_utc",
        "o.origin_consistent=true",
        "verified_alpha_hunter_execution",
    ]
    for marker in required:
        assert marker in LOWER


def test_binding_only_accepts_opening_fill_with_matching_direction():
    assert "only an opening fill may bind" in LOWER
    assert "d.direction='long' and upper(coalesce(f.side,''))='buy'" in LOWER
    assert "d.direction='short' and upper(coalesce(f.side,''))='sell'" in LOWER


def test_tables_are_append_only_rls_and_service_role_only():
    assert LOWER.count("enable row level security") >= 2
    assert LOWER.count("alpha_hunter_block_append_only_mutation") >= 2
    assert "grant select,insert on table public.alpha_hunter_execution_decision_freezes_v01" in LOWER
    assert "grant select,insert on table public.alpha_hunter_execution_fill_bindings_v01" in LOWER
    assert "to service_role" in LOWER
    assert "from public,anon,authenticated,service_role" in LOWER


def test_views_use_security_invoker():
    assert LOWER.count("security_invoker=true") >= 3


def test_no_exchange_write_authority_is_added():
    forbidden = [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "transfer",
        "withdraw",
        "trade_permission=true",
        "trade_permission = true",
        "production_promotion_permitted=true",
        "production_promotion_permitted = true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_raw_order_and_trade_ids_are_not_added_to_attribution_tables():
    decision_segment = LOWER.split(
        "create table if not exists public.alpha_hunter_execution_decision_freezes_v01",
        1,
    )[1].split("create table if not exists public.alpha_hunter_execution_fill_bindings_v01", 1)[0]
    binding_segment = LOWER.split(
        "create table if not exists public.alpha_hunter_execution_fill_bindings_v01",
        1,
    )[1].split("alter table public.alpha_hunter_execution_decision_freezes_v01", 1)[0]
    for segment in (decision_segment, binding_segment):
        assert "order_id " not in segment
        assert "trade_id " not in segment


def test_realistic_net_r_stays_blocked():
    assert "false as cost_model_validated" in LOWER
    assert "false as realistic_net_r_claim_permitted" in LOWER
    assert "first_verified_execution_captured_more_sample_required" in LOWER
