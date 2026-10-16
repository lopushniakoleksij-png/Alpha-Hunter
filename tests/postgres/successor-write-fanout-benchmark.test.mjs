// Successor-only in-memory PostgreSQL workload: DOES NOT deploy SQL or connect to Supabase.
// Compared paths are simplified strategy-observation projections inspired by the actual
// production trigger, NOT a drop-in replacement or proof of production latency improvement.
import { PGlite } from '@electric-sql/pglite';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { performance } from 'node:perf_hooks';

const N = 64;
const RUN = 'successor-synthetic-only-20261012';
const TS = '2026-10-12T11:00:00Z';
const STRATEGIES = Array.from({ length: 10 }, (_, i) => ({
  strategy_id: `S${i+1}`,
  direction: i % 2 ? 'SHORT' : 'LONG',
  status: i === 0 ? 'WATCH' : i === 3 ? 'SHADOW_CANDIDATE' : 'NO_SAFE_TRADE',
  action: i < 2 ? 'WAIT_FOR_TRIGGER' : 'NO_SAFE_TRADE',
  signal_score: i + 0.125,
  persistence: {
    strategy_instance_id: `synthetic-instance-${i + 1}`,
    first_seen_at_utc: TS,
    state: 'FIRST_SEEN',
  },
}));
const rows = Array.from({ length: N }, (_, i) => ({
  run_id: RUN, symbol: `SYNTH${String(i).padStart(3, '0')}USDT`,
  observed_at_utc: TS,
  payload: {
    last_price: 1 + i / 1000,
    multi_strategy_engine: { strategies: STRATEGIES.map(s => ({
      ...s,
      persistence: { ...s.persistence, strategy_instance_id: `${s.persistence.strategy_instance_id}-${i}` },
    })) },
  },
}));

const SCHEMA = `
CREATE TABLE src_symbol (
  run_id text NOT NULL, symbol text NOT NULL,
  observed_at_utc timestamptz NOT NULL,
  payload jsonb NOT NULL,
  PRIMARY KEY(run_id,symbol)
);
CREATE TABLE strategy_obs (
  observation_id text PRIMARY KEY, run_id text NOT NULL, symbol text NOT NULL,
  strategy_id text NOT NULL, observed_at_utc timestamptz NOT NULL,
  direction text, status text NOT NULL, action text NOT NULL, signal_score numeric,
  strategy_instance_id text, strategy_payload jsonb NOT NULL,
  shadow_only boolean NOT NULL CHECK (shadow_only),
  trade_permission boolean NOT NULL CHECK (NOT trade_permission),
  order_path text NOT NULL CHECK(order_path='NONE'),
  UNIQUE(run_id,symbol,strategy_id)
);
CREATE TABLE strategy_episode (
  episode_id text PRIMARY KEY, symbol text NOT NULL, strategy_id text NOT NULL,
  first_observation_id text NOT NULL UNIQUE, first_payload jsonb NOT NULL,
  shadow_only boolean NOT NULL CHECK(shadow_only),
  trade_permission boolean NOT NULL CHECK(NOT trade_permission),
  order_path text NOT NULL CHECK(order_path='NONE')
);
`;

const TRIGGER = `
CREATE FUNCTION synthetic_legacy_fanout() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE s jsonb; p jsonb; oid text; sid text;
BEGIN
  FOR s IN SELECT value FROM jsonb_array_elements(
    NEW.payload->'multi_strategy_engine'->'strategies'
  )
  LOOP
    p := coalesce(s->'persistence','{}'::jsonb);
    sid := s->>'strategy_id';
    oid := md5('strategy-observation-v0.1|'||NEW.run_id||'|'||NEW.symbol||'|'||sid||'|'||NEW.observed_at_utc::text);
    INSERT INTO strategy_obs(
      observation_id,run_id,symbol,strategy_id,observed_at_utc,direction,status,action,
      signal_score,strategy_instance_id,strategy_payload,shadow_only,trade_permission,order_path
    ) VALUES(
      oid,NEW.run_id,NEW.symbol,sid,NEW.observed_at_utc,upper(s->>'direction'),
      coalesce(s->>'status','UNKNOWN'),coalesce(s->>'action','NO_SAFE_TRADE'),
      nullif(s->>'signal_score','')::numeric,p->>'strategy_instance_id',
      s,true,false,'NONE'
    ) ON CONFLICT(observation_id) DO NOTHING;
    IF nullif(p->>'strategy_instance_id','') IS NOT NULL
       AND upper(s->>'direction') IN ('LONG','SHORT')
       AND s->>'status' IN ('WATCH','SHADOW_CANDIDATE')
    THEN
      INSERT INTO strategy_episode(
        episode_id,symbol,strategy_id,first_observation_id,first_payload,
        shadow_only,trade_permission,order_path
      ) VALUES(p->>'strategy_instance_id',NEW.symbol,sid,oid,s,true,false,'NONE')
      ON CONFLICT(episode_id) DO NOTHING;
    END IF;
  END LOOP;
  RETURN NEW;
END;
$fn$;
CREATE TRIGGER synthetic_legacy AFTER INSERT OR UPDATE OF payload ON src_symbol
FOR EACH ROW EXECUTE FUNCTION synthetic_legacy_fanout();
`;

const SET_BASED = `
INSERT INTO strategy_obs(
  observation_id,run_id,symbol,strategy_id,observed_at_utc,direction,status,action,
  signal_score,strategy_instance_id,strategy_payload,shadow_only,trade_permission,order_path
)
SELECT md5('strategy-observation-v0.1|'||c.run_id||'|'||c.symbol||'|'||
           (s.value->>'strategy_id')||'|'||c.observed_at_utc::text),
       c.run_id,c.symbol,s.value->>'strategy_id',c.observed_at_utc,
       upper(s.value->>'direction'),coalesce(s.value->>'status','UNKNOWN'),
       coalesce(s.value->>'action','NO_SAFE_TRADE'),
       nullif(s.value->>'signal_score','')::numeric,
       s.value->'persistence'->>'strategy_instance_id',s.value,
       true,false,'NONE'
FROM src_symbol c CROSS JOIN LATERAL
  jsonb_array_elements(c.payload->'multi_strategy_engine'->'strategies') s(value)
WHERE c.run_id=$1
ON CONFLICT(observation_id) DO NOTHING;
`;

const SET_EPISODES = `
INSERT INTO strategy_episode(
  episode_id,symbol,strategy_id,first_observation_id,first_payload,
  shadow_only,trade_permission,order_path
)
SELECT s.value->'persistence'->>'strategy_instance_id',
       c.symbol,s.value->>'strategy_id',
       md5('strategy-observation-v0.1|'||c.run_id||'|'||c.symbol||'|'||
           (s.value->>'strategy_id')||'|'||c.observed_at_utc::text),
       s.value,true,false,'NONE'
FROM src_symbol c CROSS JOIN LATERAL
  jsonb_array_elements(c.payload->'multi_strategy_engine'->'strategies') s(value)
WHERE c.run_id=$1
  AND nullif(s.value->'persistence'->>'strategy_instance_id','') IS NOT NULL
  AND upper(s.value->>'direction') IN ('LONG','SHORT')
  AND s.value->>'status' IN ('WATCH','SHADOW_CANDIDATE')
ON CONFLICT(episode_id) DO NOTHING;
`;

async function ingest(db, setBased) {
  await db.exec('BEGIN');
  try {
    // Same 64-symbol bulk request, same source payload, and same unique conflict key.
    await db.query(`
      INSERT INTO src_symbol(run_id,symbol,observed_at_utc,payload)
      SELECT x.run_id,x.symbol,x.observed_at_utc::timestamptz,x.payload
      FROM jsonb_to_recordset($1::jsonb)
       AS x(run_id text,symbol text,observed_at_utc text,payload jsonb)
      ON CONFLICT(run_id,symbol)
      DO UPDATE SET payload=excluded.payload
    `, [JSON.stringify(rows)]);
    if (setBased) {
      await db.query(SET_BASED,[RUN]);
      await db.query(SET_EPISODES,[RUN]);
    }
    await db.exec('COMMIT');
  } catch(e) {
    await db.exec('ROLLBACK');
    throw e;
  }
}

async function read(db) {
  const obs = (await db.query(`
    SELECT observation_id,run_id,symbol,strategy_id,
      to_char(observed_at_utc AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS') observed_at_utc,
      direction,status,action,signal_score::text,strategy_instance_id,
      strategy_payload,shadow_only,trade_permission,order_path
    FROM strategy_obs ORDER BY observation_id
  `)).rows;
  const episodes = (await db.query(`
    SELECT * FROM strategy_episode ORDER BY episode_id
  `)).rows;
  return {obs,episodes};
}

test('isolated row-trigger vs set-based candidate: same 640 immutable observations, 128 episodes and retry results', async () => {
  const legacy = new PGlite();
  const proposed = new PGlite();
  try {
    await legacy.exec(SCHEMA + TRIGGER);
    await proposed.exec(SCHEMA);
    const startOld = performance.now();
    await ingest(legacy,false);
    const legacyMs = performance.now() - startOld;
    const startNew = performance.now();
    await ingest(proposed,true);
    const candidateMs = performance.now() - startNew;
    const oldRows = await read(legacy);
    const newRows = await read(proposed);
    assert.equal(oldRows.obs.length, N * 10);
    assert.equal(oldRows.episodes.length, N * 2);
    assert.deepEqual(newRows, oldRows,
      'Set-based candidate must preserve every sampled deterministic row and episode, not just count');
    await ingest(legacy,false);
    await ingest(proposed,true);
    assert.deepEqual(await read(legacy),oldRows,'Legacy retry must preserve immutable rows');
    assert.deepEqual(await read(proposed),newRows,'Set-based retry must preserve immutable rows');
    console.log(JSON.stringify({
      prototype:'SIMPLIFIED_PGLITE_WASM_NOT_PRODUCTION_BENCHMARK',
      symbolRows:N,strategiesPerSymbol:10,expectedObservations:N*10,
      expectedEpisodes:N*2,
      baselineMs:Number(legacyMs.toFixed(1)),
      candidateMs:Number(candidateMs.toFixed(1)),
      relativeCandidateToBaseline: Number((candidateMs/legacyMs).toFixed(3)),
      meaningfulProductionSpeedClaim:false,
      sciencePromotionPermitted:false,orderAuthority:false,
    }));
  } finally {
    await legacy.close();
    await proposed.close();
  }
});

test('isolated candidate is atomic on validation failure: no orphan observations or symbol rows',async()=>{
 const db=new PGlite();
 try {
  await db.exec(SCHEMA);
  await db.exec('BEGIN');
  try{
   await db.query(`INSERT INTO src_symbol(run_id,symbol,observed_at_utc,payload) VALUES($1,$2,$3,$4::jsonb)`,
     [RUN,'SYNTHBROKENUSDT',TS,JSON.stringify(rows[0].payload)]);
   await assert.rejects(
     db.query(`INSERT INTO strategy_obs(observation_id,run_id,symbol,strategy_id,observed_at_utc,
        status,action,strategy_payload,shadow_only,trade_permission,order_path)
       VALUES('broken-id',$1,$2,'S1',$3,'WATCH','WAIT','{}',false,false,'NONE')`,
       [RUN,'SYNTHBROKENUSDT',TS]),
     /check constraint/i
   );
  } finally {
   await db.exec('ROLLBACK');
  }
  assert.equal((await db.query(`select count(*)::int n from src_symbol`)).rows[0].n,0);
  assert.equal((await db.query(`select count(*)::int n from strategy_obs`)).rows[0].n,0);
 }finally{await db.close();}
});
