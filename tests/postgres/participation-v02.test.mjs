import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';

const sql = readFileSync(new URL('../../ops/sql/participation_universe_endpoint_forward_v02.sql', import.meta.url), 'utf8');
const diagnostics = readFileSync(new URL('../../participation_diagnostics_v01.sql', import.meta.url), 'utf8').split('alter table')[0];
const prefix = 'private.alpha_hunter_participation_universe_endpoint_';
const run = `select private.alpha_hunter_run_participation_universe_endpoint_forward_v02()`;

async function setup() {
  const db = new PGlite();
  await db.exec(`
    create schema private;
    create role anon; create role authenticated; create role service_role;
    create schema cron;
    create table cron.job(jobid bigint, jobname text);
    create function cron.unschedule(bigint) returns boolean language sql as 'select true';
    create function cron.schedule(text,text,text) returns bigint language sql as 'select 1::bigint';
    create table public.alpha_hunter_signals(
      signal_id text primary key, direction text, reference_price float8, detected_at_utc timestamptz);
    create table public.alpha_hunter_universe_hourly(
      observation_id text primary key, selection_run_id text, symbol text,
      observed_at_utc timestamptz, source text, measurement_quality text, last_price float8);
  `);
  await db.exec(diagnostics);
  // Seed a historical registration only in this empty synthetic database.
  // Execute the actual migration unchanged afterward, including inert cron stubs.
  const insertStart = sql.indexOf('insert into private.alpha_hunter_participation_universe_endpoint_specs_v02');
  const insertEnd = sql.indexOf('on conflict(spec_id) do nothing;', insertStart) + 'on conflict(spec_id) do nothing;'.length;
  await db.exec(sql.slice(0, insertStart));
  await db.exec(sql.slice(insertStart, insertEnd).replace('clock_timestamp()', "clock_timestamp()-interval '3 days'"));
  await db.exec(sql);
  return db;
}

async function diagnostic(db, id='a', direction='LONG') {
  await db.query(`insert into public.alpha_hunter_signals values ($1,$2,100,now()-interval '26 hours')`, [id,direction]);
  await db.query(`insert into public.alpha_hunter_participation_diagnostics
    (diagnostic_id,run_id,source_signal_id,captured_at_utc,symbol,candidate_direction,classification)
    select $1,$1,$1,detected_at_utc,$1,$2,'DESCRIPTIVE' from public.alpha_hunter_signals where signal_id=$1`, [id,direction]);
}

async function anchor(db,id='a', obs=`${id}-anchor`, price=100) {
  await db.query(`insert into public.alpha_hunter_universe_hourly
    select $2,$1,$1,captured_at_utc,'PRIMARY_SCANNER_CACHED_TICKERS','CANONICAL_SCAN_TICKER_SNAPSHOT',$3
    from public.alpha_hunter_participation_diagnostics where diagnostic_id=$1`, [id,obs,price]);
}

async function endpoint(db,id='a', hours=1, lag=0, price=110) {
  await db.query(`insert into public.alpha_hunter_universe_hourly
    select $1||'-endpoint-'||$2::text||'-'||$3::text,'endpoint-run',$1,
      captured_at_utc+make_interval(hours=>$2::integer,secs=>$3::double precision),
      'PRIMARY_SCANNER_CACHED_TICKERS','CANONICAL_SCAN_TICKER_SNAPSHOT',$4
    from public.alpha_hunter_participation_diagnostics where diagnostic_id=$1`, [id,hours,lag,price]);
}

test('available anchors and materialized candidates are distinct', async () => {
  const db=await setup();
  try {
    await diagnostic(db); await anchor(db);
    const before=(await db.query('select * from private.alpha_hunter_participation_universe_t0_admission_health_v02')).rows[0];
    assert.equal(Number(before.anchor_available),1);
    assert.equal(Number(before.candidate_admitted),0);
    assert.equal(Number(before.candidate_pending_materialization),1);
    await db.exec(run);
    const after=(await db.query('select * from private.alpha_hunter_participation_universe_t0_admission_health_v02')).rows[0];
    assert.equal(Number(after.candidate_admitted),1);
    assert.equal(Number(after.candidate_pending_materialization),0);
  } finally { await db.close(); }
});

test('missing anchor can arrive later; persisted censoring never becomes a win', async () => {
  const db=await setup();
  try {
    await diagnostic(db); await db.exec(run);
    assert.equal(Number((await db.query(`select count(*) n from ${prefix}candidates_v02`)).rows[0].n),0);
    await anchor(db); await db.exec(run);
    assert.equal(Number((await db.query(`select count(*) n from ${prefix}failures_v02`)).rows[0].n),4);
    await endpoint(db); await db.exec(run);
    assert.equal(Number((await db.query(`select count(*) n from ${prefix}outcomes_v02`)).rows[0].n),0);
    assert.equal(Number((await db.query(`select count(*) n from ${prefix}failures_v02`)).rows[0].n),4);
  } finally { await db.close(); }
});

test('earliest endpoint wins, 30-minute boundary is inclusive, LONG/SHORT are symmetric', async () => {
  const db=await setup();
  try {
    for (const [id,dir] of [['a','LONG'],['b','SHORT']]) {
      await diagnostic(db,id,dir); await anchor(db,id);
      await endpoint(db,id,1,1200,120); await endpoint(db,id,1,0,110);
      await endpoint(db,id,4,1800,110); await endpoint(db,id,12,1801,110);
    }
    await db.exec(run); await db.exec(run);
    const rows=(await db.query(`select c.symbol,o.horizon_hours,o.endpoint_lag_seconds,
      o.direction_adjusted_return_pct r from ${prefix}outcomes_v02 o
      join ${prefix}candidates_v02 c using(candidate_id) order by c.symbol,o.horizon_hours`)).rows;
    assert.equal(rows.length,4);
    for(const row of rows) {
      assert.ok(Math.abs(row.r-(row.symbol==='a'?10:-10))<1e-9);
      assert.equal(row.endpoint_lag_seconds,row.horizon_hours===1?0:1800);
    }
    assert.equal(Number((await db.query(`select count(*) n from ${prefix}failures_v02`)).rows[0].n),4);
  } finally { await db.close(); }
});

test('evidence rejects UPDATE, DELETE and TRUNCATE and service role cannot execute collector', async () => {
  const db=await setup();
  try {
    await diagnostic(db); await anchor(db); await endpoint(db); await db.exec(run);
    for(const [table,key] of [['candidates','candidate_id'],['outcomes','outcome_id'],['failures','failure_id'],['runs','run_id']]) {
      for(const statement of [
        `update ${prefix}${table}_v02 set ${key}=${key}`,
        `delete from ${prefix}${table}_v02`,
        `truncate ${prefix}${table}_v02 cascade`
      ]) await assert.rejects(db.exec(statement), /append.only/i);
    }
    const perms=(await db.query(`select
      has_function_privilege('service_role','private.alpha_hunter_run_participation_universe_endpoint_forward_v02()','EXECUTE') execute,
      has_table_privilege('service_role','${prefix}candidates_v02','INSERT') insert`)).rows[0];
    assert.equal(perms.execute,false); assert.equal(perms.insert,false);
  } finally { await db.close(); }
});

test('registration stays frozen, operational pause is allowed, migration can be reapplied', async () => {
  const db=await setup();
  try {
    await assert.rejects(db.exec(`update ${prefix}specs_v02 set registered_at_utc=now()`), /append.only/i);
    await assert.rejects(db.exec(`delete from ${prefix}specs_v02`), /append.only/i);
    await assert.rejects(db.exec(`truncate ${prefix}specs_v02 cascade`), /append.only/i);
    await db.exec(`update ${prefix}specs_v02 set status='PAUSED'`);
    const result=(await db.query(run)).rows[0];
    assert.equal(Object.values(result)[0].status,'NO_ACTIVE_SPEC');
    await db.exec(sql);
    assert.equal((await db.query(`select status from ${prefix}specs_v02`)).rows[0].status,'PAUSED');
  } finally { await db.close(); }
});

test('duplicate exact anchors stop collection regardless of physical insertion order', async () => {
  for(const prices of [[100,200],[200,100]]) {
    const db=await setup();
    try {
      await diagnostic(db);
      await anchor(db,'a','first',prices[0]); await anchor(db,'a','second',prices[1]);
      await assert.rejects(db.exec(run), /AMBIGUOUS_CANONICAL_UNIVERSE_T0/);
      assert.equal(Number((await db.query(`select count(*) n from ${prefix}candidates_v02`)).rows[0].n),0);
      const health=(await db.query('select * from private.alpha_hunter_participation_universe_t0_admission_health_v02')).rows[0];
      assert.equal(Number(health.anchor_ambiguous),1);
      assert.equal(health.admission_gap_reason,'AMBIGUOUS_CANONICAL_UNIVERSE_T0');
    } finally { await db.close(); }
  }
});
