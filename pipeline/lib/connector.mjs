// A9 THE TAPE — paced, cached, ledgered connector wrapper.
// Every vendor call goes through here. Identical requests are served from the
// on-disk cache and never re-sent. Every real vendor call is appended to the
// ledger (JSONL) before the result is returned.
//
// Usage (inside Code Mode `exec`, where `tools.call_external_tool` exists):
//   import { makeClient } from '<build>/pipeline/lib/connector.mjs';
//   const c = makeClient(tools, { tier: 0 });
//   const r = await c.opticodds('/fixtures', { league: 'nfl', status: 'completed' });
//
// Data dir (caches, ledger, pacing state) lives outside the project checkout.

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

export const DATA_DIR = process.env.A9_DATA || '/home/user/workspace/a9-data';
export const LEDGER = path.join(DATA_DIR, 'ledger', 'calls.jsonl');

// Tier budgets (hard caps on *real* vendor calls per source, cumulative attempts).
// Tier 1 was approved on 2026-10-15 ~04:10 UTC with explicit caps counted from the Tier-0 position at that moment:
// OpticOdds 88 + 2,000 further attempts, Sportradar 28 + 150 further attempts, Polymarket 3,265 + 2,500 further *successful* calls.
export const TIERS = {
  0: { opticodds: 150, sportradar: 40, polymarket: Infinity, polymarketOk: Infinity },
  1: { opticodds: 88 + 2000, sportradar: 28 + 150, polymarket: Infinity, polymarketOk: 3265 + 2500 },
  // Parent review mail 2026-10-15 ~05:50 UTC: up to 30 further OpticOdds calls for one timestamped "Today" snapshot
  // (/fixtures/active + /fixtures/odds), plus Polymarket current prices under the existing Polymarket cap.
  2: { opticodds: 88 + 2000 + 30, sportradar: 28 + 150, polymarket: Infinity, polymarketOk: 3265 + 2500 },
};

// Minimum spacing between real calls, per bucket (ms).
const PACE = {
  'opticodds:historical': Math.ceil(60000 / 35), // ≤ 35/min (vendor bucket is 40/min)
  'opticodds:other': 150,
  'polymarket': 3000,                            // ≤ 20/min (parent instruction 2026-10-15 04:03 UTC)
  'sportradar': 250,
};

function sortKeys(v) {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === 'object') {
    return Object.keys(v).sort().reduce((o, k) => { o[k] = sortKeys(v[k]); return o; }, {});
  }
  return v;
}

export function cacheKey(source, args) {
  const s = JSON.stringify({ source, args: sortKeys(args) });
  return crypto.createHash('sha1').update(s).digest('hex');
}

function ensureDirs() {
  for (const d of ['cache/opticodds', 'cache/polymarket', 'cache/sportradar', 'ledger', 'state']) {
    fs.mkdirSync(path.join(DATA_DIR, d), { recursive: true });
  }
}

export function readLedger() {
  if (!fs.existsSync(LEDGER)) return [];
  return fs.readFileSync(LEDGER, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
}

export const CACHE_HITS = path.join(DATA_DIR, 'ledger', 'cache_hits.jsonl');

export function ledgerCounts() {
  const counts = { opticodds: 0, sportradar: 0, polymarket: 0, ok: {}, errors: {}, throttled: {}, cached: {} };
  for (const e of readLedger()) {
    counts[e.source] = (counts[e.source] || 0) + 1;
    if (e.ok) counts.ok[e.source] = (counts.ok[e.source] || 0) + 1;
    if (!e.ok) counts.errors[e.source] = (counts.errors[e.source] || 0) + 1;
    if (!e.ok && isTransient(e.error)) counts.throttled[e.source] = (counts.throttled[e.source] || 0) + 1;
  }
  if (fs.existsSync(CACHE_HITS)) {
    for (const l of fs.readFileSync(CACHE_HITS, 'utf8').split('\n')) { if (!l) continue; const src = l.split(',')[1]; counts.cached[src] = (counts.cached[src] || 0) + 1; }
  }
  return counts;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function paceStatePath(bucket) {
  return path.join(DATA_DIR, 'state', `pace-${bucket.replace(':', '-')}.json`);
}

function readPace(bucket) {
  try { return JSON.parse(fs.readFileSync(paceStatePath(bucket), 'utf8')); } catch { return {}; }
}

// Adaptive pacing: the interval never drops below PACE[bucket]; a 429 widens it (see noteThrottle),
// and sustained success narrows it back down slowly.
async function pace(bucket) {
  const st = readPace(bucket);
  const interval = Math.max(PACE[bucket], st.interval || PACE[bucket]);
  const wait = (st.last || 0) + interval - Date.now();
  if (wait > 0) await sleep(wait);
  fs.writeFileSync(paceStatePath(bucket), JSON.stringify({ ...st, last: Date.now(), interval }));
}

// Exponential backoff: each 429 doubles the spacing (floor PACE, ceiling 120 s); it relaxes only after sustained success.
export function noteThrottle(bucket, retryAfterSec) {
  const st = readPace(bucket);
  const interval = Math.min(120000, Math.max((st.interval || PACE[bucket]) * 2, (retryAfterSec || 1) * 1000, PACE[bucket]));
  fs.writeFileSync(paceStatePath(bucket), JSON.stringify({ ...st, interval, streak: 0, throttles: (st.throttles || 0) + 1 }));
  return interval;
}

export function noteSuccess(bucket) {
  const st = readPace(bucket);
  const streak = (st.streak || 0) + 1;
  let interval = st.interval || PACE[bucket];
  if (streak % 40 === 0 && interval > PACE[bucket]) interval = Math.max(PACE[bucket], interval * 0.85);
  fs.writeFileSync(paceStatePath(bucket), JSON.stringify({ ...st, streak, interval }));
}

export function isTransient(errText) {
  const e = String(errText || '');
  return /HTTP 429|HTTP 5\d\d|ECONNRESET|ETIMEDOUT|timeout|Too Many Requests|temporarily|rate limit/i.test(e);
}

export function retryAfterSeconds(errText) {
  const m = /Retry-After:\s*(\d+)/i.exec(String(errText || ''));
  return m ? Number(m[1]) : null;
}

// Unwrap a call_external_tool response into { data, source_metadata, raw_shape }.
function unwrap(resp) {
  let data = resp?.result;
  if (data === undefined && resp?.structured_content !== undefined) data = resp.structured_content;
  if (data === undefined && resp?.saved_paths?.length) {
    // Large results are saved to disk by the platform; read the first JSON file.
    for (const sp of resp.saved_paths) {
      try {
        const txt = fs.readFileSync(sp, 'utf8');
        try { data = JSON.parse(txt); } catch { data = txt; }
        break;
      } catch {}
    }
  }
  if (typeof data === 'string') {
    try { data = JSON.parse(data); } catch {}
  }
  return { data, source_metadata: resp?.source_metadata ?? null };
}

export function makeClient(tools, opts = {}) {
  ensureDirs();
  const tier = opts.tier ?? 0;
  const caps = TIERS[tier];
  const counts = ledgerCounts();
  const log = opts.log || (() => {});

  async function call(source, args, meta = {}) {
    const key = cacheKey(source, args);
    const file = path.join(DATA_DIR, 'cache', source, `${key}.json`);
    if (fs.existsSync(file)) {
      const cached = JSON.parse(fs.readFileSync(file, 'utf8'));
      // cache-served reads are counted separately from vendor attempts (t,source,key)
      fs.appendFileSync(CACHE_HITS, `${new Date().toISOString()},${source},${key}\n`);
      if (cached.ok || opts.returnCachedErrors) return { ...cached, cached: true };
      // a cached error can be retried only when explicitly requested
      if (!opts.retryErrors) return { ...cached, cached: true };
    }
    if ((counts[source] || 0) >= caps[source]) {
      throw new Error(`BUDGET: tier ${tier} cap reached for ${source} (${counts[source]}/${caps[source]})`);
    }
    if (source === 'polymarket' && (counts.ok[source] || 0) >= caps.polymarketOk) {
      throw new Error(`BUDGET: tier ${tier} successful-call cap reached for polymarket (${counts.ok[source]}/${caps.polymarketOk})`);
    }
    const bucket = source === 'opticodds'
      ? (args.path === '/fixtures/odds/historical' ? 'opticodds:historical' : 'opticodds:other')
      : source;
    await pace(bucket);
    const t0 = Date.now();
    let resp, err = null;
    try {
      resp = await tools.call_external_tool({ tool_name: source, source_id: source, arguments: args });
    } catch (e) {
      err = String(e?.message || e);
    }
    const ms = Date.now() - t0;
    counts[source] = (counts[source] || 0) + 1;
    counts.ok = counts.ok || {};
    let out;
    if (err) {
      out = { ok: false, source, args, key, error: err, retrieved_at: new Date(t0).toISOString(), ms };
    } else {
      const { data, source_metadata } = unwrap(resp);
      const toolErr = resp?.error || (data && typeof data === 'object' && !Array.isArray(data) && (data.error || data.detail)) || null;
      const ok = !toolErr && data !== undefined;
      out = {
        ok, source, args, key, retrieved_at: new Date(t0).toISOString(), ms,
        source_metadata, data, error: toolErr ? String(typeof toolErr === 'string' ? toolErr : JSON.stringify(toolErr)).slice(0, 2000) : null,
        hint: resp?.hint ?? null, requires_auth: resp?.requires_auth ?? null,
      };
    }
    const bytes = Buffer.byteLength(JSON.stringify(out.data ?? ''), 'utf8');
    if (out.ok) counts.ok[source] = (counts.ok[source] || 0) + 1;
    const transient = !out.ok && isTransient(out.error);
    out.transient = transient;
    out.retry_after = transient ? retryAfterSeconds(out.error) : null;
    fs.appendFileSync(LEDGER, JSON.stringify({
      t: out.retrieved_at, source, path: args.path, product: args.product ?? null,
      params: args.params ?? null, key, ok: out.ok, ms, bytes, transient,
      error: out.error ? String(out.error).slice(0, 300) : null, tier, n: counts[source], ...meta,
    }) + '\n');
    // transient failures (429 / 5xx / network) are never cached: the next attempt re-sends the request
    if (!transient) fs.writeFileSync(file, JSON.stringify(out));
    if (transient) noteThrottle(bucket, out.retry_after); else noteSuccess(bucket);
    log(`[${source} #${counts[source]}] ${args.path} ${out.ok ? 'ok' : (transient ? 'THROTTLED' : 'ERR')} ${ms}ms ${bytes}B`);
    return { ...out, cached: false };
  }

  return {
    call,
    counts: () => ({ ...counts }),
    opticodds: (p, params = {}, meta) => call('opticodds', { path: p, params }, meta),
    polymarket: (p, params = {}, meta) => call('polymarket', { path: p, params }, meta),
    sportradar: (product, p, params, meta) => call('sportradar', params ? { product, path: p, params } : { product, path: p }, meta),
  };
}
