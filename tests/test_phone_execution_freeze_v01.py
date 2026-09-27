import base64
from pathlib import Path

import app as dashboard_app


DECISION_ID = "a" * 32


def auth_header():
    token = base64.b64encode(b"operator:secret").decode("ascii")
    return {"Authorization": f"Basic {token}"}


def candidate():
    return {
        "spec_id": "SEALED-ARCH-V14-FP-20M-20260926",
        "decision_observation_id": DECISION_ID,
        "strategy_instance_id": "strategy-1",
        "decision_run_id": "run-1",
        "symbol": "GRTUSDT",
        "strategy_id": "S6",
        "direction": "SHORT",
        "action": "EXECUTE_NOW",
        "decision_observed_at_utc": "2026-09-27T20:23:19+00:00",
        "decision_captured_at_utc": "2026-09-27T20:23:23+00:00",
        "reference_price": 0.03248,
        "planned_entry_price": 0.03248,
        "stop_price": 0.03376,
        "target_price": 0.02235,
        "reward_risk": 7.91,
        "best_bid": 0.03246,
        "best_ask": 0.03247,
        "midpoint": 0.032465,
        "entry_cross_price": 0.03246,
        "entry_cross_half_spread_bps": 1.54,
        "quote_complete": True,
        "prospective_capture": True,
        "run_source": "RENDER_CRON",
        "git_commit": "abc",
        "config_sha256": "def",
        "freeze_available": True,
        "trade_permission": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }


def configure_operator(monkeypatch):
    monkeypatch.setattr(dashboard_app, "OPERATOR_USER", "operator")
    monkeypatch.setattr(dashboard_app, "OPERATOR_PASSWORD", "secret")


def test_phone_freeze_fails_closed_without_operator_auth(monkeypatch):
    monkeypatch.setattr(dashboard_app, "OPERATOR_USER", "")
    monkeypatch.setattr(dashboard_app, "OPERATOR_PASSWORD", "")

    client = dashboard_app.app.test_client()
    response = client.get("/execution-freeze")

    assert response.status_code == 503
    assert response.get_json()["error"] == "operator_auth_not_configured"


def test_phone_freeze_requires_basic_auth(monkeypatch):
    configure_operator(monkeypatch)
    client = dashboard_app.app.test_client()

    response = client.get("/execution-freeze")

    assert response.status_code == 401
    assert "Basic" in response.headers["WWW-Authenticate"]


def test_phone_freeze_page_shows_only_current_candidate(monkeypatch):
    configure_operator(monkeypatch)
    monkeypatch.setattr(
        dashboard_app,
        "execution_freeze_candidates",
        lambda: [candidate()],
    )

    client = dashboard_app.app.test_client()
    response = client.get("/execution-freeze", headers=auth_header())

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "GRTUSDT" in body
    assert "FREEZE GRTUSDT DECISION" in body
    assert "trade_permission=false" in body
    assert "order_path=NONE" in body
    assert 'name="viewport"' in body
    assert response.headers["Cache-Control"] == "no-store"


def test_phone_freeze_requires_exact_explicit_confirmation(monkeypatch):
    configure_operator(monkeypatch)
    monkeypatch.setattr(
        dashboard_app,
        "execution_freeze_candidates",
        lambda: [candidate()],
    )

    client = dashboard_app.app.test_client()
    response = client.post(
        f"/api/execution-freeze/{DECISION_ID}",
        headers=auth_header(),
        json={"decision_observation_id": DECISION_ID},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "explicit_freeze_confirmation_required"


def test_phone_freeze_commits_exact_current_decision(monkeypatch):
    configure_operator(monkeypatch)
    monkeypatch.setattr(
        dashboard_app,
        "execution_freeze_candidates",
        lambda: [candidate()],
    )
    calls = []

    def freeze(decision_id):
        calls.append(decision_id)
        return {
            "execution_event_id": "exec-test",
            "decision_observation_id": decision_id,
            "symbol": "GRTUSDT",
            "direction": "SHORT",
            "action": "EXECUTE_NOW",
            "fill_binding_status": "WAITING_FOR_EXPLICIT_USER_CONFIRMED_FILL",
        }

    monkeypatch.setattr(dashboard_app, "freeze_execution_decision", freeze)

    headers = auth_header()
    headers[dashboard_app.EXECUTION_FREEZE_CONFIRM_HEADER] = DECISION_ID

    client = dashboard_app.app.test_client()
    response = client.post(
        f"/api/execution-freeze/{DECISION_ID}",
        headers=headers,
        json={"decision_observation_id": DECISION_ID},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert calls == [DECISION_ID]
    assert payload["execution_event_id"] == "exec-test"
    assert payload["trade_permission"] is False
    assert payload["production_promotion_permitted"] is False
    assert payload["order_path"] == "NONE"


def test_phone_freeze_expired_candidate_does_not_substitute(monkeypatch):
    configure_operator(monkeypatch)
    monkeypatch.setattr(
        dashboard_app,
        "execution_freeze_candidates",
        lambda: [],
    )

    def forbidden(_decision_id):
        raise AssertionError("freeze must not be called for an expired decision")

    monkeypatch.setattr(dashboard_app, "freeze_execution_decision", forbidden)

    headers = auth_header()
    headers[dashboard_app.EXECUTION_FREEZE_CONFIRM_HEADER] = DECISION_ID

    client = dashboard_app.app.test_client()
    response = client.post(
        f"/api/execution-freeze/{DECISION_ID}",
        headers=headers,
        json={"decision_observation_id": DECISION_ID},
    )
    payload = response.get_json()

    assert response.status_code == 409
    assert payload["error"] == "decision_expired"
    assert payload["trade_permission"] is False
    assert payload["order_path"] == "NONE"


def test_freeze_rpc_wrapper_is_service_role_only_and_invoker():
    sql = Path("ops/sql/phone_execution_freeze_api_v01.sql").read_text()

    assert "security invoker" in sql.lower()
    assert (
        "revoke all on function public.alpha_hunter_freeze_execution_decision_api_v01(text)"
        in sql.lower()
    )
    assert "from public, anon, authenticated" in sql.lower()
    assert "to service_role" in sql.lower()
    assert "private.alpha_hunter_freeze_execution_decision_v01" in sql
    assert "trade_permission=false" in sql
    assert "order_path=NONE" in sql
