// Fetch OpticOdds historical odds (one call per fixture: 5 books × 3 main markets, with timeseries).
import fs from 'node:fs';
import path from 'node:path';
const DATA = process.env.A9_DATA || '/home/user/workspace/a9-data';

export const BOOKS = ['Pinnacle', 'DraftKings', 'FanDuel', 'BetMGM', 'Caesars'];
export const MARKETS_BY_SPORT = {
  football: ['moneyline', 'point_spread', 'total_points'],
  basketball: ['moneyline', 'point_spread', 'total_points'],
  baseball: ['moneyline', 'run_line', 'total_runs'],
  hockey: ['moneyline', 'puck_line', 'total_goals'],
  soccer: ['moneyline', 'asian_handicap', 'total_goals'],
};
const SPORT_OF_LEAGUE = { nfl: 'football', ncaaf: 'football', nba: 'basketball', wnba: 'basketball', mlb: 'baseball', nhl: 'hockey', mls: 'soccer', epl: 'soccer', laliga: 'soccer', seriea: 'soccer', bundesliga: 'soccer', ligue1: 'soccer', ucl: 'soccer' };

export function loadMatches() {
  return JSON.parse(fs.readFileSync(path.join(DATA, 'derived', 'matches.json'), 'utf8')).matches;
}

export async function fetchHistorical(c, match, { books = BOOKS, log = () => {} } = {}) {
  const sport = SPORT_OF_LEAGUE[match.league];
  const params = { fixture_id: match.oo_fixture_id, sportsbook: books, market: MARKETS_BY_SPORT[sport], is_main: true, include_timeseries: true };
  const r = await c.opticodds('/fixtures/odds/historical', params, { game_key: match.game_key });
  if (!r.cached) {
    const odds = r.ok ? (r.data?.data?.data?.[0]?.odds || []) : [];
    const nEntries = odds.reduce((s, o) => s + (o.entries?.length || 0), 0);
    log(`${match.game_key} ${match.away_oo} @ ${match.home_oo}: ${r.ok ? 'ok' : 'ERR ' + String(r.error).slice(0, 100)} lines=${odds.length} entries=${nEntries} books=${[...new Set(odds.map(o => o.sportsbook))].join(',')}`);
  }
  return r;
}

export async function fetchMany(c, matches, opts = {}) {
  let calls = 0, cached = 0, errors = 0;
  for (const m of matches) {
    if (opts.maxCalls !== undefined && calls >= opts.maxCalls) break;
    const r = await fetchHistorical(c, m, opts);
    if (r.cached) cached++; else { calls++; if (!r.ok) errors++; }
  }
  return { calls, cached, errors, total: matches.length };
}
