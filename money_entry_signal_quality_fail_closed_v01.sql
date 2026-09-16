-- Alpha Hunter Money Entry signal-quality fail-closed guard v0.1
--
-- Purpose:
-- Prevent any future Money Entry stage snapshot from being marked stage_eligible
-- when the upstream scanner has not positively verified direction alignment,
-- momentum, and minimum data integrity.
--
-- This is a safety-only shadow migration. It does not create thresholds, does
-- not enable trade permission, and does not add an order path.

create or replace function private.alpha_hunter_enforce_money_entry_signal_quality()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_reasons jsonb := '[]'::jsonb;
begin
  -- Only an otherwise-eligible T0/T1/T2 snapshot needs downgrading here.
  -- DATA_INSUFFICIENT / NO_T0 rows remain evidence records as written.
  if new.stage_eligible is true then
    if new.scanner_direction_aligned is not true then
      v_reasons := v_reasons || jsonb_build_array(
        case
          when new.scanner_direction_aligned is null then 'SCANNER_DIRECTION_ALIGNMENT_NOT_CAPTURED'
          else 'SCANNER_DIRECTION_NOT_ALIGNED'
        end
      );
    end if;

    if new.scanner_momentum_confirmed is not true then
      v_reasons := v_reasons || jsonb_build_array(
        case
          when new.scanner_momentum_confirmed is null then 'SCANNER_MOMENTUM_NOT_CAPTURED'
          else 'SCANNER_MOMENTUM_NOT_CONFIRMED'
        end
      );
    end if;

    if new.scanner_data_integrity_pass is not true then
      v_reasons := v_reasons || jsonb_build_array(
        case
          when new.scanner_data_integrity_pass is null then 'SCANNER_DATA_INTEGRITY_NOT_CAPTURED'
          else 'SCANNER_DATA_INTEGRITY_NOT_VERIFIED'
        end
      );
    end if;

    if jsonb_array_length(v_reasons) > 0 then
      new.stage_status := 'NO_T0';
      new.stage_eligible := false;
      new.blockers := coalesce(new.blockers, '[]'::jsonb) || v_reasons;
      new.evidence := coalesce(new.evidence, '{}'::jsonb) || jsonb_build_object(
        'signal_quality_fail_closed', true,
        'signal_quality_fail_closed_reasons', v_reasons,
        'signal_quality_guard_version', 'money-entry-signal-quality-v0.1'
      );
    end if;
  end if;

  -- Preserve the permanent research-only safety boundary regardless of caller.
  new.shadow_only := true;
  new.trade_permission := false;
  return new;
end;
$$;

revoke all on function private.alpha_hunter_enforce_money_entry_signal_quality() from public, anon, authenticated;
grant execute on function private.alpha_hunter_enforce_money_entry_signal_quality() to service_role;

drop trigger if exists trg_ah_money_entry_signal_quality_fail_closed
  on public.alpha_hunter_money_entry_stage_snapshots;
create trigger trg_ah_money_entry_signal_quality_fail_closed
before insert on public.alpha_hunter_money_entry_stage_snapshots
for each row execute function private.alpha_hunter_enforce_money_entry_signal_quality();

comment on function private.alpha_hunter_enforce_money_entry_signal_quality() is
  'Fail-closed guard: an eligible Money Entry stage requires scanner direction alignment, momentum confirmation, and minimum data integrity. Shadow only; never grants trade permission.';
