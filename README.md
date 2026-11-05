# Alpha Hunter — Research Intelligence Platform

> **Current product status (5 November 2026):** Responsive V8 web terminal is a **draft, isolated web-design proposal** in [PR #413](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/413). Underlying research engine is labelled V7.2. The V8 user interface is **not deployed to production**, and real-order authority is disabled. Passing synthetic tests does not establish live profitability, customer revenue, independent security certification, or software transfer rights.

## Current V8 product and commercial evaluation

- [V8 UI implementation and browser verification — PR #413](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/413)
- [Plan A — Evidence-led investor-readiness brief](docs/ALPHA_HUNTER_INVESTOR_READINESS_V8_20261105.md)
- [Plan B — Potential software/IP asset-sale brief](docs/ALPHA_HUNTER_BUYER_ASSET_BRIEF_V8_20261105.md)
- [Product readiness, evidence gaps, rights and handover checklist](docs/V8_PRODUCT_READINESS_AND_TRANSFER_CHECKLIST_20261105.md)
- [Open independent DBA and security acceptance gate](https://github.com/lopushniakoleksij-png/Alpha-Hunter/issues/420) — pending; production release **NO-GO**.

**Commercial posture:** Continue product engineering while preparing both potential investor and buyer evidence; no valuation, fundraising solicitation, public sale listing, paid work, merge, deployment, real trading or account/data transfer is authorised by these documents.

---

## Archived core setup guide — V1

The following describes an earlier collector setup and is retained for historical engineering context. Do not infer that every early V1 symbol, configuration or deploy instruction reflects the current V7.2/V8 runtime. Production changes require separate controlled approval.


Bitget public-data collector and conservative execution gate for five frozen USDT perpetual contracts.

## Completed scope

- Bitget contract validation, ticker, mark/index price and candles
- Open interest, current funding and historical funding comparison
- 15m / 1H / 4H trend detection
- EMA, RSI, MACD, Bollinger Bands, ATR and volume anomaly
- Support/resistance and data-integrity score
- State transitions and append-only local history
- Structural 1:5 reward-to-risk execution gate
- Local timestamped snapshots and `latest.json`
- Supabase parent and symbol-level persistence
- Duplicate-safe Supabase upserts using a deterministic run ID
- Automatic top-of-hour runner
- Local-first failure isolation: cloud failure does not discard a scan

## Permanent core execution contract

The canonical execution-quality rule is defined in `CORE_EXECUTION_SIGNAL_QUALITY_CONTRACT.md`.

**READY = EXECUTABLE CONFLUENCE, NOT CONFIDENCE.** Direction alignment, momentum confirmation, minimum data integrity, participation, structure / entry location, remaining realistic R, and portfolio risk must work together. Missing or false required evidence fails closed rather than becoming READY.

The current Money Entry development path remains `shadow_only=true` and `trade_permission=false`. The hourly signal-quality forward audit verifies that this invariant remains intact while forward evidence accumulates.

## 1. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

## 2. Configure Supabase

Run `supabase_schema.sql` in the Supabase SQL editor.

Create local environment variables from `.env.example`:

```bash
export SUPABASE_URL="https://YOUR_PROJECT.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="YOUR_SERVICE_ROLE_KEY"
```

The service-role key is for a trusted server or personal computer only. Never put it in a browser, dashboard source code or Git repository.

To run without Supabase, set `supabase.enabled` to `false` in `config.json`. Local collection continues normally when credentials are absent.

## 3. Run one scan

```bash
python run.py
```

The terminal prints `Supabase: SAVED`, `NOT_CONFIGURED`, `DISABLED`, or a non-fatal cloud failure message.

## 4. Automatic hourly execution

### Built-in runner

```bash
python hourly.py
```

It executes at the top of every UTC hour. Test one execution with:

```bash
python hourly.py --once
```

### Linux/macOS cron alternative

```cron
0 * * * * cd /absolute/path/alpha-hunter-v1 && /absolute/path/alpha-hunter-v1/.venv/bin/python run.py >> data/collector.log 2>&1
```

Only use one scheduler to avoid unnecessary duplicate runs. Supabase upserts are duplicate-safe, but exchange requests would still be repeated.

## Storage model

`alpha_hunter_snapshots` stores one complete scan payload per run.

`alpha_hunter_symbol_snapshots` stores query-friendly rows for each symbol, including state, permission, RR, price, OI, funding and integrity.

Local files remain the recovery source:

- `data/snapshots/snapshot-*.json`
- `data/snapshots/latest.json`
- `data/state-history.jsonl`

## Frozen list

Edit the five symbols in `config.json`. Current provisional list:

- VIRTUALUSDT
- SUIUSDT
- FETUSDT
- NEARUSDT
- AKTUSDT

## Execution status

- Task 1: indicators, anomalies and historical comparisons — complete
- Task 2: state transitions and 1:5 RR validation — complete
- Task 3: Supabase persistence and hourly execution — complete
- Task 4: production report, recovery queue and live validation — next

## Version 0.4.0 — Task 4 Intelligence Engine

Adds:
- volatility compression scoring
- Huge RR scorecard (0–10)
- transparent confidence estimate (explicitly not statistically calibrated)
- institutional participation status: CONFIRMED / PARTIAL / NOT_CONFIRMED
- execution verdict: LONG_READY / SHORT_READY / DIRECTION_EMERGING / WATCH / NO_SETUP
- richer terminal report
- corrected sequencing so OI change is applied before the final execution permission decision

Trade Permission remains conservative and requires all observable execution checks, including minimum 1:5 structural RR.