-- P0 sealed R8/R9/R10 activation guard dependency matrix.
-- ISOLATED PostgreSQL 16/17 only, no live Supabase data or external rights.
-- These THREE tables are deliberately minimal row-type dependencies, NOT
-- exact replicas of the production execution activation schema.
-- Exact production guard PL/pgSQL bodies and checks retained unmodified.
CREATE TABLE public.alpha_hunter_paper_execution_integrity_activation_v08(
 activation_id text PRIMARY KEY,
 activated_at_utc timestamptz NOT NULL,
 scientific_fingerprint_sha256 text NOT NULL
);
CREATE TABLE public.alpha_hunter_paper_execution_activation_v09(
 activation_id text PRIMARY KEY,
 activated_at_utc timestamptz NOT NULL,
 scientific_fingerprint_sha256 text NOT NULL
);
CREATE TABLE public.alpha_hunter_paper_execution_activation_v10(
 activation_id text PRIMARY KEY,
 spec_id text NOT NULL,
 activated_at_utc timestamptz NOT NULL,
 scientific_fingerprint_sha256 text NOT NULL
);

-- EXACT SQL from read-only production catalog captured 2026-11-02.
CREATE OR REPLACE FUNCTION private.alpha_hunter_guard_r8_profitability_activation_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_exec public.alpha_hunter_paper_execution_integrity_activation_v08%rowtype;
begin
  if new.spec_id<>'SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003' then
    return new;
  end if;

  select e.* into v_exec
  from public.alpha_hunter_paper_execution_integrity_activation_v08 e
  where e.activation_id='PAPER_EXECUTION_R8'
  order by e.activated_at_utc desc
  limit 1;

  -- Generic activation remains fail-closed and quiet until the dedicated
  -- atomic R8 activation has created the matching execution row.
  if v_exec.activation_id is null then
    return null;
  end if;

  if v_exec.activated_at_utc<>new.started_at_utc then
    raise exception
      'R8 profitability activation timestamp must match paper execution activation';
  end if;

  if coalesce(v_exec.scientific_fingerprint_sha256,'')
     <>coalesce(new.baseline_scientific_fingerprint_sha256,'')
  then
    raise exception
      'R8 profitability activation fingerprint must match paper execution activation';
  end if;

  return new;
end;
$function$
;

-- EXACT SQL from read-only production catalog captured 2026-11-02.
CREATE OR REPLACE FUNCTION private.alpha_hunter_guard_r9_activation_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
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
end; $function$
;

-- EXACT SQL from read-only production catalog captured 2026-11-02.
CREATE OR REPLACE FUNCTION private.alpha_hunter_guard_r10_profitability_activation_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  role_name text;
  exec_row public.alpha_hunter_paper_execution_activation_v10%rowtype;
begin
  select s.scientific_role into role_name
  from public.alpha_hunter_profitability_test_specs_v01 s
  where s.spec_id=new.spec_id;

  if role_name is distinct from 'SUCCESSOR_EXECUTED_PAPER_24H_R10' then
    return new;
  end if;

  select e.* into exec_row
  from public.alpha_hunter_paper_execution_activation_v10 e
  where e.spec_id=new.spec_id
  limit 1;

  if exec_row.activation_id is null then
    return null;
  end if;

  if new.started_at_utc is distinct from exec_row.activated_at_utc then
    raise exception 'R10 profitability activation timestamp must match paper execution activation';
  end if;

  if coalesce(new.baseline_scientific_fingerprint_sha256,'')
     <>exec_row.scientific_fingerprint_sha256 then
    raise exception 'R10 profitability activation fingerprint must match paper execution activation';
  end if;

  return new;
end;
$function$
;

CREATE TRIGGER p0_guard_r8 BEFORE INSERT
 ON public.alpha_hunter_profitability_test_activations_v01 FOR EACH ROW
 EXECUTE FUNCTION private.alpha_hunter_guard_r8_profitability_activation_v01();
CREATE TRIGGER p0_guard_r9 BEFORE INSERT
 ON public.alpha_hunter_profitability_test_activations_v01 FOR EACH ROW
 EXECUTE FUNCTION private.alpha_hunter_guard_r9_activation_v01();
CREATE TRIGGER p0_guard_r10 BEFORE INSERT
 ON public.alpha_hunter_profitability_test_activations_v01 FOR EACH ROW
 EXECUTE FUNCTION private.alpha_hunter_guard_r10_profitability_activation_v01();
-- No actual cohort activation rows or external execution records are copied.
