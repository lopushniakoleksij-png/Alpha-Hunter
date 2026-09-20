-- Alpha Hunter sealed prospective geometry evaluator v0.1
--
-- Operational purpose:
--   Preserve the preregistered 12H/24H public 3-minute path evidence for the
--   forward-only geometry holdout without exposing hypothesis outcomes during
--   collection.
--
-- Scientific boundary:
--   * This does NOT analyze the hypothesis.
--   * The outcome table is sealed from public/anon/authenticated/service_role.
--   * The service-role status surface exposes operational counts only.
--   * No variant-specific success/path/RR result is exposed before cohort freeze.
--   * A later, separately reviewed freeze/unseal migration is required.
--
-- Execution boundary:
--   Public market-data HTTP only. No private Bitget endpoint, order path,
--   threshold activation, T0/T1/T2 authority, risk, leverage, or promotion.

create table if not exists public.alpha_hunter_geometry_holdout_outcomes_sealed (
  outcome_id text primary key,
  spec_id text not null,
  binding_id text not null,
  diagnostic_id text not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  research_variant text not null check (
    research_variant in (
      '1H_STOP_1H_TARGET',
      '15M_STOP_1H_TARGET',
      '15M_STOP_4H_TARGET',
      '1H_STOP_4H_TARGET'
    )
  ),
  horizon_hours integer not null check (horizon_hours in (12,24)),
  decision_available_at_utc timestamptz not null,
  horizon_due_at_utc timestamptz not null,

  reference_candle_at_utc timestamptz,
  reference_open double precision,
  reference_geometry_valid boolean,
  reference_rr double precision,

  frozen_stop double precision,
  frozen_target double precision,

  expected_candle_count integer,
  observed_candle_count integer,
  missing_candle_count integer,

  first_stop_candle_at_utc timestamptz,
  first_target_candle_at_utc timestamptz,
  path_class text not null check (
    path_class in (
      'TARGET_FIRST',
      'STOP_FIRST',
      'NEITHER',
      'BOTH_TOUCHED_IN_SAME_3M_CANDLE',
      'REFERENCE_GEOMETRY_INVALID',
      'DATA_INSUFFICIENT'
    )
  ),
  q5_target_first boolean,

  evaluation_status text not null check (
    evaluation_status in (
      'EVALUATED',
      'AMBIGUOUS_INTRABAR',
      'REFERENCE_GEOMETRY_INVALID',
      'DATA_INSUFFICIENT'
    )
  ),
  measurement_source text not null
    check (measurement_source='BITGET_PUBLIC_V3_3M_CANDLES'),
  evaluator_version text not null
    check (evaluator_version='geometry-holdout-sealed-evaluator-v0.1'),

  reference_price_is_fill_claim boolean not null default false
    check (reference_price_is_fill_claim=false),
  exact_intrabar_order_claim_permitted boolean not null default false
    check (exact_intrabar_order_claim_permitted=false),

  source_evidence_hash text not null
    check (source_evidence_hash ~ '^[0-9a-f]{64}$'),
  result_hash text not null unique
    check (result_hash ~ '^[0-9a-f]{64}$'),

  evaluated_at_utc timestamptz not null default clock_timestamp(),

  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),

  unique(binding_id,research_variant,horizon_hours),
  check (horizon_due_at_utc=decision_available_at_utc + make_interval(hours=>horizon_hours)),
  check (
    evaluation_status<>'EVALUATED'
    or path_class in ('TARGET_FIRST','STOP_FIRST','NEITHER')
  ),
  check (
    path_class<>'BOTH_TOUCHED_IN_SAME_3M_CANDLE'
    or evaluation_status='AMBIGUOUS_INTRABAR'
  ),
  check (
    q5_target_first is null
    or (
      evaluation_status='EVALUATED'
      and reference_geometry_valid=true
      and reference_rr is not null
    )
  )
);


create table if not exists public.alpha_hunter_geometry_holdout_evaluator_failures (
  failure_id text primary key,
  spec_id text,
  binding_id text,
  horizon_hours integer,
  failed_at_utc timestamptz not null default clock_timestamp(),
  error_class text not null,
  error_message text not null,
  evaluator_version text not null
    check (evaluator_version='geometry-holdout-sealed-evaluator-v0.1'),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE')
);


alter table public.alpha_hunter_geometry_holdout_outcomes_sealed enable row level security;
alter table public.alpha_hunter_geometry_holdout_evaluator_failures enable row level security;

-- Intentionally NO SELECT grant to service_role. Results remain sealed.
revoke all on table public.alpha_hunter_geometry_holdout_outcomes_sealed
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_geometry_holdout_evaluator_failures
  from public,anon,authenticated,service_role;


create index if not exists idx_ah_geometry_holdout_outcomes_binding_horizon
  on public.alpha_hunter_geometry_holdout_outcomes_sealed(
    binding_id,horizon_hours,research_variant
  );

create index if not exists idx_ah_geometry_holdout_eval_failure_binding_horizon
  on public.alpha_hunter_geometry_holdout_evaluator_failures(
    binding_id,horizon_hours,failed_at_utc desc
  );


create or replace function private.alpha_hunter_block_geometry_holdout_outcome_mutation_v01()
returns trigger
language plpgsql
security invoker
set search_path=''
as $$
begin
  raise exception 'sealed geometry holdout outcomes are append-only';
end;
$$;

revoke all on function private.alpha_hunter_block_geometry_holdout_outcome_mutation_v01()
  from public,anon,authenticated,service_role;


drop trigger if exists trg_ah_geometry_holdout_outcomes_sealed_append_only
  on public.alpha_hunter_geometry_holdout_outcomes_sealed;
create trigger trg_ah_geometry_holdout_outcomes_sealed_append_only
before update or delete on public.alpha_hunter_geometry_holdout_outcomes_sealed
for each row execute function private.alpha_hunter_block_geometry_holdout_outcome_mutation_v01();

drop trigger if exists trg_ah_geometry_holdout_evaluator_failures_append_only
  on public.alpha_hunter_geometry_holdout_evaluator_failures;
create trigger trg_ah_geometry_holdout_evaluator_failures_append_only
before update or delete on public.alpha_hunter_geometry_holdout_evaluator_failures
for each row execute function private.alpha_hunter_block_geometry_holdout_outcome_mutation_v01();


create or replace function private.alpha_hunter_record_geometry_holdout_eval_failure_v01(
  p_spec_id text,
  p_binding_id text,
  p_horizon_hours integer,
  p_error_class text,
  p_error_message text
)
returns void
language plpgsql
security definer
set search_path=''
as $$
begin
  insert into public.alpha_hunter_geometry_holdout_evaluator_failures(
    failure_id,spec_id,binding_id,horizon_hours,error_class,error_message,
    evaluator_version,shadow_only,trade_permission,
    production_promotion_permitted,order_path
  ) values (
    pg_catalog.md5(
      coalesce(p_spec_id,'NO_SPEC')||'|'
      ||coalesce(p_binding_id,'NO_BINDING')||'|'
      ||coalesce(p_horizon_hours::text,'NO_HORIZON')||'|'
      ||coalesce(p_error_class,'NO_CLASS')||'|'
      ||clock_timestamp()::text
    ),
    p_spec_id,p_binding_id,p_horizon_hours,
    coalesce(p_error_class,'UNCLASSIFIED'),
    left(coalesce(p_error_message,'UNKNOWN'),1000),
    'geometry-holdout-sealed-evaluator-v0.1',
    true,false,false,'NONE'
  );
exception when others then
  null;
end;
$$;

revoke all on function private.alpha_hunter_record_geometry_holdout_eval_failure_v01(
  text,text,integer,text,text
) from public,anon,authenticated,service_role;


create or replace function private.alpha_hunter_insert_geometry_holdout_data_insufficient_v01(
  p_binding_id text,
  p_horizon_hours integer,
  p_reason text
)
returns integer
language plpgsql
security definer
set search_path=''
as $$
declare
  b public.alpha_hunter_geometry_holdout_bindings%rowtype;
  v_variant record;
  v_due timestamptz;
  v_hash text;
  v_inserted integer := 0;
begin
  select * into b
  from public.alpha_hunter_geometry_holdout_bindings
  where binding_id=p_binding_id
    and group_name='ELIGIBLE'
    and shadow_only=true
    and trade_permission=false;

  if not found then
    return 0;
  end if;

  v_due := b.decision_available_at_utc + make_interval(hours=>p_horizon_hours);

  for v_variant in
    select key as research_variant,value as geometry
    from jsonb_each(b.variant_geometry)
    where key in (
      '1H_STOP_1H_TARGET',
      '15M_STOP_1H_TARGET',
      '15M_STOP_4H_TARGET',
      '1H_STOP_4H_TARGET'
    )
  loop
    v_hash := pg_catalog.encode(
      extensions.digest(
        jsonb_build_object(
          'spec_id',b.spec_id,
          'binding_id',b.binding_id,
          'research_variant',v_variant.research_variant,
          'horizon_hours',p_horizon_hours,
          'path_class','DATA_INSUFFICIENT',
          'reason',left(coalesce(p_reason,'UNKNOWN'),500),
          'source_evidence_hash',b.source_evidence_hash,
          'evaluator_version','geometry-holdout-sealed-evaluator-v0.1'
        )::text,
        'sha256'
      ),
      'hex'
    );

    insert into public.alpha_hunter_geometry_holdout_outcomes_sealed(
      outcome_id,spec_id,binding_id,diagnostic_id,symbol,direction,
      research_variant,horizon_hours,decision_available_at_utc,horizon_due_at_utc,
      reference_candle_at_utc,reference_open,reference_geometry_valid,reference_rr,
      frozen_stop,frozen_target,
      expected_candle_count,observed_candle_count,missing_candle_count,
      first_stop_candle_at_utc,first_target_candle_at_utc,
      path_class,q5_target_first,evaluation_status,
      measurement_source,evaluator_version,
      reference_price_is_fill_claim,exact_intrabar_order_claim_permitted,
      source_evidence_hash,result_hash,
      shadow_only,trade_permission,production_promotion_permitted,order_path
    ) values (
      pg_catalog.md5(
        'geometry-holdout-sealed-v0.1|'||b.binding_id||'|'
        ||v_variant.research_variant||'|'||p_horizon_hours::text
      ),
      b.spec_id,b.binding_id,b.diagnostic_id,b.symbol,b.direction,
      v_variant.research_variant,p_horizon_hours,
      b.decision_available_at_utc,v_due,
      null,null,null,null,
      private.alpha_hunter_geometry_holdout_number_v01(
        v_variant.geometry->>'stop'
      ),
      private.alpha_hunter_geometry_holdout_number_v01(
        v_variant.geometry->>'target'
      ),
      null,null,null,null,null,
      'DATA_INSUFFICIENT',null,'DATA_INSUFFICIENT',
      'BITGET_PUBLIC_V3_3M_CANDLES',
      'geometry-holdout-sealed-evaluator-v0.1',
      false,false,b.source_evidence_hash,v_hash,
      true,false,false,'NONE'
    )
    on conflict(binding_id,research_variant,horizon_hours) do nothing;

    if found then
      v_inserted := v_inserted+1;
    end if;
  end loop;

  return v_inserted;
end;
$$;

revoke all on function private.alpha_hunter_insert_geometry_holdout_data_insufficient_v01(
  text,integer,text
) from public,anon,authenticated,service_role;


create or replace function private.alpha_hunter_run_geometry_holdout_sealed_v01()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  r record;

  v_reference_start timestamptz;
  v_horizon_due timestamptz;
  v_last_expected_open timestamptz;
  v_expected_count integer;
  v_observed_count integer;
  v_missing_count integer;
  v_reference_open double precision;

  v_url text;
  v_status integer;
  v_content text;
  v_payload jsonb;

  v_prior_failures integer;
  v_inserted integer;
  v_processed integer := 0;
  v_finalized_sets integer := 0;
  v_sealed_rows integer := 0;
  v_retry_failures integer := 0;
  v_data_insufficient_sets integer := 0;
  v_err text;
begin
  for r in
    with due as (
      select
        b.*,
        h.horizon_hours,
        b.decision_available_at_utc
          + make_interval(hours=>h.horizon_hours) as horizon_due_at_utc
      from public.alpha_hunter_geometry_holdout_bindings b
      cross join (values(12),(24)) h(horizon_hours)
      where b.spec_id='AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01'
        and b.group_name='ELIGIBLE'
        and b.shadow_only=true
        and b.trade_permission=false
        and b.decision_available_at_utc
              + make_interval(hours=>h.horizon_hours)
              + interval '5 minutes' <= clock_timestamp()
        and not exists (
          select 1
          from public.alpha_hunter_geometry_holdout_outcomes_sealed o
          where o.binding_id=b.binding_id
            and o.horizon_hours=h.horizon_hours
        )
    )
    select *
    from due
    order by horizon_due_at_utc,binding_id
    limit 40
  loop
    v_processed := v_processed+1;

    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(
        'GEOMETRY_HOLDOUT_EVAL|'
        ||r.binding_id||'|'||r.horizon_hours::text,
        0
      )
    );

    if exists (
      select 1
      from public.alpha_hunter_geometry_holdout_outcomes_sealed o
      where o.binding_id=r.binding_id
        and o.horizon_hours=r.horizon_hours
    ) then
      continue;
    end if;

    begin
      if r.symbol !~ '^[A-Z0-9]+USDT$' then
        raise exception 'SYMBOL_NOT_URL_SAFE';
      end if;

      v_horizon_due := r.horizon_due_at_utc;

      v_reference_start := pg_catalog.to_timestamp(
        ceil(
          extract(epoch from r.decision_available_at_utc)/180.0
        )*180.0
      );

      v_last_expected_open := pg_catalog.to_timestamp(
        floor(
          (extract(epoch from v_horizon_due)-180.0)/180.0
        )*180.0
      );

      if v_last_expected_open<v_reference_start then
        raise exception 'INVALID_EXPECTED_CANDLE_WINDOW';
      end if;

      v_expected_count := (
        floor(
          extract(epoch from(v_last_expected_open-v_reference_start))/180.0
        )::integer + 1
      );

      if v_expected_count<=0 or v_expected_count>1000 then
        raise exception 'EXPECTED_CANDLE_COUNT_OUT_OF_RANGE:%',v_expected_count;
      end if;

      v_url := pg_catalog.format(
        'https://api.bitget.com/api/v3/market/candles?category=USDT-FUTURES&symbol=%s&interval=3m&startTime=%s&endTime=%s&limit=1000',
        r.symbol,
        floor(extract(epoch from v_reference_start)*1000)::bigint,
        floor(extract(epoch from v_horizon_due)*1000)::bigint
      );

      select (x).status,(x).content
      into v_status,v_content
      from (select extensions.http_get(v_url) as x) q;

      if v_status<>200 then
        raise exception 'BITGET_HTTP_STATUS:%',v_status;
      end if;

      v_payload := v_content::jsonb;

      if coalesce(v_payload->>'code','')<>'00000' then
        raise exception 'BITGET_PAYLOAD_CODE:%',v_payload->>'code';
      end if;

      with raw as (
        select value as bar
        from jsonb_array_elements(coalesce(v_payload->'data','[]'::jsonb))
      ),
      parsed as (
        select distinct on ((bar->>0)::bigint)
          pg_catalog.to_timestamp((bar->>0)::double precision/1000.0) as ts,
          (bar->>1)::double precision as open_price,
          (bar->>2)::double precision as high_price,
          (bar->>3)::double precision as low_price,
          (bar->>4)::double precision as close_price
        from raw
        where (bar->>0) ~ '^[0-9]+$'
          and (bar->>1) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>2) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>3) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>4) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        order by (bar->>0)::bigint
      ),
      w as (
        select *
        from parsed
        where ts>=v_reference_start
          and ts<=v_last_expected_open
      ),
      expected as (
        select g as ts
        from pg_catalog.generate_series(
          v_reference_start,
          v_last_expected_open,
          interval '3 minutes'
        ) g
      )
      select
        (select count(*)::integer from w),
        (
          select count(*)::integer
          from expected e
          where not exists (
            select 1 from w where w.ts=e.ts
          )
        ),
        (
          select open_price
          from w
          where ts=v_reference_start
          limit 1
        )
      into
        v_observed_count,
        v_missing_count,
        v_reference_open;

      if v_reference_open is null
         or v_missing_count<>0
         or v_observed_count<>v_expected_count then
        raise exception
          'INCOMPLETE_3M_COVERAGE expected=% observed=% missing=% ref=%',
          v_expected_count,v_observed_count,v_missing_count,v_reference_open;
      end if;

      with raw as (
        select value as bar
        from jsonb_array_elements(coalesce(v_payload->'data','[]'::jsonb))
      ),
      parsed as (
        select distinct on ((bar->>0)::bigint)
          pg_catalog.to_timestamp((bar->>0)::double precision/1000.0) as ts,
          (bar->>1)::double precision as open_price,
          (bar->>2)::double precision as high_price,
          (bar->>3)::double precision as low_price,
          (bar->>4)::double precision as close_price
        from raw
        where (bar->>0) ~ '^[0-9]+$'
          and (bar->>1) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>2) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>3) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>4) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        order by (bar->>0)::bigint
      ),
      w as (
        select *
        from parsed
        where ts>=v_reference_start
          and ts<=v_last_expected_open
      ),
      variants as (
        select
          key as research_variant,
          private.alpha_hunter_geometry_holdout_number_v01(value->>'stop') as stop_price,
          private.alpha_hunter_geometry_holdout_number_v01(value->>'target') as target_price
        from jsonb_each(r.variant_geometry)
        where key in (
          '1H_STOP_1H_TARGET',
          '15M_STOP_1H_TARGET',
          '15M_STOP_4H_TARGET',
          '1H_STOP_4H_TARGET'
        )
      ),
      geometry as (
        select
          v.*,
          (
            v_reference_open is not null
            and v_reference_open>0
            and v.stop_price is not null
            and v.target_price is not null
            and (
              (r.direction='LONG'
                and v.stop_price<v_reference_open
                and v.target_price>v_reference_open)
              or
              (r.direction='SHORT'
                and v.stop_price>v_reference_open
                and v.target_price<v_reference_open)
            )
          ) as geometry_valid,
          case
            when v_reference_open is not null
             and v.stop_price is not null
             and abs(v_reference_open-v.stop_price)>0
             and (
               (r.direction='LONG'
                 and v.stop_price<v_reference_open
                 and v.target_price>v_reference_open)
               or
               (r.direction='SHORT'
                 and v.stop_price>v_reference_open
                 and v.target_price<v_reference_open)
             )
            then abs(v.target_price-v_reference_open)
                 /abs(v_reference_open-v.stop_price)
          end as reference_rr
        from variants v
      ),
      touches as (
        select
          g.*,
          min(w.ts) filter (
            where g.geometry_valid
              and (
                (r.direction='LONG' and w.low_price<=g.stop_price)
                or
                (r.direction='SHORT' and w.high_price>=g.stop_price)
              )
          ) as first_stop,
          min(w.ts) filter (
            where g.geometry_valid
              and (
                (r.direction='LONG' and w.high_price>=g.target_price)
                or
                (r.direction='SHORT' and w.low_price<=g.target_price)
              )
          ) as first_target
        from geometry g
        cross join w
        group by
          g.research_variant,g.stop_price,g.target_price,
          g.geometry_valid,g.reference_rr
      ),
      resolved as (
        select
          t.*,
          case
            when not t.geometry_valid then 'REFERENCE_GEOMETRY_INVALID'
            when t.first_stop is not null
              and t.first_target is not null
              and t.first_stop=t.first_target
              then 'BOTH_TOUCHED_IN_SAME_3M_CANDLE'
            when t.first_stop is not null
              and (t.first_target is null or t.first_stop<t.first_target)
              then 'STOP_FIRST'
            when t.first_target is not null
              and (t.first_stop is null or t.first_target<t.first_stop)
              then 'TARGET_FIRST'
            else 'NEITHER'
          end as path_class
        from touches t
      ),
      final_rows as (
        select
          x.*,
          case
            when x.path_class='BOTH_TOUCHED_IN_SAME_3M_CANDLE'
              then null::boolean
            when x.path_class='REFERENCE_GEOMETRY_INVALID'
              then null::boolean
            else (
              x.reference_rr>=5.0
              and x.path_class='TARGET_FIRST'
            )
          end as q5_target_first,
          case
            when x.path_class='BOTH_TOUCHED_IN_SAME_3M_CANDLE'
              then 'AMBIGUOUS_INTRABAR'
            when x.path_class='REFERENCE_GEOMETRY_INVALID'
              then 'REFERENCE_GEOMETRY_INVALID'
            else 'EVALUATED'
          end as evaluation_status
        from resolved x
      ),
      hashed as (
        select
          f.*,
          pg_catalog.encode(
            extensions.digest(
              jsonb_build_object(
                'spec_id',r.spec_id,
                'binding_id',r.binding_id,
                'research_variant',f.research_variant,
                'horizon_hours',r.horizon_hours,
                'reference_candle_at_utc',v_reference_start,
                'reference_open',v_reference_open,
                'reference_geometry_valid',f.geometry_valid,
                'reference_rr',f.reference_rr,
                'frozen_stop',f.stop_price,
                'frozen_target',f.target_price,
                'expected_candle_count',v_expected_count,
                'observed_candle_count',v_observed_count,
                'missing_candle_count',v_missing_count,
                'first_stop',f.first_stop,
                'first_target',f.first_target,
                'path_class',f.path_class,
                'q5_target_first',f.q5_target_first,
                'evaluation_status',f.evaluation_status,
                'source_evidence_hash',r.source_evidence_hash,
                'evaluator_version','geometry-holdout-sealed-evaluator-v0.1'
              )::text,
              'sha256'
            ),
            'hex'
          ) as result_hash
        from final_rows f
      ),
      ins as (
        insert into public.alpha_hunter_geometry_holdout_outcomes_sealed(
          outcome_id,spec_id,binding_id,diagnostic_id,symbol,direction,
          research_variant,horizon_hours,
          decision_available_at_utc,horizon_due_at_utc,
          reference_candle_at_utc,reference_open,
          reference_geometry_valid,reference_rr,
          frozen_stop,frozen_target,
          expected_candle_count,observed_candle_count,missing_candle_count,
          first_stop_candle_at_utc,first_target_candle_at_utc,
          path_class,q5_target_first,evaluation_status,
          measurement_source,evaluator_version,
          reference_price_is_fill_claim,exact_intrabar_order_claim_permitted,
          source_evidence_hash,result_hash,
          shadow_only,trade_permission,production_promotion_permitted,order_path
        )
        select
          pg_catalog.md5(
            'geometry-holdout-sealed-v0.1|'||r.binding_id||'|'
            ||h.research_variant||'|'||r.horizon_hours::text
          ),
          r.spec_id,r.binding_id,r.diagnostic_id,r.symbol,r.direction,
          h.research_variant,r.horizon_hours,
          r.decision_available_at_utc,v_horizon_due,
          v_reference_start,v_reference_open,
          h.geometry_valid,h.reference_rr,
          h.stop_price,h.target_price,
          v_expected_count,v_observed_count,v_missing_count,
          h.first_stop,h.first_target,
          h.path_class,h.q5_target_first,h.evaluation_status,
          'BITGET_PUBLIC_V3_3M_CANDLES',
          'geometry-holdout-sealed-evaluator-v0.1',
          false,false,r.source_evidence_hash,h.result_hash,
          true,false,false,'NONE'
        from hashed h
        on conflict(binding_id,research_variant,horizon_hours) do nothing
        returning 1
      )
      select count(*)::integer into v_inserted from ins;

      if v_inserted=4 then
        v_finalized_sets := v_finalized_sets+1;
      end if;
      v_sealed_rows := v_sealed_rows+v_inserted;

    exception when others then
      v_err := left(sqlerrm,1000);

      perform private.alpha_hunter_record_geometry_holdout_eval_failure_v01(
        r.spec_id,r.binding_id,r.horizon_hours,
        case
          when v_err like 'INCOMPLETE_3M_COVERAGE%' then 'INCOMPLETE_3M_COVERAGE'
          when v_err like 'BITGET_HTTP_STATUS:%' then 'BITGET_HTTP_ERROR'
          when v_err like 'BITGET_PAYLOAD_CODE:%' then 'BITGET_PAYLOAD_ERROR'
          else 'EVALUATOR_ERROR'
        end,
        v_err
      );

      select count(*)::integer into v_prior_failures
      from public.alpha_hunter_geometry_holdout_evaluator_failures f
      where f.binding_id=r.binding_id
        and f.horizon_hours=r.horizon_hours;

      if v_prior_failures>=3
         and clock_timestamp()>r.horizon_due_at_utc + interval '6 hours' then
        v_inserted :=
          private.alpha_hunter_insert_geometry_holdout_data_insufficient_v01(
            r.binding_id,r.horizon_hours,v_err
          );
        v_sealed_rows := v_sealed_rows+v_inserted;
        if v_inserted=4 then
          v_data_insufficient_sets := v_data_insufficient_sets+1;
        end if;
      else
        v_retry_failures := v_retry_failures+1;
      end if;
    end;
  end loop;

  return jsonb_build_object(
    'mode','GEOMETRY_HOLDOUT_SEALED_COLLECTION',
    'bindings_horizons_processed',v_processed,
    'sealed_complete_sets',v_finalized_sets,
    'sealed_rows_written',v_sealed_rows,
    'retry_failures',v_retry_failures,
    'data_insufficient_sets',v_data_insufficient_sets,
    'outcomes_exposed',false,
    'primary_analysis_performed',false,
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_run_geometry_holdout_sealed_v01()
  from public,anon,authenticated,service_role;


create or replace function private.alpha_hunter_geometry_holdout_sealed_operational_status_v01()
returns table(
  sealed_rows bigint,
  complete_binding_horizon_sets bigint,
  evaluator_failure_events bigint,
  latest_evaluated_at_utc timestamptz,
  primary_results_exposed boolean,
  shadow_only boolean,
  trade_permission boolean
)
language sql
stable
security definer
set search_path=''
as $$
  select
    (select count(*) from public.alpha_hunter_geometry_holdout_outcomes_sealed),
    (
      select count(*)
      from (
        select binding_id,horizon_hours
        from public.alpha_hunter_geometry_holdout_outcomes_sealed
        group by binding_id,horizon_hours
        having count(*)=4
      ) x
    ),
    (select count(*) from public.alpha_hunter_geometry_holdout_evaluator_failures),
    (select max(evaluated_at_utc) from public.alpha_hunter_geometry_holdout_outcomes_sealed),
    false,
    true,
    false;
$$;

revoke all on function private.alpha_hunter_geometry_holdout_sealed_operational_status_v01()
  from public,anon,authenticated;
grant execute on function private.alpha_hunter_geometry_holdout_sealed_operational_status_v01()
  to service_role;


create or replace view public.alpha_hunter_geometry_holdout_collection_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  h.spec_id,
  h.hypothesis_id,
  h.scientific_status,
  h.registered_at_utc,
  h.collection_ends_at_utc,
  h.captured,
  h.eligible,
  h.excluded,
  h.capture_failures,
  h.capture_sample_gate_met,
  s.sealed_rows,
  s.complete_binding_horizon_sets,
  s.evaluator_failure_events,
  s.latest_evaluated_at_utc,
  s.primary_results_exposed,
  'SEALED_OUTCOME_COLLECTION - NO PEEKING'::text as evaluator_state,
  'WAIT_FOR FROZEN COHORT GATE; DO NOT QUERY SEALED OUTCOMES'::text as next_gate,
  'NONE'::text as scientific_conclusion,
  h.shadow_only,
  h.trade_permission,
  h.production_promotion_permitted,
  h.order_path
from public.alpha_hunter_geometry_holdout_status_v01 h
cross join lateral
  private.alpha_hunter_geometry_holdout_sealed_operational_status_v01() s;

revoke all on public.alpha_hunter_geometry_holdout_collection_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_geometry_holdout_collection_status_v01
  to service_role;


do $$
begin
  if not exists(
    select 1
    from cron.job
    where jobname='alpha-hunter-geometry-holdout-sealed-hourly'
  ) then
    perform cron.schedule(
      'alpha-hunter-geometry-holdout-sealed-hourly',
      '38 * * * *',
      'select private.alpha_hunter_run_geometry_holdout_sealed_v01();'
    );
  end if;
end;
$$;
