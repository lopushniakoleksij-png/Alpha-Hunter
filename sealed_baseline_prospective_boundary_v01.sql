-- Alpha Hunter sealed profitability baseline prospective-boundary fix v0.1
--
-- Scientific integrity fix only:
-- A sealed test may activate only from a canonical scan collected at or after
-- that spec's preregistration timestamp. No pre-registration scan can be used
-- as the baseline for a newly preregistered cohort.
--
-- This patch does not change strategy logic, thresholds, profitability gates,
-- sample requirements, trade permission or production promotion.

create or replace function private.alpha_hunter_try_activate_profitability_test_v01()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_spec public.alpha_hunter_profitability_test_specs_v01%rowtype;
  v_parent public.alpha_hunter_snapshots%rowtype;
  v_valid_symbols integer;
  v_strategy_rows integer;
  v_micro_rows integer;
  v_closed_rows integer;
  v_previous_source text;
  v_catalyst_version text;
  v_config_sha text;
  v_activated integer := 0;
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
    v_parent := null;

    select p.* into v_parent
    from public.alpha_hunter_snapshots p
    where p.collected_at_utc>=v_spec.preregistered_at_utc
      and p.payload->'validation_identity'->>'git_commit'=v_spec.frozen_git_commit
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

    v_previous_source := coalesce(
      v_parent.payload->'previous_snapshot_context'->>'source',
      'NONE'
    );
    v_catalyst_version := coalesce(
      v_parent.payload->'catalyst_summary'->>'version',
      ''
    );
    v_config_sha := coalesce(
      v_parent.payload->'validation_identity'->>'config_sha256',
      ''
    );

    if v_config_sha='' then
      continue;
    end if;

    insert into public.alpha_hunter_profitability_test_activations_v01(
      spec_id,baseline_run_id,started_at_utc,baseline_config_sha256,
      baseline_git_commit,baseline_previous_snapshot_source,
      baseline_catalyst_version,baseline_symbol_rows,baseline_strategy_rows,
      baseline_microstructure_rows,baseline_closed_candle_rows,
      activation_checks
    ) values (
      v_spec.spec_id,v_parent.run_id,v_parent.collected_at_utc,v_config_sha,
      v_spec.frozen_git_commit,v_previous_source,v_catalyst_version,
      v_valid_symbols,v_strategy_rows,v_micro_rows,v_closed_rows,
      jsonb_build_object(
        'prospective_boundary_ok',
          v_parent.collected_at_utc>=v_spec.preregistered_at_utc,
        'baseline_after_preregistration',true,
        'strategy_count_ok',true,
        'previous_context_ok',true,
        'catalyst_v02_ok',true,
        'strategy_rows_complete',true,
        'microstructure_rows_complete',true,
        'closed_candle_rows_complete',true
      )
    )
    on conflict(spec_id) do nothing;

    if found then
      v_activated := v_activated+1;
    end if;
  end loop;

  return jsonb_build_object(
    'protocol_version','sealed-profitability-v0.1',
    'prospective_boundary_enforced',true,
    'activated_specs',v_activated,
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_try_activate_profitability_test_v01()
  from public,anon,authenticated,service_role;
