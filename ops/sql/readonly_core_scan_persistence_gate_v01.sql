-- READ-ONLY: production and isolated-acceptance evidence.
-- No writes, functions, DDL, privileges or trade execution.
-- Exactly five CORE evidence families; separate downstream paper-lifecycle
-- acceptance remains mandatory before calling an end-to-end scan complete.
with recent as (
  select run_id,collected_at_utc,symbol_count,error_count
  from public.alpha_hunter_snapshots
  order by collected_at_utc desc limit 12
),
counts as (
  select r.*,
    (select count(*) from public.alpha_hunter_symbol_snapshots c
     where c.run_id=r.run_id) as symbol_rows,
    (select count(*) from public.alpha_hunter_signals s
     where s.run_id=r.run_id) as signal_rows,
    (select count(*) from public.alpha_hunter_signal_features f
     where f.run_id=r.run_id) as feature_rows,
    (select count(*) from public.alpha_hunter_readiness_observations_v01 o
     where o.run_id=r.run_id) as readiness_rows,
    (select count(*) from public.alpha_hunter_signal_features f
     where f.run_id=r.run_id and not exists (
       select 1 from public.alpha_hunter_signals s
       where s.signal_id=f.signal_id and s.run_id=f.run_id and s.symbol=f.symbol
     )) as orphan_features,
    (select count(*) from public.alpha_hunter_readiness_observations_v01 o
     where o.run_id=r.run_id and not exists (
       select 1 from public.alpha_hunter_symbol_snapshots c
       where c.run_id=o.run_id and c.symbol=o.symbol
     )) as orphan_readiness
  from recent r
)
select
  run_id, collected_at_utc, symbol_count, error_count,
  symbol_rows,signal_rows,feature_rows,readiness_rows,
  orphan_features,orphan_readiness,
  case
    when error_count <> 0 then 'REVIEW_SCAN_ERRORS'
    when symbol_rows=symbol_count and signal_rows=symbol_count
      and feature_rows=symbol_count and readiness_rows=symbol_count
      and orphan_features=0 and orphan_readiness=0 then 'CORE_PASS'
    else 'CORE_FAIL'
  end as core_persistence_status
from counts
order by collected_at_utc desc;
