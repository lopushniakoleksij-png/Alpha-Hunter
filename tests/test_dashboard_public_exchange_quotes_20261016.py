"""Read-only public exchange quotes during a sealed test's Supabase outage.

Never mark external ticker data as canonical scans, paper evidence or trade permission.
"""
import time
import requests
import pytest

import app as dashboard


@pytest.fixture(autouse=True)
def empty_market_cache(monkeypatch):
    monkeypatch.setattr(dashboard, "_PUBLIC_MARKET_CACHE_UNTIL", 0.0)
    monkeypatch.setattr(dashboard, "_PUBLIC_MARKET_CACHE", None)


def exchange_payload(now_ms, *, stale=False, incomplete=False, invalid=False):
    quotes = []
    for symbol in dashboard.PUBLIC_MARKET_SYMBOLS:
        quotes.append({
            "symbol": symbol,
            "category": "USDT-FUTURES",
            "lastPrice": "-10" if invalid and symbol == "BTCUSDT" else "100.25",
            "ts": str(now_ms - 180_000 if stale else now_ms - 1500),
        })
    if incomplete:
        quotes.pop()
    return {"code": "00000", "requestTime": now_ms, "data": quotes}


def install_feed(monkeypatch, payload):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    calls = []

    def get(url, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse()

    monkeypatch.setattr(dashboard.requests, "get", get)
    return calls


def test_fresh_quotes_display_separately_and_never_authorize_trading(monkeypatch):
    now_ms = int(time.time() * 1000)
    calls = install_feed(monkeypatch, exchange_payload(now_ms))
    response = dashboard.app.test_client().get("/api/public-market")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["quotes"]) == 4
    assert data["canonical_evidence"] is False
    assert data["paper_test_evidence"] is False
    assert data["trade_permission"] is False
    assert data["market_status"] == "PUBLIC_QUOTES_ONLY"
    assert response.headers["Cache-Control"] == "no-store"
    assert len(calls) == 1
    assert calls[0][1] == {"category": "USDT-FUTURES"}
    assert calls[0][2] == (1.5, 3.0)
    cached = dashboard.app.test_client().get("/api/public-market")
    assert cached.status_code == 200
    assert len(calls) == 1


@pytest.mark.parametrize("payload_kwargs", [
    {"stale": True}, {"incomplete": True}, {"invalid": True},
])
def test_bad_market_evidence_fails_closed_without_prices(monkeypatch, payload_kwargs):
    install_feed(monkeypatch, exchange_payload(int(time.time() * 1000), **payload_kwargs))
    resp = dashboard.app.test_client().get("/api/public-market")
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["error"] == "public_market_unavailable"
    assert data["canonical_evidence"] is False
    assert data["trade_permission"] is False
    assert "quotes" not in data


def test_upstream_timeout_fails_closed_with_short_bounded_attempt(monkeypatch):
    calls = []

    def get(*args, **kwargs):
        calls.append(kwargs)
        raise requests.ReadTimeout("synthetic Bitget outage")

    monkeypatch.setattr(dashboard.requests, "get", get)
    resp = dashboard.app.test_client().get("/api/public-market")
    assert resp.status_code == 503
    assert calls == [{"params": {"category": "USDT-FUTURES"}, "timeout": (1.5, 3.0)}]
    assert resp.get_json()["paper_test_evidence"] is False
    assert dashboard.app.test_client().get("/api/public-market").status_code == 503
    assert len(calls) == 1


def test_recovery_page_keeps_canonical_warning_and_displays_source_separately(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "isolated-service")
    monkeypatch.setattr(
        dashboard,
        "_DASHBOARD_READ_UNAVAILABLE_UNTIL",
        dashboard.time.monotonic() + 60.0,
    )
    response = dashboard.app.test_client().get("/")
    body = response.get_data(as_text=True)
    assert response.status_code == 503
    assert "LIVE DATA TEMPORARILY UNAVAILABLE" in body
    assert "Bitget public market prices" in body
    assert "Not Alpha Hunter verified signals" in body
    assert "/api/public-market" in body
    assert "Trading actions are intentionally hidden" in body
