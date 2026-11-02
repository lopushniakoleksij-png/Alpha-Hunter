"""P0 disposable PG16/17 production-count trigger-shape benchmark.

No production network, no secrets, no Supabase URL, no exchange, no positions.
Synthetic rows approximate count and 10 strategies, NOT exact production payload
width, permissions, planner data distribution, downstream complete trigger code,
or production concurrency. Outputs inspectable metrics, never signs off release.
"""
import json
import math
import os
import pathlib
import statistics
import time

import psycopg
from psycopg.types.json import Jsonb

OUTCOMES = 453263
HIST_OBSERVATIONS = 1640424
SYMBOLS = 62
STRATEGIES = 10
SCHEMA = "ah_p0_benchmark_local"
DSN = os.environ.get("AH_LOCAL_BENCH_PG_DSN", "")
OUT = pathlib.Path(os.environ.get("AH_BENCH_OUTPUT_DIR", "/tmp/ah-bench-evidence"))


def verify_isolated_dsn():
    if (os.getenv("AH_LOCAL_PG_BENCH_ONLY") != "1"
            or "host=127.0.0.1" not in DSN
            or "dbname=postgres" not in DSN
            or "password=isolated-only" not in DSN):
        raise RuntimeError("Refuse all database targets other than isolated local GitHub PG fixture")


def main():
    verify_isolated_dsn()
    OUT.mkdir(parents=True, exist_ok=True)
    report={"status":"UNVERIFIED_UNTIL_FULL_LOCAL_BENCHMARK_PASS",
            "test_kind":"PRODUCTION_ROW_COUNTS_SYNTHETIC_TRIGGER_SHAPE_NOT_FULL_SCHEMA",
            "release_approval":False,"production_mutation":False,
            "historical_reclassification":False,"trade_permission":False,
            "pg_major":None, "row_counts_expected":{
                "forward_outcomes":OUTCOMES,"historical_strategy_observations":HIST_OBSERVATIONS,
                "scan_symbols":SYMBOLS,"strategies_each":STRATEGIES}}
    with psycopg.connect(DSN,autocommit=True) as conn:
        ver=int(conn.execute("SHOW server_version_num").fetchone()[0])
        if ver//10000 not in (16,17):
            raise RuntimeError("Only PG16/17 ephemeral benchmark accepted")
        report["pg_major"]=ver//10000
        conn.execute("SET statement_timeout='15000ms'")
        conn.execute("DROP SCHEMA IF EXISTS ah_p0_benchmark_local CASCADE")
        conn.execute("CREATE SCHEMA ah_p0_benchmark_local")
        try:
            conn.execute("""
              CREATE TABLE ah_p0_benchmark_local.forward_outcomes(
                episode bigint PRIMARY KEY, strategy_id text NOT NULL,
                horizon_hours integer NOT NULL, direction text NOT NULL,
                entry_status text NOT NULL, quality text NOT NULL,
                ordering_ambiguous boolean NOT NULL, evaluated_at timestamptz NOT NULL,
                mae double precision, mfe double precision)
            """)
            conn.execute("""
              INSERT INTO ah_p0_benchmark_local.forward_outcomes
              SELECT g, 'S'||(g%10)::text, 24,
                 CASE WHEN g%2=0 THEN 'SHORT' ELSE 'LONG' END,
                 CASE WHEN g%17=0 THEN 'TRIGGERED_EXECUTE_NOW' ELSE 'NOT_TRIGGERED' END,
                 CASE WHEN g%7=0 THEN 'COMPLETE_ENOUGH' ELSE 'INCOMPLETE' END,
                 g%23=0, timestamptz '2026-10-01+00' + (g*interval '1 seconds'),
                 (g%1300)::double precision/1000,(g%2000)::double precision/1000
              FROM generate_series(1,453263) AS g
            """)
            conn.execute("""
              CREATE TABLE ah_p0_benchmark_local.history_observations(
                observation_id bigint PRIMARY KEY, strategy_id text NOT NULL,
                observed_at timestamptz NOT NULL,
                evidence jsonb NOT NULL)
            """)
            conn.execute("""
              INSERT INTO ah_p0_benchmark_local.history_observations
              SELECT g,'S'||(g%10)::text,
                timestamptz '2026-10-01+00'+(g*interval '1 seconds'),
                jsonb_build_object('quality','synthetic','score',g%100,'trade_permission',false)
              FROM generate_series(1,1640424) AS g
            """)
            conn.execute("ANALYZE ah_p0_benchmark_local.forward_outcomes")
            conn.execute("ANALYZE ah_p0_benchmark_local.history_observations")
            def payoff_query():
                return conn.execute("""
                   SELECT count(*),
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY mae),
                    percentile_cont(0.90) WITHIN GROUP (ORDER BY mfe)
                   FROM ah_p0_benchmark_local.forward_outcomes
                   WHERE horizon_hours=24
                     AND strategy_id='S2'
                     AND direction='SHORT'
                     AND entry_status='TRIGGERED_EXECUTE_NOW'
                     AND quality='COMPLETE_ENOUGH'
                     AND ordering_ambiguous=false
                     AND evaluated_at <= timestamptz '2026-11-02 11:20+00'
                     AND mae IS NOT NULL AND mfe IS NOT NULL
                """).fetchone()
            s=time.perf_counter()
            baseline=payoff_query()
            report["unindexed_percentile_ms"]=round((time.perf_counter()-s)*1000,3)
            conn.execute("""
               CREATE INDEX idx_ah_p0_payoff_partial
               ON ah_p0_benchmark_local.forward_outcomes(strategy_id,direction,evaluated_at)
               INCLUDE (mae,mfe)
               WHERE horizon_hours=24
                 AND entry_status='TRIGGERED_EXECUTE_NOW'
                 AND quality='COMPLETE_ENOUGH'
                 AND ordering_ambiguous=false
                 AND mae IS NOT NULL AND mfe IS NOT NULL
            """)
            conn.execute("ANALYZE ah_p0_benchmark_local.forward_outcomes")
            s=time.perf_counter();indexed=payoff_query()
            report["indexed_percentile_ms"]=round((time.perf_counter()-s)*1000,3)
            if baseline != indexed:
                raise AssertionError("Index changed percentile value")
            report["percentile_result_parity"]=True

            conn.execute("""
              CREATE TABLE ah_p0_benchmark_local.symbol_children(
                 run_id text NOT NULL,symbol text NOT NULL,payload jsonb NOT NULL,
                 PRIMARY KEY(run_id,symbol))
            """)
            conn.execute("""
              CREATE TABLE ah_p0_benchmark_local.scan_observations(
                 observation_id text PRIMARY KEY,run_id text NOT NULL,
                 symbol text NOT NULL,strategy_id text NOT NULL)
            """)
            conn.execute("""
              CREATE TABLE ah_p0_benchmark_local.scan_episodes(
                 episode_id text PRIMARY KEY,symbol text NOT NULL,strategy_id text NOT NULL)
            """)
            conn.execute("""
              CREATE FUNCTION ah_p0_benchmark_local.per_observation()
              RETURNS trigger LANGUAGE plpgsql AS $$
              DECLARE v numeric;
              BEGIN
                SELECT percentile_cont(0.5) WITHIN GROUP(ORDER BY mae)
                INTO v FROM ah_p0_benchmark_local.forward_outcomes
                WHERE horizon_hours=24
                   AND strategy_id=NEW.strategy_id
                   AND direction='SHORT'
                   AND entry_status='TRIGGERED_EXECUTE_NOW'
                   AND quality='COMPLETE_ENOUGH'
                   AND ordering_ambiguous=false
                   AND mae IS NOT NULL AND mfe IS NOT NULL;
                RETURN NEW;
              END $$;
            """)
            conn.execute("""
              CREATE TRIGGER trg_nested_percentile AFTER INSERT
              ON ah_p0_benchmark_local.scan_observations FOR EACH ROW
              EXECUTE FUNCTION ah_p0_benchmark_local.per_observation()
            """)
            conn.execute("""
              CREATE FUNCTION ah_p0_benchmark_local.per_symbol()
              RETURNS trigger LANGUAGE plpgsql AS $$
              DECLARE v jsonb; id text;
              BEGIN
                FOR v IN SELECT value FROM jsonb_array_elements(
                     NEW.payload->'multi_strategy_engine'->'strategies')
                LOOP
                  id := md5(NEW.run_id||NEW.symbol||(v->>'strategy_id'));
                  INSERT INTO ah_p0_benchmark_local.scan_observations
                      (observation_id,run_id,symbol,strategy_id)
                  VALUES(id,NEW.run_id,NEW.symbol,v->>'strategy_id')
                  ON CONFLICT DO NOTHING;
                  INSERT INTO ah_p0_benchmark_local.scan_episodes
                      (episode_id,symbol,strategy_id)
                  VALUES(md5(NEW.symbol||(v->>'strategy_id')),
                         NEW.symbol,v->>'strategy_id')
                  ON CONFLICT DO NOTHING;
                END LOOP;
                RETURN NEW;
              END $$;
            """)
            conn.execute("""
              CREATE TRIGGER trg_symbol_capture AFTER INSERT OR UPDATE OF payload
              ON ah_p0_benchmark_local.symbol_children FOR EACH ROW
              EXECUTE FUNCTION ah_p0_benchmark_local.per_symbol()
            """)
            strategies=[{"strategy_id":"S"+str(i),"status":"WATCH","direction":"SHORT"}
                        for i in range(STRATEGIES)]
            batch_times=[]
            def write_chunk(indices):
                placeholders=",".join(["(%s,%s,%s)"]*len(indices))
                args=[]
                for i in indices:
                    args.extend(("synthetic-run","TEST%03dUSDT"%i,
                                 Jsonb({"symbol":"TEST%03dUSDT"%i,
                                        "multi_strategy_engine":{"strategies":strategies}})))
                sql=("INSERT INTO ah_p0_benchmark_local.symbol_children(run_id,symbol,payload) VALUES "
                     + placeholders + " ON CONFLICT(run_id,symbol) DO UPDATE SET payload=EXCLUDED.payload")
                t=time.perf_counter()
                conn.execute(sql,args)
                return (time.perf_counter()-t)*1000
            for k in range(0,32,8):
                batch_times.append(write_chunk(range(k,k+8)))
            conn.execute("""
              CREATE FUNCTION ah_p0_benchmark_local.cancel_33()
              RETURNS trigger LANGUAGE plpgsql AS $$
              BEGIN
                IF NEW.symbol='TEST032USDT' THEN
                   RAISE EXCEPTION 'synthetic 57014' USING ERRCODE='57014';
                END IF;
                RETURN NEW;
              END $$
            """)
            conn.execute("""
              CREATE TRIGGER a_cancel_33 BEFORE INSERT
              ON ah_p0_benchmark_local.symbol_children FOR EACH ROW
              EXECUTE FUNCTION ah_p0_benchmark_local.cancel_33()
            """)
            failed=False
            try:
                write_chunk(range(32,40))
            except psycopg.errors.QueryCanceled:
                failed=True
            if not failed: raise AssertionError("SQLSTATE 57014 injection not triggered")
            observed_partial=conn.execute(
                "SELECT count(*) FROM ah_p0_benchmark_local.symbol_children").fetchone()[0]
            if observed_partial!=32: raise AssertionError("failed batch committed unexpected children")
            conn.execute("DROP TRIGGER a_cancel_33 ON ah_p0_benchmark_local.symbol_children")
            for k in range(32,62,8):
                batch_times.append(write_chunk(range(k,min(k+8,62))))
            count=conn.execute(
                "SELECT count(*) FROM ah_p0_benchmark_local.symbol_children").fetchone()[0]
            obs=conn.execute(
                "SELECT count(*) FROM ah_p0_benchmark_local.scan_observations").fetchone()[0]
            ep=conn.execute(
                "SELECT count(*) FROM ah_p0_benchmark_local.scan_episodes").fetchone()[0]
            if (count,obs,ep)!=(SYMBOLS,SYMBOLS*STRATEGIES,SYMBOLS*STRATEGIES):
                raise AssertionError("nested child/strategy/episode census mismatch")
            s=time.perf_counter()
            write_chunk(range(0,8))
            report["replay_batch_ms"]=round((time.perf_counter()-s)*1000,2)
            obs2=conn.execute("SELECT count(*) FROM ah_p0_benchmark_local.scan_observations").fetchone()[0]
            if obs2!=obs:raise AssertionError("idempotent replay created extra observations")
            # No production credentials or schema used. Time measurements are
            # runner-specific and not a verified production p95/SLA.
            report.update({"sqlstate_57014_test":"PASS","partial_after_failure":observed_partial,
              "child_count":count,"new_strategy_observations":obs,"episode_count":ep,
              "batch_count":len(batch_times),"batch_p50_ms":round(statistics.median(batch_times),2),
              "batch_p95_ms":round(sorted(batch_times)[math.ceil(0.95*len(batch_times))-1],2),
              "batch_max_ms":round(max(batch_times),2),
              "index_rollback_test":"NOT_YET_DONE",
              "row_counts_actual":{
                "outcomes":conn.execute("SELECT count(*) FROM ah_p0_benchmark_local.forward_outcomes").fetchone()[0],
                "historical_observations":conn.execute("SELECT count(*) FROM ah_p0_benchmark_local.history_observations").fetchone()[0]},
              "synthetic_sizes_bytes":{
                "outcomes":conn.execute("SELECT pg_total_relation_size('ah_p0_benchmark_local.forward_outcomes')").fetchone()[0],
                "historical_observations":conn.execute("SELECT pg_total_relation_size('ah_p0_benchmark_local.history_observations')").fetchone()[0]}})
            if report["row_counts_actual"] != {
                "outcomes":OUTCOMES,"historical_observations":HIST_OBSERVATIONS}:
                raise AssertionError("benchmark row-count scale is not correct")
            conn.execute("DROP INDEX ah_p0_benchmark_local.idx_ah_p0_payoff_partial")
            report["index_rollback_test"]="PASS"
            report["status"]="PASS_SYNTHETIC_COUNT_SHAPE_ONLY"
        finally:
            conn.execute("DROP SCHEMA IF EXISTS ah_p0_benchmark_local CASCADE")
    (OUT/"benchmark.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,sort_keys=True))
    print("PRODUCTION-equivalent assurance: NOT ESTABLISHED; independent DBA approval: PENDING")


if __name__=="__main__":
    main()
