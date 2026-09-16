from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, render_template_string, request

from alpha_hunter.services.statistics import StatisticsService
from performance_page import PERFORMANCE_PAGE


app = Flask(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SNAPSHOT_TABLE = os.getenv("ALPHA_HUNTER_SNAPSHOT_TABLE", "alpha_hunter_snapshots")

REFERENCE_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}

scan_lock = threading.Lock()
scan_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "status": "idle",
    "error": None,
    "return_code": None,
}


def load_runtime_config() -> dict[str, Any]:
    path = Path(__file__).resolve().with_name("config.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


RUNTIME_CONFIG = load_runtime_config()
MINIMUM_EXECUTION_RR = float(
    RUNTIME_CONFIG.get("candidate_quality", {}).get(
        "minimum_execution_reward_risk",
        RUNTIME_CONFIG.get("minimum_reward_risk", 5.0),
    )
)


def supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def latest_snapshot() -> dict[str, Any]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase environment variables are not configured")

    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/{SNAPSHOT_TABLE}",
        params={
            "select": "run_id,collected_at_utc,version,symbol_count,error_count,payload",
            "order": "collected_at_utc.desc",
            "limit": "1",
        },
        headers=supabase_headers(),
        timeout=15,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise RuntimeError("No Alpha Hunter snapshots found")
    return rows[0].get("payload") or {}


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def execution_checks(row: dict[str, Any]) -> dict[str, bool]:
    setup = row.get("execution_setup", {})
    raw = setup.get("checks", {})
    return {
        "direction": raw.get("direction_aligned") is True,
        "structure": raw.get("structure_valid") is True,
        "momentum": raw.get("momentum_confirmed") is True,
        "participation": raw.get("participation_confirmed") is True,
        "funding": raw.get("funding_not_extreme") is True,
        "integrity": raw.get("data_integrity_min_88") is True,
        "rr": raw.get("rr_minimum_met") is True,
    }


def required_entry_for_rr(
    stop: float,
    target: float,
    minimum_rr: float,
) -> float | None:
    if minimum_rr <= 0 or stop == target:
        return None
    return (target + minimum_rr * stop) / (minimum_rr + 1.0)


def build_money_action(row: dict[str, Any]) -> dict[str, Any]:
    """Turn scanner evidence into an explicit execution state.

    Discovery is never presented as an execution recommendation. A READY_NOW
    action requires the existing V7 execution permission. A RETEST_PLAN is only
    calculated when every core execution check except remaining R already passes,
    the current market phase is still an allowed pre/early phase, and a better
    price can restore the configured minimum R:R without crossing invalidation.
    """
    setup = row.get("execution_setup", {})
    checks = execution_checks(row)
    direction = str(setup.get("direction") or "").upper()
    current = safe_optional_float(row.get("last_price"))
    stop = safe_optional_float(setup.get("stop"))
    target = safe_optional_float(setup.get("target"))
    rr = safe_optional_float(setup.get("rr"))
    phase = str(row.get("market_phase") or "")
    timing = str(row.get("opportunity_timing") or "")
    rejections = list(row.get("rejection_reasons") or [])

    if bool(row.get("v7_trade_ready")):
        return {
            "status": "READY_NOW",
            "label": "EXECUTE NOW",
            "priority": 3,
            "direction": direction,
            "entry": current,
            "stop": stop,
            "target": target,
            "rr": rr,
            "minimum_rr": MINIMUM_EXECUTION_RR,
            "distance_pct": 0.0,
            "reason": "All existing V7 execution gates passed.",
            "cancel": "Cancel if structure invalidates or execution evidence changes before entry.",
        }

    core_without_rr = all(
        checks[name]
        for name in (
            "direction",
            "structure",
            "momentum",
            "participation",
            "funding",
            "integrity",
        )
    )

    allowed_retest_phase = phase in {
        "ACCUMULATION",
        "COMPRESSION",
        "RECOVERY",
        "IGNITION",
    }

    if (
        core_without_rr
        and not checks["rr"]
        and allowed_retest_phase
        and direction in {"LONG", "SHORT"}
        and current is not None
        and stop is not None
        and target is not None
    ):
        required = required_entry_for_rr(stop, target, MINIMUM_EXECUTION_RR)
        geometry_ok = False
        if required is not None:
            if direction == "LONG":
                geometry_ok = stop < required < current < target
            else:
                geometry_ok = target < current < required < stop

        if geometry_ok and required is not None:
            distance_pct = abs(required - current) / current * 100 if current else None
            return {
                "status": "RETEST_PLAN",
                "label": "BEST RETEST / LIMIT ZONE",
                "priority": 2,
                "direction": direction,
                "entry": required,
                "stop": stop,
                "target": target,
                "rr": MINIMUM_EXECUTION_RR,
                "minimum_rr": MINIMUM_EXECUTION_RR,
                "distance_pct": distance_pct,
                "reason": (
                    "Signal quality passes, but the current price is too late. "
                    "This is the nearest price that restores the configured minimum R:R."
                ),
                "cancel": (
                    "Do not use the zone if direction, momentum or participation has failed by retest, "
                    "or if structural invalidation is reached first."
                ),
            }

    failed = [name for name, passed in checks.items() if not passed]
    reason = "Blocked: " + ", ".join(failed) if failed else "No executable geometry"
    if rejections:
        reason += ". Quality: " + ", ".join(rejections)

    return {
        "status": "RESEARCH_ONLY",
        "label": "RESEARCH / WATCH",
        "priority": 0,
        "direction": direction or None,
        "entry": None,
        "stop": stop,
        "target": target,
        "rr": rr,
        "minimum_rr": MINIMUM_EXECUTION_RR,
        "distance_pct": None,
        "reason": reason,
        "cancel": None,
        "phase": phase,
        "timing": timing,
    }


def dashboard_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    symbols = [
        dict(row)
        for row in snapshot.get("symbols", [])
        if "error" not in row
    ]

    for row in symbols:
        intel = row.get("intelligence", {})
        setup = row.get("execution_setup", {})
        row["_score"] = safe_float(intel.get("huge_rr_score"))
        row["_confidence"] = safe_float(intel.get("confidence_estimate_pct"))
        row["_behaviour"] = safe_float(row.get("behaviour_score"))
        row["_rr"] = setup.get("rr")
        row["_direction"] = setup.get("direction")
        row["_trade"] = bool(row.get("v7_trade_ready"))
        row["_discovery"] = bool(row.get("discovery_permission"))
        row["_phase"] = row.get("market_phase", "—")
        row["_timing"] = row.get("opportunity_timing", "—")
        row["_reference"] = row.get("symbol") in REFERENCE_SYMBOLS
        row["_rejection"] = ", ".join(row.get("rejection_reasons") or [])
        row["_action"] = build_money_action(row)

    discovery_symbols = [row for row in symbols if not row["_reference"]]

    actionable = sorted(
        [row for row in discovery_symbols if row["_action"]["priority"] > 0],
        key=lambda row: (
            row["_action"]["priority"],
            -safe_float(row["_action"].get("distance_pct")),
            row["_behaviour"],
            row["_score"],
        ),
        reverse=True,
    )

    ranked_research = sorted(
        discovery_symbols,
        key=lambda row: (
            row["_discovery"],
            row["_behaviour"],
            row["_score"],
        ),
        reverse=True,
    )

    trade_ready = [row for row in actionable if row["_action"]["status"] == "READY_NOW"]
    retest_plans = [row for row in actionable if row["_action"]["status"] == "RETEST_PLAN"]
    best_action = actionable[0] if actionable else None

    account = snapshot.get("private_account", {})
    universe = snapshot.get("universe", {})

    return {
        "snapshot": snapshot,
        "best_action": best_action,
        "actionable": actionable[:10],
        "trade_ready": trade_ready,
        "retest_plans": retest_plans,
        "research": ranked_research[:25],
        "references": sorted(
            [row for row in symbols if row["_reference"]],
            key=lambda row: row.get("symbol", ""),
        ),
        "positions": account.get("open_positions", []),
        "account_status": account.get("status", "UNKNOWN"),
        "universe": universe,
        "updated": snapshot.get("collected_at_utc"),
        "btc_change_24h": safe_float(snapshot.get("btc_change_24h_pct")),
        "minimum_execution_rr": MINIMUM_EXECUTION_RR,
        "discovery_summary": snapshot.get("discovery_summary", {}),
    }


def run_scan_worker() -> None:
    project_root = os.path.dirname(os.path.abspath(__file__))
    with scan_lock:
        scan_state.update(
            running=True,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            status="running",
            error=None,
            return_code=None,
        )

    try:
        completed = subprocess.run(
            [sys.executable, "run.py"],
            cwd=project_root,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        with scan_lock:
            scan_state["return_code"] = completed.returncode
            if completed.returncode == 0:
                scan_state["status"] = "completed"
                scan_state["error"] = None
            else:
                scan_state["status"] = "failed"
                scan_state["error"] = (completed.stderr or completed.stdout or "Unknown scanner error").strip()[-5000:]
    except subprocess.TimeoutExpired:
        with scan_lock:
            scan_state["status"] = "failed"
            scan_state["error"] = "Scan timed out after 15 minutes"
    except Exception as exc:
        with scan_lock:
            scan_state["status"] = "failed"
            scan_state["error"] = f"Unable to run scanner: {exc}"
    finally:
        with scan_lock:
            scan_state["running"] = False
            scan_state["finished_at"] = datetime.now(timezone.utc).isoformat()


PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Alpha Hunter V7.2 — Money Action</title>
<style>
:root{--bg:#071018;--panel:#0d1822;--line:#1c2c39;--text:#e8f0f6;--muted:#8ea1b2;--green:#24d18f;--red:#ff6474;--amber:#ffbf47;--blue:#4db6ff}
*{box-sizing:border-box} body{margin:0;background:linear-gradient(180deg,#050b11,#09131c);color:var(--text);font-family:Inter,system-ui,-apple-system,sans-serif}
.wrap{max-width:1500px;margin:auto;padding:20px}.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-end;margin-bottom:18px}
h1{margin:0;font-size:28px}.sub,.muted,.small{color:var(--muted)}.small{font-size:12px}.panel,.card{background:rgba(13,24,34,.96);border:1px solid var(--line);border-radius:16px}.panel{padding:18px;margin-bottom:16px}.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px}.card{padding:14px}.label{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.value{font-size:24px;font-weight:800;margin-top:4px}
.action-ready{border-color:#1f6a50;box-shadow:0 0 0 1px rgba(36,209,143,.15)}.action-retest{border-color:#7a6224}.action-none{border-color:#314454}.action-title{font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.ready{color:var(--green)}.retest{color:var(--amber)}.reject,.short{color:var(--red)}.long{color:var(--green)}
.action-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-top:14px}.metric{background:#09131c;border:1px solid #162734;border-radius:12px;padding:11px}.metric b{display:block;margin-top:4px;font-size:16px}.reason{margin-top:12px;padding:11px;border-left:3px solid var(--blue);background:#09131c;color:#b9c7d2;font-size:13px;line-height:1.45}
.layout{display:grid;grid-template-columns:3fr 1fr;gap:16px}table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;color:var(--muted);padding:9px 6px;border-bottom:1px solid var(--line)}td{padding:10px 6px;border-bottom:1px solid #142431;white-space:nowrap}.wrap-cell{white-space:normal;min-width:180px}.badge{display:inline-block;padding:4px 8px;border-radius:999px;border:1px solid var(--line);font-size:10px;font-weight:700}.badge-ready{color:var(--green);border-color:#1f6a50}.badge-retest{color:var(--amber);border-color:#7a6224}.badge-research{color:var(--muted)}
.run-button{border:1px solid #1f6a50;background:#123b2d;color:var(--green);padding:10px 14px;border-radius:10px;font-weight:800;cursor:pointer}.run-button:disabled{opacity:.5}.status{padding:9px 12px;border:1px solid var(--line);border-radius:999px;background:var(--panel);font-size:12px}.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.side-row{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px solid #142431;font-size:12px}.empty{color:var(--muted);padding:16px 0}.warning{color:var(--amber)}
@media(max-width:1000px){.cards{grid-template-columns:repeat(2,1fr)}.layout{grid-template-columns:1fr}.action-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:650px){.wrap{padding:12px}.top{align-items:flex-start;flex-direction:column}.cards{grid-template-columns:1fr 1fr}.action-grid{grid-template-columns:1fr 1fr}table{display:block;overflow-x:auto}h1{font-size:24px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div><h1>Alpha Hunter V7.2</h1><div class="sub">Execution first. Discovery is research until it becomes a money action.</div></div>
    <div><div class="toolbar"><a href="/performance" style="color:#4db6ff;text-decoration:none">Performance</a><button id="runScanButton" class="run-button" onclick="runScan()">Run Fresh Scan</button><div class="status">Updated {{ data.updated or 'Unavailable' }}</div></div><div id="scanMessage" class="small" style="margin-top:7px;text-align:right">Scanner ready</div></div>
  </div>

  <div class="cards">
    <div class="card"><div class="label">Universe</div><div class="value">{{ data.universe.get('selected_count',0) }}</div><div class="small">deep-scanned</div></div>
    <div class="card"><div class="label">Ready now</div><div class="value ready">{{ data.trade_ready|length }}</div><div class="small">strict execution</div></div>
    <div class="card"><div class="label">Retest plans</div><div class="value warning">{{ data.retest_plans|length }}</div><div class="small">price must come to us</div></div>
    <div class="card"><div class="label">Minimum R:R</div><div class="value">{{ '%.1f'|format(data.minimum_execution_rr) }}R</div><div class="small">not relaxed</div></div>
    <div class="card"><div class="label">BTC 24H</div><div class="value {{ 'long' if data.btc_change_24h>0 else 'short' if data.btc_change_24h<0 else '' }}">{{ '%.2f'|format(data.btc_change_24h) }}%</div><div class="small">regime reference</div></div>
  </div>

  {% if data.best_action %}
    {% set row=data.best_action %}{% set a=row._action %}
    <div class="panel {{ 'action-ready' if a.status=='READY_NOW' else 'action-retest' }}">
      <div class="action-title {{ 'ready' if a.status=='READY_NOW' else 'retest' }}">🟢 MONEY ACTION NOW — {{ a.label }}</div>
      <h2 style="margin:8px 0 0">{{ row.symbol }} {{ a.direction }}</h2>
      <div class="action-grid">
        <div class="metric"><span class="label">Status</span><b>{{ a.status }}</b></div>
        <div class="metric"><span class="label">Entry / zone</span><b>{{ a.entry }}</b></div>
        <div class="metric"><span class="label">Stop / invalidation</span><b>{{ a.stop }}</b></div>
        <div class="metric"><span class="label">Target</span><b>{{ a.target }}</b></div>
        <div class="metric"><span class="label">R:R</span><b>{{ '%.2f'|format(a.rr or 0) }}</b></div>
        <div class="metric"><span class="label">Distance to action</span><b>{{ '%.2f'|format(a.distance_pct or 0) }}%</b></div>
      </div>
      <div class="reason"><b>Why:</b> {{ a.reason }}<br><b>Cancel:</b> {{ a.cancel }}</div>
    </div>
  {% else %}
    <div class="panel action-none">
      <div class="action-title">MONEY ACTION NOW</div>
      <h2 style="margin:8px 0">NO VALID EXECUTION YET</h2>
      <div class="reason">The app will not turn a discovery coin into a trade recommendation. Run a fresh scan or wait for the next scan; the first candidate that passes the execution contract will replace this block automatically.</div>
    </div>
  {% endif %}

  <div class="layout">
    <main>
      <div class="panel">
        <h2 style="margin-top:0">Action Queue</h2>
        {% if data.actionable %}
        <table><thead><tr><th>Symbol</th><th>Action</th><th>Side</th><th>Entry</th><th>Stop</th><th>Target</th><th>R:R</th><th>Distance</th></tr></thead><tbody>
        {% for row in data.actionable %}{% set a=row._action %}
        <tr><td><b>{{ row.symbol }}</b></td><td><span class="badge {{ 'badge-ready' if a.status=='READY_NOW' else 'badge-retest' }}">{{ a.status }}</span></td><td class="{{ 'long' if a.direction=='LONG' else 'short' }}">{{ a.direction }}</td><td>{{ a.entry }}</td><td>{{ a.stop }}</td><td>{{ a.target }}</td><td>{{ '%.2f'|format(a.rr or 0) }}</td><td>{{ '%.2f'|format(a.distance_pct or 0) }}%</td></tr>
        {% endfor %}</tbody></table>
        {% else %}<div class="empty">No executable or valid retest plan in the current snapshot.</div>{% endif %}
      </div>

      <div class="panel">
        <h2 style="margin-top:0">Research / Discovery Radar</h2>
        <div class="small" style="margin-bottom:10px">These rows are information, not trade recommendations. They become actionable only through the Money Action block above.</div>
        <table><thead><tr><th>#</th><th>Symbol</th><th>Price</th><th>Phase</th><th>Timing</th><th>Behaviour</th><th>State</th><th>R:R</th><th>Execution</th><th>Reason</th></tr></thead><tbody>
        {% for row in data.research %}
        <tr><td>{{ loop.index }}</td><td><b>{{ row.symbol }}</b></td><td>{{ row.last_price }}</td><td>{{ row._phase }}</td><td>{{ row._timing }}</td><td>{{ '%.2f'|format(row._behaviour) }}</td><td class="{{ 'long' if 'LONG' in row.state else 'short' if 'SHORT' in row.state else '' }}">{{ row.state }}</td><td>{{ '%.2f'|format(row._rr) if row._rr is not none else '—' }}</td><td><span class="badge {{ 'badge-ready' if row._action.status=='READY_NOW' else 'badge-retest' if row._action.status=='RETEST_PLAN' else 'badge-research' }}">{{ row._action.label }}</span></td><td class="wrap-cell muted">{{ row._action.reason }}</td></tr>
        {% endfor %}</tbody></table>
      </div>

      <div class="panel"><h2 style="margin-top:0">Bitget Open Positions</h2>
      {% if data.positions %}<table><thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Mark</th><th>Leverage</th><th>Unrealized P/L</th></tr></thead><tbody>
      {% for p in data.positions %}<tr><td><b>{{ p.symbol }}</b></td><td>{{ p.hold_side }}</td><td>{{ p.total }}</td><td>{{ p.open_price_avg }}</td><td>{{ p.mark_price }}</td><td>{{ p.leverage }}×</td><td>{{ p.unrealized_pl }}</td></tr>{% endfor %}
      </tbody></table>{% else %}<div class="empty">No open Bitget positions detected.</div>{% endif %}</div>
    </main>

    <aside>
      <div class="panel"><h2 style="margin-top:0">Reference / Regime</h2>{% for row in data.references %}<div class="side-row"><span><b>{{ row.symbol }}</b></span><span>{{ row.last_price }}</span></div>{% else %}<div class="empty">No reference assets.</div>{% endfor %}</div>
      <div class="panel"><h2 style="margin-top:0">Product Contract</h2><div class="small">Discovery ≠ recommendation.<br><br>READY NOW requires the existing execution permission.<br><br>RETEST PLAN requires direction + structure + momentum + participation + funding + integrity, with only price/R:R still needing improvement.<br><br>No threshold is relaxed.</div></div>
    </aside>
  </div>
</div>
<script>
let scanPollTimer=null;
async function runScan(){const b=document.getElementById('runScanButton'),m=document.getElementById('scanMessage');b.disabled=true;m.textContent='Starting fresh scan...';try{const r=await fetch('/api/run-scan',{method:'POST'}),x=await r.json();if(!r.ok)throw new Error(x.error||'Unable to start scan');m.textContent='Scan running...';if(scanPollTimer)clearInterval(scanPollTimer);scanPollTimer=setInterval(checkScanStatus,3000)}catch(e){m.textContent='Scan failed: '+e.message;b.disabled=false}}
async function checkScanStatus(){const b=document.getElementById('runScanButton'),m=document.getElementById('scanMessage');try{const r=await fetch('/api/scan-status'),x=await r.json();if(x.running){m.textContent='Scan running...';b.disabled=true;return}if(x.status==='completed'){clearInterval(scanPollTimer);m.textContent='Scan complete. Refreshing...';setTimeout(()=>location.reload(),700);return}if(x.status==='failed'){clearInterval(scanPollTimer);m.textContent='Scan failed: '+(x.error||'unknown error');b.disabled=false;return}b.disabled=false}catch(e){m.textContent='Unable to read scan status';b.disabled=false}}
</script>
</body>
</html>
"""


@app.get("/")
def dashboard():
    try:
        return render_template_string(PAGE, data=dashboard_payload(latest_snapshot()))
    except Exception as exc:
        return render_template_string("<h1>Alpha Hunter Dashboard</h1><p>{{ error }}</p>", error=str(exc)), 503


@app.get("/api/latest")
def api_latest():
    try:
        return jsonify(dashboard_payload(latest_snapshot()))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@app.post("/api/run-scan")
def api_run_scan():
    with scan_lock:
        if scan_state["running"]:
            return jsonify({"status": "running", "message": "A scan is already running"}), 202
        scan_state["running"] = True
        scan_state["status"] = "starting"
        scan_state["error"] = None

    threading.Thread(target=run_scan_worker, daemon=True).start()
    return jsonify({"status": "started", "message": "Alpha Hunter V7.2 scan started"}), 202


@app.get("/api/scan-status")
def api_scan_status():
    with scan_lock:
        return jsonify(dict(scan_state))


@app.get("/performance")
def performance_dashboard():
    try:
        horizon = int(request.args.get("horizon", "1"))
        if horizon not in {1, 4, 12, 24}:
            horizon = 1
        report = StatisticsService(SUPABASE_URL, SUPABASE_KEY).report(horizon)
        return render_template_string(PERFORMANCE_PAGE, data=report)
    except Exception as exc:
        return render_template_string("<h1>Performance Analytics</h1><p>{{ error }}</p><p><a href='/'>Back</a></p>", error=str(exc)), 503


@app.get("/api/performance")
def api_performance():
    try:
        horizon = int(request.args.get("horizon", "1"))
        if horizon not in {1, 4, 12, 24}:
            horizon = 1
        return jsonify(StatisticsService(SUPABASE_URL, SUPABASE_KEY).report(horizon))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "alpha-hunter-dashboard",
        "version": "7.2",
        "scan_status": scan_state["status"],
        "scan_running": scan_state["running"],
        "minimum_execution_rr": MINIMUM_EXECUTION_RR,
        "time_utc": datetime.now(timezone.utc).isoformat(),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
