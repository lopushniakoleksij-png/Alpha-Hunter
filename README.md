# Alpha Hunter V1 — Proper Core v0.3.0

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
