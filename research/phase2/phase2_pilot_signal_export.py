"""Alpha Hunter Phase 2 — isolated read-only Supabase signal cohort export.

Requires psycopg v3 only in the *private* Codespace export environment.
Database credentials are entered privately with getpass, never stored in files.
Exports exactly the frozen 175-row 2026-11-08 UTC BTC/ETH/SOL cohort.
No writes, DDL, production scanner changes, trades or broad backfill.
"""
import argparse
import getpass
import os
import tempfile
from pathlib import Path

from phase2_pilot_offline_certify import validate_signals

DB_HOST = "aws-0-eu-west-1.pooler.supabase.com"
DB_PORT = 5432
DB_USER = "postgres.yjgtjzymfurqzqqxcrnp"
DB_NAME = "postgres"
PRIVATE_ROOT = (Path.home()/".alpha-hunter-phase2-private").resolve()
QUERY = """COPY (
    SELECT signal_id, symbol, detected_at_utc, created_at,
           state, direction, trade_permission, entry_price,
           stop_loss, take_profit, reference_price,
           huge_rr_score, confidence_estimate_pct, reward_risk
    FROM public.alpha_hunter_signals
    WHERE symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT')
      AND detected_at_utc >= '2026-11-08T00:00:00Z'
      AND detected_at_utc <  '2026-11-09T00:00:00Z'
    ORDER BY symbol, detected_at_utc, signal_id
) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)"""

def export_cohort(out, *, password, connector=None):
    destination = Path(out).absolute()
    if (not destination.is_absolute() or not destination.parent.is_dir()
            or destination.is_symlink() or destination.exists()
            or destination.parent.resolve()!=PRIVATE_ROOT):
        raise ValueError("output must be a NEW file directly under the existing private QA directory")
    if not password:
        raise ValueError("password required for authorized read-only database connection")
    if connector is None:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg v3 is not installed in the private export environment") from exc
        connector = psycopg.connect

    descriptor, temp_name = tempfile.mkstemp(prefix=".pilot-signal-export-", suffix=".csv",
                                             dir=str(PRIVATE_ROOT))
    os.chmod(temp_name,0o600)
    try:
        # autocommit=True lets us open one explicit REPEATABLE READ, READ ONLY
        # transaction, then transfer bytes using server-side COPY TO STDOUT.
        with connector(host=DB_HOST,port=DB_PORT,user=DB_USER,
                       dbname=DB_NAME,password=password,
                       sslmode="require",connect_timeout=20,
                       autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                try:
                    cur.execute("SET LOCAL TIME ZONE 'UTC'")
                    with os.fdopen(descriptor,"wb") as fh:
                        descriptor=-1
                        with cur.copy(QUERY) as reader:
                            for block in reader:
                                fh.write(block)
                        fh.flush()
                        os.fsync(fh.fileno())
                    cur.execute("COMMIT")
                except BaseException:
                    cur.execute("ROLLBACK")
                    raise
        rows, digest = validate_signals(Path(temp_name))
        if destination.exists() or destination.is_symlink():
            raise ValueError("private destination already exists; no overwriting")
        os.link(temp_name,destination)  # fails if another process created target
        return {"signals":len(rows),"symbols":["BTCUSDT","ETHUSDT","SOLUSDT"],
                "sha256":digest,"output":str(destination),
                "read_only":True}
    finally:
        if descriptor>=0:
            os.close(descriptor)
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    opt=p.parse_args()
    password=getpass.getpass("Existing Supabase DB password (hidden; not saved): ")
    result=export_cohort(opt.out,password=password)
    print("READ-ONLY SIGNAL EXPORT: PASS")
    print("Records:",result["signals"],"SHA-256:",result["sha256"])
    print("Private evidence:",result["output"])

if __name__=="__main__":
    main()
