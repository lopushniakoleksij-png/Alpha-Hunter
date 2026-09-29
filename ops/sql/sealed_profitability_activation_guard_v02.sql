-- Alpha Hunter sealed profitability activation guard v0.2
--
-- Fixes two scientific-integrity gaps in the legacy activator:
-- 1) baseline snapshots must be at/after preregistration and the frozen cadence
--    contract baseline_not_before_utc;
-- 2) when a scientific fingerprint is frozen, the baseline snapshot must match
--    it exactly.
--
-- This changes activation correctness only. It does not alter trading
-- thresholds, strategies, costs, risk, execution authority or promotion rules.

create or replace function private.alpha_hunter_try_activate_profitability_test_v02()
returns jsonb
language plpgsql
security definer
set search_path=''
as $function$
declare
  v_spec public.alpha_hunter_profitability_test_specs_v01%rowtype;
  v_contract public.alpha_hunter_profitability_cadence_contract_v01%rowtype;
  v_parent public.alpha_hunter_snapshots%rowtype;
  v_valid_symbols integer;
  v_strategy_rows integer;
  v_micro_rows integer;
  v_closed_rows integer;
  v_previous_source text;
  v_catalyst_version text;
  v_config_sha text;
  v_scientific_fingerprint text;
  v_not_before timestamptz;
  v_activated integer:=0;
begin
  for v_spec in
    select s.*
    from public.alpha_hunter_profitability_test_specs_v01 s
    where not exists (
      select 1
      from public.alpha_hunter_profitability_test_activations_v01 a
      where a.spec_id=s.spec_id
    )
    order by s.preregistered_at_utc
  loop
    select c.* into v_contract
    from public.alpha_hunter_profitability_cadence_contract_v01 c
    where c.spec_id=v_spec.spec_id
    limit 1;

    v_not_before:=greatest(
      v_spec.preregistered_at_utc,
      coalesce(v_contract.baseline_not_before_utc,v_spec.preregistered_at_utc)
    );

    select p.* into v_parent
    from public.alpha_hunter_snapshots p
    where p.collected_at_utc>=v_not_before
      and p.payload->'validation_identity'->>'run_source'
          =v_spec.required_run_source
      and p.payload->'validation_identity'->>'git_commit'
          =v_spec.frozen_git_commit
      and (
        v_spec.frozen_scientific_fingerprint_sha256 is null
        or p.payload->'validation_identity'->>'scientific_fingerprint_sha256'
           =v_spec.frozen_scientific_fingerprint_sha256
      )
      and coalesce(
        (p.payload->'multi_strategy_summary'->>'configured_strategy_count')::integer,
        0
      )=v_spec.required_strategy_count
      and coalesce(
        (p.payload->'multi_strategy_summary'->>'total_evaluations')::integer,
        0
      )>0
      and coalesce(
        p.payload->'previous_snapshot_context'->>'source',
        'NONE'
      )<>'NONE'
      and coalesce(
        p.payload->'catalyst_summary'->>'version',
        ''
      )='0.2'
    order by p.collected_at_utc
    limit 1;

    if v_parent.run_id is null then
      continue;
    end if;

    select
      count(*) filter(where c.error is null),
      count(*) filter(
        where c.error is null
          and jsonb_typeof(c.payload->'multi_strategy_engine')='object'
      ),
      count(*) filter(
        where c.error is null
          and jsonb_typeof(c.payload->'microstructure')='object'
      ),
      count(*) filter(
        where c.error is null
          and jsonb_typeof(
            c.payload->'timeframes'->'1H'->'last_closed_candle'
          )='object'
      )
    into
      v_valid_symbols,
      v_strategy_rows,
      v_micro_rows,
      v_closed_rows
    from public.alpha_hunter_symbol_snapshots c
    where c.run_id=v_parent.run_id;

    if v_valid_symbols=0
       or v_strategy_rows<>v_valid_symbols
       or v_micro_rows<>v_valid_symbols
       or v_closed_rows<>v_valid_symbols
    then
      continue;
    end if;

    v_previous_source:=coalesce(
      v_parent.payload->'previous_snapshot_context'->>'source',
      'NONE'
    );
    v_catalyst_version:=coalesce(
      v_parent.payload->'catalyst_summary'->>'version',
      ''
    );
    v_config_sha:=coalesce(
      v_parent.payload->'validation_identity'->>'config_sha256',
      ''
    );
    v_scientific_fingerprint:=coalesce(
      v_parent.payload->'validation_identity'->>'scientific_fingerprint_sha256',
      ''
    );

    if v_config_sha='' then
      continue;
    end if;

    if v_spec.frozen_scientific_fingerprint_sha256 is not null
       and v_scientific_fingerprint<>v_spec.frozen_scientific_fingerprint_sha256
    then
      continue;
    end if;

    insert into public.alpha_hunter_profitability_test_activations_v01(
      spec_id,baseline_run_id,started_at_utc,baseline_config_sha256,
      baseline_git_commit,baseline_previous_snapshot_source,
      baseline_catalyst_version,baseline_symbol_rows,baseline_strategy_rows,
      baseline_microstructure_rows,baseline_closed_candle_rows,
      activation_checks,baseline_scientific_fingerprint_sha256
    ) values (
      v_spec.spec_id,
      v_parent.run_id,
      v_parent.collected_at_utc,
      v_config_sha,
      v_spec.frozen_git_commit,
      v_previous_source,
      v_catalyst_version,
      v_valid_symbols,
      v_strategy_rows,
      v_micro_rows,
      v_closed_rows,
      jsonb_build_object(
        'preregistration_boundary_ok',
          v_parent.collected_at_utc>=v_spec.preregistered_at_utc,
        'cadence_not_before_boundary_ok',
          v_parent.collected_at_utc>=v_not_before,
        'scientific_fingerprint_ok',
          (
            v_spec.frozen_scientific_fingerprint_sha256 is null
            or v_scientific_fingerprint
               =v_spec.frozen_scientific_fingerprint_sha256
          ),
        'strategy_count_ok',true,
        'previous_context_ok',true,
        'catalyst_v02_ok',true,
        'strategy_rows_complete',true,
        'microstructure_rows_complete',true,
        'closed_candle_rows_complete',true
      ),
      nullif(v_scientific_fingerprint,'')
    )
    on conflict(spec_id) do nothing;

    if found then
      v_activated:=v_activated+1;
    end if;
  end loop;

  return jsonb_build_object(
    'protocol_version','sealed-profitability-activation-v0.2',
    'activated_specs',v_activated,
    'preregistration_boundary_enforced',true,
    'cadence_not_before_boundary_enforced',true,
    'scientific_fingerprint_enforced',true,
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_try_activate_profitability_test_v02()
from public,anon,authenticated,service_role;

select cron.alter_job(
  job_id := (
    select jobid
    from cron.job
    where jobname='alpha-hunter-profitability-test-activation-v01-hourly'
  ),
  schedule := '8,38 * * * *',
  command := 'select private.alpha_hunter_try_activate_profitability_test_v02();',
  active := true
);
