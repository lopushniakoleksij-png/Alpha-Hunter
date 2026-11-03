-- RESEARCH ONLY — DO NOT APPLY TO PRODUCTION OR ANY LIVE DATABASE.
-- Successor-only transaction proposal. No scanner wiring, grants, or migrations.
-- A single PostgreSQL function invocation is one transaction: any raised error
-- rolls back both parent and all children. Requires DBA/security review before
-- use in a separately authorised disposable PG16/17 environment.
-- NO production authority or paper admission is conferred by this artifact.
--
-- The caller must supply a previously constructed compact parent and all child
-- rows. No historical backfill, overwrite or retry of ambiguous writes.
create or replace function public.ah_research_atomic_snapshot_v01(
    p_parent jsonb, p_children jsonb
) returns integer
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
    v_run_id text;
    v_expected integer;
    v_actual integer;
begin
    if jsonb_typeof(p_parent) is distinct from 'object'
       or jsonb_typeof(p_children) is distinct from 'array' then
        raise exception 'invalid parent or children JSON type';
    end if;
    v_run_id := p_parent->>'run_id';
    if v_run_id is null or v_run_id = '' or v_run_id <> btrim(v_run_id) then
        raise exception 'missing or invalid canonical run ID';
    end if;
    if (p_parent->>'symbol_count') !~ '^[0-9]{1,4}$' then
        raise exception 'invalid declared symbol count';
    end if;
    v_expected := (p_parent->>'symbol_count')::integer;
    v_actual := jsonb_array_length(p_children);
    if v_expected < 1 or v_expected > 1000 or v_actual <> v_expected then
        raise exception 'canonical child count mismatch';
    end if;
    if exists (
        select 1 from jsonb_array_elements(p_children) as child(value)
        where jsonb_typeof(value) is distinct from 'object'
           or value->>'run_id' is distinct from v_run_id
           or value->>'symbol' is null
           or value->>'symbol' = ''
           or value->>'symbol' <> btrim(value->>'symbol')
           or jsonb_typeof(value->'payload') is distinct from 'object'
           or value->'payload'->>'symbol' is distinct from value->>'symbol'
    ) then
        raise exception 'invalid canonical child identity';
    end if;
    if (
        select count(distinct value->>'symbol')
        from jsonb_array_elements(p_children) as child(value)
    ) <> v_expected then
        raise exception 'duplicate canonical child symbol';
    end if;
    if p_parent->'payload'->>'run_id' is distinct from v_run_id then
        raise exception 'parent compact payload run ID mismatch';
    end if;
    -- Immutable successor publication: never overwrite existing run evidence.
    insert into public.alpha_hunter_snapshots
        (run_id, collected_at_utc, version, product_type,
         symbol_count, error_count, payload)
    select v_run_id,
           (p_parent->>'collected_at_utc')::timestamptz,
           p_parent->>'version', p_parent->>'product_type',
           v_expected, (p_parent->>'error_count')::integer,
           p_parent->'payload';

    insert into public.alpha_hunter_symbol_snapshots
        (run_id, symbol, collected_at_utc, state, previous_state,
         state_changed, trade_permission, direction, reward_risk,
         last_price, open_interest, funding_rate, data_integrity_score,
         error, payload)
    select v_run_id, c.symbol, c.collected_at_utc, c.state,
           c.previous_state, c.state_changed, c.trade_permission,
           c.direction, c.reward_risk, c.last_price, c.open_interest,
           c.funding_rate, c.data_integrity_score, c.error, c.payload
    from jsonb_to_recordset(p_children) as c(
        run_id text, symbol text, collected_at_utc timestamptz,
        state text, previous_state text, state_changed boolean,
        trade_permission boolean, direction text, reward_risk double precision,
        last_price double precision, open_interest double precision,
        funding_rate double precision, data_integrity_score integer,
        error text, payload jsonb
    );

    get diagnostics v_actual = row_count;
    if v_actual <> v_expected then
        raise exception 'canonical child insert count mismatch';
    end if;
    return v_actual;
end;
$$;
-- No GRANT, no API integration, no deployment. Security review required.
