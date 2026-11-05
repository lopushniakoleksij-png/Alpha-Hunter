-- P0 successor research ONLY: disposable PostgreSQL/PostgREST contract.
-- Not a production migration. DO NOT install in live Supabase.
-- No SECURITY DEFINER, no trading authority, no PUBLIC execute permission.
-- The composite-row insertion here is limited to isolated test fixtures;
-- production schema defaults, privileges, mixed load and operational approval
-- are deliberately NOT represented by this artifact.
CREATE OR REPLACE FUNCTION public.ah_p0_research_atomic_canonical_v02(
    p_parent jsonb, p_children jsonb, p_signals jsonb,
    p_features jsonb, p_readiness jsonb
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_run text;
    v_expected int;
    v_children text[];
    v_signals text[];
    v_features text[];
    v_readiness text[];
    v_signal_ids text[];
    v_feature_ids text[];
    v_count int;
BEGIN
    IF jsonb_typeof(p_parent) IS DISTINCT FROM 'object'
        OR jsonb_typeof(p_children) IS DISTINCT FROM 'array'
        OR jsonb_typeof(p_signals) IS DISTINCT FROM 'array'
        OR jsonb_typeof(p_features) IS DISTINCT FROM 'array'
        OR jsonb_typeof(p_readiness) IS DISTINCT FROM 'array'
    THEN RAISE EXCEPTION 'invalid canonical publication JSON shape'; END IF;

    v_run := p_parent->>'run_id';
    IF v_run IS NULL OR length(btrim(v_run)) < 8
        OR v_run <> btrim(v_run) THEN
        RAISE EXCEPTION 'invalid run_id';
    END IF;
    IF (p_parent->>'symbol_count') !~ '^[0-9]{1,4}$' THEN
        RAISE EXCEPTION 'invalid symbol_count';
    END IF;
    v_expected := (p_parent->>'symbol_count')::int;
    IF v_expected < 1 OR v_expected > 1000 THEN
        RAISE EXCEPTION 'symbol_count outside bounded research contract';
    END IF;
    IF jsonb_array_length(p_children) <> v_expected
       OR jsonb_array_length(p_signals) <> v_expected
       OR jsonb_array_length(p_features) <> v_expected
       OR jsonb_array_length(p_readiness) <> v_expected THEN
        RAISE EXCEPTION 'all five evidence groups must be complete';
    END IF;
    IF exists (
        SELECT 1 FROM (
            SELECT value AS j FROM jsonb_array_elements(p_children)
            UNION ALL SELECT value FROM jsonb_array_elements(p_signals)
            UNION ALL SELECT value FROM jsonb_array_elements(p_features)
            UNION ALL SELECT value FROM jsonb_array_elements(p_readiness)
        ) src
        WHERE jsonb_typeof(j) <> 'object'
            OR j->>'run_id' IS DISTINCT FROM v_run
            OR j->>'symbol' IS NULL
            OR j->>'symbol' = ''
            OR j->>'trade_permission' IS DISTINCT FROM 'false'
    ) THEN
        RAISE EXCEPTION 'invalid run/symbol identity or forbidden trade permission';
    END IF;
    IF exists (
        SELECT 1 FROM jsonb_array_elements(p_children) AS child
        WHERE jsonb_typeof(child->'payload') <> 'object'
          OR child->'payload'->>'symbol' IS DISTINCT FROM child->>'symbol'
    ) THEN
        RAISE EXCEPTION 'canonical child payload identity mismatch';
    END IF;

    SELECT array_agg(value->>'symbol' ORDER BY value->>'symbol')
      INTO v_children FROM jsonb_array_elements(p_children);
    SELECT array_agg(value->>'symbol' ORDER BY value->>'symbol'),
           array_agg(value->>'signal_id' ORDER BY value->>'signal_id')
      INTO v_signals,v_signal_ids FROM jsonb_array_elements(p_signals);
    SELECT array_agg(value->>'symbol' ORDER BY value->>'symbol'),
           array_agg(value->>'signal_id' ORDER BY value->>'signal_id')
      INTO v_features,v_feature_ids FROM jsonb_array_elements(p_features);
    SELECT array_agg(value->>'symbol' ORDER BY value->>'symbol')
      INTO v_readiness FROM jsonb_array_elements(p_readiness);
    IF v_children IS DISTINCT FROM v_signals
       OR v_children IS DISTINCT FROM v_features
       OR v_children IS DISTINCT FROM v_readiness
       OR v_signal_ids IS DISTINCT FROM v_feature_ids
       OR (SELECT count(DISTINCT s) FROM unnest(v_children) s) <> v_expected
       OR (SELECT count(DISTINCT s) FROM unnest(v_signal_ids) s) <> v_expected
    THEN
        RAISE EXCEPTION 'canonical symbol or signal identity mismatch';
    END IF;
    IF exists (SELECT 1 FROM public.alpha_hunter_snapshots WHERE run_id=v_run)
    THEN
        RAISE EXCEPTION 'ambiguous existing canonical run requires independent readback';
    END IF;

    -- All statements below are one PostgREST function-call transaction.
    -- A trigger failure or HTTP server-side SQL exception rolls them ALL back.
    INSERT INTO public.alpha_hunter_snapshots
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_snapshots, jsonb_build_array(p_parent)) AS x;
    INSERT INTO public.alpha_hunter_symbol_snapshots
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_symbol_snapshots, p_children) AS x;
    INSERT INTO public.alpha_hunter_signals
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_signals, p_signals) AS x;
    INSERT INTO public.alpha_hunter_signal_features
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_signal_features, p_features) AS x;
    INSERT INTO public.alpha_hunter_readiness_observations_v01
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_readiness_observations_v01, p_readiness) AS x;

    SELECT count(*) INTO v_count FROM public.alpha_hunter_symbol_snapshots
      WHERE run_id=v_run;
    IF v_count <> v_expected
      OR (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id=v_run) <> v_expected
      OR (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id=v_run) <> v_expected
      OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id=v_run) <> v_expected
    THEN
        RAISE EXCEPTION 'canonical atomic post-insert count verification failed';
    END IF;
    UPDATE public.alpha_hunter_snapshots
       SET payload=jsonb_set(payload,'{_canonical_publication_state}','"VERIFIED"'::jsonb,true)
     WHERE run_id=v_run;

    RETURN jsonb_build_object('status','VERIFIED','run_id',v_run,
                              'child_count',v_count,'feature_count',v_expected);
END;
$$;
REVOKE ALL ON FUNCTION public.ah_p0_research_atomic_canonical_v02(
    jsonb,jsonb,jsonb,jsonb,jsonb) FROM PUBLIC;
-- No GRANT in this research artifact. The disposable test runner may grant
-- temporary execute to its local-only non-login role after schema creation.
