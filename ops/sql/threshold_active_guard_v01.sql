-- Alpha Hunter global Money Entry threshold ACTIVE guard v0.1
--
-- Problem:
--   public.alpha_hunter_money_entry_threshold_sets is append-only and global.
--   The production stage reads the newest ACTIVE validated row without a
--   direction key. A LONG-only threshold holdout must therefore never become
--   a global ACTIVE threshold row and silently apply to SHORT.
--
-- ACTIVE contract:
--   * all T0/T1/T2 numeric thresholds are present and positive;
--   * validated_at_utc and activated_at_utc are present;
--   * the row explicitly declares GLOBAL_BOTH_DIRECTIONS;
--   * LONG and SHORT independently passed the SAME frozen threshold contract;
--   * both direction proofs carry the same threshold_contract_hash;
--   * a real ACTIVE validated execution-cost model is referenced;
--   * threshold rows remain shadow_only=true / trade_permission=false.
--
-- This trigger does not validate thresholds, activate thresholds, change any
-- current row, or grant trade permission. It only rejects unsafe future ACTIVE
-- inserts into the existing direction-agnostic table.

create or replace function private.alpha_hunter_guard_money_entry_threshold_active_v01()
returns trigger
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_scope text;
  v_contract_hash text;
  v_long_hash text;
  v_short_hash text;
  v_cost_model_id text;
  v_long_pass boolean;
  v_short_pass boolean;
  v_cost_ok boolean:=false;
begin
  if new.status<>'ACTIVE' then
    return new;
  end if;

  if new.shadow_only is not true or new.trade_permission is not false then
    raise exception 'ACTIVE threshold set rejected: safety boundary must remain shadow_only=true and trade_permission=false';
  end if;

  if new.validated_at_utc is null or new.activated_at_utc is null then
    raise exception 'ACTIVE threshold set rejected: validated_at_utc and activated_at_utc are required';
  end if;

  if new.max_t0_stop_distance_pct is null
     or new.min_t0_remaining_r is null
     or new.min_t1_remaining_r is null
     or new.min_t2_remaining_r is null
  then
    raise exception 'ACTIVE threshold set rejected: complete T0/T1/T2 numeric thresholds are required';
  end if;

  if new.max_t0_stop_distance_pct<=0
     or new.min_t0_remaining_r<=0
     or new.min_t1_remaining_r<=0
     or new.min_t2_remaining_r<=0
  then
    raise exception 'ACTIVE threshold set rejected: all numeric thresholds must be positive';
  end if;

  v_scope:=new.evidence_reference->>'production_scope';
  v_contract_hash:=nullif(new.evidence_reference->>'threshold_contract_hash','');
  v_long_hash:=nullif(new.evidence_reference#>>'{long_validation,threshold_contract_hash}','');
  v_short_hash:=nullif(new.evidence_reference#>>'{short_validation,threshold_contract_hash}','');

  begin
    v_long_pass:=(new.evidence_reference#>>'{long_validation,passed}')::boolean;
  exception when others then
    v_long_pass:=false;
  end;

  begin
    v_short_pass:=(new.evidence_reference#>>'{short_validation,passed}')::boolean;
  exception when others then
    v_short_pass:=false;
  end;

  if v_scope is distinct from 'GLOBAL_BOTH_DIRECTIONS' then
    raise exception 'ACTIVE threshold set rejected: direction-agnostic production table requires GLOBAL_BOTH_DIRECTIONS evidence';
  end if;

  if v_long_pass is not true or v_short_pass is not true then
    raise exception 'ACTIVE threshold set rejected: independent LONG and SHORT validation must both pass';
  end if;

  if v_contract_hash is null
     or v_long_hash is null
     or v_short_hash is null
     or v_contract_hash<>v_long_hash
     or v_contract_hash<>v_short_hash
  then
    raise exception 'ACTIVE threshold set rejected: LONG and SHORT must validate the same frozen threshold_contract_hash';
  end if;

  v_cost_model_id:=nullif(new.evidence_reference->>'validated_execution_cost_model_id','');

  if v_cost_model_id is not null then
    select exists(
      select 1
      from public.alpha_hunter_execution_cost_model_versions c
      where c.cost_model_id=v_cost_model_id
        and c.status='ACTIVE'
        and c.validated_at_utc is not null
        and c.activated_at_utc is not null
        and c.shadow_only is true
        and c.trade_permission is false
    ) into v_cost_ok;
  end if;

  if not v_cost_ok then
    raise exception 'ACTIVE threshold set rejected: referenced execution cost model is not ACTIVE and validated';
  end if;

  new.evidence_reference:=
    coalesce(new.evidence_reference,'{}'::jsonb)
    || jsonb_build_object(
      'active_guard_version','money-entry-threshold-active-guard-v0.1',
      'global_direction_safety_verified',true,
      'complete_t0_t1_t2_thresholds_verified',true,
      'validated_execution_cost_model_verified',true
    );

  return new;
end;
$function$;

revoke all on function private.alpha_hunter_guard_money_entry_threshold_active_v01()
from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_money_entry_threshold_active_guard_v01
  on public.alpha_hunter_money_entry_threshold_sets;

create trigger trg_ah_money_entry_threshold_active_guard_v01
before insert on public.alpha_hunter_money_entry_threshold_sets
for each row
execute function private.alpha_hunter_guard_money_entry_threshold_active_v01();

-- Existing rows are untouched. Current ACTIVE row count is expected to remain 0.
