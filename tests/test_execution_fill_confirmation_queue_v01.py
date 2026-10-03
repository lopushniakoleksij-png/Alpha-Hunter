import base64
from pathlib import Path

import app as dashboard_app
from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "ops/sql/execution_fill_confirmation_queue_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def auth_header():
    token = base64.b64encode(b"operator:secret").decode("ascii")
    return {"Authorization": f"Basic {token}"}


def configure_operator(monkeypatch):
    monkeypatch.setattr(dashboard_app, "OPERATOR_USER", "operator")
    monkeypatch.setattr(dashboard_app, "OPERATOR_PASSWORD", "secret")


def candidate(status="UNIQUE_EVIDENCE_COMPLETE_MATCH"):
    return {
        "execution_event_id": "exec-candidate-1",
        "spec_id": "SEALED-R7",
        "symbol": "QNTUSDT",
        "strategy_id": "S3",
        "direction": "LONG",
        "action": "PLACE_LIMIT",
        "frozen_at_utc": "2026-10-03T03:00:00+00:00",
        "planned_entry_price": 250.0,
        "reward_risk": 5.5,
        "best_bid": 249.9,
        "best_ask": 250.0,
        "entry_cross_price": 250.0,
        "fill_evidence_id": "fill-candidate-1",
        "fill_time_utc": "2026-10-03T03:02:00+00:00",
        "trade_id": "trade-exact-1",
        "order_id": "order-exact-1",
        "side": "BUY",
        "price": 250.1,
        "base_volume": 1.0,
        "quote_volume": 250.1,
        "fee_amount": -0.15,
        "fee_coin": "USDT",
        "order_type": "LIMIT",
        "order_created_at_utc": "2026-10-03T03:01:00+00:00",
        "freeze_to_order_seconds": 60.0,
        "order_to_fill_seconds": 60.0,
        "candidate_adverse_arrival_to_fill_bps": 4.0,
        "realized_fee_bps": 6.0,
        "fill_candidate_count": 1,
        "event_candidate_count": 1,
        "candidate_status": status,
        "explicit_user_confirmation_required": True,
        "automatic_binding_permitted": False,
        "attribution_claim_permitted": False,
    }


def test_confirmation_queue_sql_parses():
    assert parse_sql(SQL)


def test_confirmation_queue_requires_complete_exact_evidence():
    required = [
        "upper(coalesce(f.trade_side,''))='open'",
        "tr.complete=true",
        "tr.schema_validated=true",
        "o.order_identity_sha256 is not null",
        "o.order_created_at_utc is not null",
        "o.origin_consistent=true",
        "f.cost_fields_complete=true",
        "o.order_created_at_utc>=d.frozen_at_utc",
        "f.fill_time_utc>=o.order_created_at_utc",
    ]
    for marker in required:
        assert marker in LOWER


def test_confirmation_queue_enforces_sealed_freshness_window():
    assert "maximum_interval_minutes" in LOWER
    assert "make_interval(mins=>a.maximum_interval_minutes)" in LOWER
    assert "make_interval(mins=>v_max_interval_minutes)" in LOWER
    assert "stale attribution rejected" in LOWER


def test_confirmation_queue_never_auto_binds_or_claims_attribution():
    required = [
        "false as automatic_binding_permitted",
        "true as explicit_user_confirmation_required",
        "false as attribution_claim_permitted",
        "false as slippage_claim_permitted",
        "false as cost_model_activation_permitted",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in LOWER

    for forbidden in [
        "place_order(",
        "cancel_order(",
        "modify_order(",
        "set_leverage(",
        "automatic_binding_permitted,true",
    ]:
        assert forbidden not in LOWER


def test_confirmation_queue_exposes_ambiguity_instead_of_resolving_it():
    assert "fill_candidate_count" in LOWER
    assert "event_candidate_count" in LOWER
    assert "unique_evidence_complete_match" in LOWER
    assert "ambiguous_evidence_complete_match" in LOWER
    assert "row_number() over" in LOWER


def test_binding_function_requires_current_candidate_pair_and_explicit_confirmation():
    assert "p_explicit_user_confirmation is not true" in LOWER
    assert "alpha_hunter_execution_fill_confirmation_candidates_v01 c" in LOWER
    assert "c.execution_event_id=d.execution_event_id" in LOWER
    assert "c.fill_evidence_id=f.fill_evidence_id" in LOWER
    assert "candidate_queue_gate_passed',true" in LOWER
    assert "automatic_binding_permitted', false" in LOWER


def test_confirmation_queue_page_requires_operator_auth(monkeypatch):
    configure_operator(monkeypatch)
    client = dashboard_app.app.test_client()

    response = client.get("/execution-confirmations")

    assert response.status_code == 401


def test_confirmation_queue_page_shows_exact_candidate_and_no_auto_binding(monkeypatch):
    configure_operator(monkeypatch)
    monkeypatch.setattr(
        dashboard_app,
        "pending_execution_fill_confirmations",
        lambda: [candidate()],
    )
    monkeypatch.setattr(
        dashboard_app,
        "execution_fill_confirmation_status",
        lambda: {
            "candidate_pair_count": 1,
            "unique_candidate_pairs": 1,
            "ambiguous_candidate_pairs": 0,
            "verified_alpha_hunter_executions": 0,
        },
    )

    client = dashboard_app.app.test_client()
    response = client.get(
        "/execution-confirmations",
        headers=auth_header(),
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "trade-exact-1" in body
    assert "order-exact-1" in body
    assert "UNIQUE_EVIDENCE_COMPLETE_MATCH" in body
    assert "REVIEW EXACT FILL" in body
    assert "A candidate is not attribution" in body
    assert "automatic_binding_permitted=false" in body
    assert "attribution_claim_permitted=false" in body


def test_confirmation_queue_page_exposes_ambiguity(monkeypatch):
    configure_operator(monkeypatch)
    row = candidate("AMBIGUOUS_EVIDENCE_COMPLETE_MATCH")
    row["fill_candidate_count"] = 2
    row["event_candidate_count"] = 3

    monkeypatch.setattr(
        dashboard_app,
        "pending_execution_fill_confirmations",
        lambda: [row],
    )
    monkeypatch.setattr(
        dashboard_app,
        "execution_fill_confirmation_status",
        lambda: {
            "candidate_pair_count": 1,
            "unique_candidate_pairs": 0,
            "ambiguous_candidate_pairs": 1,
            "verified_alpha_hunter_executions": 0,
        },
    )

    client = dashboard_app.app.test_client()
    response = client.get(
        "/execution-confirmations",
        headers=auth_header(),
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "AMBIGUOUS_EVIDENCE_COMPLETE_MATCH" in body
    assert "fill matches 2 frozen decisions" in body
    assert "event has 3 candidate fills" in body
