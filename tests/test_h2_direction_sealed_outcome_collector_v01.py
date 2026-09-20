from pathlib import Path

CAPTURE = Path("h2_direction_architecture_capture_v01.sql").read_text(encoding="utf-8")
PREREG1 = Path("h2_direction_sealed_evaluator_prereg_v01.sql").read_text(encoding="utf-8")
PREREG2 = Path("h2_direction_sealed_evaluator_prereg_v02.sql").read_text(encoding="utf-8")
COLLECTOR = Path("h2_direction_sealed_outcome_collector_v01.sql").read_text(encoding="utf-8")
LOWER = COLLECTOR.lower()


def test_h2_service_role_has_no_direct_write_grants():
    assert "grant select,insert on table public.alpha_hunter_h2_direction" not in CAPTURE.lower()
    assert "from public,anon,authenticated,service_role" in CAPTURE
    assert "from public,anon,authenticated,service_role" in PREREG1
    assert "from public,anon,authenticated,service_role" in PREREG2
    assert "grant select on table public.alpha_hunter_h2_direction_captures_v01" in CAPTURE.lower()


def test_v02_prereg_is_idempotent_after_exact_registration():
    assert "and not exists(" in PREREG2
    assert "where evaluator_spec_id=v_id" in PREREG2
    assert "cannot supersede after H2 outcome table creation" in PREREG2


def test_sealed_outcomes_are_not_service_role_readable():
    assert "revoke all on public.alpha_hunter_h2_direction_outcomes_sealed_v01" in COLLECTOR
    assert "from public,anon,authenticated,service_role" in COLLECTOR
    assert "grant select on public.alpha_hunter_h2_direction_outcomes_sealed_v01" not in COLLECTOR.lower()
    assert "grant select on public.alpha_hunter_h2_direction_sealed_failures_v01" not in COLLECTOR.lower()


def test_status_surface_is_service_role_select_only():
    assert "revoke all on public.alpha_hunter_h2_direction_sealed_collection_status_v01" in COLLECTOR
    assert "grant select on public.alpha_hunter_h2_direction_sealed_collection_status_v01" in COLLECTOR
    assert "primary_results_exposed boolean not null default false" in COLLECTOR
    assert "outcome_access_permitted boolean not null default false" in COLLECTOR


def test_exact_1m_two_page_collection_is_frozen():
    required = [
        "expected_minute_count=1440",
        "observed_minute_count=1440",
        "missing_minute_count=0",
        "interval=1m",
        "limit=1000",
        "interval '12 hours'-interval '1 minute'",
        "v_page2_start-interval '1 minute'",
        "extensions.urlencode(r.symbol::varchar)",
        "INCOMPLETE_1M_COVERAGE",
    ]
    for marker in required:
        assert marker in COLLECTOR


def test_collector_waits_for_full_24h_horizon():
    assert "h2_anchor_at_utc+interval '24 hours'+interval '5 minutes'" in COLLECTOR
    assert "WAITING_FOR_FIRST_24H_HORIZON" in COLLECTOR


def test_cost_adjusted_primary_remains_withheld():
    required = [
        "cost_model_applied=false",
        "SEALED_PRE_COST_PATH_ONLY_COST_MODEL_REQUIRED_AT_FREEZE",
        "h2_realistic_net_r is null",
        "legacy_realistic_net_r is null",
        "realistic_net_r_delta is null",
        "'cost_model_applied',false",
    ]
    for marker in required:
        assert marker in COLLECTOR


def test_collector_has_no_trade_or_promotion_authority():
    forbidden = [
        "trade_permission=true",
        "production_promotion_permitted=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER
    assert "'order_path','NONE'" in COLLECTOR
