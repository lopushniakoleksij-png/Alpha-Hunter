begin;

-- Alpha Hunter known-defect sealed-test invalidation v0.1.
--
-- Scientific governance only:
-- - append-only invalidation evidence;
-- - does not change strategy logic, thresholds, paper order logic, or exchange authority;
-- - makes the realtime test engine fail closed for an invalidated sealed cohort.

create table if not exists public.alpha_hunter_profitability_test_invalidations_v01 (
  invalidation_id text primary key,
  spec_id text not null references public.alpha_hunter_profitability_test_specs_v01(spec_id),
  invalidated_at_utc timestamptz not null default clock_timestamp(),
  defect_class text not null,
  reason text not null,
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'SEALED_TEST_KNOWN_DEFECT_INVALIDATION',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_profitability_invalidations_spec_time_v01
  on public.alpha_hunter_profitability_test_invalidations_v01(
    spec_id,invalidated_at_utc desc
  );

alter table public.alpha_hunter_profitability_test_invalidations_v01
  enable row level security;

revoke all on public.alpha_hunter_profitability_test_invalidations_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profitability_test_invalidations_v01
  to service_role;

drop trigger if exists trg_ah_profitability_invalidations_append_only_v01
  on public.alpha_hunter_profitability_test_invalidations_v01;
create trigger trg_ah_profitability_invalidations_append_only_v01
before update or delete on public.alpha_hunter_profitability_test_invalidations_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

insert into public.alpha_hunter_profitability_test_invalidations_v01(
  invalidation_id,spec_id,invalidated_at_utc,defect_class,reason,evidence
) values (
  'inv-r7-paper-monitoring-and-duplicate-exposure-20261003',
  'SEALED-ARCH-V14R7-FP-20M-20261003',
  clock_timestamp(),
  'PAPER_LIFECYCLE_INTEGRITY_DEFECT',
  'R7 is not a clean profitability cohort: one completed paper stop was first observed 560.224 minutes after protection activation, and repeated same-symbol/strategy/direction paper orders created stacked correlated exposures.',
  jsonb_build_object(
    'monitoring_gap',jsonb_build_object(
      'entry_order_id','1714f518f0afc4c821d9d4bead8843bc',
      'symbol','EIGENUSDT',
      'direction','LONG',
      'protection_created_at_utc','2026-10-02T13:43:25.980324+00:00',
      'first_exit_observation_at_utc','2026-10-02T23:03:39.440554+00:00',
      'maximum_observed_gap_minutes',560.224,
      'sealed_maximum_interval_minutes',35,
      'observed_stop_exit_r',-5.481325236766965,
      'interpretation','MONITORING_GAP_ARTIFACT_NOT_CLEAN_STOP_PERFORMANCE'
    ),
    'duplicate_exposure',jsonb_build_object(
      'confirmed_examples',jsonb_build_array(
        jsonb_build_object(
          'symbol','ONDOUSDT','strategy_id','S3','direction','LONG',
          'same_idea_completed_positions',3
        ),
        jsonb_build_object(
          'symbol','PYTHUSDT','strategy_id','S2','direction','LONG',
          'same_idea_completed_positions',3
        )
      ),
      'root_cause','NO_ONE_ACTIVE_OR_RESTING_PAPER_EXPOSURE_ADMISSION_GUARD',
      'economic_effect','ONE_SIGNAL_COULD_BE_MULTIPLIED_INTO_MULTIPLE_CORRELATED_PAPER_BETS'
    ),
    'historical_evidence_mutated',false,
    'r7_results_permitted_for_final_profitability_claim',false,
    'required_next_action','CORRECT_ENGINE_AND_PREREGISTER_NEW_FINGERPRINTED_COHORT'
  )
)
on conflict(invalidation_id) do nothing;


create or replace function private.alpha_hunter_refresh_test_engine_v05()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_base_result jsonb;
  v_base public.alpha_hunter_test_engine_runs_v01%rowtype;
  v_inv public.alpha_hunter_profitability_test_invalidations_v01%rowtype;
  v_id text;
  v_now timestamptz:=clock_timestamp();
begin
  v_base_result:=private.alpha_hunter_refresh_test_engine_v04();

  select r.* into v_base
  from public.alpha_hunter_test_engine_runs_v01 r
  where r.test_engine_run_id=v_base_result->>'test_engine_run_id'
  limit 1;

  if v_base.test_engine_run_id is null then
    raise exception 'Base test-engine refresh did not produce a readable run';
  end if;

  select i.* into v_inv
  from public.alpha_hunter_profitability_test_invalidations_v01 i
  where i.spec_id=v_base.spec_id
  order by i.invalidated_at_utc desc,i.created_at desc
  limit 1;

  if v_inv.invalidation_id is null then
    return v_base_result || jsonb_build_object(
      'known_defect_invalidation',false,
      'engine_version','realtime-test-engine-db-v0.5-known-defect-invalidation'
    );
  end if;

  v_id:=md5(
    'realtime-test-engine-db-v0.5-known-defect-invalidation|'
    ||v_base.spec_id||'|'||v_now::text||'|'||v_inv.invalidation_id
  );

  insert into public.alpha_hunter_test_engine_runs_v01
  select (
    jsonb_populate_record(
      null::public.alpha_hunter_test_engine_runs_v01,
      to_jsonb(v_base)
      || jsonb_build_object(
        'test_engine_run_id',v_id,
        'evaluated_at_utc',v_now,
        'engine_version','realtime-test-engine-db-v0.5-known-defect-invalidation',
        'operational_status','BLOCKED',
        'profitability_status','INVALIDATED_BY_KNOWN_PRODUCTION_DEFECT',
        'verdict','NOT_PROVEN',
        'blockers',
          coalesce(v_base.blockers,'[]'::jsonb)
          || jsonb_build_array(
            'SCIENTIFIC_TEST_INVALIDATED_KNOWN_DEFECT',
            'PAPER_LIFECYCLE_INTEGRITY_DEFECT'
          ),
        'source_status',
          coalesce(v_base.source_status,'{}'::jsonb)
          || jsonb_build_object(
            'known_defect_invalidation',true,
            'known_defect_invalidation_id',v_inv.invalidation_id,
            'known_defect_class',v_inv.defect_class,
            'known_defect_reason',v_inv.reason,
            'known_defect_evidence',v_inv.evidence,
            'r7_final_profitability_claim_permitted',false
          ),
        'economics',
          coalesce(v_base.economics,'{}'::jsonb)
          || jsonb_build_object(
            'scientific_cohort_valid',false,
            'final_profitability_claim_permitted',false,
            'required_next_action',
            'CORRECT_ENGINE_AND_PREREGISTER_NEW_FINGERPRINTED_COHORT'
          ),
        'live_money_claim_permitted',false,
        'trade_permission',false,
        'threshold_change_permitted',false,
        'production_promotion_permitted',false,
        'order_path','NONE',
        'created_at',v_now
      )
    )
  ).*;

  return jsonb_build_object(
    'test_engine_run_id',v_id,
    'spec_id',v_base.spec_id,
    'operational_status','BLOCKED',
    'profitability_status','INVALIDATED_BY_KNOWN_PRODUCTION_DEFECT',
    'verdict','NOT_PROVEN',
    'known_defect_invalidation',true,
    'known_defect_invalidation_id',v_inv.invalidation_id,
    'blockers',
      coalesce(v_base.blockers,'[]'::jsonb)
      || jsonb_build_array(
        'SCIENTIFIC_TEST_INVALIDATED_KNOWN_DEFECT',
        'PAPER_LIFECYCLE_INTEGRITY_DEFECT'
      ),
    'paper_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_refresh_test_engine_v05()
  from public;
grant execute on function private.alpha_hunter_refresh_test_engine_v05()
  to postgres,service_role;

select cron.alter_job(
  job_id := (
    select jobid
    from cron.job
    where jobname='alpha-hunter-test-engine-db-refresh-v02'
  ),
  schedule := '5,25,45 * * * *',
  command := 'select private.alpha_hunter_refresh_test_engine_v05();'
);

commit;
