-- ALPHA HUNTER — READ-ONLY CORE SCAN FAILURE TAXONOMY V01
-- Run against the live PostgreSQL catalog ONLY as SELECT. No writes, locks,
-- trigger execution, historical repair, row mutation or trading action.
-- PARENT_ONLY and READINESS_MISSING are distinct incomplete-write signatures.
-- Scan error_count counts upstream symbol errors, NOT database write failures.
-- 24 recent parents; child lookups are scoped by run_id (verify indexed paths).
-- This validates only core families, NOT downstream paper-trading evidence.
with recent as (
    select run_id, collected_at_utc, symbol_count, error_count,
           payload->>'_storage_contract' as parent_storage_contract
    from public.alpha_hunter_snapshots
    order by collected_at_utc desc limit 24
),
scans as (
    select r.*,
        (select count(*) from public.alpha_hunter_symbol_snapshots c
         where c.run_id = r.run_id) as symbol_rows,
        (select count(*) from public.alpha_hunter_signals s
         where s.run_id = r.run_id) as signal_rows,
        (select count(*) from public.alpha_hunter_signal_features f
         where f.run_id = r.run_id) as feature_rows,
        (select count(*) from public.alpha_hunter_readiness_observations_v01 o
         where o.run_id = r.run_id) as readiness_rows,
        (select count(*) from public.alpha_hunter_signal_features f
         where f.run_id = r.run_id and not exists (
             select 1 from public.alpha_hunter_signals s
             where s.run_id = f.run_id and s.signal_id = f.signal_id
               and s.symbol = f.symbol
         )) as orphan_features,
        (select count(*) from public.alpha_hunter_readiness_observations_v01 o
         where o.run_id = r.run_id and not exists (
             select 1 from public.alpha_hunter_symbol_snapshots c
             where c.run_id = o.run_id and c.symbol = o.symbol
         )) as orphan_readiness
    from recent r
),
classified as (
    select *,
        case
            when error_count <> 0 then 'SCAN_SYMBOL_ERRORS'
            when symbol_rows = symbol_count
              and signal_rows = symbol_count
              and feature_rows = symbol_count
              and readiness_rows = symbol_count
              and orphan_features = 0 and orphan_readiness = 0
              then 'CORE_PASS'
            when symbol_count > 0
              and symbol_rows = 0 and signal_rows = 0
              and feature_rows = 0 and readiness_rows = 0
              then 'PARENT_ONLY'
            when symbol_count > 0
              and symbol_rows = symbol_count
              and signal_rows = symbol_count
              and feature_rows = symbol_count
              and readiness_rows = 0
              and orphan_features = 0 then 'READINESS_MISSING'
            else 'OTHER_INCOMPLETE'
        end as failure_category
    from scans
)
select run_id, collected_at_utc, symbol_count, error_count,
       symbol_rows, signal_rows, feature_rows, readiness_rows,
       orphan_features, orphan_readiness,
       coalesce(parent_storage_contract,'UNVERSIONED') as parent_storage_contract,
       failure_category
from classified
order by collected_at_utc desc;
