-- P0 review-only PostgREST symbol-persistence write pressure.
-- SELECT ONLY; do not reset statistics, change timeouts, touch triggers, or deploy.
-- pg_stat_statements metrics are cumulative since last statistics reset, not "today".
WITH symbol_upsert AS (
 SELECT count(*)::bigint matching_statement_shapes,
        COALESCE(sum(calls),0)::bigint total_calls,
        round((sum(total_exec_time)/nullif(sum(calls),0))::numeric,1) weighted_mean_ms,
        round(max(max_exec_time)::numeric,1) max_observed_ms,
        COALESCE(sum(temp_blks_written),0)::bigint temp_blocks_written,
        COALESCE(sum(wal_bytes),0)::numeric total_wal_bytes,
        COALESCE(sum(shared_blks_read),0)::bigint shared_blocks_read
 FROM extensions.pg_stat_statements
 WHERE query LIKE '%INSERT INTO "public"."alpha_hunter_symbol_snapshots"%'
), table_sizes AS (
 SELECT pg_total_relation_size('public.alpha_hunter_symbol_snapshots'::regclass)::bigint symbol_total_bytes,
        pg_total_relation_size('public.alpha_hunter_strategy_observations_v01'::regclass)::bigint strategy_observation_total_bytes,
        (
          pg_total_relation_size('public.alpha_hunter_symbol_snapshots'::regclass)
          - pg_relation_size('public.alpha_hunter_symbol_snapshots'::regclass)
          - pg_indexes_size('public.alpha_hunter_symbol_snapshots'::regclass)
        )::bigint symbol_toast_and_other_bytes
), trailing_strategies AS (
 SELECT count(*)::bigint strategy_observation_rows,
        count(distinct run_id)::bigint canonical_runs_with_strategy_rows,
        count(distinct (run_id,symbol))::bigint distinct_symbol_runs,
        round(count(*)::numeric/nullif(count(distinct(run_id,symbol)),0),2) strategies_per_symbol_run
 FROM public.alpha_hunter_strategy_observations_v01
 WHERE observed_at_utc>=now()-interval '24 hours'
), trigger_state AS (
 SELECT count(*) FILTER (WHERE tgname='trg_ah_capture_strategy_observations_v01' AND tgenabled='O')::bigint active_symbol_strategy_triggers
 FROM pg_trigger WHERE tgrelid='public.alpha_hunter_symbol_snapshots'::regclass
 AND NOT tgisinternal
)
SELECT now() AT TIME ZONE 'utc' audited_at_utc,
 s.*,b.*,t.*,g.*,
 (SELECT unnest(rolconfig) FROM pg_roles WHERE rolname='service_role'
    AND EXISTS(SELECT 1 FROM unnest(rolconfig) cfg WHERE cfg LIKE 'statement_timeout=%')
    LIMIT 1) service_role_statement_timeout_config,
 'READ_ONLY_DIAGNOSTIC_NOT_PROOF_OF_TRIGGER_EXCLUSIVE_CAUSE'::text evidence_class
FROM symbol_upsert s CROSS JOIN table_sizes b CROSS JOIN trailing_strategies t CROSS JOIN trigger_state g;
