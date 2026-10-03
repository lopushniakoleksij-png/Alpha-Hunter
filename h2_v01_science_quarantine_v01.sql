-- Alpha Hunter H2 v0.1 sealed-science quarantine v0.1
--
-- Issue #311 proved that H2 capture v0.1 used the still-forming 15m candle
-- instead of the preregistered latest CLOSED 15m candle. Issue #313 therefore
-- quarantines the v0.1 capture/evaluator/outcome stream without deleting,
-- rewriting, or exposing any sealed result.
--
-- This repair:
--   * records an immutable quarantine;
--   * preserves the existing sealed-outcome count as operational metadata only;
--   * unschedules only the exact known v0.1 sealed collector job;
--   * replaces manual collector invocation with a fail-closed quarantine status;
--   * does not read or expose any sealed result value;
--   * does not change R3, thresholds, production, trade permissions, or orders.

create table if not exists public.alpha_hunter_h2_science_quarantines_v01 (
  quarantine_id text primary key
    check(quarantine_id='AH-H2-V01-TRIGGER-SOURCE-QUARANTINE-20261003'),
  capture_spec_id text not null
    check(capture_spec_id='AH-DIRECTION-ARCHITECTURE-H2-CAPTURE-V01'),
  evaluator_spec_id text not null
    check(evaluator_spec_id='AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02'),
  quarantined_at_utc timestamptz not null default clock_timestamp(),
  reason_code text not null
    check(reason_code='FORMING_15M_TRIGGER_SOURCE_MISMATCH_ISSUE_311'),
  reason_detail text not null,
  sealed_outcome_sets_at_quarantine bigint not null check(sealed_outcome_sets_at_quarantine>=0),
  existing_evidence_preserved boolean not null default true
    check(existing_evidence_preserved=true),
  historical_results_exposed boolean not null default false
    check(historical_results_exposed=false),
  sealed_outcome_collection_permitted boolean not null default false
    check(sealed_outcome_collection_permitted=false),
  outcome_access_permitted boolean not null default false
    check(outcome_access_permitted=false),
  confirmatory_analysis_permitted boolean not null default false
    check(confirmatory_analysis_permitted=false),
  t0_authorized boolean not null default false check(t0_authorized=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  superseding_capture_spec_id text not null
    check(superseding_capture_spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02'),
  created_at_utc timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_h2_science_quarantines_v01 enable row level security;

revoke all on public.alpha_hunter_h2_science_quarantines_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_h2_science_quarantines_v01
  to service_role;

drop trigger if exists trg_ah_h2_science_quarantine_append_only_v01
  on public.alpha_hunter_h2_science_quarantines_v01;
create trigger trg_ah_h2_science_quarantine_append_only_v01
before update or delete on public.alpha_hunter_h2_science_quarantines_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


do $$
declare
  v_status public.alpha_hunter_h2_direction_sealed_collection_status_v01%rowtype;
begin
  if not exists (
    select 1
    from public.alpha_hunter_h2_direction_evaluator_specs_v02 e
    where e.evaluator_spec_id='AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02'
      and e.capture_spec_id='AH-DIRECTION-ARCHITECTURE-H2-CAPTURE-V01'
      and e.status='PREREGISTERED_LOCKED'
      and e.outcome_access_permitted=false
      and e.primary_results_exposed=false
      and e.confirmatory_analysis_permitted=false
      and e.threshold_change_permitted=false
      and e.production_promotion_permitted=false
      and e.trade_permission=false
      and e.order_path='NONE'
  ) then
    raise exception 'H2 v0.1 quarantine requires locked sealed evaluator safety contract';
  end if;

  select *
  into v_status
  from public.alpha_hunter_h2_direction_sealed_collection_status_v01
  where status_id='AH-H2-DIRECTION-SEALED-COLLECTION-V01';

  if v_status.status_id is null then
    raise exception 'H2 v0.1 quarantine requires sealed collection status row';
  end if;

  insert into public.alpha_hunter_h2_science_quarantines_v01(
    quarantine_id,capture_spec_id,evaluator_spec_id,reason_code,reason_detail,
    sealed_outcome_sets_at_quarantine,existing_evidence_preserved,
    historical_results_exposed,sealed_outcome_collection_permitted,
    outcome_access_permitted,confirmatory_analysis_permitted,t0_authorized,
    threshold_change_permitted,production_promotion_permitted,shadow_only,
    trade_permission,order_path,superseding_capture_spec_id
  ) values (
    'AH-H2-V01-TRIGGER-SOURCE-QUARANTINE-20261003',
    'AH-DIRECTION-ARCHITECTURE-H2-CAPTURE-V01',
    'AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02',
    'FORMING_15M_TRIGGER_SOURCE_MISMATCH_ISSUE_311',
    'H2 v0.1 preregistered latest CLOSED 15m trigger but live audit proved the implementation used a still-forming latest_candle and EMA9 including that forming bar; v0.1 evidence is preserved but cannot validate corrected H2.',
    v_status.sealed_outcome_set_count,
    true,false,false,false,false,false,false,false,true,false,'NONE',
    'AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02'
  )
  on conflict(quarantine_id) do nothing;
end;
$$;


create or replace view public.alpha_hunter_h2_v01_science_quarantine_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  q.quarantine_id,
  q.capture_spec_id,
  q.evaluator_spec_id,
  q.quarantined_at_utc,
  q.reason_code,
  q.reason_detail,
  q.sealed_outcome_sets_at_quarantine,
  c.sealed_outcome_set_count as sealed_outcome_sets_current_operational_count,
  c.last_run_at_utc as last_sealed_collection_at_utc,
  q.existing_evidence_preserved,
  q.historical_results_exposed,
  q.sealed_outcome_collection_permitted,
  q.outcome_access_permitted,
  q.confirmatory_analysis_permitted,
  q.t0_authorized,
  q.threshold_change_permitted,
  q.production_promotion_permitted,
  q.shadow_only,
  q.trade_permission,
  q.order_path,
  q.superseding_capture_spec_id,
  false as v01_confirmatory_use_permitted,
  false as v01_maturity_transfer_to_v02_permitted,
  'QUARANTINED_TRIGGER_SOURCE_CONTRACT_INVALID'::text as scientific_status,
  'COLLECT_NEW_FORWARD_H2_V02_ONLY'::text as next_gate
from public.alpha_hunter_h2_science_quarantines_v01 q
join public.alpha_hunter_h2_direction_sealed_collection_status_v01 c
  on c.evaluator_spec_id=q.evaluator_spec_id
where q.quarantine_id='AH-H2-V01-TRIGGER-SOURCE-QUARANTINE-20261003';

revoke all on public.alpha_hunter_h2_v01_science_quarantine_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_h2_v01_science_quarantine_status_v01
  to service_role;


do $$
declare
  v_job cron.job%rowtype;
begin
  select *
  into v_job
  from cron.job
  where jobname='alpha-hunter-h2-direction-sealed-outcome-hourly';

  if v_job.jobid is not null then
    if v_job.schedule<>'28 */6 * * *'
       or v_job.command<>'select private.alpha_hunter_run_h2_direction_sealed_v01();'
       or v_job.active is not true
    then
      raise exception 'H2 v0.1 quarantine refuses unexpected sealed collector job contract';
    end if;

    perform cron.unschedule(v_job.jobid);
  end if;
end;
$$;


create or replace function private.alpha_hunter_run_h2_direction_sealed_v01()
returns jsonb
language plpgsql
security definer
set search_path=''
as $function$
begin
  return jsonb_build_object(
    'status','QUARANTINED_TRIGGER_SOURCE_CONTRACT_INVALID',
    'capture_spec_id','AH-DIRECTION-ARCHITECTURE-H2-CAPTURE-V01',
    'evaluator_spec_id','AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02',
    'reason_code','FORMING_15M_TRIGGER_SOURCE_MISMATCH_ISSUE_311',
    'existing_evidence_preserved',true,
    'sealed_outcome_collection_permitted',false,
    'outcome_access_permitted',false,
    'confirmatory_analysis_permitted',false,
    't0_authorized',false,
    'threshold_change_permitted',false,
    'production_promotion_permitted',false,
    'shadow_only',true,
    'trade_permission',false,
    'order_path','NONE',
    'next_gate','COLLECT_NEW_FORWARD_H2_V02_ONLY'
  );
end;
$function$;

revoke all on function private.alpha_hunter_run_h2_direction_sealed_v01()
  from public,anon,authenticated,service_role;

-- No existing H2 v0.1 capture, anchor, sealed outcome, failure, evaluator-spec,
-- or collection-status row is updated or deleted by this quarantine.
-- No sealed outcome value is selected or exposed.
