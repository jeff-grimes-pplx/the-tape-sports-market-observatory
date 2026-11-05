// Enumerate completed OpticOdds fixtures for a league inside a window, paging with `page`.
// Dedupes by game_id, preferring the has_odds:true row.
export function compactFixture(f) {
  return {
    id: f.id, numerical_id: f.numerical_id, game_id: f.game_id, league: f.league?.id, sport: f.sport?.id,
    start_date: f.start_date, status: f.status, has_odds: f.has_odds, is_live: f.is_live,
    home: f.home_competitors?.map((t) => ({ id: t.id, name: t.name, abbreviation: t.abbreviation })) || [],
    away: f.away_competitors?.map((t) => ({ id: t.id, name: t.name, abbreviation: t.abbreviation })) || [],
    home_display: f.home_team_display, away_display: f.away_team_display,
    home_record: f.home_record, away_record: f.away_record, home_starter: f.home_starter, away_starter: f.away_starter,
    venue_name: f.venue_name, venue_location: f.venue_location, venue_neutral: f.venue_neutral,
    season_type: f.season_type, season_year: f.season_year, season_week: f.season_week,
    tournament: f.tournament?.name ?? f.tournament ?? null,
    result: f.result ? { home: f.result.scores?.home?.total ?? null, away: f.result.scores?.away?.total ?? null,
      home_periods: f.result.scores?.home?.periods ?? null, away_periods: f.result.scores?.away?.periods ?? null,
      period: f.result.in_play_data?.period ?? null } : null,
    weather: f.weather ?? null, weather_temp: f.weather_temp ?? null, broadcast: f.broadcast ?? null,
  };
}

export async function discoverLeague(c, { league, windowStart, windowEnd, maxPages = 12, log = () => {} }) {
  const rows = []; const pages = [];
  for (let page = 1; page <= maxPages; page++) {
    const params = { league, status: 'completed', start_date_after: windowStart, start_date_before: windowEnd };
    if (page > 1) params.page = page;
    const r = await c.opticodds('/fixtures', params);
    if (!r.ok) { pages.push({ page, ok: false, error: r.error }); log(`${league} page ${page} ERR ${r.error}`); break; }
    const d = r.data?.data || {};
    const data = d.data || [];
    pages.push({ page, ok: true, n: data.length, has_more: d.has_more ?? null, returned_page: d.page ?? null, cached: r.cached });
    log(`${league} page ${page}: n=${data.length} has_more=${d.has_more} returned_page=${d.page}${r.cached ? ' (cache)' : ''}`);
    for (const f of data) rows.push(compactFixture(f));
    if (!d.has_more || data.length === 0) break;
  }
  // dedupe by game_id preferring has_odds
  const byGame = new Map();
  for (const f of rows) {
    const k = f.game_id || f.id;
    const prev = byGame.get(k);
    if (!prev || (f.has_odds && !prev.has_odds)) byGame.set(k, f);
  }
  return { fixtures: [...byGame.values()], rawCount: rows.length, pages };
}
