// Enumerate closed Polymarket game events for a league tag, newest endDate first,
// stopping once a whole page ends before the window start. Returns compact records
// (main markets only: moneyline / spreads / totals) plus raw page stats.
import fs from 'node:fs';
import path from 'node:path';

const MAIN = new Set(['moneyline', 'spreads', 'totals']);

function parseJSONish(v) {
  if (Array.isArray(v)) return v;
  if (typeof v === 'string') { try { return JSON.parse(v); } catch { return null; } }
  return v ?? null;
}

export function compactEvent(e) {
  const markets = (e.markets || []).filter((m) => MAIN.has(m.sportsMarketType)).map((m) => ({
    id: m.id, slug: m.slug, question: m.question, type: m.sportsMarketType,
    line: m.line ?? null, outcomes: parseJSONish(m.outcomes), outcomePrices: parseJSONish(m.outcomePrices),
    tokens: parseJSONish(m.clobTokenIds), volume: m.volumeNum ?? (m.volume ? Number(m.volume) : null),
    closedTime: m.closedTime ?? null, gameStartTime: m.gameStartTime ?? null, createdAt: m.createdAt ?? null,
    startDate: m.startDate ?? null, acceptingOrdersTimestamp: m.acceptingOrdersTimestamp ?? null,
    feesEnabled: m.feesEnabled ?? null, feeSchedule: m.feeSchedule ?? null, takerBaseFee: m.takerBaseFee ?? null,
    feeType: m.feeType ?? null, umaResolutionStatus: m.umaResolutionStatus ?? null, conditionId: m.conditionId ?? null,
    orderPriceMinTickSize: m.orderPriceMinTickSize ?? null,
  }));
  return {
    id: e.id, slug: e.slug, title: e.title, startTime: e.startTime ?? null, eventDate: e.eventDate ?? null,
    endDate: e.endDate ?? null, startDate: e.startDate ?? null, createdAt: e.createdAt ?? null,
    sport: e.sport?.sport ?? null, primaryTagId: e.sport?.primaryTagId ?? null, seriesSlug: e.seriesSlug ?? null,
    tags: (e.tags || []).map((t) => Number(t.id)),
    teams: (e.teams || []).map((t) => ({ name: t.name, abbreviation: t.abbreviation, alias: t.alias, ordering: t.ordering, league: t.league, id: t.id })),
    score: e.score ?? null, period: e.period ?? null, finishedTimestamp: e.finishedTimestamp ?? null,
    closedTime: e.closedTime ?? null, volume: e.volume ?? null, nMarketsAll: (e.markets || []).length, gameId: e.gameId ?? null,
    markets,
  };
}

export async function discoverTag(c, { tagId, windowStart, windowEnd, maxPages = 40, startPage = 0, log = () => {} }) {
  const ws = Date.parse(windowStart), we = Date.parse(windowEnd);
  const out = []; const pages = [];
  for (let page = startPage; page < startPage + maxPages; page++) {
    const r = await c.polymarket('/events', { tag_id: tagId, closed: true, limit: 50, offset: page * 50, order: 'endDate', ascending: false });
    if (!r.ok) { pages.push({ page, ok: false, error: r.error }); log(`tag ${tagId} page ${page} ERR ${r.error}`); break; }
    const evs = r.data?.data || [];
    let minEnd = Infinity, maxEnd = -Infinity, kept = 0;
    for (const e of evs) {
      const end = Date.parse(e.endDate || e.startTime || 0);
      if (Number.isFinite(end)) { minEnd = Math.min(minEnd, end); maxEnd = Math.max(maxEnd, end); }
      const st = Date.parse(e.startTime || e.endDate || 0);
      const isGame = (e.teams || []).length === 2 && (e.markets || []).some((m) => MAIN.has(m.sportsMarketType));
      if (isGame && st >= ws && st <= we) { out.push(compactEvent(e)); kept++; }
    }
    pages.push({ page, ok: true, n: evs.length, kept, minEnd: Number.isFinite(minEnd) ? new Date(minEnd).toISOString() : null, maxEnd: Number.isFinite(maxEnd) ? new Date(maxEnd).toISOString() : null, cached: r.cached });
    log(`tag ${tagId} page ${page}: n=${evs.length} kept=${kept} endDate ${pages[pages.length-1].minEnd} … ${pages[pages.length-1].maxEnd}${r.cached ? ' (cache)' : ''}`);
    if (evs.length < 50) break;
    if (Number.isFinite(maxEnd) && maxEnd < ws - 2 * 86400e3) break; // whole page older than window
  }
  // dedupe by event id
  const seen = new Set(); const uniq = [];
  for (const e of out) { if (!seen.has(e.id)) { seen.add(e.id); uniq.push(e); } }
  return { events: uniq, pages };
}

export function saveDerived(name, obj) {
  const dir = path.join(process.env.A9_DATA || '/home/user/workspace/a9-data', 'derived');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, name), JSON.stringify(obj));
  return path.join(dir, name);
}
