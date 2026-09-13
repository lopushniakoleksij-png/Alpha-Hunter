-- Alpha Hunter cloud production control plane v0.3 upgrade
-- Adds exact-stage, cost-evidence and portfolio-risk veto stages while preserving
-- historical 4-stage and 5-stage control-run evidence.

alter table public.alpha_hunter_control_plane_runs
  alter column expected_stage_count set default 7;
alter table public.alpha_hunter_control_plane_runs
  drop constraint if exists alpha_hunter_control_plane_runs_expected_stage_count_check;
alter table public.alpha_hunter_control_plane_runs
  add constraint alpha_hunter_control_plane_runs_expected_stage_count_check
  check (expected_stage_count in (4,5,7));

alter table public.alpha_hunter_control_plane_step_events
  drop constraint if exists alpha_hunter_control_plane_step_events_stage_name_check;
alter table public.alpha_hunter_control_plane_step_events
  add constraint alpha_hunter_control_plane_step_events_stage_name_check
  check (stage_name in ('ANSWER_KEY','PARENT_DIRECTION','MONEY_ENTRY_BRIDGE','MONEY_ENTRY_STAGE','MONEY_SCORECARD','COST_EVIDENCE','PORTFOLIO_RISK'));
alter table public.alpha_hunter_control_plane_step_events
  drop constraint if exists alpha_hunter_control_plane_step_events_stage_order_check;
alter table public.alpha_hunter_control_plane_step_events
  add constraint alpha_hunter_control_plane_step_events_stage_order_check check (stage_order between 1 and 7);

create or replace function private.alpha_hunter_run_controlled_stage(p_stage text,p_reference_at timestamptz default clock_timestamp())
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_control_run_id text;v_hour timestamptz;v_stage text:=upper(p_stage);v_stage_order integer;v_prev_stage text;v_attempt integer;
  v_started timestamptz;v_finished timestamptz;v_result jsonb:='{}'::jsonb;v_status text:='PASS';v_error text;v_source_run_id text;
  v_existing record;v_prev_ok boolean:=true;v_event_id text;
begin
  select i.control_run_id,i.scheduled_hour_utc into v_control_run_id,v_hour
  from private.alpha_hunter_control_plane_identity(p_reference_at) i;

  v_stage_order:=case v_stage
    when 'ANSWER_KEY' then 1
    when 'PARENT_DIRECTION' then 2
    when 'MONEY_ENTRY_BRIDGE' then 3
    when 'MONEY_ENTRY_STAGE' then 4
    when 'MONEY_SCORECARD' then 5
    when 'COST_EVIDENCE' then 6
    when 'PORTFOLIO_RISK' then 7
    else null end;
  if v_stage_order is null then raise exception 'unsupported Alpha Hunter controlled stage: %',p_stage;end if;

  v_prev_stage:=case v_stage_order
    when 2 then 'ANSWER_KEY'
    when 3 then 'PARENT_DIRECTION'
    when 4 then 'MONEY_ENTRY_BRIDGE'
    when 5 then 'MONEY_ENTRY_STAGE'
    when 6 then 'MONEY_SCORECARD'
    when 7 then 'COST_EVIDENCE'
    else null end;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_control_run_id||'|'||v_stage,0));

  insert into public.alpha_hunter_control_plane_runs(
    control_run_id,scheduled_hour_utc,started_at_utc,overall_status,expected_stage_count,release_version,payload
  ) values(
    v_control_run_id,v_hour,clock_timestamp(),'RUNNING',7,'cloud-control-plane-v0.3-production-gates',
    jsonb_build_object('execution_mode','PHONE_CLOUD','canonical_hour',v_hour)
  ) on conflict(control_run_id) do nothing;

  select s.* into v_existing
  from public.alpha_hunter_control_plane_step_events s
  where s.control_run_id=v_control_run_id and s.stage_name=v_stage and s.status in('PASS','DEGRADED')
  order by s.attempt_no desc limit 1;
  if found then
    return jsonb_build_object(
      'mode','ALPHA_HUNTER_CONTROLLED_STAGE','control_run_id',v_control_run_id,'stage',v_stage,
      'status',v_existing.status,'deduplicated',true,'source_run_id',v_existing.source_run_id,
      'result',v_existing.result_payload,'shadow_only',true,'trade_permission',false
    );
  end if;

  if v_prev_stage is not null then
    select exists(
      select 1 from public.alpha_hunter_control_plane_step_events s
      where s.control_run_id=v_control_run_id and s.stage_name=v_prev_stage and s.status in('PASS','DEGRADED')
    ) into v_prev_ok;
  end if;

  select coalesce(max(s.attempt_no),0)+1 into v_attempt
  from public.alpha_hunter_control_plane_step_events s
  where s.control_run_id=v_control_run_id and s.stage_name=v_stage;
  v_started:=clock_timestamp();

  if not v_prev_ok then
    v_status:='SKIPPED';v_error:='PREDECESSOR_NOT_SUCCESSFUL:'||v_prev_stage;v_result:=jsonb_build_object('reason',v_error);
  else
    begin
      case v_stage
        when 'ANSWER_KEY' then
          v_result:=public.alpha_hunter_collect_big_mover_answer_key();
          v_source_run_id:=v_result#>>'{scoring,latest_feature_run_id}';
          if coalesce((v_result->>'ticker_count')::integer,0)<=0 then v_status:='FAILED';v_error:='NO_BITGET_TICKERS_RETURNED';end if;
        when 'PARENT_DIRECTION' then
          v_result:=private.alpha_hunter_collect_big_mover_parent_direction();v_source_run_id:=v_result->>'run_id';
          if coalesce((v_result->>'failed_rows')::integer,0)>0 then v_status:='DEGRADED';end if;
        when 'MONEY_ENTRY_BRIDGE' then
          v_result:=private.alpha_hunter_run_big_mover_money_entry_pipeline();v_source_run_id:=v_result->>'run_id';
        when 'MONEY_ENTRY_STAGE' then
          v_result:=private.alpha_hunter_capture_money_entry_stage_snapshots(v_control_run_id);v_source_run_id:=v_result->>'run_id';
          if coalesce(v_result->>'threshold_status','')='NO_ACTIVE_VALIDATED_THRESHOLD_SET' then v_status:='DEGRADED';end if;
        when 'MONEY_SCORECARD' then
          v_result:=private.alpha_hunter_run_big_mover_money_scorecard();
          select r.source_run_id into v_source_run_id from public.alpha_hunter_control_plane_runs r where r.control_run_id=v_control_run_id;
          if coalesce((v_result->>'retryable_errors')::integer,0)>0 then v_status:='DEGRADED';end if;
        when 'COST_EVIDENCE' then
          v_result:=private.alpha_hunter_capture_execution_cost_evidence(v_control_run_id);v_source_run_id:=v_result->>'run_id';
          if coalesce(v_result->>'cost_model_status','')<>'ACTIVE_VALIDATED_COST_MODEL' then v_status:='DEGRADED';end if;
        when 'PORTFOLIO_RISK' then
          v_result:=private.alpha_hunter_assess_portfolio_risk(v_control_run_id);v_source_run_id:=v_result->>'run_id';
          if coalesce(v_result->>'risk_policy_status','')<>'ACTIVE_VALIDATED_RISK_POLICY'
             or coalesce(v_result->>'account_state_status','')<>'CONNECTED_READ_ONLY_COMPLETE'
             or coalesce(v_result->>'position_ledger_status','')<>'VERIFIED_SNAPSHOT' then v_status:='DEGRADED';end if;
      end case;

      if coalesce(v_result->>'trade_permission','false')<>'false'
         or coalesce(v_result->>'shadow_only','true')<>'true' then
        v_status:='FAILED';v_error:=coalesce(v_error||';','')||'SAFETY_BOUNDARY_VIOLATION_IN_STAGE_RESULT';
      end if;
      if v_stage='PORTFOLIO_RISK' and coalesce(v_result->>'execution_authorized','false')<>'false' then
        v_status:='FAILED';v_error:=coalesce(v_error||';','')||'RISK_ENGINE_AUTHORIZATION_BOUNDARY_VIOLATION';
      end if;
    exception when others then
      v_status:='FAILED';v_error:=left(sqlerrm,1000);v_result:=jsonb_build_object('exception',v_error);
    end;
  end if;

  v_finished:=clock_timestamp();
  v_event_id:=md5(v_control_run_id||'|'||v_stage||'|'||v_attempt::text||'|'||v_started::text);
  insert into public.alpha_hunter_control_plane_step_events(
    step_event_id,control_run_id,stage_name,stage_order,attempt_no,status,started_at_utc,finished_at_utc,duration_ms,
    source_run_id,result_payload,error,shadow_only,trade_permission
  ) values(
    v_event_id,v_control_run_id,v_stage,v_stage_order,v_attempt,v_status,v_started,v_finished,
    extract(epoch from(v_finished-v_started))*1000.0,v_source_run_id,coalesce(v_result,'{}'::jsonb),v_error,true,false
  );

  update public.alpha_hunter_control_plane_runs r
  set source_run_id=case when r.source_run_id is null then v_source_run_id else r.source_run_id end,
      updated_at=clock_timestamp(),payload=r.payload||jsonb_build_object('last_stage',v_stage,'last_stage_status',v_status)
  where r.control_run_id=v_control_run_id;

  return jsonb_build_object(
    'mode','ALPHA_HUNTER_CONTROLLED_STAGE','control_run_id',v_control_run_id,'stage',v_stage,'status',v_status,
    'attempt',v_attempt,'deduplicated',false,'source_run_id',v_source_run_id,'error',v_error,'result',v_result,
    'shadow_only',true,'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_run_controlled_stage(text,timestamptz) from public,anon,authenticated;
grant execute on function private.alpha_hunter_run_controlled_stage(text,timestamptz) to service_role;

create or replace function private.alpha_hunter_finalize_control_plane_hour(p_reference_at timestamptz default clock_timestamp())
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_control_run_id text;v_hour timestamptz;v_expected_count integer;v_pass integer:=0;v_degraded integer:=0;v_failed integer:=0;v_skipped integer:=0;
  v_missing jsonb:='[]'::jsonb;v_warnings jsonb:='[]'::jsonb;v_source_consistent boolean:=false;v_order_valid boolean:=false;
  v_latest_signal timestamptz;v_latest_answer timestamptz;v_latest_shadow timestamptz;v_freshness text:='DATA_INSUFFICIENT';v_safety text:='PASS';
  v_safety_violations integer:=0;v_status text;v_health_id text;v_incident_key text;v_should_incident boolean:=false;
  v_active_thresholds integer:=0;v_active_cost_models integer:=0;v_active_risk_policies integer:=0;v_verified_account integer:=0;
begin
  select i.control_run_id,i.scheduled_hour_utc into v_control_run_id,v_hour
  from private.alpha_hunter_control_plane_identity(p_reference_at) i;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_control_run_id||'|FINALIZE',0));

  insert into public.alpha_hunter_control_plane_runs(
    control_run_id,scheduled_hour_utc,started_at_utc,overall_status,expected_stage_count,release_version,payload
  ) values(
    v_control_run_id,v_hour,clock_timestamp(),'RUNNING',7,'cloud-control-plane-v0.3-production-gates',
    jsonb_build_object('execution_mode','PHONE_CLOUD','canonical_hour',v_hour)
  ) on conflict(control_run_id) do nothing;

  select r.expected_stage_count into v_expected_count from public.alpha_hunter_control_plane_runs r where r.control_run_id=v_control_run_id;

  with expected(stage_name,stage_order) as (
    select * from(values('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_ENTRY_STAGE',4),('MONEY_SCORECARD',5),('COST_EVIDENCE',6),('PORTFOLIO_RISK',7)) v(stage_name,stage_order) where v_expected_count=7
    union all select * from(values('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_ENTRY_STAGE',4),('MONEY_SCORECARD',5)) v(stage_name,stage_order) where v_expected_count=5
    union all select * from(values('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_SCORECARD',4)) v(stage_name,stage_order) where v_expected_count=4
  ),latest as(
    select distinct on(s.stage_name) s.* from public.alpha_hunter_control_plane_step_events s
    where s.control_run_id=v_control_run_id order by s.stage_name,s.attempt_no desc
  )
  select count(*) filter(where l.status='PASS'),count(*) filter(where l.status='DEGRADED'),count(*) filter(where l.status='FAILED'),
         count(*) filter(where l.status='SKIPPED'),
         coalesce(jsonb_agg(e.stage_name order by e.stage_order) filter(where l.stage_name is null or l.status not in('PASS','DEGRADED')),'[]'::jsonb)
  into v_pass,v_degraded,v_failed,v_skipped,v_missing
  from expected e left join latest l using(stage_name);

  with latest as(
    select distinct on(s.stage_name) s.* from public.alpha_hunter_control_plane_step_events s
    where s.control_run_id=v_control_run_id order by s.stage_name,s.attempt_no desc
  )
  select coalesce(count(distinct source_run_id) filter(where source_run_id is not null)<=1,false)
  into v_source_consistent from latest;

  with expected(stage_name,stage_order) as (
    select * from(values('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_ENTRY_STAGE',4),('MONEY_SCORECARD',5),('COST_EVIDENCE',6),('PORTFOLIO_RISK',7)) v(stage_name,stage_order) where v_expected_count=7
    union all select * from(values('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_ENTRY_STAGE',4),('MONEY_SCORECARD',5)) v(stage_name,stage_order) where v_expected_count=5
    union all select * from(values('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_SCORECARD',4)) v(stage_name,stage_order) where v_expected_count=4
  ),latest as(
    select distinct on(s.stage_name) s.* from public.alpha_hunter_control_plane_step_events s
    where s.control_run_id=v_control_run_id order by s.stage_name,s.attempt_no desc
  ),ordered as(
    select e.stage_order,l.finished_at_utc,lag(l.finished_at_utc) over(order by e.stage_order) prev_finished
    from expected e join latest l using(stage_name) where l.status in('PASS','DEGRADED')
  )
  select coalesce(count(*)=v_expected_count and bool_and(prev_finished is null or finished_at_utc>=prev_finished),false)
  into v_order_valid from ordered;

  select max(s.captured_at_utc) into v_latest_signal from public.alpha_hunter_signal_features s;
  select max(a.observed_at_utc) into v_latest_answer from public.alpha_hunter_big_mover_answer_key a;
  select max(b.captured_at_utc) into v_latest_shadow from public.alpha_hunter_big_mover_shadow b;
  if v_latest_signal is null or v_latest_answer is null or v_latest_shadow is null then v_freshness:='DATA_INSUFFICIENT';
  elsif clock_timestamp()-v_latest_signal>interval '90 minutes'
     or clock_timestamp()-v_latest_answer>interval '90 minutes'
     or clock_timestamp()-v_latest_shadow>interval '90 minutes' then v_freshness:='STALE';
  else v_freshness:='FRESH';end if;

  select
    (select count(*) from public.alpha_hunter_big_mover_shadow x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_parent_direction_shadow x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_money_entry_shadow x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_money_entry_stage_snapshots x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_money_scorecard_candidates x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_money_scorecard_outcomes x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_execution_cost_model_versions x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_execution_cost_evidence x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_risk_policy_versions x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_portfolio_risk_assessments x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_account_state_snapshots x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_open_position_snapshots x where x.trade_permission<>false or x.shadow_only<>true)
  into v_safety_violations;
  if v_safety_violations>0 then v_safety:='FAIL';end if;

  select count(*) into v_active_thresholds from public.alpha_hunter_money_entry_threshold_sets t
  where t.status='ACTIVE' and t.validated_at_utc is not null and t.activated_at_utc is not null;
  select count(*) into v_active_cost_models from public.alpha_hunter_execution_cost_model_versions c
  where c.status='ACTIVE' and c.validated_at_utc is not null and c.activated_at_utc is not null;
  select count(*) into v_active_risk_policies from public.alpha_hunter_risk_policy_versions p
  where p.status='ACTIVE' and p.validated_at_utc is not null and p.activated_at_utc is not null;
  select count(*) into v_verified_account from public.alpha_hunter_account_state_snapshots a
  where a.connection_status='CONNECTED_READ_ONLY' and a.complete=true and a.schema_validated=true
    and clock_timestamp()-a.captured_at_utc<=interval '90 minutes';

  if jsonb_array_length(v_missing)>0 then v_warnings:=v_warnings||jsonb_build_array('MISSING_OR_UNSUCCESSFUL_STAGE');end if;
  if not v_source_consistent then v_warnings:=v_warnings||jsonb_build_array('SOURCE_RUN_ID_MISMATCH');end if;
  if not v_order_valid then v_warnings:=v_warnings||jsonb_build_array('STAGE_ORDER_NOT_PROVEN');end if;
  if v_freshness<>'FRESH' then v_warnings:=v_warnings||jsonb_build_array('DATA_FRESHNESS_'||v_freshness);end if;
  if v_safety<>'PASS' then v_warnings:=v_warnings||jsonb_build_array('SAFETY_BOUNDARY_VIOLATION');end if;
  if v_expected_count=7 and v_active_thresholds=0 then v_warnings:=v_warnings||jsonb_build_array('READINESS_NO_ACTIVE_MONEY_ENTRY_THRESHOLDS');end if;
  if v_expected_count=7 and v_active_cost_models=0 then v_warnings:=v_warnings||jsonb_build_array('READINESS_NO_ACTIVE_COST_MODEL');end if;
  if v_expected_count=7 and v_active_risk_policies=0 then v_warnings:=v_warnings||jsonb_build_array('READINESS_NO_ACTIVE_RISK_POLICY');end if;
  if v_expected_count=7 and v_verified_account=0 then v_warnings:=v_warnings||jsonb_build_array('READINESS_NO_VERIFIED_ACCOUNT_STATE');end if;

  v_status:=case
    when v_safety='FAIL' or jsonb_array_length(v_missing)>0 or v_failed>0 or v_skipped>0 or not v_source_consistent or not v_order_valid then 'FAILED'
    when v_degraded>0 or v_freshness<>'FRESH' then 'DEGRADED'
    else 'PASS' end;

  v_should_incident:=v_status='FAILED' or v_safety='FAIL' or v_freshness<>'FRESH'
    or jsonb_array_length(v_missing)>0 or not v_source_consistent or not v_order_valid;

  v_health_id:=md5(v_control_run_id||'|'||clock_timestamp()::text||'|'||v_status);
  insert into public.alpha_hunter_control_plane_health_events(
    health_event_id,control_run_id,checked_at_utc,status,stage_order_valid,source_run_consistent,data_freshness_status,safety_status,
    missing_stages,warnings,payload,shadow_only,trade_permission
  ) values(
    v_health_id,v_control_run_id,clock_timestamp(),v_status,v_order_valid,v_source_consistent,v_freshness,v_safety,v_missing,v_warnings,
    jsonb_build_object(
      'expected_stage_count',v_expected_count,'latest_signal_feature_utc',v_latest_signal,'latest_answer_key_utc',v_latest_answer,
      'latest_big_mover_shadow_utc',v_latest_shadow,'safety_violation_count',v_safety_violations,
      'freshness_contract','HOURLY_SOURCE_MAX_AGE_90_MINUTES',
      'readiness',jsonb_build_object(
        'active_money_entry_threshold_sets',v_active_thresholds,'active_cost_models',v_active_cost_models,
        'active_risk_policies',v_active_risk_policies,'verified_recent_account_snapshots',v_verified_account
      ),
      'expected_stage_order',case
        when v_expected_count=7 then jsonb_build_array('ANSWER_KEY','PARENT_DIRECTION','MONEY_ENTRY_BRIDGE','MONEY_ENTRY_STAGE','MONEY_SCORECARD','COST_EVIDENCE','PORTFOLIO_RISK')
        when v_expected_count=5 then jsonb_build_array('ANSWER_KEY','PARENT_DIRECTION','MONEY_ENTRY_BRIDGE','MONEY_ENTRY_STAGE','MONEY_SCORECARD')
        else jsonb_build_array('ANSWER_KEY','PARENT_DIRECTION','MONEY_ENTRY_BRIDGE','MONEY_SCORECARD') end
    ),true,false
  );

  update public.alpha_hunter_control_plane_runs r
  set finalized_at_utc=clock_timestamp(),overall_status=v_status,passed_stage_count=v_pass,degraded_stage_count=v_degraded,
      failed_stage_count=v_failed,skipped_stage_count=v_skipped,data_freshness_status=v_freshness,safety_status=v_safety,
      updated_at=clock_timestamp(),payload=r.payload||jsonb_build_object(
        'missing_stages',v_missing,'warnings',v_warnings,'latest_health_event_id',v_health_id,
        'readiness_only_degradation',v_status='DEGRADED' and not v_should_incident
      )
  where r.control_run_id=v_control_run_id;

  v_incident_key:=v_control_run_id||'|CONTROL_PLANE_HEALTH';
  if v_should_incident then
    if not exists(select 1 from public.alpha_hunter_production_incident_events e where e.incident_key=v_incident_key and e.event_type='OPEN') then
      insert into public.alpha_hunter_production_incident_events(
        incident_event_id,incident_key,control_run_id,event_type,severity,incident_type,occurred_at_utc,details,shadow_only,trade_permission
      ) values(
        md5(v_incident_key||'|OPEN'),v_incident_key,v_control_run_id,'OPEN',case when v_safety='FAIL' then 'CRITICAL' else 'HIGH' end,
        'CONTROL_PLANE_HEALTH',clock_timestamp(),jsonb_build_object(
          'status',v_status,'missing_stages',v_missing,'warnings',v_warnings,'safety_status',v_safety,'freshness_status',v_freshness
        ),true,false
      );
    end if;
  elsif exists(select 1 from public.alpha_hunter_production_incident_events e where e.incident_key=v_incident_key and e.event_type='OPEN')
    and not exists(select 1 from public.alpha_hunter_production_incident_events e where e.incident_key=v_incident_key and e.event_type='RESOLVED') then
      insert into public.alpha_hunter_production_incident_events(
        incident_event_id,incident_key,control_run_id,event_type,severity,incident_type,occurred_at_utc,details,shadow_only,trade_permission
      ) values(
        md5(v_incident_key||'|RESOLVED'),v_incident_key,v_control_run_id,'RESOLVED','INFO','CONTROL_PLANE_HEALTH',clock_timestamp(),
        jsonb_build_object('status',v_status,'resolved_by_health_event_id',v_health_id),true,false
      );
  end if;

  return jsonb_build_object(
    'mode','ALPHA_HUNTER_CLOUD_CONTROL_PLANE_FINALIZE','control_run_id',v_control_run_id,'expected_stage_count',v_expected_count,
    'status',v_status,'passed',v_pass,'degraded',v_degraded,'failed',v_failed,'skipped',v_skipped,'missing_stages',v_missing,
    'stage_order_valid',v_order_valid,'source_run_consistent',v_source_consistent,'data_freshness_status',v_freshness,
    'safety_status',v_safety,'warnings',v_warnings,'incident_required',v_should_incident,'shadow_only',true,'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_finalize_control_plane_hour(timestamptz) from public,anon,authenticated;
grant execute on function private.alpha_hunter_finalize_control_plane_hour(timestamptz) to service_role;

-- Harden the older immutable direction-transition trigger function.
alter function public.alpha_hunter_block_direction_transition_mutation() set search_path = '';

-- Canonical seven-stage cloud schedule. Historical rows remain 4/5-stage compatible.
do $outer$
declare r record;
begin
  for r in select jobid from cron.job where jobname in (
    'alpha-hunter-big-mover-shadow-hourly','alpha-hunter-big-mover-parent-direction-hourly',
    'alpha-hunter-big-mover-money-entry-bridge-hourly','alpha-hunter-money-entry-stage-hourly',
    'alpha-hunter-big-mover-money-scorecard-hourly','alpha-hunter-execution-cost-evidence-hourly',
    'alpha-hunter-portfolio-risk-veto-hourly','alpha-hunter-control-plane-finalize-hourly'
  ) loop perform cron.unschedule(r.jobid);end loop;

  perform cron.schedule('alpha-hunter-big-mover-shadow-hourly','10 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('ANSWER_KEY',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-big-mover-parent-direction-hourly','11 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('PARENT_DIRECTION',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-big-mover-money-entry-bridge-hourly','12 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_BRIDGE',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-money-entry-stage-hourly','13 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_STAGE',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-big-mover-money-scorecard-hourly','14 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('MONEY_SCORECARD',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-execution-cost-evidence-hourly','15 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('COST_EVIDENCE',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-portfolio-risk-veto-hourly','16 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('PORTFOLIO_RISK',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-control-plane-finalize-hourly','20 * * * *',$cmd$select private.alpha_hunter_finalize_control_plane_hour(clock_timestamp());$cmd$);
end;
$outer$;
