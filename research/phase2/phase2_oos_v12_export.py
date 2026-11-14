"""Authorized read-only COPY of exact three pre-locked OOS dates into private QA.

Requires psycopg v3 already installed in private .pilot-export-venv. Hidden
password prompt only. No production DB writes, no config change, no public
signal upload. Does not open or modify any previous V1.0 / V1.1 evidence.
"""
import argparse
import csv
import getpass
import hashlib
import os
import tempfile
from collections import Counter
from pathlib import Path

BASE=(Path.home()/".alpha-hunter-phase2-private").resolve()
EXPECTED={"2026-10-20":174,"2026-10-21":77,"2026-10-23":199}
FIELDS={"signal_id","symbol","detected_at_utc","created_at","direction",
        "trade_permission","entry_price","stop_loss","take_profit",
        "reward_risk","execution_checks_json","trade_permission_reason"}

COPY_SQL="""COPY (
 SELECT signal_id,symbol,detected_at_utc,created_at,direction,
        trade_permission,entry_price,stop_loss,take_profit,
        reward_risk,
        COALESCE((payload->'execution_setup'->'checks')::text,'{}') AS execution_checks_json,
        COALESCE(payload->>'trade_permission_reason','') AS trade_permission_reason
 FROM public.alpha_hunter_signals
 WHERE symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT')
   AND ((detected_at_utc >= '2026-10-20T00:00:00Z' AND detected_at_utc < '2026-10-22T00:00:00Z')
    OR  (detected_at_utc >= '2026-10-23T00:00:00Z' AND detected_at_utc < '2026-10-24T00:00:00Z'))
 ORDER BY detected_at_utc,signal_id
) TO STDOUT WITH (FORMAT CSV, HEADER TRUE)"""

def inspect_export(path):
    data=Path(path).read_bytes()
    with Path(path).open(newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f)
        if not FIELDS.issubset(reader.fieldnames or []):
            raise ValueError("missing snapshot column")
        rows=list(reader)
    if len(rows)!=450 or len({r["signal_id"] for r in rows})!=450:
        raise ValueError("source snapshot has wrong row count or duplicates")
    if any(r["symbol"] not in ("BTCUSDT","ETHUSDT","SOLUSDT") for r in rows):
        raise ValueError("wrong instrument universe")
    if any(r["trade_permission"].strip().lower() not in ("false","f","0") for r in rows):
        raise ValueError("non-blocked permission in frozen pilot")
    days=Counter(r["detected_at_utc"][:10] for r in rows)
    if dict(days)!=EXPECTED:
        raise ValueError("incorrect frozen-day record counts: "+str(dict(days)))
    return {"records":len(rows),"by_day":dict(sorted(days.items())),
            "sha256":hashlib.sha256(data).hexdigest()}

def export(out,password,connector=None):
    out=Path(out)
    if not out.is_absolute() or out.parent.resolve()!=BASE or out.exists() or out.is_symlink():
        raise ValueError("must create a new private evidence CSV directly under QA root")
    if not password:raise ValueError("authorized read-only DB password required")
    if connector is None:
        import psycopg
        connector=psycopg.connect
    fd,temp=tempfile.mkstemp(prefix=".oos-v12-signal-export-",suffix=".csv",dir=str(BASE))
    os.chmod(temp,0o600)
    try:
        with connector(host="aws-0-eu-west-1.pooler.supabase.com",port=5432,
                       user="postgres.yjgtjzymfurqzqqxcrnp",dbname="postgres",
                       password=password,sslmode="require",connect_timeout=20,autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                try:
                    cur.execute("SET LOCAL TIME ZONE 'UTC'")
                    with os.fdopen(fd,"wb") as f:
                        fd=-1
                        with cur.copy(COPY_SQL) as stream:
                            for part in stream:
                                f.write(part)
                        f.flush();os.fsync(f.fileno())
                    cur.execute("COMMIT")
                except BaseException:
                    cur.execute("ROLLBACK")
                    raise
        info=inspect_export(temp)
        if out.exists() or out.is_symlink():raise ValueError("destination appeared; refuse overwrite")
        os.link(temp,out)
        return dict(info,private_output=str(out),readonly=True)
    finally:
        if fd>=0:os.close(fd)
        try:os.unlink(temp)
        except FileNotFoundError:pass

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",required=True,type=Path)
    opts=p.parse_args()
    password=getpass.getpass("Supabase database password (hidden, never saved): ")
    result=export(opts.out,password)
    print("OOS V1.2 READ-ONLY 450-ROW EXPORT: PASS")
    print("Days:",result["by_day"])
    print("SHA256:",result["sha256"])
    print("Private file:",result["private_output"])
