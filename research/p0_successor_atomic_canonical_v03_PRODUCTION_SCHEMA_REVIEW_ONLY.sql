-- P0 successor research ONLY: disposable PostgreSQL/PostgREST contract.
-- Not a production migration. DO NOT install in live Supabase.
-- No SECURITY DEFINER, no trading authority, no PUBLIC execute permission.
-- Production-schema compatibility review (2026-11-05): defaulted NOT NULL
-- columns in the live five tables need explicit values before composite
-- recordset insertion; omitted JSON keys otherwise become explicit SQL NULL.
-- The real SECURITY DEFINER trigger functions and production permissions
-- remain untouched and have NOT been execution-benchmarked by this patch.
-- This remains a DISPOSABLE-ONLY proposal; no installed RPC or grant.
CREATE OR REPLACE FUNCTION public.ah_p0_research_atomic_canonical_v03(
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
    v_expected_signals text[];
    v_expected_readiness text[];
    v_manifest_symbols text[];
    v_source_errors int;
    v_count int;
    v_parent jsonb;
    v_children_normalized jsonb;
    v_signals_normalized jsonb;
    v_features_normalized jsonb;
    v_readiness_normalized jsonb;
BEGIN
    IF jsonb_typeof(p_parent) IS DISTINCT FROM 'object'
        OR jsonb_typeof(p_children) IS DISTINCT FROM 'array'
        OR jsonb_typeof(p_signals) IS DISTINCT FROM 'array'
        OR jsonb_typeof(p_features) IS DISTINCT FROM 'array'
        OR jsonb_typeof(p_readiness) IS DISTINCT FROM 'array'
    THEN RAISE EXCEPTION 'invalid canonical publication JSON shape'; END IF;

    IF jsonb_typeof(p_parent->'payload') IS DISTINCT FROM 'object'
       OR p_parent->'payload'->>'run_id' IS DISTINCT FROM p_parent->>'run_id'
       OR p_parent->'payload' ? '_canonical_publication_state' THEN
        RAISE EXCEPTION 'invalid or previously marked canonical parent payload';
    END IF;

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
    IF jsonb_array_length(p_children) <> v_expected THEN
        RAISE EXCEPTION 'parent and child cardinality mismatch';
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
            OR jsonb_typeof(j->'symbol') IS DISTINCT FROM 'string'
            OR btrim(j->>'symbol') = ''
            OR j->'trade_permission' IS DISTINCT FROM 'false'::jsonb
    ) THEN
        RAISE EXCEPTION 'invalid run/symbol identity or forbidden trade permission';
    END IF;
    IF exists (
        SELECT 1 FROM jsonb_array_elements(p_children) AS child
        WHERE jsonb_typeof(child->'payload') IS DISTINCT FROM 'object'
          OR child->'payload'->>'symbol' IS DISTINCT FROM child->>'symbol'
          OR child->'payload'->'trade_permission' = 'true'::jsonb
    ) THEN
        RAISE EXCEPTION 'canonical child payload identity or permission mismatch';
    END IF;
    IF p_parent->'payload'->'trade_permission' = 'true'::jsonb
       OR EXISTS (
          SELECT 1 FROM jsonb_array_elements(
            CASE WHEN jsonb_typeof(p_parent->'payload'->'symbols') = 'array'
                 THEN p_parent->'payload'->'symbols' ELSE '[]'::jsonb END
          ) AS e
          WHERE e->'trade_permission' = 'true'::jsonb
       )
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_signals) AS e
                  WHERE e->'payload'->'trade_permission' = 'true'::jsonb)
       OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_features) AS e
                  WHERE e->'source_payload'->'trade_permission' = 'true'::jsonb)
    THEN
        RAISE EXCEPTION 'forbidden nested trade permission';
    END IF;

    -- Match the ACTUAL writer's source-evidence cardinality:
    -- all children persist, readiness excludes payloads carrying an 'error'
    -- key, signals/features also exclude a NULL/missing last_price.
    -- The column "error" may be NULL even when the source has that key.
    SELECT COALESCE(array_agg(j->>'symbol' ORDER BY j->>'symbol'),
                    ARRAY[]::text[]),
           COALESCE(array_agg(j->>'symbol' ORDER BY j->>'symbol')
               FILTER (WHERE NOT (j->'payload' ? 'error')),
                    ARRAY[]::text[]),
           COALESCE(array_agg(j->>'symbol' ORDER BY j->>'symbol')
               FILTER (WHERE NOT (j->'payload' ? 'error')
                         AND (j->'payload'->>'last_price') IS NOT NULL),
                    ARRAY[]::text[]),
           count(*) FILTER (WHERE j->'payload' ? 'error')
      INTO v_children,v_expected_readiness,v_expected_signals,v_source_errors
      FROM jsonb_array_elements(p_children) AS e(j);

    IF (p_parent->>'error_count') !~ '^[0-9]{1,4}
    IF exists (SELECT 1 FROM public.alpha_hunter_snapshots WHERE run_id=v_run)
    THEN
        RAISE EXCEPTION 'ambiguous existing canonical run requires independent readback';
    END IF;

    -- Production defaulted NOT NULL fields, verified read-only on 2026-11-05:
    -- parent: error_count/created_at; symbols: state_changed,
    -- trade_permission/created_at; signals: trade_permission/created_at;
    -- features: trade_permission/features/source_payload/created_at;
    -- readiness: trade_permission/v7_trade_ready/created_at.
    -- Defaults are only added for ABSENT keys. Explicit JSON nulls still
    -- fail NOT NULL constraints, and all unknown/unlisted fields are preserved.
    -- Inserting the VERIFIED marker in the SAME atomic parent INSERT avoids
    -- a second UPDATE OF payload and its extra production trigger firing.
    v_parent := jsonb_build_object('error_count', 0, 'created_at', now()) || p_parent;
    v_parent := jsonb_set(
      v_parent, '{payload}',
      jsonb_set(v_parent->'payload', '{_canonical_publication_state}', '"VERIFIED"'::jsonb, true),
      false
    );

    SELECT jsonb_agg(
      jsonb_build_object('state_changed', false,
                         'trade_permission', false, 'created_at', now()) || e.value
      ORDER BY e.ordinality)
      INTO v_children_normalized
    FROM jsonb_array_elements(p_children) WITH ORDINALITY AS e(value, ordinality);

    SELECT jsonb_agg(
      jsonb_build_object('trade_permission', false, 'created_at', now()) || e.value
      ORDER BY e.ordinality)
      INTO v_signals_normalized
    FROM jsonb_array_elements(p_signals) WITH ORDINALITY AS e(value, ordinality);
    v_signals_normalized := COALESCE(v_signals_normalized, '[]'::jsonb);

    SELECT jsonb_agg(
      jsonb_build_object('trade_permission', false, 'created_at', now(),
                         'features', '{}'::jsonb, 'source_payload', '{}'::jsonb)
         || e.value ORDER BY e.ordinality)
      INTO v_features_normalized
    FROM jsonb_array_elements(p_features) WITH ORDINALITY AS e(value, ordinality);
    v_features_normalized := COALESCE(v_features_normalized, '[]'::jsonb);

    SELECT jsonb_agg(
      jsonb_build_object('trade_permission', false,
                         'v7_trade_ready', false, 'created_at', now()) || e.value
      ORDER BY e.ordinality)
      INTO v_readiness_normalized
    FROM jsonb_array_elements(p_readiness) WITH ORDINALITY AS e(value, ordinality);
    v_readiness_normalized := COALESCE(v_readiness_normalized, '[]'::jsonb);

    -- All five statements share one PostgREST function-call transaction.
    -- A trigger failure rolls the whole publication back.
    INSERT INTO public.alpha_hunter_snapshots
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_snapshots, jsonb_build_array(v_parent)) AS x;
    INSERT INTO public.alpha_hunter_symbol_snapshots
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_symbol_snapshots, v_children_normalized) AS x;
    INSERT INTO public.alpha_hunter_signals
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_signals, v_signals_normalized) AS x;
    INSERT INTO public.alpha_hunter_signal_features
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_signal_features, v_features_normalized) AS x;
    INSERT INTO public.alpha_hunter_readiness_observations_v01
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_readiness_observations_v01, v_readiness_normalized) AS x;

    SELECT count(*) INTO v_count FROM public.alpha_hunter_symbol_snapshots
      WHERE run_id=v_run;
    IF v_count <> v_expected
      OR (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id=v_run)
            <> cardinality(v_expected_signals)
      OR (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id=v_run)
            <> cardinality(v_expected_signals)
      OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id=v_run)
            <> cardinality(v_expected_readiness)
    THEN
        RAISE EXCEPTION 'canonical atomic post-insert count verification failed';
    END IF;
    RETURN jsonb_build_object('status','VERIFIED','run_id',v_run,
                              'child_count',v_count,
                              'feature_count',cardinality(v_expected_signals),
                              'readiness_count',cardinality(v_expected_readiness),
                              'source_error_count',v_source_errors,
                              'source_quality',CASE WHEN v_source_errors=0
                               THEN 'NO_RECORDED_SOURCE_ERRORS'
                               ELSE 'SOURCE_ERRORS_RECORDED' END);
END;
$$;
REVOKE ALL ON FUNCTION public.ah_p0_research_atomic_canonical_v03(
    jsonb,jsonb,jsonb,jsonb,jsonb) FROM PUBLIC;
-- Do NOT grant any production role or install in Supabase.
-- The disposable test harness may grant EXECUTE only to ah_p0_local_writer.
-- Live trigger side effects (including paper-order creation) remain unapproved.
 THEN
        RAISE EXCEPTION 'parent missing or invalid source error_count';
    END IF;
    IF (p_parent->>'error_count')::int <> v_source_errors
       OR jsonb_array_length(p_signals) <> cardinality(v_expected_signals)
       OR jsonb_array_length(p_features) <> cardinality(v_expected_signals)
       OR jsonb_array_length(p_readiness) <> cardinality(v_expected_readiness)
    THEN
        RAISE EXCEPTION 'canonical evidence group cardinality mismatch';
    END IF;

    SELECT COALESCE(array_agg(value->>'symbol' ORDER BY value->>'symbol'),
                    ARRAY[]::text[]),
           COALESCE(array_agg(value->>'signal_id' ORDER BY value->>'signal_id'),
                    ARRAY[]::text[])
      INTO v_signals,v_signal_ids FROM jsonb_array_elements(p_signals);
    SELECT COALESCE(array_agg(value->>'symbol' ORDER BY value->>'symbol'),
                    ARRAY[]::text[]),
           COALESCE(array_agg(value->>'signal_id' ORDER BY value->>'signal_id'),
                    ARRAY[]::text[])
      INTO v_features,v_feature_ids FROM jsonb_array_elements(p_features);
    SELECT COALESCE(array_agg(value->>'symbol' ORDER BY value->>'symbol'),
                    ARRAY[]::text[])
      INTO v_readiness FROM jsonb_array_elements(p_readiness);

    IF v_expected_signals IS DISTINCT FROM v_signals
       OR v_expected_signals IS DISTINCT FROM v_features
       OR v_expected_readiness IS DISTINCT FROM v_readiness
       OR v_signal_ids IS DISTINCT FROM v_feature_ids
       OR (SELECT count(DISTINCT s) FROM unnest(v_children) s) <> v_expected
       OR (SELECT count(DISTINCT s) FROM unnest(v_signal_ids) s)
            <> cardinality(v_expected_signals)
       OR EXISTS (
           SELECT 1 FROM (
             SELECT value->>'symbol',value->>'signal_id'
               FROM jsonb_array_elements(p_signals)
             EXCEPT
             SELECT value->>'symbol',value->>'signal_id'
               FROM jsonb_array_elements(p_features)
           ) AS mismatched
       ) OR EXISTS (
           SELECT 1 FROM (
             SELECT value->>'symbol',value->>'signal_id'
               FROM jsonb_array_elements(p_features)
             EXCEPT
             SELECT value->>'symbol',value->>'signal_id'
               FROM jsonb_array_elements(p_signals)
           ) AS mismatched
       )
    THEN
        RAISE EXCEPTION 'canonical symbol or signal identity mismatch';
    END IF;

    IF jsonb_typeof(p_parent->'payload'->'symbols') IS DISTINCT FROM 'array'
       OR jsonb_array_length(p_parent->'payload'->'symbols') <> v_expected
    THEN
        RAISE EXCEPTION 'canonical parent manifest invalid';
    END IF;
    SELECT COALESCE(array_agg(j->>'symbol' ORDER BY j->>'symbol'),
                    ARRAY[]::text[])
      INTO v_manifest_symbols
      FROM jsonb_array_elements(p_parent->'payload'->'symbols') AS e(j);
    IF v_manifest_symbols IS DISTINCT FROM v_children THEN
        RAISE EXCEPTION 'canonical parent/child symbol inventory mismatch';
    END IF;
    IF exists (SELECT 1 FROM public.alpha_hunter_snapshots WHERE run_id=v_run)
    THEN
        RAISE EXCEPTION 'ambiguous existing canonical run requires independent readback';
    END IF;

    -- Production defaulted NOT NULL fields, verified read-only on 2026-11-05:
    -- parent: error_count/created_at; symbols: state_changed,
    -- trade_permission/created_at; signals: trade_permission/created_at;
    -- features: trade_permission/features/source_payload/created_at;
    -- readiness: trade_permission/v7_trade_ready/created_at.
    -- Defaults are only added for ABSENT keys. Explicit JSON nulls still
    -- fail NOT NULL constraints, and all unknown/unlisted fields are preserved.
    -- Inserting the VERIFIED marker in the SAME atomic parent INSERT avoids
    -- a second UPDATE OF payload and its extra production trigger firing.
    v_parent := jsonb_build_object('error_count', 0, 'created_at', now()) || p_parent;
    v_parent := jsonb_set(
      v_parent, '{payload}',
      jsonb_set(v_parent->'payload', '{_canonical_publication_state}', '"VERIFIED"'::jsonb, true),
      false
    );

    SELECT jsonb_agg(
      jsonb_build_object('state_changed', false,
                         'trade_permission', false, 'created_at', now()) || e.value
      ORDER BY e.ordinality)
      INTO v_children_normalized
    FROM jsonb_array_elements(p_children) WITH ORDINALITY AS e(value, ordinality);

    SELECT jsonb_agg(
      jsonb_build_object('trade_permission', false, 'created_at', now()) || e.value
      ORDER BY e.ordinality)
      INTO v_signals_normalized
    FROM jsonb_array_elements(p_signals) WITH ORDINALITY AS e(value, ordinality);

    SELECT jsonb_agg(
      jsonb_build_object('trade_permission', false, 'created_at', now(),
                         'features', '{}'::jsonb, 'source_payload', '{}'::jsonb)
         || e.value ORDER BY e.ordinality)
      INTO v_features_normalized
    FROM jsonb_array_elements(p_features) WITH ORDINALITY AS e(value, ordinality);

    SELECT jsonb_agg(
      jsonb_build_object('trade_permission', false,
                         'v7_trade_ready', false, 'created_at', now()) || e.value
      ORDER BY e.ordinality)
      INTO v_readiness_normalized
    FROM jsonb_array_elements(p_readiness) WITH ORDINALITY AS e(value, ordinality);

    -- All five statements share one PostgREST function-call transaction.
    -- A trigger failure rolls the whole publication back.
    INSERT INTO public.alpha_hunter_snapshots
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_snapshots, jsonb_build_array(v_parent)) AS x;
    INSERT INTO public.alpha_hunter_symbol_snapshots
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_symbol_snapshots, v_children_normalized) AS x;
    INSERT INTO public.alpha_hunter_signals
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_signals, v_signals_normalized) AS x;
    INSERT INTO public.alpha_hunter_signal_features
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_signal_features, v_features_normalized) AS x;
    INSERT INTO public.alpha_hunter_readiness_observations_v01
      SELECT (x).* FROM jsonb_populate_recordset(
        NULL::public.alpha_hunter_readiness_observations_v01, v_readiness_normalized) AS x;

    SELECT count(*) INTO v_count FROM public.alpha_hunter_symbol_snapshots
      WHERE run_id=v_run;
    IF v_count <> v_expected
      OR (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id=v_run) <> v_expected
      OR (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id=v_run) <> v_expected
      OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id=v_run) <> v_expected
    THEN
        RAISE EXCEPTION 'canonical atomic post-insert count verification failed';
    END IF;
    RETURN jsonb_build_object('status','VERIFIED','run_id',v_run,
                              'child_count',v_count,'feature_count',v_expected);
END;
$$;
REVOKE ALL ON FUNCTION public.ah_p0_research_atomic_canonical_v03(
    jsonb,jsonb,jsonb,jsonb,jsonb) FROM PUBLIC;
-- Do NOT grant any production role or install in Supabase.
-- The disposable test harness may grant EXECUTE only to ah_p0_local_writer.
-- Live trigger side effects (including paper-order creation) remain unapproved.
