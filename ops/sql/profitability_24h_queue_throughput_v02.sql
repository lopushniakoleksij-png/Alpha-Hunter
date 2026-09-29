-- Alpha Hunter profitability 24H queue throughput v0.2
--
-- Operational throughput only. Reuses the already-tested bounded 30-row queue
-- collector three times per scheduled run. Scientific horizon, eligibility,
-- candle ordering, target/stop logic and trade permissions are unchanged.

create or replace function private.alpha_hunter_capture_strategy_24h_queue_burst_v02()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_pass integer;
  v_result jsonb;
  v_results jsonb:='[]'::jsonb;
begin
  for v_pass in 1..3 loop
    v_result:=private.alpha_hunter_capture_strategy_24h_queue_v01();
    v_results:=v_results||jsonb_build_array(v_result);
  end loop;

  return jsonb_build_object(
    'model_version','strategy-24h-queue-burst-v0.2',
    'passes',3,
    'max_rows_per_pass',30,
    'max_rows_per_run',90,
    'results',v_results,
    'paper_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_capture_strategy_24h_queue_burst_v02()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_capture_strategy_24h_queue_burst_v02()
to postgres;

select cron.alter_job(
  job_id := (
    select jobid
    from cron.job
    where jobname='alpha-hunter-strategy-24h-profitability-catchup-v01'
  ),
  schedule := '1,14,26,35 * * * *',
  command := 'select private.alpha_hunter_capture_strategy_24h_queue_burst_v02();',
  active := true
);
