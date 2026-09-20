-- Alpha Hunter prospective multi-timeframe geometry holdout v0.1
--
-- Starts a fresh, forward-only scientific clock for the primary geometry
-- hypothesis selected from the retrospective v0.3 research screen.
--
-- IMPORTANT:
--   * Historical geometry rows are prohibited from entering the holdout.
--   * Capture uses candidate-time evidence only and never reads outcomes.
--   * This migration does not evaluate the hypothesis.
--   * This migration does not change execution thresholds, T0/T1/T2 authority,
--     risk, leverage, cron, exchange calls, or production permission.
--   * Every persistent row is shadow_only=true, trade_permission=false,
--     production_promotion_permitted=false, order_path='NONE'.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;


create table if not exists public.alpha_hunter_geometry_holdout_specs (
  spec_id text primary key,
  hypothesis_id text not null unique,
  registered_at_utc timestamptz not null default clock_timestamp(),
  collection_ends_at_utc timestamptz not null,
  status text not null default 'COLLECTING'
    check (status='COLLECTING'),

  primary_variant text not null
    check (primary_variant='15M_STOP_4H_TARGET'),
  baseline_variant text not null
    check (baseline_variant='1H_STOP_1H_TARGET'),
  primary_endpoint text not null
    check (primary_endpoint='Q5_TARGET_FIRST_24H'),
  primary_horizon_hours integer not null
    check (primary_horizon_hours=24),
  secondary_horizon_hours integer not null
    check (secondary_horizon_hours=12),

  minimum_paired_candidates integer not null
    check (minimum_paired_candidates=100),
  minimum_symbols integer not null
    check (minimum_symbols=30),
  minimum_utc_days integer not null
    check (minimum_utc_days=20),
  minimum_candidates_per_direction integer not null
    check (minimum_candidates_per_direction=25),
  maximum_collection_days integer not null
    check (maximum_collection_days=60),

  protocol jsonb not null check (jsonb_typeof(protocol)='object'),
  source_schema_fingerprint text not null
    check (source_schema_fingerprint ~ '^[0-9a-f]{64}$'),
  source_query_fingerprint text not null
    check (source_query_fingerprint ~ '^[0-9a-f]{64}$'),
  spec_hash text not null unique
    check (spec_hash ~ '^[0-9a-f]{64}$'),
  capture_contract_version text not null
    check (capture_contract_version='geometry-prospective-holdout-v0.1'),

  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),

  check (collection_ends_at_utc=registered_at_utc + interval '60 days')
);


create table if not exists public.alpha_hunter_geometry_holdout_bindings (
  binding_id text primary key,
  spec_id text not null
    references public.alpha_hunter_geometry_holdout_specs(spec_id),
  diagnostic_id text not null,
  source_signal_id text,

  registered_at_utc timestamptz not null,
  source_captured_at_utc timestamptz not null,
  source_created_at_utc timestamptz not null,
  decision_available_at_utc timestamptz not null,

  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  entry_price double precision,

  support_15m double precision,
  resistance_15m double precision,
  support_1h double precision,
  resistance_1h double precision,
  support_4h double precision,
  resistance_4h double precision,

  variant_geometry jsonb not null
    check (jsonb_typeof(variant_geometry)='object'),

  group_name text not null
    check (group_name in ('ELIGIBLE','EXCLUDED')),
  eligibility_reason text not null,
  data_quality_ok boolean not null,

  source_model_version text not null,
  source_schema_fingerprint text not null
    check (source_schema_fingerprint ~ '^[0-9a-f]{64}$'),
  source_query_fingerprint text not null
    check (source_query_fingerprint ~ '^[0-9a-f]{64}$'),
  source_evidence_hash text not null
    check (source_evidence_hash ~ '^[0-9a-f]{64}$'),

  capture_contract_version text not null
    check (capture_contract_version='geometry-prospective-holdout-v0.1'),
  holdout boolean not null default true check (holdout=true),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  captured_at_utc timestamptz not null default clock_timestamp(),

  unique(spec_id,diagnostic_id),
  check (decision_available_at_utc>=source_created_at_utc),
  check (group_name='EXCLUDED' or data_quality_ok=true)
);


create table if not exists public.alpha_hunter_geometry_holdout_capture_failures (
  failure_id text primary key,
  spec_id text,
  diagnostic_id text,
  failed_at_utc timestamptz not null default clock_timestamp(),
  sqlstate text not null,
  error_message text not null,
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE')
);


alter table public.alpha_hunter_geometry_holdout_specs enable row level security;
alter table public.alpha_hunter_geometry_holdout_bindings enable row level security;
alter table public.alpha_hunter_geometry_holdout_capture_failures enable row level security;

revoke all on table public.alpha_hunter_geometry_holdout_specs
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_geometry_holdout_bindings
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_geometry_holdout_capture_failures
  from public,anon,authenticated,service_role;

grant select on table public.alpha_hunter_geometry_holdout_specs to service_role;
grant select on table public.alpha_hunter_geometry_holdout_bindings to service_role;
grant select on table public.alpha_hunter_geometry_holdout_capture_failures to service_role;


create index if not exists idx_ah_geometry_holdout_cooldown
  on public.alpha_hunter_geometry_holdout_bindings(
    spec_id,symbol,direction,decision_available_at_utc desc
  );

create index if not exists idx_ah_geometry_holdout_group_time
  on public.alpha_hunter_geometry_holdout_bindings(
    spec_id,group_name,decision_available_at_utc
  );


create or replace function private.alpha_hunter_block_geometry_holdout_mutation_v01()
returns trigger
language plpgsql
security invoker
set search_path=''
as $$
begin
  raise exception 'geometry holdout evidence is append-only';
end;
$$;

revoke all on function private.alpha_hunter_block_geometry_holdout_mutation_v01()
  from public,anon,authenticated,service_role;


drop trigger if exists trg_ah_geometry_holdout_specs_append_only
  on public.alpha_hunter_geometry_holdout_specs;
create trigger trg_ah_geometry_holdout_specs_append_only
before update or delete on public.alpha_hunter_geometry_holdout_specs
for each row execute function private.alpha_hunter_block_geometry_holdout_mutation_v01();

drop trigger if exists trg_ah_geometry_holdout_bindings_append_only
  on public.alpha_hunter_geometry_holdout_bindings;
create trigger trg_ah_geometry_holdout_bindings_append_only
before update or delete on public.alpha_hunter_geometry_holdout_bindings
for each row execute function private.alpha_hunter_block_geometry_holdout_mutation_v01();

drop trigger if exists trg_ah_geometry_holdout_failures_append_only
  on public.alpha_hunter_geometry_holdout_capture_failures;
create trigger trg_ah_geometry_holdout_failures_append_only
before update or delete on public.alpha_hunter_geometry_holdout_capture_failures
for each row execute function private.alpha_hunter_block_geometry_holdout_mutation_v01();


create or replace function private.alpha_hunter_geometry_holdout_number_v01(p_value text)
returns double precision
language plpgsql
immutable
security invoker
set search_path=''
as $$
begin
  if p_value is null
     or p_value !~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' then
    return null;
  end if;
  return p_value::double precision;
exception when others then
  return null;
end;
$$;

revoke all on function private.alpha_hunter_geometry_holdout_number_v01(text)
  from public,anon,authenticated,service_role;


create or replace function private.alpha_hunter_geometry_variant_v01(
  p_direction text,
  p_entry double precision,
  p_stop double precision,
  p_target double precision
)
returns jsonb
language plpgsql
immutable
security invoker
set search_path=''
as $$
declare
  v_valid boolean := false;
  v_rr double precision;
  v_stop_distance_pct double precision;
  v_target_distance_pct double precision;
begin
  if p_entry is not null and p_entry>0
     and p_stop is not null and p_target is not null then
    v_valid := (
      (upper(p_direction)='LONG' and p_stop<p_entry and p_target>p_entry)
      or
      (upper(p_direction)='SHORT' and p_stop>p_entry and p_target<p_entry)
    );

    v_stop_distance_pct := abs(p_entry-p_stop)/p_entry*100.0;
    v_target_distance_pct := abs(p_target-p_entry)/p_entry*100.0;

    if v_valid and abs(p_entry-p_stop)>0 then
      v_rr := abs(p_target-p_entry)/abs(p_entry-p_stop);
    end if;
  end if;

  return jsonb_build_object(
    'valid',v_valid,
    'stop',p_stop,
    'target',p_target,
    'rr',v_rr,
    'stop_distance_pct',v_stop_distance_pct,
    'target_distance_pct',v_target_distance_pct
  );
end;
$$;

revoke all on function private.alpha_hunter_geometry_variant_v01(
  text,double precision,double precision,double precision
) from public,anon,authenticated,service_role;


create or replace function private.alpha_hunter_geometry_variant_bundle_v01(
  p_direction text,
  p_entry double precision,
  p_support_15m double precision,
  p_resistance_15m double precision,
  p_support_1h double precision,
  p_resistance_1h double precision,
  p_support_4h double precision,
  p_resistance_4h double precision
)
returns jsonb
language plpgsql
immutable
security invoker
set search_path=''
as $$
declare
  v_stop_15m double precision;
  v_target_1h double precision;
  v_stop_1h double precision;
  v_target_4h double precision;
begin
  if upper(p_direction)='LONG' then
    v_stop_15m := p_support_15m;
    v_stop_1h := p_support_1h;
    v_target_1h := p_resistance_1h;
    v_target_4h := p_resistance_4h;
  elsif upper(p_direction)='SHORT' then
    v_stop_15m := p_resistance_15m;
    v_stop_1h := p_resistance_1h;
    v_target_1h := p_support_1h;
    v_target_4h := p_support_4h;
  end if;

  return jsonb_build_object(
    '1H_STOP_1H_TARGET',
      private.alpha_hunter_geometry_variant_v01(
        p_direction,p_entry,v_stop_1h,v_target_1h
      ),
    '15M_STOP_1H_TARGET',
      private.alpha_hunter_geometry_variant_v01(
        p_direction,p_entry,v_stop_15m,v_target_1h
      ),
    '15M_STOP_4H_TARGET',
      private.alpha_hunter_geometry_variant_v01(
        p_direction,p_entry,v_stop_15m,v_target_4h
      ),
    '1H_STOP_4H_TARGET',
      private.alpha_hunter_geometry_variant_v01(
        p_direction,p_entry,v_stop_1h,v_target_4h
      )
  );
end;
$$;

revoke all on function private.alpha_hunter_geometry_variant_bundle_v01(
  text,double precision,double precision,double precision,double precision,
  double precision,double precision,double precision
) from public,anon,authenticated,service_role;


create or replace function private.alpha_hunter_geometry_holdout_source_schema_fingerprint_v01()
returns text
language sql
stable
security invoker
set search_path=''
as $$
  with cols as (
    select
      'geometry'::text as source_relation,
      a.attnum,
      a.attname,
      pg_catalog.format_type(a.atttypid,a.atttypmod) as data_type,
      a.attnotnull
    from pg_catalog.pg_attribute a
    where a.attrelid=pg_catalog.to_regclass(
            'public.alpha_hunter_geometry_diagnostics'
          )
      and a.attnum>0
      and not a.attisdropped
      and a.attname=any(array[
        'diagnostic_id','run_id','source_signal_id','captured_at_utc',
        'symbol','candidate_direction','explicit_entry','model_version',
        'shadow_only','trade_permission','created_at'
      ])

    union all

    select
      'features'::text,
      a.attnum,
      a.attname,
      pg_catalog.format_type(a.atttypid,a.atttypmod),
      a.attnotnull
    from pg_catalog.pg_attribute a
    where a.attrelid=pg_catalog.to_regclass(
            'public.alpha_hunter_signal_features'
          )
      and a.attnum>0
      and not a.attisdropped
      and a.attname=any(array[
        'signal_id','run_id','symbol','captured_at_utc','source_payload'
      ])
  )
  select pg_catalog.encode(
    extensions.digest(
      pg_catalog.string_agg(
        source_relation||':'||attname||':'||data_type||':'||attnotnull::text,
        '|' order by source_relation,attnum
      ),
      'sha256'
    ),
    'hex'
  )
  from cols;
$$;

revoke all on function private.alpha_hunter_geometry_holdout_source_schema_fingerprint_v01()
  from public,anon,authenticated,service_role;


create or replace function private.alpha_hunter_geometry_holdout_query_fingerprint_v01()
returns text
language sql
stable
security invoker
set search_path=''
as $$
  select pg_catalog.encode(
    extensions.digest(
      coalesce(
        pg_catalog.pg_get_viewdef(
          pg_catalog.to_regclass(
            'public.alpha_hunter_geometry_multitimeframe_observations_v03'
          ),
          true
        ),
        ''
      )
      || '|SOURCE_CAPTURE|'
      || coalesce(
        pg_catalog.pg_get_functiondef(
          pg_catalog.to_regprocedure(
            'private.alpha_hunter_capture_geometry_diagnostics()'
          )
        ),
        ''
      )
      || '|HOLDOUT_VARIANT|'
      || coalesce(
        pg_catalog.pg_get_functiondef(
          pg_catalog.to_regprocedure(
            'private.alpha_hunter_geometry_variant_v01(text,double precision,double precision,double precision)'
          )
        ),
        ''
      )
      || '|HOLDOUT_BUNDLE|'
      || coalesce(
        pg_catalog.pg_get_functiondef(
          pg_catalog.to_regprocedure(
            'private.alpha_hunter_geometry_variant_bundle_v01(text,double precision,double precision,double precision,double precision,double precision,double precision,double precision)'
          )
        ),
        ''
      )
      || '|HOLDOUT_CAPTURE|'
      || coalesce(
        pg_catalog.pg_get_functiondef(
          pg_catalog.to_regprocedure(
            'private.alpha_hunter_capture_geometry_holdout_v01()'
          )
        ),
        ''
      ),
      'sha256'
    ),
    'hex'
  );
$$;

revoke all on function private.alpha_hunter_geometry_holdout_query_fingerprint_v01()
  from public,anon,authenticated,service_role;


create or replace function private.alpha_hunter_capture_geometry_holdout_v01()
returns trigger
language plpgsql
security definer
set search_path=''
as $$
declare
  v_spec public.alpha_hunter_geometry_holdout_specs%rowtype;
  v_decision_available_at timestamptz := clock_timestamp();
  v_schema_fingerprint text;
  v_query_fingerprint text;

  v_source_payload jsonb;
  v_source_run_id text;
  v_source_symbol text;

  v_support_15m double precision;
  v_resistance_15m double precision;
  v_support_1h double precision;
  v_resistance_1h double precision;
  v_support_4h double precision;
  v_resistance_4h double precision;

  v_bundle jsonb := '{}'::jsonb;
  v_all_variants_valid boolean := false;
  v_group_name text := 'EXCLUDED';
  v_reason text := 'UNCLASSIFIED';
  v_data_quality_ok boolean := false;
  v_source_hash text;
begin
  select * into v_spec
  from public.alpha_hunter_geometry_holdout_specs
  where spec_id='AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01'
    and status='COLLECTING';

  if not found then
    return new;
  end if;

  v_schema_fingerprint :=
    private.alpha_hunter_geometry_holdout_source_schema_fingerprint_v01();
  v_query_fingerprint :=
    private.alpha_hunter_geometry_holdout_query_fingerprint_v01();

  if new.shadow_only is not true or new.trade_permission is not false then
    v_reason := 'SAFETY_BOUNDARY_VIOLATION';

  elsif v_schema_fingerprint is distinct from v_spec.source_schema_fingerprint then
    v_reason := 'SOURCE_SCHEMA_DRIFT';

  elsif v_query_fingerprint is distinct from v_spec.source_query_fingerprint then
    v_reason := 'SOURCE_QUERY_DRIFT';

  elsif new.model_version
      is distinct from 'geometry-diagnostics-v0.2.2-money-entry-scope-aligned' then
    v_reason := 'SOURCE_VERSION_DRIFT';

  elsif new.created_at<=v_spec.registered_at_utc
     or new.captured_at_utc<=v_spec.registered_at_utc then
    v_reason := 'NOT_STRICTLY_POST_REGISTRATION';

  elsif v_decision_available_at>v_spec.collection_ends_at_utc
     or new.created_at>v_spec.collection_ends_at_utc
     or new.captured_at_utc>v_spec.collection_ends_at_utc then
    v_reason := 'AFTER_COLLECTION_WINDOW';

  elsif new.source_signal_id is null then
    v_reason := 'SOURCE_SIGNAL_MISSING';

  elsif new.explicit_entry is null or new.explicit_entry<=0 then
    v_reason := 'ENTRY_MISSING_OR_INVALID';

  else
    select
      sf.source_payload,
      sf.run_id,
      sf.symbol
    into
      v_source_payload,
      v_source_run_id,
      v_source_symbol
    from public.alpha_hunter_signal_features sf
    where sf.signal_id=new.source_signal_id
      and sf.run_id=new.run_id
      and sf.symbol=new.symbol
    order by sf.captured_at_utc desc
    limit 1;

    if not found or v_source_payload is null then
      v_reason := 'FROZEN_SOURCE_PAYLOAD_MISSING';
    else
      v_support_15m :=
        private.alpha_hunter_geometry_holdout_number_v01(
          v_source_payload#>>'{timeframes,15m,support}'
        );
      v_resistance_15m :=
        private.alpha_hunter_geometry_holdout_number_v01(
          v_source_payload#>>'{timeframes,15m,resistance}'
        );
      v_support_1h :=
        private.alpha_hunter_geometry_holdout_number_v01(
          v_source_payload#>>'{timeframes,1H,support}'
        );
      v_resistance_1h :=
        private.alpha_hunter_geometry_holdout_number_v01(
          v_source_payload#>>'{timeframes,1H,resistance}'
        );
      v_support_4h :=
        private.alpha_hunter_geometry_holdout_number_v01(
          v_source_payload#>>'{timeframes,4H,support}'
        );
      v_resistance_4h :=
        private.alpha_hunter_geometry_holdout_number_v01(
          v_source_payload#>>'{timeframes,4H,resistance}'
        );

      v_bundle := private.alpha_hunter_geometry_variant_bundle_v01(
        new.candidate_direction,
        new.explicit_entry,
        v_support_15m,
        v_resistance_15m,
        v_support_1h,
        v_resistance_1h,
        v_support_4h,
        v_resistance_4h
      );

      v_all_variants_valid :=
        coalesce((v_bundle#>>'{1H_STOP_1H_TARGET,valid}')::boolean,false)
        and coalesce((v_bundle#>>'{15M_STOP_1H_TARGET,valid}')::boolean,false)
        and coalesce((v_bundle#>>'{15M_STOP_4H_TARGET,valid}')::boolean,false)
        and coalesce((v_bundle#>>'{1H_STOP_4H_TARGET,valid}')::boolean,false);

      if not v_all_variants_valid then
        v_reason := 'COMMON_VARIANT_GEOMETRY_INCOMPLETE';
      else
        perform pg_catalog.pg_advisory_xact_lock(
          pg_catalog.hashtextextended(
            v_spec.spec_id||'|'||new.symbol||'|'||new.candidate_direction,
            0
          )
        );

        if exists (
          select 1
          from public.alpha_hunter_geometry_holdout_bindings b
          where b.spec_id=v_spec.spec_id
            and b.symbol=new.symbol
            and b.direction=new.candidate_direction
            and b.group_name='ELIGIBLE'
            and b.decision_available_at_utc
                  > v_decision_available_at - interval '24 hours'
        ) then
          v_reason := 'SYMBOL_DIRECTION_24H_COOLDOWN';
        else
          v_group_name := 'ELIGIBLE';
          v_reason := 'COMMON_VARIANT_GEOMETRY_COMPLETE';
          v_data_quality_ok := true;
        end if;
      end if;
    end if;
  end if;

  v_source_hash := pg_catalog.encode(
    extensions.digest(
      jsonb_build_object(
        'diagnostic_id',new.diagnostic_id,
        'run_id',new.run_id,
        'source_signal_id',new.source_signal_id,
        'captured_at_utc',new.captured_at_utc,
        'created_at',new.created_at,
        'symbol',new.symbol,
        'direction',new.candidate_direction,
        'entry_price',new.explicit_entry,
        'source_model_version',new.model_version,
        'source_payload',coalesce(v_source_payload,'{}'::jsonb),
        'variant_geometry',coalesce(v_bundle,'{}'::jsonb),
        'shadow_only',new.shadow_only,
        'trade_permission',new.trade_permission
      )::text,
      'sha256'
    ),
    'hex'
  );

  insert into public.alpha_hunter_geometry_holdout_bindings(
    binding_id,spec_id,diagnostic_id,source_signal_id,
    registered_at_utc,source_captured_at_utc,source_created_at_utc,
    decision_available_at_utc,symbol,direction,entry_price,
    support_15m,resistance_15m,support_1h,resistance_1h,
    support_4h,resistance_4h,variant_geometry,
    group_name,eligibility_reason,data_quality_ok,source_model_version,
    source_schema_fingerprint,source_query_fingerprint,source_evidence_hash,
    capture_contract_version,holdout,shadow_only,trade_permission,
    production_promotion_permitted,order_path
  ) values (
    pg_catalog.md5(v_spec.spec_id||'|'||new.diagnostic_id),
    v_spec.spec_id,new.diagnostic_id,new.source_signal_id,
    v_spec.registered_at_utc,new.captured_at_utc,new.created_at,
    v_decision_available_at,new.symbol,new.candidate_direction,new.explicit_entry,
    v_support_15m,v_resistance_15m,v_support_1h,v_resistance_1h,
    v_support_4h,v_resistance_4h,coalesce(v_bundle,'{}'::jsonb),
    v_group_name,v_reason,v_data_quality_ok,new.model_version,
    v_schema_fingerprint,v_query_fingerprint,v_source_hash,
    'geometry-prospective-holdout-v0.1',true,true,false,false,'NONE'
  )
  on conflict(spec_id,diagnostic_id) do nothing;

  return new;

exception when others then
  begin
    insert into public.alpha_hunter_geometry_holdout_capture_failures(
      failure_id,spec_id,diagnostic_id,sqlstate,error_message,
      shadow_only,trade_permission,production_promotion_permitted,order_path
    ) values (
      pg_catalog.md5(
        coalesce(v_spec.spec_id,'NO_SPEC')
        ||'|'||coalesce(new.diagnostic_id,'NO_DIAGNOSTIC')
        ||'|'||sqlstate||'|'||clock_timestamp()::text
      ),
      v_spec.spec_id,new.diagnostic_id,sqlstate,left(sqlerrm,1000),
      true,false,false,'NONE'
    );
  exception when others then
    null;
  end;

  raise warning 'geometry holdout capture failed for diagnostic %: %',
    new.diagnostic_id,left(sqlerrm,500);
  return new;
end;
$$;

revoke all on function private.alpha_hunter_capture_geometry_holdout_v01()
  from public,anon,authenticated,service_role;


drop trigger if exists trg_ah_capture_geometry_holdout_v01
  on public.alpha_hunter_geometry_diagnostics;
create trigger trg_ah_capture_geometry_holdout_v01
after insert on public.alpha_hunter_geometry_diagnostics
for each row execute function private.alpha_hunter_capture_geometry_holdout_v01();


create or replace function private.alpha_hunter_register_geometry_holdout_v01()
returns void
language plpgsql
security definer
set search_path=''
as $$
declare
  v_spec_id constant text := 'AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01';
  v_hypothesis_id constant text :=
    'H_15M_STOP_4H_TARGET_Q5_PATH_VS_1H_BASELINE_24H_V1';

  v_schema_fingerprint text;
  v_query_fingerprint text;
  v_spec_hash text;
  v_protocol jsonb;
  v_registered_at timestamptz;
  v_existing public.alpha_hunter_geometry_holdout_specs%rowtype;
begin
  v_schema_fingerprint :=
    private.alpha_hunter_geometry_holdout_source_schema_fingerprint_v01();
  v_query_fingerprint :=
    private.alpha_hunter_geometry_holdout_query_fingerprint_v01();

  if v_schema_fingerprint is null or v_query_fingerprint is null then
    raise exception 'geometry holdout source fingerprint is unavailable';
  end if;

  v_protocol := jsonb_build_object(
    'design',
      'prospective paired candidate-level structural-geometry holdout; capture-only in v0.1',
    'selection_context',
      '15M_STOP_4H_TARGET was selected as the single primary alternative after the explicitly retrospective v0.3 exploratory screen; all pre-registration observations are prohibited from confirmatory use',
    'primary_contrast',
      '15M_STOP_4H_TARGET minus 1H_STOP_1H_TARGET on the same future candidate',
    'primary_endpoint',
      'Q5_TARGET_FIRST_24H',
    'primary_endpoint_definition',
      'binary paired endpoint: using the first post-decision fully complete public Bitget 3m candle open as reference price, recompute variant validity and RR from frozen stop/target; success=reference RR >= 5.0 AND target is touched before stop within 24H; STOP_FIRST and NEITHER are failures; BOTH_TOUCHED_IN_SAME_3M_CANDLE is ambiguous/incomplete and may not be direction-guessed',
    'reference_price_rule',
      'reference open is the open of the first fully complete public Bitget 3m candle whose open_time >= ceil_3m(decision_available_at_utc); never use a pre-decision candle or source entry as a fill claim',
    'path_rule',
      'scan fully complete public Bitget 3m candles in chronological order; LONG stop touch=low<=frozen stop, target touch=high>=frozen target; SHORT stop touch=high>=frozen stop, target touch=low<=frozen target; if both first occur in one candle classify BOTH_TOUCHED_IN_SAME_3M_CANDLE and do not infer intrabar order',
    'primary_horizon_hours',24,
    'secondary_horizon_hours',12,
    'secondary_endpoints',
      jsonb_build_array(
        'Q5_TARGET_FIRST_12H',
        'TARGET_FIRST_RATE_REGARDLESS_OF_RR',
        'STOP_FIRST_RATE',
        'NEITHER_RATE',
        'REFERENCE_RR_DISTRIBUTION',
        '15M_STOP_1H_TARGET_DESCRIPTIVE',
        '1H_STOP_4H_TARGET_DESCRIPTIVE'
      ),
    'candidate_unit',
      'one eligible symbol-direction diagnostic after a 24H symbol-direction cooldown; all four variants are frozen on the same candidate',
    'eligibility_rule',
      'strictly post-registration v0.2.2 scope-aligned shadow geometry row with trade_permission=false, matching frozen signal payload, positive entry, and candidate-time valid geometry for all four preregistered variants',
    'overlap_rule',
      'first ELIGIBLE symbol-direction observation after a 24-hour cooldown; overlapping rows remain EXCLUDED and visible',
    'minimum_paired_candidates',100,
    'minimum_symbols',30,
    'minimum_utc_days',20,
    'minimum_candidates_per_direction',25,
    'maximum_collection_days',60,
    'pairing_rule',
      'within-candidate pairing is intrinsic: the same eligible candidate supplies baseline and primary-alternative geometry; no post-hoc matching or replacement',
    'primary_statistic',
      'paired mean difference in binary Q5_TARGET_FIRST_24H success, primary alternative minus baseline',
    'inference',
      'one-sided exact McNemar test for discordant paired outcomes at alpha 0.025 plus a 95% candidate-clustered bootstrap confidence interval for the paired success-rate difference; support additionally requires positive lower confidence bound and at least +5 percentage points absolute paired success-rate improvement',
    'minimum_practical_effect_percentage_points',5.0,
    'bootstrap',
      'resample eligible candidate bindings with replacement; keep baseline and all variants together within each resampled candidate; 100000 draws; PRNG seed 2026092001; percentile 2.5%/97.5% interval',
    'missing_data_rule',
      'primary pair requires complete reference candle coverage and non-ambiguous 24H first-touch classification for both primary alternative and baseline; no imputation; if incomplete primary pairs exceed 10% of otherwise eligible matured candidates, result is INCONCLUSIVE',
    'multiplicity_rule',
      'one confirmatory primary contrast and one confirmatory 24H endpoint only; 12H and other geometry variants are secondary/descriptive and cannot independently support the hypothesis',
    'day_60_rule',
      'freeze the cohort at the first scheduled UTC-day close when all minimum gates are met, otherwise at day 60; if gates are not met by day 60 conclude INCONCLUSIVE without extending or relaxing',
    'source_rule',
      'capture from alpha_hunter_geometry_diagnostics model geometry-diagnostics-v0.2.2-money-entry-scope-aligned and its exact frozen alpha_hunter_signal_features payload only; source/view/function fingerprints must remain unchanged',
    'prohibited_claims',
      jsonb_build_array(
        'actual_fill',
        'live_profitability',
        'production_ready',
        'threshold_validated',
        'T0_authorized',
        'T1_authorized',
        'T2_authorized'
      ),
    'claim_ceiling',
      'PROSPECTIVELY SUPPORTED IN SHADOW - INDEPENDENT REPLICATION REQUIRED; never READY, profitable, executable, or production-safe',
    'falsification',
      'any preregistration breach, source/fingerprint drift, safety violation, outcome peeking before cohort freeze, primary p-value > 0.025, primary 95% lower bound <= 0, paired improvement < 5 percentage points, excessive incomplete-pair attrition, or failure to meet sample gates by day 60 prevents support',
    'capture_contract_version','geometry-prospective-holdout-v0.1',
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );

  v_spec_hash := pg_catalog.encode(
    extensions.digest(
      jsonb_build_object(
        'spec_id',v_spec_id,
        'hypothesis_id',v_hypothesis_id,
        'primary_variant','15M_STOP_4H_TARGET',
        'baseline_variant','1H_STOP_1H_TARGET',
        'primary_endpoint','Q5_TARGET_FIRST_24H',
        'protocol',v_protocol,
        'source_schema_fingerprint',v_schema_fingerprint,
        'source_query_fingerprint',v_query_fingerprint
      )::text,
      'sha256'
    ),
    'hex'
  );

  select * into v_existing
  from public.alpha_hunter_geometry_holdout_specs
  where spec_id=v_spec_id;

  if found then
    if v_existing.spec_hash is distinct from v_spec_hash
       or v_existing.protocol is distinct from v_protocol
       or v_existing.source_schema_fingerprint
            is distinct from v_schema_fingerprint
       or v_existing.source_query_fingerprint
            is distinct from v_query_fingerprint
       or v_existing.collection_ends_at_utc
            is distinct from v_existing.registered_at_utc + interval '60 days' then
      raise exception 'geometry holdout specification conflict for %',v_spec_id;
    end if;
  else
    v_registered_at := clock_timestamp();

    insert into public.alpha_hunter_geometry_holdout_specs(
      spec_id,hypothesis_id,registered_at_utc,collection_ends_at_utc,
      primary_variant,baseline_variant,primary_endpoint,
      primary_horizon_hours,secondary_horizon_hours,
      minimum_paired_candidates,minimum_symbols,minimum_utc_days,
      minimum_candidates_per_direction,maximum_collection_days,
      protocol,source_schema_fingerprint,source_query_fingerprint,spec_hash,
      capture_contract_version,shadow_only,trade_permission,
      production_promotion_permitted,order_path
    ) values (
      v_spec_id,v_hypothesis_id,
      v_registered_at,v_registered_at + interval '60 days',
      '15M_STOP_4H_TARGET','1H_STOP_1H_TARGET','Q5_TARGET_FIRST_24H',
      24,12,100,30,20,25,60,
      v_protocol,v_schema_fingerprint,v_query_fingerprint,v_spec_hash,
      'geometry-prospective-holdout-v0.1',true,false,false,'NONE'
    );
  end if;
end;
$$;

revoke all on function private.alpha_hunter_register_geometry_holdout_v01()
  from public,anon,authenticated,service_role;


-- Register only after all capture helpers, the capture function, and its trigger
-- exist. There is therefore no post-registration gap in which a new canonical
-- geometry row could arrive without being classified by this holdout.
select private.alpha_hunter_register_geometry_holdout_v01();
drop function private.alpha_hunter_register_geometry_holdout_v01();


create or replace view public.alpha_hunter_geometry_holdout_status_v01
with (security_invoker=true,security_barrier=true)
as
with counts as (
  select
    s.spec_id,
    count(b.binding_id) as captured,
    count(b.binding_id) filter (where b.group_name='ELIGIBLE') as eligible,
    count(b.binding_id) filter (where b.group_name='EXCLUDED') as excluded,
    count(distinct b.symbol) filter (where b.group_name='ELIGIBLE') as symbols,
    count(distinct (b.decision_available_at_utc at time zone 'UTC')::date)
      filter (where b.group_name='ELIGIBLE') as utc_days,
    count(b.binding_id)
      filter (where b.group_name='ELIGIBLE' and b.direction='LONG') as long_eligible,
    count(b.binding_id)
      filter (where b.group_name='ELIGIBLE' and b.direction='SHORT') as short_eligible
  from public.alpha_hunter_geometry_holdout_specs s
  left join public.alpha_hunter_geometry_holdout_bindings b
    on b.spec_id=s.spec_id
  group by s.spec_id
)
select
  s.spec_id,
  s.hypothesis_id,
  'COLLECTING - CAPTURE ONLY - NOT YET EVALUABLE'::text as scientific_status,
  s.registered_at_utc,
  s.collection_ends_at_utc,
  s.primary_variant,
  s.baseline_variant,
  s.primary_endpoint,
  s.primary_horizon_hours,
  s.secondary_horizon_hours,
  c.captured,
  c.eligible,
  c.excluded,
  c.symbols,
  c.utc_days,
  c.long_eligible,
  c.short_eligible,
  (
    c.eligible>=s.minimum_paired_candidates
    and c.symbols>=s.minimum_symbols
    and c.utc_days>=s.minimum_utc_days
    and c.long_eligible>=s.minimum_candidates_per_direction
    and c.short_eligible>=s.minimum_candidates_per_direction
  ) as capture_sample_gate_met,
  (
    select count(*)
    from public.alpha_hunter_geometry_holdout_capture_failures f
    where f.spec_id=s.spec_id
  ) as capture_failures,
  s.minimum_paired_candidates,
  s.minimum_symbols,
  s.minimum_utc_days,
  s.minimum_candidates_per_direction,
  'IMPLEMENT_FROZEN_PUBLIC_3M_FIRST_TOUCH_EVALUATOR; DO NOT CHANGE SPEC OR READ PRIMARY OUTCOMES BEFORE COHORT FREEZE'::text as next_gate,
  'NONE'::text as scientific_conclusion,
  s.spec_hash,
  s.source_schema_fingerprint,
  s.source_query_fingerprint,
  s.shadow_only,
  s.trade_permission,
  s.production_promotion_permitted,
  s.order_path
from public.alpha_hunter_geometry_holdout_specs s
join counts c on c.spec_id=s.spec_id;

revoke all on public.alpha_hunter_geometry_holdout_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_geometry_holdout_status_v01 to service_role;
