// Process Polymarket price-history work items through the cached, paced client.
// Transient failures (429 / 5xx) back off and retry the same item; nothing transient is cached.
import fs from 'node:fs';
import path from 'node:path';
const DATA = process.env.A9_DATA || '/home/user/workspace/a9-data';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const ROLE_ORDER = { ml: 0, draw: 0, total: 1, spread: 1 };

export async function runWork(c, { maxCalls = 100000, maxMs = 1e12, log = () => {}, filter = () => true, maxRetries = 8, sortBy = null } = {}) {
  let work = JSON.parse(fs.readFileSync(path.join(DATA, 'derived', 'pm_work.json'), 'utf8')).items.filter(filter);
  if (sortBy === 'moneyline-first') {
    // keep the interval order (1d, 1w, 1m = most time-sensitive first) but within it do all moneyline/draw items before spreads/totals
    const iv = { '1d': 0, '1w': 1, '1m': 2 };
    work = work.map((it, i) => [it, i]).sort((a, b) => (iv[a[0].interval] - iv[b[0].interval]) || (ROLE_ORDER[a[0].role] - ROLE_ORDER[b[0].role]) || (a[1] - b[1])).map((x) => x[0]);
  }
  const t0 = Date.now();
  let calls = 0, cached = 0, errors = 0, throttled = 0, done = 0, points = 0, gaveUp = 0;
  for (const it of work) {
    if (calls >= maxCalls || Date.now() - t0 > maxMs) break;
    let attempt = 0, r;
    for (;;) {
      r = await c.polymarket('/prices-history', { market: it.token, interval: it.interval, fidelity: it.fidelity }, { game_key: it.game_key, role: it.role });
      if (r.cached) break;
      calls++;
      if (r.ok || !r.transient) break;
      throttled++;
      attempt++;
      if (attempt > maxRetries || calls >= maxCalls) { gaveUp++; break; }
      const wait = Math.min(90000, Math.max((r.retry_after || 1) * 1000, 2000 * 2 ** (attempt - 1)));
      log(`throttled (${it.game_key} ${it.role} ${it.interval}); attempt ${attempt}, waiting ${(wait / 1000).toFixed(0)}s`);
      await sleep(wait);
    }
    done++;
    if (r.cached) { cached++; continue; }
    if (!r.ok) { errors++; if (!r.transient) log(`ERR ${it.game_key} ${it.role} ${it.interval}: ${String(r.error).slice(0, 120)}`); continue; }
    const h = r.data?.data?.history || r.data?.history || [];
    points += h.length;
    if (calls % 100 === 0) log(`${calls} calls (${throttled} throttled), ${done}/${work.length} items, ${errors} errors, ${points} pts, ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  return { items: work.length, done, calls, cached, errors, throttled, gaveUp, points, seconds: (Date.now() - t0) / 1000 };
}
