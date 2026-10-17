-- READ ONLY, NO UNSEAL, NO PRIMARY SCIENTIFIC OUTCOMES.
-- No production changes, no cron ALTER/UNSCHEDULE, no invoking evaluator.
-- Compare operational aggregates ONLY. Counts are binding/horizon SETS
-- (not 4 variant rows per set; not independently executable trades).

-- 1. Frozen study identity/summary. This status is metadata-only.
select spec_id,registered_at_utc,collection_ends_at_utc,scientific_status,
       captured,eligible,excluded,primary_results_exposed,
       complete_binding_horizon_sets,sealed_rows,evaluator_failure_events,
       latest_evaluated_at_utc,scientific_conclusion,trade_permission,
       production_promotion_permitted
from public.alpha_hunter_geometry_holdout_collection_status_v01;

-- 2. Independently count due sets via original decision timestamps.
-- It does not infer outcomes or access any sealed table.
with eligible as (
 select binding_id,decision_available_at_utc
 from public.alpha_hunter_geometry_holdout_bindings
 where spec_id='AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01'
   and group_name='ELIGIBLE'
), due as (
 select h.horizon_hours,count(*) as possible,
        count(*) filter(where decision_available_at_utc+
          make_interval(hours=>h.horizon_hours)+interval '5 minutes'<=now()) as due,
        count(*) filter(where decision_available_at_utc+
          make_interval(hours=>h.horizon_hours)+interval '6 hours'<=now()) as due_plus_six_hours
 from eligible cross join (values(12),(24)) h(horizon_hours)
 group by h.horizon_hours
)
select now() as inspected_utc,horizon_hours,possible,due,due_plus_six_hours
from due order by horizon_hours;

-- 3. Prospective intake over fixed previous 7 calendar days of UTC time.
select count(*) as eligible_added_last_7d
from public.alpha_hunter_geometry_holdout_bindings
where spec_id='AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01'
  and group_name='ELIGIBLE'
  and decision_available_at_utc >= now()-interval '7 days';

-- 4. READ scheduler settings; do not execute scheduling or evaluator.
select jobname,schedule,active,
       position('limit 40' in lower(pg_get_functiondef(
         'private.alpha_hunter_run_geometry_holdout_sealed_v01()'::regprocedure
       )))>0 as max_40_in_sql
from cron.job
where jobname='alpha-hunter-geometry-holdout-sealed-hourly';

-- 5. Actual cron status; successful invocation does NOT prove a set completed.
select j.jobname,count(d.runid) as total_runs,
       count(d.runid) filter(where d.status='succeeded') as succeeded,
       count(d.runid) filter(where d.status<>'succeeded') as non_success,
       max(d.start_time) as latest_run_utc
from cron.job j left join cron.job_run_details d on d.jobid=j.jobid
where j.jobname='alpha-hunter-geometry-holdout-sealed-hourly'
group by j.jobname;
