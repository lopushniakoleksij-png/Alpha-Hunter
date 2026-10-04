from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pglast import parse_sql

from alpha_hunter.paper_horizon import (
    PROTOCOL, reconcile_successor_protections, successor_admission_permitted,
)
from alpha_hunter.paper_exit import reconcile_active_protections
from test_paper_exit_v04 import snapshot, position

ENTRY = datetime(2026, 10, 4, tzinfo=timezone.utc)


def inputs(minutes=1440, direction='LONG'):
    p = position(direction, stop=9 if direction=='LONG' else 11,
                 target=15 if direction=='LONG' else 5)
    p.update(horizon_protocol=PROTOCOL, horizon_scientific_fingerprint_sha256='fingerprint',
             entry_completed_at_utc=ENTRY.isoformat(),
             previous_exit_observed_at_utc=(ENTRY+timedelta(minutes=minutes-20)).isoformat(),
             horizon_integrity_failed=False, unresolved_protective_evidence=False)
    s = snapshot(bid=10, ask=10.1)
    s['collected_at_utc']=(ENTRY+timedelta(minutes=minutes)).isoformat()
    s['validation_identity']={'run_source':'RENDER_CRON','runtime_role':'RENDER_CRON',
                              'scientific_fingerprint_sha256':'fingerprint'}
    return s,p


@pytest.mark.parametrize('direction,side,reference',[('LONG','SELL',10),('SHORT','BUY',10.1)])
def test_horizon_closes_at_executable_side_without_fake_protective_order(direction,side,reference):
    s,p=inputs(direction=direction)
    a,f,e=reconcile_successor_protections(s,[p])
    assert a[0]['outcome']=='HORIZON_CLOSED'
    assert f[0]['side']==side and f[0]['cross_price_reference']==reference
    assert f[0]['triggered_protective_order_id'] is None
    assert f[0]['full_economic_pnl_claim_permitted'] is False
    assert e[0]['state']=='HORIZON_CLOSED'
    assert e[0]['event_type']=='PAPER_HORIZON_EXIT_RECONCILED'
    assert a[0]['evidence']['horizon_integrity_failed'] is False


@pytest.mark.parametrize('minutes,closed',[(1439.999,False),(1440,True),(1475,True),(1475.0001,False)])
def test_exact_horizon_and_observation_lag_boundaries(minutes,closed):
    s,p=inputs(minutes)
    a,f,e=reconcile_successor_protections(s,[p])
    assert bool(f)==closed
    if minutes>1475:
        assert 'HORIZON_OBSERVATION_LAG_EXCEEDED' in a[0]['blockers']


def test_delayed_limit_uses_completed_fill_not_submission():
    s,p=inputs(1430)
    p['submitted_at_utc']=(ENTRY-timedelta(minutes=30)).isoformat()
    assert reconcile_successor_protections(s,[p])[1]==[]


@pytest.mark.parametrize('bid,outcome',[(8.9,'STOP_TRIGGERED'),(15.1,'TARGET_TRIGGERED')])
def test_protective_exit_precedes_horizon(bid,outcome):
    s,p=inputs();s['symbols'][0].update(bid_price=bid,ask_price=bid+.1)
    a,f,e=reconcile_successor_protections(s,[p])
    assert a[0]['outcome']==outcome
    assert f[0]['protection_type']!='HORIZON_24H'


@pytest.mark.parametrize('defect', ['missing_quote','depth','fee','ambiguous','prior_failure','prior_trigger','gap'])
def test_no_fabricated_or_delayed_horizon_fill(defect):
    s,p=inputs()
    if defect=='missing_quote': s['symbols']=[]
    if defect=='depth': s['symbols'][0]['bid_size']=1
    if defect=='fee': p['public_taker_fee_bps']=None
    if defect=='ambiguous': p['stop_trigger_price']=16
    if defect=='prior_failure': p['horizon_integrity_failed']=True
    if defect=='prior_trigger': p['unresolved_protective_evidence']=True
    if defect=='gap': p['previous_exit_observed_at_utc']=(ENTRY+timedelta(hours=23)).isoformat()
    a,f,e=reconcile_successor_protections(s,[p])
    assert f==[] and e==[]
    assert a[0]['evidence']['horizon_integrity_failed'] is True
    # Persisted failure blocks a later attractive quote.
    later,pp=inputs(1450);pp['horizon_integrity_failed']=True
    assert reconcile_successor_protections(later,[pp])[1]==[]


@pytest.mark.parametrize('defect',['source','fingerprint','clock','replay'])
def test_identity_and_replay_fail_closed(defect):
    s,p=inputs()
    if defect=='source':s['validation_identity']['runtime_role']='WEB'
    if defect=='fingerprint':s['validation_identity']['scientific_fingerprint_sha256']='other'
    if defect=='clock':p['entry_completed_at_utc']='invalid'
    if defect=='replay':p['previous_exit_observed_at_utc']=s['collected_at_utc']
    a,f,e=reconcile_successor_protections(s,[p])
    assert not f and not e and a[0]['outcome']=='HORIZON_FAILED'


def test_duplicate_run_is_noop():
    s,p=inputs()
    assert reconcile_successor_protections(s,[p],attempted_entry_order_ids={'order-1'})==([],[],[])


def test_later_protective_management_keeps_failure_visible():
    s,p=inputs(1500);p['horizon_integrity_failed']=True
    s['symbols'][0].update(bid_price=15.1,ask_price=15.2)
    a,f,e=reconcile_successor_protections(s,[p])
    assert f and e and a[0]['outcome']=='TARGET_TRIGGERED'
    assert a[0]['evidence']['horizon_integrity_failed'] is True


def test_legacy_r8_policy_is_byte_for_byte_unchanged():
    s,p=inputs(1500)
    for field in list(p):
        if field.startswith('horizon_'):p.pop(field)
    assert reconcile_successor_protections(s,[p])==reconcile_active_protections(s,[p])


def test_successor_admission_is_explicit_and_fingerprint_bound():
    s,p=inputs()
    a={'protocol_version':PROTOCOL,'activated_at_utc':ENTRY.isoformat(),
       'admission_cutoff_at_utc':(ENTRY+timedelta(days=30)).isoformat(),
       'scientific_fingerprint_sha256':'fingerprint'}
    assert successor_admission_permitted(s,[a])
    assert not successor_admission_permitted(s,[])
    assert not successor_admission_permitted(s,[a,a])
    for value in [ENTRY,ENTRY+timedelta(days=31)]:
        invalid=deepcopy(s);invalid['collected_at_utc']=value.isoformat()
        assert not successor_admission_permitted(invalid,[a])
    invalid=deepcopy(s);invalid['validation_identity']['scientific_fingerprint_sha256']='R8'
    assert not successor_admission_permitted(invalid,[a])


def test_migration_parses_without_activating_successor():
    sql=(Path(__file__).parents[1]/'ops/sql/paper_horizon_successor_v09.sql').read_text()
    assert parse_sql(sql)
    assert 'insert into public.alpha_hunter_paper_execution_activation_v09' not in sql.lower()


def test_missing_predue_observation_cannot_reset_monitoring_gap_as_valid():
    s,p=inputs(1200);s['symbols']=[]
    a,f,e=reconcile_successor_protections(s,[p])
    assert not f and not e
    assert a[0]['evidence']['horizon_integrity_failed'] is True


def test_activation_functions_parse():
    assert parse_sql((Path(__file__).parents[1]/'ops/sql/paper_successor_activation_v09.sql').read_text())


@pytest.mark.parametrize('direction', ['LONG', 'SHORT'])
@pytest.mark.parametrize('offset_seconds', [0, 8])
def test_entry_run_is_not_a_post_fill_monitoring_observation(direction, offset_seconds):
    s,p=inputs(0,direction)
    p['entry_completed_source_run_id']=s['run_id']
    p['entry_completed_at_utc']=(ENTRY+timedelta(seconds=offset_seconds)).isoformat()
    p['previous_exit_observed_at_utc']=None
    # Even a trigger-like quote cannot establish ordering within the entry run.
    s['symbols'][0].update(bid_price=8,ask_price=8.1)
    assert reconcile_successor_protections(s,[p])==([],[],[])


@pytest.mark.parametrize('minutes,failed', [(20,False),(35,False),(35.01,True)])
def test_first_later_observation_gap_is_measured_from_fill(minutes,failed):
    s,p=inputs(minutes)
    p['previous_exit_observed_at_utc']=None
    a,f,e=reconcile_successor_protections(s,[p])
    assert not f and not e
    assert a[0]['evidence']['horizon_integrity_failed'] is failed
    assert ('HORIZON_MONITORING_GAP_EXCEEDED' in a[0]['blockers']) is failed


@pytest.mark.parametrize('source', ['GITHUB_REALTIME_HOURLY','WEB',None])
def test_noncanonical_discovery_cannot_poison_or_advance_successor_history(source):
    s,p=inputs()
    s['validation_identity'].update(run_source=source,runtime_role='OTHER',
                                    scientific_fingerprint_sha256='other')
    assert reconcile_successor_protections(s,[p])==([],[],[])
    legacy=deepcopy(p);legacy.pop('horizon_protocol')
    assert reconcile_successor_protections(s,[legacy])==reconcile_active_protections(s,[legacy])


@pytest.mark.parametrize('previous', ['invalid',''])
def test_corrupt_previous_clock_is_not_treated_as_first_observation(previous):
    s,p=inputs(0);p['previous_exit_observed_at_utc']=previous
    p['entry_completed_source_run_id']=s['run_id']
    a,f,e=reconcile_successor_protections(s,[p])
    assert not f and not e and 'HORIZON_CLOCK_EVIDENCE_INVALID' in a[0]['blockers']


def test_entry_run_with_existing_history_is_still_replay_failure():
    s,p=inputs(0);p['entry_completed_source_run_id']=s['run_id']
    p['previous_exit_observed_at_utc']=s['collected_at_utc']
    a,f,e=reconcile_successor_protections(s,[p])
    assert not f and not e and a[0]['outcome']=='HORIZON_FAILED'


def test_same_time_from_different_run_is_not_exempt():
    s,p=inputs(0);p['previous_exit_observed_at_utc']=None
    a,f,e=reconcile_successor_protections(s,[p])
    assert not f and not e and a[0]['outcome']=='HORIZON_FAILED'


def test_first_later_observation_preserves_recorded_failure():
    s,p=inputs(20);p['previous_exit_observed_at_utc']=None
    p['horizon_integrity_failed']=True
    a,f,e=reconcile_successor_protections(s,[p])
    assert a[0]['evidence']['horizon_integrity_failed'] is True
    assert 'HORIZON_PRIOR_FAILURE' in a[0]['blockers']
