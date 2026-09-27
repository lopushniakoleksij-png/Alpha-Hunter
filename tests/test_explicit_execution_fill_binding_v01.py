import base64
from pathlib import Path

import app as dashboard_app


EXECUTION_ID = "exec-test-123"
FILL_ID = "fill-test-456"


def auth_header():
    token = base64.b64encode(b"operator:secret").decode("ascii")
    return {"Authorization": f"Basic {token}"}


def configure_operator(monkeypatch):
    monkeypatch.setattr(dashboard_app, "OPERATOR_USER", "operator")
    monkeypatch.setattr(dashboard_app, "OPERATOR_PASSWORD", "secret")


def frozen():
    return {
        "execution_event_id": EXECUTION_ID,
        "symbol": "GRTUSDT",
        "direction": "SHORT",
        "action": "EXECUTE_NOW",
        "frozen_at_utc": "2026-09-27T20:30:00+00:00",
        "planned_entry_price": 0.03248,
        "entry_cross_price": 0.03246,
    }


def compatible_fill(ready=True):
    return {
        "fill_evidence_id": FILL_ID,
        "traceability_run_id": "trace-1",
        "fill_time_utc": "2026-09-27T20:31:00+00:00",
        "trade_id": "trade-123",
        "order_id": "order-456",
        "symbol": "GRTUSDT",
        "side": "SELL",
        "trade_side": "OPEN",
        "trade_scope": "TAKER",
        "price": 0.03245,
        "base_volume": 100.0,
        "quote_volume": 3.245,
        "fee_amount": -0.001,
        "fee_coin": "USDT",
        "_trace_complete": ready,
        "_order": {
            "order_evidence_id": "order-evidence-1" if ready else None,
            "order_identity_sha256": "abc" if ready else None,
            "order_created_at_utc": (
                "2026-09-27T20:30:30+00:00" if ready else None
            ),
            "origin_consistent": True if ready else None,
        },
        "_binding_ready": ready,
    }


def test_binding_page_requires_operator_auth(monkeypatch):
    configure_operator(monkeypatch)
    client = dashboard_app.app.test_client()

    response = client.get(f"/execution-bind/{EXECUTION_ID}")

    assert response.status_code == 401


def test_binding_page_shows_exact_ids_and_no_auto_attribution(monkeypatch):
    configure_operator(monkeypatch)
    monkeypatch.setattr(
        dashboard_app,
        "execution_freeze_by_id",
        lambda execution_id: frozen() if execution_id == EXECUTION_ID else None,
    )
    monkeypatch.setattr(
        dashboard_app,
        "execution_binding_by_event",
        lambda execution_id: None,
    )
    monkeypatch.setattr(
        dashboard_app,
        "compatible_execution_fills",
        lambda row: [compatible_fill(True)],
    )

    client = dashboard_app.app.test_client()
    response = client.get(
        f"/execution-bind/{EXECUTION_ID}",
        headers=auth_header(),
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "trade-123" in body
    assert "order-456" in body
    assert "I CONFIRM THIS EXACT BITGET FILL" in body
    assert "Compatibility filtering is not attribution" in body
    assert "trade_permission=false" in body
    assert "order_path=NONE" in body
    assert response.headers["Cache-Control"] == "no-store"


def test_binding_page_disables_incomplete_order_evidence(monkeypatch):
    configure_operator(monkeypatch)
    monkeypatch.setattr(dashboard_app, "execution_freeze_by_id", lambda _id: frozen())
    monkeypatch.setattr(dashboard_app, "execution_binding_by_event", lambda _id: None)
    monkeypatch.setattr(
        dashboard_app,
        "compatible_execution_fills",
        lambda row: [compatible_fill(False)],
    )

    client = dashboard_app.app.test_client()
    response = client.get(
        f"/execution-bind/{EXECUTION_ID}",
        headers=auth_header(),
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Not binding-ready yet" in body
    assert "I CONFIRM THIS EXACT BITGET FILL" not in body


def test_binding_api_requires_exact_confirmation(monkeypatch):
    configure_operator(monkeypatch)
    client = dashboard_app.app.test_client()

    response = client.post(
        f"/api/execution-bind/{EXECUTION_ID}/{FILL_ID}",
        headers=auth_header(),
        json={
            "execution_event_id": EXECUTION_ID,
            "fill_evidence_id": FILL_ID,
            "explicit_user_confirmation": True,
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "explicit_exact_fill_confirmation_required"


def test_binding_api_refuses_fill_not_ready_and_never_substitutes(monkeypatch):
    configure_operator(monkeypatch)
    monkeypatch.setattr(dashboard_app, "execution_freeze_by_id", lambda _id: frozen())
    monkeypatch.setattr(
        dashboard_app,
        "compatible_execution_fills",
        lambda row: [compatible_fill(False)],
    )

    def forbidden(*_args):
        raise AssertionError("binding RPC must not run for non-ready fill")

    monkeypatch.setattr(dashboard_app, "bind_execution_fill", forbidden)

    headers = auth_header()
    headers[dashboard_app.EXECUTION_BIND_CONFIRM_HEADER] = (
        f"{EXECUTION_ID}:{FILL_ID}"
    )

    client = dashboard_app.app.test_client()
    response = client.post(
        f"/api/execution-bind/{EXECUTION_ID}/{FILL_ID}",
        headers=headers,
        json={
            "execution_event_id": EXECUTION_ID,
            "fill_evidence_id": FILL_ID,
            "explicit_user_confirmation": True,
        },
    )
    payload = response.get_json()

    assert response.status_code == 409
    assert payload["error"] == "fill_not_binding_ready"
    assert payload["trade_permission"] is False
    assert payload["order_path"] == "NONE"


def test_binding_api_binds_only_exact_confirmed_pair(monkeypatch):
    configure_operator(monkeypatch)
    monkeypatch.setattr(dashboard_app, "execution_freeze_by_id", lambda _id: frozen())
    monkeypatch.setattr(
        dashboard_app,
        "compatible_execution_fills",
        lambda row: [compatible_fill(True)],
    )
    calls = []

    def bind(execution_id, fill_id):
        calls.append((execution_id, fill_id))
        return {
            "binding_id": "bind-test",
            "execution_event_id": execution_id,
            "fill_evidence_id": fill_id,
        }

    monkeypatch.setattr(dashboard_app, "bind_execution_fill", bind)

    headers = auth_header()
    headers[dashboard_app.EXECUTION_BIND_CONFIRM_HEADER] = (
        f"{EXECUTION_ID}:{FILL_ID}"
    )

    client = dashboard_app.app.test_client()
    response = client.post(
        f"/api/execution-bind/{EXECUTION_ID}/{FILL_ID}",
        headers=headers,
        json={
            "execution_event_id": EXECUTION_ID,
            "fill_evidence_id": FILL_ID,
            "explicit_user_confirmation": True,
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert calls == [(EXECUTION_ID, FILL_ID)]
    assert payload["binding_id"] == "bind-test"
    assert payload["trade_permission"] is False
    assert payload["production_promotion_permitted"] is False
    assert payload["order_path"] == "NONE"


def test_sql_binding_gate_enforces_prospective_exact_evidence():
    sql = Path("ops/sql/explicit_execution_fill_binding_v01.sql").read_text()
    lower = sql.lower()

    assert "p_explicit_user_confirmation is not true" in lower
    assert "f.fill_time_utc < d.frozen_at_utc" in lower
    assert "upper(f.symbol) <> upper(d.symbol)" in lower
    assert "upper(coalesce(f.trade_side, '')) <> 'open'" in lower
    assert "tr.complete is not true" in lower
    assert "tr.schema_validated is not true" in lower
    assert "o.order_identity_sha256 is null" in lower
    assert "o.order_created_at_utc < d.frozen_at_utc" in lower
    assert "o.origin_consistent is not true" in lower
    assert "'user_explicit_exact_fill'" in lower
    assert "'symbol_time_proximity_attribution_permitted', false" in lower
    assert "'automatic_binding_permitted', false" in lower
    assert "security invoker" in lower
    assert "to service_role" in lower
    assert "trade_permission" in lower
    assert "'none'" in lower
