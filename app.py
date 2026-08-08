from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from typing import Any

import requests
from flask import Flask, jsonify, render_template_string, request

from alpha_hunter.services.statistics import StatisticsService
from performance_page import PERFORMANCE_PAGE


app = Flask(__name__)


SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "",
).rstrip("/")

SUPABASE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    "",
)

SNAPSHOT_TABLE = os.getenv(
    "ALPHA_HUNTER_SNAPSHOT_TABLE",
    "alpha_hunter_snapshots",
)


scan_lock = threading.Lock()

scan_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "status": "idle",
    "error": None,
    "return_code": None,
}


def supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization":
            f"Bearer {SUPABASE_KEY}",
        "Content-Type":
            "application/json",
    }


def latest_snapshot() -> dict[str, Any]:

    if (
        not SUPABASE_URL
        or not SUPABASE_KEY
    ):
        raise RuntimeError(
            "Supabase environment "
            "variables are not configured"
        )

    response = requests.get(
        (
            f"{SUPABASE_URL}"
            f"/rest/v1/"
            f"{SNAPSHOT_TABLE}"
        ),
        params={
            "select": (
                "run_id,"
                "collected_at_utc,"
                "version,"
                "symbol_count,"
                "error_count,"
                "payload"
            ),
            "order":
                "collected_at_utc.desc",
            "limit":
                "1",
        },
        headers=
            supabase_headers(),
        timeout=15,
    )

    response.raise_for_status()

    rows = response.json()

    if not rows:
        raise RuntimeError(
            "No Alpha Hunter "
            "snapshots found"
        )

    return (
        rows[0].get(
            "payload"
        )
        or {}
    )


def safe_float(
    value: Any,
) -> float:

    try:
        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def dashboard_payload(
    snapshot:
        dict[str, Any],
) -> dict[str, Any]:

    symbols = [
        row
        for row
        in snapshot.get(
            "symbols",
            [],
        )
        if "error"
        not in row
    ]

    for row in symbols:

        intel = row.get(
            "intelligence",
            {},
        )

        setup = row.get(
            "execution_setup",
            {},
        )

        row["_score"] = (
            safe_float(
                intel.get(
                    "huge_rr_score"
                )
            )
        )

        row["_confidence"] = (
            safe_float(
                intel.get(
                    "confidence_estimate_pct"
                )
            )
        )

        row["_rr"] = (
            setup.get("rr")
        )

        row["_direction"] = (
            setup.get(
                "direction"
            )
        )

        row["_trade"] = bool(
            row.get(
                "trade_permission"
            )
        )

    ranked = sorted(
        symbols,
        key=lambda row:
            row["_score"],
        reverse=True,
    )

    longs = [
        row
        for row
        in ranked
        if (
            "LONG"
            in str(
                row.get(
                    "state",
                    "",
                )
            )
            or str(
                row["_direction"]
            ).upper()
            == "LONG"
        )
    ]

    shorts = [
        row
        for row
        in ranked
        if (
            "SHORT"
            in str(
                row.get(
                    "state",
                    "",
                )
            )
            or str(
                row["_direction"]
            ).upper()
            == "SHORT"
        )
    ]

    trade_ready = [
        row
        for row
        in ranked
        if row["_trade"]
    ]

    universe = (
        snapshot.get(
            "universe",
            {},
        )
    )

    account = (
        snapshot.get(
            "private_account",
            {},
        )
    )

    return {
        "snapshot":
            snapshot,

        "ranked":
            ranked[:20],

        "longs":
            longs[:10],

        "shorts":
            shorts[:10],

        "trade_ready":
            trade_ready,

        "positions":
            account.get(
                "open_positions",
                [],
            ),

        "account_status":
            account.get(
                "status",
                "UNKNOWN",
            ),

        "universe":
            universe,

        "updated":
            snapshot.get(
                "collected_at_utc"
            ),
    }


def run_scan_worker() -> None:

    project_root = os.path.dirname(
        os.path.abspath(
            __file__
        )
    )

    with scan_lock:

        scan_state[
            "running"
        ] = True

        scan_state[
            "started_at"
        ] = datetime.now(
            timezone.utc
        ).isoformat()

        scan_state[
            "finished_at"
        ] = None

        scan_state[
            "status"
        ] = "running"

        scan_state[
            "error"
        ] = None

        scan_state[
            "return_code"
        ] = None

    try:

        completed = (
            subprocess.run(
                [
                    sys.executable,
                    "run.py",
                ],
                cwd=
                    project_root,
                env=
                    os.environ.copy(),
                capture_output=
                    True,
                text=
                    True,
                timeout=
                    900,
                check=
                    False,
            )
        )

        with scan_lock:

            scan_state[
                "return_code"
            ] = completed.returncode

        if (
            completed.returncode
            != 0
        ):

            error_text = (
                completed.stderr
                or completed.stdout
                or (
                    "Unknown scanner "
                    "error"
                )
            ).strip()

            with scan_lock:

                scan_state[
                    "status"
                ] = "failed"

                scan_state[
                    "error"
                ] = (
                    error_text[
                        -5000:
                    ]
                )

        else:

            with scan_lock:

                scan_state[
                    "status"
                ] = "completed"

                scan_state[
                    "error"
                ] = None

    except (
        subprocess.TimeoutExpired
    ):

        with scan_lock:

            scan_state[
                "status"
            ] = "failed"

            scan_state[
                "error"
            ] = (
                "Scan timed out "
                "after 15 minutes"
            )

    except Exception as exc:

        with scan_lock:

            scan_state[
                "status"
            ] = "failed"

            scan_state[
                "error"
            ] = (
                "Unable to run "
                f"scanner: {exc}"
            )

    finally:

        with scan_lock:

            scan_state[
                "running"
            ] = False

            scan_state[
                "finished_at"
            ] = datetime.now(
                timezone.utc
            ).isoformat()


PAGE = r"""
<!doctype html>

<html lang="en">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="
        width=device-width,
        initial-scale=1
    "
>

<meta
    http-equiv="refresh"
    content="300"
>

<title>
Alpha Hunter V7
</title>

<style>

:root {
    --bg:#071018;
    --panel:#0d1822;
    --line:#1c2c39;
    --text:#e8f0f6;
    --muted:#8ea1b2;
    --green:#24d18f;
    --red:#ff6474;
    --amber:#ffbf47;
    --blue:#4db6ff;
}

* {
    box-sizing:border-box;
}

body {
    margin:0;
    background:
        linear-gradient(
            180deg,
            #050b11,
            #09131c
        );
    color:
        var(--text);
    font-family:
        Inter,
        system-ui,
        -apple-system,
        sans-serif;
}

.wrap {
    max-width:1500px;
    margin:auto;
    padding:24px;
}

.top {
    display:flex;
    justify-content:
        space-between;
    gap:20px;
    align-items:
        flex-end;
    margin-bottom:20px;
}

h1 {
    margin:0;
    font-size:30px;
}

.sub {
    color:
        var(--muted);
    margin-top:6px;
}

.status {
    padding:9px 13px;
    border:
        1px solid
        var(--line);
    border-radius:999px;
    background:
        var(--panel);
}

.grid {
    display:grid;
    grid-template-columns:
        repeat(
            4,
            1fr
        );
    gap:14px;
    margin-bottom:18px;
}

.card,
.panel {
    background:
        rgba(
            13,
            24,
            34,
            .94
        );
    border:
        1px solid
        var(--line);
    border-radius:16px;
}

.card {
    padding:18px;
}

.label {
    font-size:12px;
    text-transform:
        uppercase;
    letter-spacing:.08em;
    color:
        var(--muted);
}

.value {
    font-size:26px;
    font-weight:750;
    margin-top:6px;
}

.layout {
    display:grid;
    grid-template-columns:
        2fr 1fr;
    gap:18px;
}

.panel {
    padding:18px;
    margin-bottom:18px;
}

.panel h2 {
    font-size:17px;
    margin:
        0 0 14px;
}

table {
    width:100%;
    border-collapse:
        collapse;
    font-size:13px;
}

th {
    text-align:left;
    color:
        var(--muted);
    font-weight:600;
    padding:10px 8px;
    border-bottom:
        1px solid
        var(--line);
}

td {
    padding:11px 8px;
    border-bottom:
        1px solid
        #142431;
    white-space:
        nowrap;
}

.score {
    font-weight:800;
}

.long {
    color:
        var(--green);
}

.short {
    color:
        var(--red);
}

.badge {
    display:inline-block;
    padding:4px 8px;
    border-radius:999px;
    border:
        1px solid
        var(--line);
    font-size:11px;
}

.yes {
    color:
        var(--green);
    border-color:
        #1f6a50;
}

.no {
    color:
        var(--muted);
}

.empty {
    color:
        var(--muted);
    padding:18px 0;
}

.small {
    font-size:12px;
    color:
        var(--muted);
}

.run-button {
    border:
        1px solid
        #1f6a50;
    background:
        #123b2d;
    color:
        #24d18f;
    padding:
        10px 14px;
    border-radius:10px;
    font-weight:700;
    cursor:pointer;
}

.run-button:disabled {
    opacity:.55;
    cursor:
        not-allowed;
}

.scan-message {
    font-size:12px;
    color:
        var(--muted);
    margin-top:6px;
    text-align:right;
}

@media(
    max-width:900px
) {

    .grid {
        grid-template-columns:
            repeat(
                2,
                1fr
            );
    }

    .layout {
        grid-template-columns:
            1fr;
    }

    .wrap {
        padding:14px;
    }

    .top {
        align-items:
            flex-start;
        flex-direction:
            column;
    }
}

</style>

</head>

<body>

<div class="wrap">

    <div class="top">

        <div>

            <h1>
                Alpha Hunter V7
            </h1>

            <div class="sub">
                Behaviour Intelligence
                & Full-Market Discovery
            </div>

        </div>

        <div>

            <div
                style="
                    display:flex;
                    gap:10px;
                    align-items:center
                "
            >

                <a
                    href="/performance"
                    style="
                        color:#4db6ff;
                        text-decoration:none
                    "
                >
                    Performance Analytics
                </a>

                <button
                    id="runScanButton"
                    class="run-button"
                    onclick="runScan()"
                >
                    Run Scan
                </button>

                <div class="status">
                    Updated
                    {{
                        data.updated
                        or
                        "Unavailable"
                    }}
                </div>

            </div>

            <div
                id="scanMessage"
                class="scan-message"
            >
                Manual scanner ready
            </div>

        </div>

    </div>


    <div class="grid">

        <div class="card">

            <div class="label">
                Universe
            </div>

            <div class="value">
                {{
                    data.universe.get(
                        "selected_count",
                        0
                    )
                }}
            </div>

            <div class="small">
                of
                {{
                    data.universe.get(
                        "total_contracts",
                        0
                    )
                }}
                contracts
            </div>

        </div>


        <div class="card">

            <div class="label">
                Trade Ready
            </div>

            <div class="value">
                {{
                    data.trade_ready
                    | length
                }}
            </div>

            <div class="small">
                execution permission granted
            </div>

        </div>


        <div class="card">

            <div class="label">
                Open Positions
            </div>

            <div class="value">
                {{
                    data.positions
                    | length
                }}
            </div>

            <div class="small">
                Bitget private API:
                {{
                    data.account_status
                }}
            </div>

        </div>


        <div class="card">

            <div class="label">
                Top Score
            </div>

            <div class="value">
                {{
                    "%.1f"
                    | format(
                        data.ranked[0]
                        ._score
                    )
                    if data.ranked
                    else "—"
                }}
            </div>

            <div class="small">
                {{
                    data.ranked[0]
                    .symbol
                    if data.ranked
                    else
                    "No candidate"
                }}
            </div>

        </div>

    </div>


    <div class="layout">

        <main>

            <div class="panel">

                <h2>
                    Top Opportunities
                </h2>

                <table>

                    <thead>

                        <tr>

                            <th>#</th>
                            <th>Symbol</th>
                            <th>Price</th>
                            <th>State</th>
                            <th>Score</th>
                            <th>Conf.</th>
                            <th>RR</th>
                            <th>Trade</th>

                        </tr>

                    </thead>

                    <tbody>

                    {% for row in data.ranked %}

                        <tr>

                            <td>
                                {{
                                    loop.index
                                }}
                            </td>

                            <td>
                                <b>
                                    {{
                                        row.symbol
                                    }}
                                </b>
                            </td>

                            <td>
                                {{
                                    row.last_price
                                }}
                            </td>

                            <td
                                class="{{
                                    'short'
                                    if
                                    'SHORT'
                                    in
                                    row.state
                                    else
                                    'long'
                                    if
                                    'LONG'
                                    in
                                    row.state
                                    else
                                    ''
                                }}"
                            >
                                {{
                                    row.state
                                }}
                            </td>

                            <td
                                class="score"
                            >
                                {{
                                    "%.1f"
                                    | format(
                                        row._score
                                    )
                                }}
                            </td>

                            <td>
                                {{
                                    "%.1f"
                                    | format(
                                        row._confidence
                                    )
                                }}%
                            </td>

                            <td>
                                {{
                                    "%.2f"
                                    | format(
                                        row._rr
                                    )
                                    if
                                    row._rr
                                    is not none
                                    else
                                    "—"
                                }}
                            </td>

                            <td>

                                <span
                                    class="
                                        badge
                                        {{
                                            'yes'
                                            if
                                            row._trade
                                            else
                                            'no'
                                        }}
                                    "
                                >

                                    {{
                                        "READY"
                                        if
                                        row._trade
                                        else
                                        "WATCH"
                                    }}

                                </span>

                            </td>

                        </tr>

                    {% endfor %}

                    </tbody>

                </table>

            </div>


            <div class="panel">

                <h2>
                    Bitget Open Positions
                </h2>

                {% if data.positions %}

                    <table>

                        <thead>

                            <tr>
                                <th>Symbol</th>
                                <th>Side</th>
                                <th>Size</th>
                                <th>Entry</th>
                                <th>Mark</th>
                                <th>Leverage</th>
                                <th>Unrealized P/L</th>
                            </tr>

                        </thead>

                        <tbody>

                        {% for p in data.positions %}

                            <tr>

                                <td>
                                    <b>
                                        {{ p.symbol }}
                                    </b>
                                </td>

                                <td>
                                    {{ p.hold_side }}
                                </td>

                                <td>
                                    {{ p.total }}
                                </td>

                                <td>
                                    {{ p.open_price_avg }}
                                </td>

                                <td>
                                    {{ p.mark_price }}
                                </td>

                                <td>
                                    {{ p.leverage }}×
                                </td>

                                <td>
                                    {{ p.unrealized_pl }}
                                </td>

                            </tr>

                        {% endfor %}

                        </tbody>

                    </table>

                {% else %}

                    <div class="empty">
                        No open Bitget
                        positions detected.
                    </div>

                {% endif %}

            </div>

        </main>


        <aside>

            <div class="panel">

                <h2>
                    Long Radar
                </h2>

                {% for row in data.longs %}

                    <div
                        style="
                            display:flex;
                            justify-content:
                                space-between;
                            padding:
                                9px 0;
                            border-bottom:
                                1px solid
                                #142431
                        "
                    >

                        <span>
                            {{ row.symbol }}
                        </span>

                        <span class="long">
                            {{
                                "%.1f"
                                | format(
                                    row._score
                                )
                            }}
                        </span>

                    </div>

                {% else %}

                    <div class="empty">
                        No long candidates.
                    </div>

                {% endfor %}

            </div>


            <div class="panel">

                <h2>
                    Short Radar
                </h2>

                {% for row in data.shorts %}

                    <div
                        style="
                            display:flex;
                            justify-content:
                                space-between;
                            padding:
                                9px 0;
                            border-bottom:
                                1px solid
                                #142431
                        "
                    >

                        <span>
                            {{ row.symbol }}
                        </span>

                        <span class="short">
                            {{
                                "%.1f"
                                | format(
                                    row._score
                                )
                            }}
                        </span>

                    </div>

                {% else %}

                    <div class="empty">
                        No short candidates.
                    </div>

                {% endfor %}

            </div>

        </aside>

    </div>

</div>


<script>

let scanPollTimer = null;

async function runScan() {

    const button =
        document.getElementById(
            "runScanButton"
        );

    const message =
        document.getElementById(
            "scanMessage"
        );

    button.disabled = true;

    message.textContent =
        "Starting V7 full-market scan...";

    try {

        const response =
            await fetch(
                "/api/run-scan",
                {
                    method:
                        "POST"
                }
            );

        const result =
            await response.json();

        if (!response.ok) {

            throw new Error(
                result.error
                ||
                "Unable to start scan"
            );

        }

        message.textContent =
            "Scan running in background...";

        startScanPolling();

    } catch (error) {

        message.textContent =
            "Scan failed: "
            + error.message;

        button.disabled =
            false;
    }
}


function startScanPolling() {

    if (scanPollTimer) {
        clearInterval(
            scanPollTimer
        );
    }

    scanPollTimer =
        setInterval(
            checkScanStatus,
            3000
        );
}


async function checkScanStatus() {

    const button =
        document.getElementById(
            "runScanButton"
        );

    const message =
        document.getElementById(
            "scanMessage"
        );

    try {

        const response =
            await fetch(
                "/api/scan-status"
            );

        const result =
            await response.json();

        if (result.running) {

            message.textContent =
                "V7 scan running...";

            button.disabled =
                true;

            return;
        }

        if (
            result.status
            ===
            "completed"
        ) {

            clearInterval(
                scanPollTimer
            );

            scanPollTimer =
                null;

            message.textContent =
                "Scan completed. "
                + "Refreshing...";

            setTimeout(
                () => {
                    window.location.reload();
                },
                1000
            );

            return;
        }

        if (
            result.status
            ===
            "failed"
        ) {

            clearInterval(
                scanPollTimer
            );

            scanPollTimer =
                null;

            message.textContent =
                "Scan failed: "
                +
                (
                    result.error
                    ||
                    "unknown error"
                );

            button.disabled =
                false;

            return;
        }

        button.disabled =
            false;

    } catch (error) {

        message.textContent =
            "Unable to read scan status";

        button.disabled =
            false;
    }
}

</script>

</body>

</html>
"""


@app.get("/")
def dashboard():

    try:

        snapshot = (
            latest_snapshot()
        )

        return (
            render_template_string(
                PAGE,
                data=
                    dashboard_payload(
                        snapshot
                    ),
            )
        )

    except Exception as exc:

        return (
            render_template_string(
                (
                    "<h1>"
                    "Alpha Hunter Dashboard"
                    "</h1>"
                    "<p>"
                    "{{ error }}"
                    "</p>"
                ),
                error=
                    str(exc),
            ),
            503,
        )


@app.get("/api/latest")
def api_latest():

    try:

        return jsonify(
            dashboard_payload(
                latest_snapshot()
            )
        )

    except Exception as exc:

        return (
            jsonify({
                "error":
                    str(exc)
            }),
            503,
        )


@app.post("/api/run-scan")
def api_run_scan():

    with scan_lock:

        if scan_state[
            "running"
        ]:

            return (
                jsonify({
                    "status":
                        "running",

                    "message":
                        (
                            "A scan is "
                            "already running"
                        ),
                }),
                202,
            )

        scan_state[
            "running"
        ] = True

        scan_state[
            "status"
        ] = "starting"

        scan_state[
            "error"
        ] = None

    thread = threading.Thread(
        target=
            run_scan_worker,
        daemon=True,
    )

    thread.start()

    return (
        jsonify({
            "status":
                "started",

            "message":
                (
                    "Alpha Hunter V7 "
                    "scan started"
                ),
        }),
        202,
    )


@app.get("/api/scan-status")
def api_scan_status():

    with scan_lock:

        return jsonify(
            dict(
                scan_state
            )
        )


@app.get("/performance")
def performance_dashboard():

    try:

        horizon = int(
            request.args.get(
                "horizon",
                "1",
            )
        )

        if horizon not in {
            1,
            4,
            12,
            24,
        }:

            horizon = 1

        report = (
            StatisticsService(
                SUPABASE_URL,
                SUPABASE_KEY,
            ).report(
                horizon
            )
        )

        return (
            render_template_string(
                PERFORMANCE_PAGE,
                data=
                    report,
            )
        )

    except Exception as exc:

        return (
            render_template_string(
                (
                    "<h1>"
                    "Performance Analytics"
                    "</h1>"
                    "<p>"
                    "{{ error }}"
                    "</p>"
                    "<p>"
                    "<a href='/'>"
                    "Back"
                    "</a>"
                    "</p>"
                ),
                error=
                    str(exc),
            ),
            503,
        )


@app.get("/api/performance")
def api_performance():

    try:

        horizon = int(
            request.args.get(
                "horizon",
                "1",
            )
        )

        if horizon not in {
            1,
            4,
            12,
            24,
        }:

            horizon = 1

        return jsonify(
            StatisticsService(
                SUPABASE_URL,
                SUPABASE_KEY,
            ).report(
                horizon
            )
        )

    except Exception as exc:

        return (
            jsonify({
                "error":
                    str(exc)
            }),
            503,
        )


@app.get("/health")
def health():

    return jsonify({
        "status":
            "ok",

        "service":
            "alpha-hunter-dashboard",

        "scan_status":
            scan_state[
                "status"
            ],

        "scan_running":
            scan_state[
                "running"
            ],

        "time_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),
    })


if __name__ == "__main__":

    app.run(
        host=
            "0.0.0.0",

        port=int(
            os.getenv(
                "PORT",
                "10000",
            )
        ),
    )
