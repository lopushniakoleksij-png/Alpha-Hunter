begin;
-- Install these owner-only functions; neither installation nor preregistration activates R9.
create or replace function private.alpha_hunter_preregister_r9_v01(
 requested_git_commit text, requested_scientific_fingerprint text
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare v public.alpha_hunter_profitability_test_specs_v01%rowtype;
begin
 if requested_git_commit !~ '^[a-f0-9]{40}$' or requested_scientific_fingerprint !~ '^[a-f0-9]{64}$'
   or requested_git_commit is null or requested_scientific_fingerprint is null then
   raise exception 'Exact reviewed commit and fingerprint required'; end if;
 insert into public.alpha_hunter_profitability_test_specs_v01
 (spec_id,protocol_version,frozen_git_commit,required_strategy_count,required_minimum_rr,
 evaluation_horizon_hours,minimum_test_days,minimum_completed_paper_trades,confidence_z,
 require_validated_cost_model,scientific_role,required_run_source,frozen_scientific_fingerprint_sha256)
 values('SEALED-ARCH-V14R9-EXEC-PAPER-24H-20261004','paper-horizon-24h-v0.1',
 requested_git_commit,10,5,24,30,100,1.96,true,'SUCCESSOR_EXECUTED_PAPER_24H','RENDER_CRON',
 requested_scientific_fingerprint) on conflict(spec_id) do nothing;
 select * into strict v from public.alpha_hunter_profitability_test_specs_v01
 where spec_id='SEALED-ARCH-V14R9-EXEC-PAPER-24H-20261004';
 if v.frozen_git_commit<>requested_git_commit
   or v.frozen_scientific_fingerprint_sha256<>requested_scientific_fingerprint then
   raise exception 'Existing preregistration is immutable and has a different identity'; end if;
 return jsonb_build_object('status','PREREGISTERED_NOT_ACTIVATED','spec_id',v.spec_id);
end; $$;
revoke all on function private.alpha_hunter_preregister_r9_v01(text,text)
 from public,anon,authenticated,service_role;

create or replace function private.alpha_hunter_guard_r9_activation_v01()
returns trigger language plpgsql security invoker set search_path='' as $$
declare e public.alpha_hunter_paper_execution_activation_v09%rowtype;
begin
 if new.spec_id<>'SEALED-ARCH-V14R9-EXEC-PAPER-24H-20261004' then return new; end if;
 select * into e from public.alpha_hunter_paper_execution_activation_v09
 where activation_id='PAPER_EXECUTION_R9';
 if e.activation_id is null then return null; end if;
 if new.started_at_utc<>e.activated_at_utc
   or new.baseline_scientific_fingerprint_sha256<>e.scientific_fingerprint_sha256 then
   raise exception 'R9 activation identity must align atomically'; end if;
 return new;
end; $$;
revoke all on function private.alpha_hunter_guard_r9_activation_v01()
 from public,anon,authenticated,service_role;
create trigger trg_ah_r9_profitability_activation_interlock
 before insert on public.alpha_hunter_profitability_test_activations_v01
 for each row execute function private.alpha_hunter_guard_r9_activation_v01();

create or replace function private.alpha_hunter_activate_r9_v01(
 requested_git_commit text, requested_scientific_fingerprint text
) returns jsonb language plpgsql security invoker set search_path='' as $$
declare
 sp public.alpha_hunter_profitability_test_specs_v01%rowtype;
 p public.alpha_hunter_snapshots%rowtype;
 existing public.alpha_hunter_paper_execution_activation_v09%rowtype;
 verified timestamptz; started timestamptz;
 valid_symbols integer; strategy_rows integer; micro_rows integer; closed_rows integer;
begin
 perform pg_advisory_xact_lock(hashtextextended('alpha-hunter-r9-activation',0));
 select * into strict sp from public.alpha_hunter_profitability_test_specs_v01
 where spec_id='SEALED-ARCH-V14R9-EXEC-PAPER-24H-20261004';
 if sp.frozen_git_commit is distinct from requested_git_commit
 or sp.frozen_scientific_fingerprint_sha256 is distinct from requested_scientific_fingerprint then
   raise exception 'R9 preregistered identity mismatch'; end if;
 select * into existing from public.alpha_hunter_paper_execution_activation_v09
 where activation_id='PAPER_EXECUTION_R9';
 if existing.activation_id is not null then
  if existing.release_git_commit<>requested_git_commit or
    existing.scientific_fingerprint_sha256<>requested_scientific_fingerprint then
    raise exception 'R9 already activated under a different identity'; end if;
  return jsonb_build_object('status','ALREADY_ACTIVATED','started_at_utc',existing.activated_at_utc);
 end if;
 select * into p from public.alpha_hunter_snapshots
 where payload->'validation_identity'->>'run_source'='RENDER_CRON'
 order by collected_at_utc desc limit 1;
 if p.run_id is null or p.collected_at_utc<sp.preregistered_at_utc
 or p.collected_at_utc<clock_timestamp()-interval '35 minutes'
 or p.collected_at_utc>clock_timestamp()
 or p.payload->'validation_identity'->>'git_commit' is distinct from requested_git_commit
 or p.payload->'validation_identity'->>'scientific_fingerprint_sha256' is distinct from requested_scientific_fingerprint
 or p.payload->'validation_identity'->>'runtime_role' is distinct from 'RENDER_CRON'
 or nullif(p.payload->'validation_identity'->>'config_sha256','') is null
 or coalesce(p.payload->'previous_snapshot_context'->>'source','NONE')='NONE'
 or p.payload->'catalyst_summary'->>'version' is distinct from '0.2'
 or coalesce((p.payload->'multi_strategy_summary'->>'configured_strategy_count')::integer,0)<>10 then
  raise exception 'Fresh corrected canonical runtime with complete identity is required'; end if;
 if not exists(select 1 from public.alpha_hunter_production_deployment_runtime_status_v03
   where deployment_status='MATCHED' and live_runtime_git_commit=requested_git_commit) then
  raise exception 'Deployment target must match corrected runtime'; end if;
 select count(*) filter(where error is null),
 count(*) filter(where error is null and jsonb_typeof(payload->'multi_strategy_engine')='object'),
 count(*) filter(where error is null and jsonb_typeof(payload->'microstructure')='object'),
 count(*) filter(where error is null and jsonb_typeof(payload->'timeframes'->'1H'->'last_closed_candle')='object')
 into valid_symbols,strategy_rows,micro_rows,closed_rows
 from public.alpha_hunter_symbol_snapshots where run_id=p.run_id;
 if valid_symbols=0 or strategy_rows<>valid_symbols or micro_rows<>valid_symbols or closed_rows<>valid_symbols then
  raise exception 'Corrected baseline child evidence is incomplete'; end if;
 verified:=clock_timestamp(); started:=verified+interval '1 microsecond';
 insert into public.alpha_hunter_paper_execution_activation_v09
 (activation_id,spec_id,protocol_version,activated_at_utc,runtime_verified_at_utc,
 admission_cutoff_at_utc,release_git_commit,scientific_fingerprint_sha256,evidence)
 values('PAPER_EXECUTION_R9',sp.spec_id,'paper-horizon-24h-v0.1',started,verified,
 started+interval '30 days',requested_git_commit,requested_scientific_fingerprint,
 jsonb_build_object('verified_run_id',p.run_id,'legacy_protection_preserved',true,
 'first_unusable_due_observation_fails_cohort',true,'historical_evidence_reused',false));
 insert into public.alpha_hunter_profitability_test_activations_v01
 (spec_id,baseline_run_id,started_at_utc,baseline_config_sha256,baseline_git_commit,
 baseline_previous_snapshot_source,baseline_catalyst_version,baseline_symbol_rows,
 baseline_strategy_rows,baseline_microstructure_rows,baseline_closed_candle_rows,
 activation_checks,baseline_scientific_fingerprint_sha256,scientific_role)
 values(sp.spec_id,p.run_id,started,p.payload->'validation_identity'->>'config_sha256',
 requested_git_commit,p.payload->'previous_snapshot_context'->>'source','0.2',
 valid_symbols,strategy_rows,micro_rows,closed_rows,
 jsonb_build_object('atomic_successor_activation',true,'admission_starts_after_verification',true,
 'sample_source','alpha_hunter_paper_cohort_members_v09','all_admitted_denominator',true),
 requested_scientific_fingerprint,'SUCCESSOR_EXECUTED_PAPER_24H_ACTIVATION');
 return jsonb_build_object('status','ACTIVATED','spec_id',sp.spec_id,'started_at_utc',started,
 'admission_cutoff_at_utc',started+interval '30 days','paper_only',true,'order_path','NONE');
end; $$;
revoke all on function private.alpha_hunter_activate_r9_v01(text,text)
 from public,anon,authenticated,service_role;
commit;
