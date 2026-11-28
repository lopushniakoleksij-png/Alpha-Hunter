#!/usr/bin/env python3
"""E6 disposable PostgreSQL 17 ONLY: concurrent atomic RPCs for 30/50/61.

Uses two real, overlapping psql sessions for each size, first identical and
then conflicting retries. Exercises the candidate synthetic trigger graph,
not the owner's private production-equivalent schema or latency acceptance.

No real scanner, external services, order controls, private files or spending.
"""
import json
import os
import subprocess
import time

SIZES = (30, 50, 61)
CASES = ("IDENTICAL", "CONFLICT")
CONTAINERLESS_CI_ENV = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REF_NAME": "fix/supabase-write-timeout-qa",
    "PGHOST": "127.0.0.1",
    "PGDATABASE": "isolated_atomic_scan_qa",
    "PGUSER": "postgres",
}

SETUP_SQL = r"""
DO $guard$
BEGIN
  IF current_database() <> 'isolated_atomic_scan_qa'
     OR current_user <> 'postgres'
     OR to_regclass('public.qa_atomic_scale_fixtures_v01') IS NULL
     OR to_regclass('public.qa_atomic_trigger_events') IS NULL THEN
    RAISE EXCEPTION 'QA_E6_MS_WRONG_DISPOSABLE_DB';
  END IF;
END $guard$;

INSERT INTO public.qa_atomic_scale_fixtures_v01
  (case_name,parent_rows,children_rows,signals_rows,features_rows,readiness_rows)
SELECT v.case_name,
  jsonb_set(
    jsonb_set(seed.parent_rows,'{0,run_id}',to_jsonb(v.run_id)),
    '{0,symbol_count}',to_jsonb(v.size)),
  (SELECT jsonb_agg(jsonb_set(e,'{run_id}',to_jsonb(v.run_id)) ORDER BY ord)
    FROM jsonb_array_elements(seed.children_rows) WITH ORDINALITY z(e,ord)
    WHERE ord<=v.size),
  (SELECT jsonb_agg(
     jsonb_set(jsonb_set(e,'{run_id}',to_jsonb(v.run_id)),
       '{signal_id}',to_jsonb(v.run_id||'_SIGNAL_'||ord::text))
     ORDER BY ord)
    FROM jsonb_array_elements(seed.signals_rows) WITH ORDINALITY z(e,ord)
    WHERE ord<=v.size),
  (SELECT jsonb_agg(
     jsonb_set(jsonb_set(e,'{run_id}',to_jsonb(v.run_id)),
       '{signal_id}',to_jsonb(v.run_id||'_SIGNAL_'||ord::text))
     ORDER BY ord)
    FROM jsonb_array_elements(seed.features_rows) WITH ORDINALITY z(e,ord)
    WHERE ord<=v.size),
  (SELECT jsonb_agg(jsonb_set(e,'{run_id}',to_jsonb(v.run_id)) ORDER BY ord)
    FROM jsonb_array_elements(seed.readiness_rows) WITH ORDINALITY z(e,ord)
    WHERE ord<=v.size)
FROM public.qa_atomic_scale_fixtures_v01 seed
CROSS JOIN (VALUES
  ('QA_E6MS_30_IDENTICAL','QA_E6MS_30_IDENTICAL',30),
  ('QA_E6MS_30_CONFLICT','QA_E6MS_30_CONFLICT',30),
  ('QA_E6MS_50_IDENTICAL','QA_E6MS_50_IDENTICAL',50),
  ('QA_E6MS_50_CONFLICT','QA_E6MS_50_CONFLICT',50),
  ('QA_E6MS_61_IDENTICAL','QA_E6MS_61_IDENTICAL',61),
  ('QA_E6MS_61_CONFLICT','QA_E6MS_61_CONFLICT',61)
) v(case_name,run_id,size)
WHERE seed.case_name='SIXTY_ONE';

DO $validate$
DECLARE v record;
BEGIN
  FOR v IN
    SELECT case_name,(parent_rows->0->>'symbol_count')::int n,
      jsonb_array_length(children_rows) sy,
      jsonb_array_length(signals_rows) si,
      jsonb_array_length(features_rows) fe,
      jsonb_array_length(readiness_rows) re
    FROM public.qa_atomic_scale_fixtures_v01
    WHERE case_name LIKE 'QA_E6MS_%'
  LOOP
    IF v.n NOT IN (30,50,61) OR v.n<>v.sy OR v.n<>v.si
       OR v.n<>v.fe OR v.n<>v.re THEN
      RAISE EXCEPTION 'QA_E6_MS_BAD_FIXTURE_%',v.case_name;
    END IF;
  END LOOP;
  IF (SELECT count(*) FROM public.qa_atomic_scale_fixtures_v01
      WHERE case_name LIKE 'QA_E6MS_%')<>6 THEN
    RAISE EXCEPTION 'QA_E6_MS_MISSING_FIXTURES';
  END IF;
END $validate$;

CREATE OR REPLACE FUNCTION public.qa_e6_ms_delay_v01()
RETURNS trigger LANGUAGE plpgsql AS $delay$
BEGIN
  IF new.run_id LIKE 'QA_E6MS_%' AND new.symbol='T001USDT' THEN
    PERFORM pg_catalog.pg_sleep(3);
  END IF;
  RETURN new;
END $delay$;
CREATE TRIGGER qa_e6_ms_delay_v01
AFTER INSERT ON public.alpha_hunter_symbol_snapshots
FOR EACH ROW EXECUTE FUNCTION public.qa_e6_ms_delay_v01();
"""

VERIFY_SQL = r"""
DO $verify$
DECLARE v record;
  receipt jsonb;
  before_events bigint;
BEGIN
  IF current_database()<>'isolated_atomic_scan_qa'
     OR current_user<>'postgres' THEN
    RAISE EXCEPTION 'QA_E6_MS_WRONG_DISPOSABLE_DB';
  END IF;
  FOR v IN SELECT case_name,parent_rows,children_rows,signals_rows,
                  features_rows,readiness_rows,
                  (parent_rows->0->>'run_id') AS run_id,
                  (parent_rows->0->>'symbol_count')::int n
           FROM public.qa_atomic_scale_fixtures_v01
           WHERE case_name LIKE 'QA_E6MS_%'
           ORDER BY case_name
  LOOP
    IF (SELECT count(*) FROM public.alpha_hunter_snapshots
        WHERE run_id=v.run_id)<>1
       OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots
        WHERE run_id=v.run_id)<>v.n
       OR (SELECT count(*) FROM public.alpha_hunter_signals
        WHERE run_id=v.run_id)<>v.n
       OR (SELECT count(*) FROM public.alpha_hunter_signal_features
        WHERE run_id=v.run_id)<>v.n
       OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01
        WHERE run_id=v.run_id)<>v.n
       OR (SELECT count(*) FROM public.qa_atomic_trigger_events
        WHERE run_id=v.run_id)<>(1+5*v.n)
       OR (SELECT version FROM public.alpha_hunter_snapshots
        WHERE run_id=v.run_id)<>(v.parent_rows->0->>'version')
    THEN RAISE EXCEPTION 'QA_E6_MS_INCOMPLETE_OR_DUPLICATE_%',v.case_name; END IF;

    SELECT count(*) INTO before_events FROM public.qa_atomic_trigger_events
      WHERE run_id=v.run_id;
    receipt:=public.alpha_hunter_commit_core_scan_v01(
       v.parent_rows,v.children_rows,v.signals_rows,
       v.features_rows,v.readiness_rows);
    IF receipt->>'committed'<>'true'
       OR receipt->>'run_id'<>v.run_id
       OR (receipt->>'parent_count')::int<>1
       OR (receipt->>'symbol_count')::int<>v.n
       OR (receipt->>'signal_count')::int<>v.n
       OR (receipt->>'feature_count')::int<>v.n
       OR (receipt->>'readiness_count')::int<>v.n
       OR (SELECT count(*) FROM public.qa_atomic_trigger_events
           WHERE run_id=v.run_id)<>before_events
    THEN RAISE EXCEPTION 'QA_E6_MS_REPLAY_OR_RECEIPT_INVALID_%',v.case_name; END IF;
  END LOOP;
  RAISE NOTICE 'PASS: 30/50/61 real overlapping sessions preserve exactly once full core scan and synthetic effects';
END $verify$;
DROP TRIGGER qa_e6_ms_delay_v01 ON public.alpha_hunter_symbol_snapshots;
DROP FUNCTION public.qa_e6_ms_delay_v01();
"""


def run_checked(sql, timeout=25):
    return subprocess.run(
        ["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
        text=True, capture_output=True, timeout=timeout, check=True,
    ).stdout.strip()


def guard():
    for k, expected in CONTAINERLESS_CI_ENV.items():
        if os.environ.get(k) != expected:
            raise RuntimeError(f"REFUSED: isolated PG17 only: {k}")
    if run_checked("SELECT current_database(),current_user", 8) != (
        "isolated_atomic_scan_qa|postgres"
    ):
        raise RuntimeError("REFUSED: PostgreSQL identity is not disposable QA")


def subprocess_rpc(sql, label):
    env = dict(os.environ, PGAPPNAME=label)
    return subprocess.Popen(
        ["psql", "-X", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )


def wait_until(query, process, label, duration=2.8):
    end = time.monotonic() + duration
    while time.monotonic() < end:
        if process.poll() is not None:
            raise AssertionError(f"{label}: ended before contention observed")
        if int(run_checked(query, 5)) > 0:
            return
        time.sleep(0.05)
    raise AssertionError(f"{label}: expected PG wait not observed")


def rpc_sql(case, conflict=False):
    parent = (
        "jsonb_set(parent_rows,'{0,version}',"
        "to_jsonb('QA_E6_MS_CONFLICT_VERSION'::text))"
        if conflict else "parent_rows"
    )
    return (
        "SELECT public.alpha_hunter_commit_core_scan_v01("
        f"{parent},children_rows,signals_rows,features_rows,readiness_rows)"
        " FROM public.qa_atomic_scale_fixtures_v01 "
        f"WHERE case_name='{case}'"
    )


def receipt(output, size, title):
    try:
        val = json.loads(output.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{title}: invalid JSON receipt") from exc
    expected = {
        "committed": True, "run_id": title,
        "parent_count": 1, "symbol_count": size,
        "signal_count": size, "feature_count": size,
        "readiness_count": size,
    }
    for key, want in expected.items():
        if val.get(key) != want:
            raise AssertionError(f"{title}: wrong {key} in receipt")
    return val


def exercise(size, mode):
    case = f"QA_E6MS_{size}_{mode}"
    name1 = f"AHQA_MS_{size}_{mode}_FIRST"
    name2 = f"AHQA_MS_{size}_{mode}_SECOND"
    a = subprocess_rpc(rpc_sql(case), name1)
    b = None
    try:
        wait_until(
            "SELECT count(*) FROM pg_stat_activity "
            f"WHERE application_name='{name1}' AND wait_event='PgSleep'",
            a, f"{case} first nested trigger",
        )
        b = subprocess_rpc(rpc_sql(case, conflict=mode=="CONFLICT"), name2)
        wait_until(
            "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid "
            f"WHERE a.application_name='{name2}' AND l.locktype='advisory' AND NOT l.granted",
            b, f"{case} second advisory lock",
        )
        output1, error1 = a.communicate(timeout=20)
        output2, error2 = b.communicate(timeout=20)
        if a.returncode:
            raise AssertionError(f"{case}: first transaction failed: {error1[-250:]}")
        val1 = receipt(output1, size, case)
        if mode == "CONFLICT":
            if b.returncode == 0:
                raise AssertionError(f"{case}: conflicting writer incorrectly committed")
            if "core scan persisted content mismatch for alpha_hunter_snapshots" not in error2:
                raise AssertionError(f"{case}: conflict rejected for unexpected reason")
        else:
            if b.returncode:
                raise AssertionError(f"{case}: identical retry failed: {error2[-250:]}")
            if val1 != receipt(output2, size, case):
                raise AssertionError(f"{case}: identical retry changed receipt")
        print(f"PASS: {size} symbols, concurrent {mode.lower()} writers serialized")
    finally:
        for process in (a,b):
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


def main():
    guard()
    run_checked(SETUP_SQL, 30)
    for size in SIZES:
        for mode in CASES:
            exercise(size, mode)
    run_checked(VERIFY_SQL, 30)
    print("PASS: disposable PostgreSQL 17 30/50/61 concurrency plus duplicate-free replay")
    print("NOT_CERTIFIED: private schema, production trigger parity, performance p95/p99, DBA/security")


if __name__ == "__main__":
    main()
