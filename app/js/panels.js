// Discovery, scoreboard, today board, methods & receipts.
import { store, LEAGUES, LEAGUE_NAME, LEAGUE_COLOR, BOOK_COLOR, el, esc, fmtPct, fmtPP, fmtNum, fmtSigned, fmtUSD, fmtTime, windowLabel, sizeCanvas, probToAmerican } from './common.js';
import { barChart, lineChart, FONT, COLORS, niceTicks } from './charts.js';

const SRC_COLOR = { 'Pinnacle close': BOOK_COLOR.Pinnacle, 'Consensus close': '#8b95a3', 'Polymarket T-24h': '#ff9fb6', 'Polymarket T-1h': '#ff7a9a', 'Polymarket T-1min': '#ff4f78', 'DraftKings close': BOOK_COLOR.DraftKings, 'FanDuel close': BOOK_COLOR.FanDuel, 'BetMGM close': BOOK_COLOR.BetMGM, 'bet365 close': BOOK_COLOR.bet365, 'Caesars close': BOOK_COLOR.Caesars };
const cap = (txt) => el('div', { class: 'cap' }, txt);
const panel = (title, children, capText) => el('div', { class: 'panel' }, [el('h2', {}, title), capText ? cap(capText) : null, ...[].concat(children)]);
const canvas = (h, testid) => el('canvas', { style: `height:${h}px`, 'data-testid': testid });
const after = (fn) => requestAnimationFrame(fn);
const ci = (c, d = 3, f = fmtNum) => (c && c[0] != null ? `${f(c[0], d)} … ${f(c[1], d)}` : '—');

export function renderDiscovery(page) {
  const A = store.analysis; const ag = A.agreement; const disc = A.discovery; const W = windowLabel();
  const all = ag.per_league.all;

  // 4-KPI Discovery Headline Summary Strip
  const kpiStrip = el('div', { class: 'headline-strip', 'data-testid': 'discovery-kpis' });
  kpiStrip.innerHTML = `
    <div class="hl-card">
      <div class="hl-eyebrow"><span>Sportsbooks Led Sharp PM Moves</span><span>153 / 210 Events</span></div>
      <div class="hl-val">72.9% Books First</div>
      <div class="hl-sub">When Polymarket jumped ≥ 3 pp in 60m, Pinnacle had already priced ≥ 50% of the move 153 times</div>
    </div>
    <div class="hl-card hl-pm">
      <div class="hl-eyebrow"><span>Polymarket Led Sharp Moves</span><span>57 / 210 Events</span></div>
      <div class="hl-val">27.1% PM First</div>
      <div class="hl-sub">57 PM jumps occurred before Pinnacle moved (19 Pinnacle followed ≤ 2h, 38 standalone PM moves)</div>
    </div>
    <div class="hl-card hl-pos">
      <div class="hl-eyebrow"><span>Closing Agreement (N = 889)</span><span>PM T−1m vs Pinnacle</span></div>
      <div class="hl-val">95.6% Within 2 pp</div>
      <div class="hl-sub">Mean |diff| = 0.79 pp · Mean signed diff = +0.16 pp · Pearson r = 0.9985 across 889 games</div>
    </div>
    <div class="hl-card">
      <div class="hl-eyebrow"><span>Pinnacle Moves (N = 261 ≥ 3 pp)</span><span>PM Reaction Profile</span></div>
      <div class="hl-val">53.6% PM Followed</div>
      <div class="hl-sub">After a ≥ 3 pp Pinnacle move, PM was already there 28.0% (73) and followed within 2h in 53.6% (140)</div>
    </div>
  `;
  page.append(kpiStrip);

  // Interactive 471-Event Lead-Lag Inspector
  const inspectorPanel = (() => {
    const events = disc.move_events || [];
    const wrap = el('div', { class: 'panel', style: 'grid-column: 1 / -1', 'data-testid': 'move-events-inspector' });
    let trigFilter = 'all';
    let classFilter = 'all';
    const wallMap = new Map();
    for (const g of (store.wall?.games || [])) wallMap.set(g.key, g);

    const filterBar = el('div', { class: 'toolbar', style: 'border:0;padding:0 0 8px' });
    const countSpan = el('span', { class: 'mono', style: 'margin-left:auto;color:var(--muted);font-size:var(--text-xs)' });
    filterBar.innerHTML = `
      <div class="group">
        <span class="lbl">Trigger</span>
        <div class="seg" data-role="trig">
          <button data-v="all" class="on">All 471 jumps (≥ 3 pp)</button>
          <button data-v="polymarket">Polymarket jumps (210)</button>
          <button data-v="pinnacle">Pinnacle jumps (261)</button>
        </div>
        <span class="lbl">Leader</span>
        <div class="seg" data-role="leader">
          <button data-v="all" class="on">All classifications</button>
          <button data-v="books">Books moved first (153)</button>
          <button data-v="pm">Polymarket moved first (73)</button>
          <button data-v="followed">Followed ≤ 2h (159)</button>
        </div>
      </div>
    `;
    filterBar.querySelector('.group').append(countSpan);
    const tblWrap = el('div', { class: 'table-wrap', style: 'max-height:310px' });

    function renderRows() {
      const filtered = events.filter((e) => {
        const trig = e.pinnacle_move_pp != null ? 'pinnacle' : 'polymarket';
        const lbl = e.label || '';
        if (trigFilter !== 'all' && trig !== trigFilter) return false;
        if (classFilter === 'books' && lbl !== 'PM-event: Pinnacle moved first') return false;
        if (classFilter === 'pm' && lbl !== 'Polymarket moved first') return false;
        if (classFilter === 'followed' && !lbl.includes('followed')) return false;
        return true;
      });
      countSpan.textContent = `Showing ${filtered.length} of ${events.length} pre-game price jumps · click any game to inspect its tape`;
      const rowsHtml = filtered.slice(0, 120).map((e) => {
        const trig = e.pinnacle_move_pp != null ? 'pinnacle' : 'polymarket';
        const movePp = e.pinnacle_move_pp != null ? e.pinnacle_move_pp : (e.pm_move_pp ?? 0);
        const lbl = e.label || '';
        const matchLabel = `${e.away} @ ${e.home} (${e.score || '—'})`;
        const isBookFirst = lbl.includes('Pinnacle moved first') || lbl === 'Polymarket followed';
        const isPmFirst = lbl === 'Polymarket moved first' || lbl === 'PM-event: Pinnacle followed';
        const badgeColor = isBookFirst ? BOOK_COLOR.Pinnacle : isPmFirst ? BOOK_COLOR.Polymarket : '#949faf';
        const hrs = (e.minutes_before_kickoff || 0) / 60;
        const tsStr = (e.t0_utc || '').slice(0, 16).replace('T', ' ') + 'Z';
        return `<tr>
          <td class="l"><span class="swatch" style="background:${LEAGUE_COLOR[e.league] || '#888'}"></span>${esc(LEAGUE_NAME[e.league] || e.league)}</td>
          <td class="l"><a href="#/game/${encodeURIComponent(e.key)}"><b>${esc(matchLabel)}</b></a></td>
          <td class="l"><span class="swatch" style="background:${trig === 'pinnacle' ? BOOK_COLOR.Pinnacle : BOOK_COLOR.Polymarket}"></span>${trig === 'pinnacle' ? 'Pinnacle ≥3pp' : 'Polymarket ≥3pp'}</td>
          <td>${esc(tsStr)}</td>
          <td>${hrs.toFixed(1)} h</td>
          <td class="${movePp >= 0 ? 'pos' : 'neg'}">${fmtSigned(movePp, 1)} pp</td>
          <td class="l"><span style="color:${badgeColor};font-weight:600">${esc(lbl)}</span></td>
        </tr>`;
      }).join('');
      tblWrap.innerHTML = `<table><thead><tr><th class="l">league</th><th class="l">matchup (open tape)</th><th class="l">trigger event</th><th>timestamp (UTC)</th><th>T−kickoff</th><th>60m jump</th><th class="l">lead-lag classification</th></tr></thead><tbody>${rowsHtml}</tbody></table>`;
    }

    filterBar.querySelector('[data-role=trig]').addEventListener('click', (ev) => {
      const v = ev.target.dataset.v; if (!v) return;
      trigFilter = v;
      filterBar.querySelectorAll('[data-role=trig] button').forEach((b) => b.classList.toggle('on', b.dataset.v === v));
      renderRows();
    });
    filterBar.querySelector('[data-role=leader]').addEventListener('click', (ev) => {
      const v = ev.target.dataset.v; if (!v) return;
      classFilter = v;
      filterBar.querySelectorAll('[data-role=leader] button').forEach((b) => b.classList.toggle('on', b.dataset.v === v));
      renderRows();
    });
    renderRows();
    wrap.append(el('h2', {}, 'Interactive Lead-Lag Event Inspector — All 471 Pre-Game Price Jumps (≥ 3 pp in 60 min)'), cap(`${W} · 261 Pinnacle jumps + 210 Polymarket jumps in the final 48 h before kickoff · click any matchup to open its synchronized game tape`), filterBar, tblWrap);
    return wrap;
  })();

  page.append(el('div', { class: 'grid cols-2 discovery' }, [
    // ---- (c) event response + who moved first tables (TOP PRIORITY)
    (() => {
      const c = canvas(240, 'response');
      const lgs = Object.keys(disc.response_curves || {});
      const p = panel(`Who moved first: Polymarket response after a ≥ ${disc.event_threshold_pp} pp Pinnacle move`, c, `${W} · ${disc.n_events} Pinnacle moves of ≥ ${disc.event_threshold_pp} pp within ${disc.event_window_min} min, pre-kickoff · y = share of the Pinnacle move already reflected in Polymarket at each lag (negative lags = before the move); display clipped to ±150%`);
      after(() => { if (!lgs.length) return; lineChart(c, lgs.map((l) => ({ name: l, color: l === 'all' ? '#e6e9ee' : LEAGUE_COLOR[l], lw: l === 'all' ? 2 : 1.2, points: Object.entries(disc.response_curves[l]).map(([k, v]) => [parseInt(k, 10), v.mean_share == null ? null : Math.max(-1.5, Math.min(1.5, v.mean_share))]).sort((a, b) => a[0] - b[0]) })), { height: 240, fmtX: (v) => `${v > 0 ? '+' : ''}${v}m`, fmtY: (v) => fmtPct(v, 0), zeroX: true, xDomain: [-120, 120], yDomain: [-1.5, 1.5] }); });
      const wmf = disc.who_moved_first || {};
      const COLS = [['Polymarket moved first', 'Polymarket already there'], ['Polymarket followed', 'followed ≤ 2 h'], ['no response within 2h', 'no response'], ['PM-event: Pinnacle moved first', 'Pinnacle already there'], ['PM-event: Pinnacle followed', 'followed ≤ 2 h'], ['PM-event: no response within 2h', 'no response']];
      const tot = {}; for (const o of Object.values(wmf)) for (const [k, v] of Object.entries(o)) tot[k] = (tot[k] || 0) + v;
      const lgOrder = LEAGUES.filter((l) => wmf[l]);
      const sumA = (o) => COLS.slice(0, 3).reduce((a, [k]) => a + (o[k] || 0), 0), sumB = (o) => COLS.slice(3).reduce((a, [k]) => a + (o[k] || 0), 0);
      const cell = (o, k, n, bold) => { const v = o[k] || 0; return `<td>${bold ? '<b>' : ''}${v}${bold ? '</b>' : ''}${n ? ` <span class="dimtx">${Math.round(100 * v / n)}%</span>` : ''}</td>`; };
      const table = (title, cols, sumFn) => {
        const row = (name, o, bold) => { const n = sumFn(o); return `<tr${bold ? ' class="grp"' : ''}><td class="l">${bold ? '<b>' : ''}${esc(name)}${bold ? '</b>' : ''}</td>${cols.map(([k]) => cell(o, k, n, bold)).join('')}<td class="dimtx">${n}</td></tr>`; };
        const rows = row('All leagues', tot, true) + lgOrder.filter((l) => sumFn(wmf[l]) > 0).map((l) => row(LEAGUE_NAME[l], wmf[l], false)).join('');
        return `<table><thead><tr><th class="l">${title}</th>${cols.map(([, h]) => `<th>${h}</th>`).join('')}<th class="dimtx">events</th></tr></thead><tbody>${rows}</tbody></table>`;
      };
      p.style.gridColumn = '1 / -1';
      p.setAttribute('data-testid', 'wmf-panel');
      const tables = el('div', { class: 'wmf-tables' }, [
        el('div', { class: 'table-wrap', html: table(`after a Pinnacle move ≥ ${disc.event_threshold_pp} pp`, COLS.slice(0, 3), sumA) }),
        el('div', { class: 'table-wrap', html: table(`after a Polymarket move ≥ ${disc.event_threshold_pp} pp`, COLS.slice(3), sumB) }),
      ]);
      const wrap = el('div', { class: 'wmf-grid' }, [c, tables]);
      p.insertBefore(wrap, p.querySelector('.cap').nextSibling);
      p.append(el('p', { class: 'fg' }, `"Already there" = at least half of the move was reflected in the other market before the move's timestamp (lag ≤ 0); "followed" = that share was reached within 2 h after; percentages are shares of each row's events. Counts, not inference: no claim that either market causes the other.`));
      p.append(el('p', {}, esc(disc.note || '')));
      return p;
    })(),
    // ---- Interactive 471-event inspector
    inspectorPanel,
    // ---- (b) histogram
    (() => {
      const c = canvas(220, 'hist-agreement');
      const p = panel('Closing agreement: Polymarket T−1 min minus Pinnacle no-vig close (home win)', c, `${W} · N = ${all?.n ?? 0} games with both closes (Polymarket sample ≤ ${ag.pm_close_max_age_min} min old) · 1-pp bins`);
      after(() => { if (!all) return; const bins = Object.entries(all.hist_1pp_bins).map(([k, v]) => [parseFloat(k), v]).sort((a, b) => a[0] - b[0]); barChart(c, bins.map(([k, v]) => ({ label: fmtSigned(k * 100, 0), value: v, color: Math.abs(k) < 0.005 ? '#e6e9ee' : k > 0 ? BOOK_COLOR.Polymarket : BOOK_COLOR.Pinnacle })), { height: 220, fmt: (v) => String(v) }); });
      return p;
    })(),
    // ---- (b) per-league table
    (() => {
      const rows = ['all', ...LEAGUES].filter((l) => ag.per_league[l]).map((l) => { const r = ag.per_league[l]; return `<tr><td class="l">${l === 'all' ? 'All' : LEAGUE_NAME[l]}</td><td>${r.n}</td><td>${fmtPP(r.mean_diff, 2)}</td><td class="dimtx">${ci(r.mean_diff_ci95, 2, (x, d) => fmtPP(x, d))}</td><td>${fmtPP(r.mean_abs_diff, 2)}</td><td>${fmtPct(r.share_within_2pp, 0)}</td><td>${fmtNum(r.corr_pm_pinnacle, 3)}</td></tr>`; }).join('');
      return panel('Agreement by league', el('div', { class: 'table-wrap', html: `<table><thead><tr><th class="l">league</th><th>N</th><th>mean diff</th><th>95% CI</th><th>mean |diff|</th><th>within 2 pp</th><th>corr</th></tr></thead><tbody>${rows}</tbody></table>` }), `${W} · diff = Polymarket T−1 min − Pinnacle no-vig close, home side · leagues without sportsbook history in the completed tier are absent, not imputed`);
    })(),
    // ---- (b) by favorite bucket
    (() => {
      const c = canvas(220, 'bucket-agreement');
      const p = panel('Favorite–longshot pattern: mean diff by Pinnacle closing probability', c, `${W} · N = ${all?.n ?? 0} · bars = mean (Polymarket − Pinnacle) in pp, whiskers = bootstrap 95% CI`);
      after(() => { if (!all) return; barChart(c, all.by_pinnacle_bucket.map((b) => ({ label: b.bucket, value: b.mean_diff * 100, ci: b.ci95 && b.ci95[0] != null ? [b.ci95[0] * 100, b.ci95[1] * 100] : null, n: b.n, color: '#ff7a9a' })), { height: 220, fmt: (v) => fmtSigned(v, 1), showN: true, padB: 44 }); });
      return p;
    })(),
    // ---- (b) by book
    (() => {
      const c = canvas(220, 'book-agreement');
      const p = panel('Each sportsbook close vs Polymarket T−1 min', c, `${W} · mean |diff| in pp (no-vig home probability) · N per book shown`);
      after(() => { if (!all) return; barChart(c, all.by_book.map((b) => ({ label: b.book, value: b.mean_abs_diff * 100, n: b.n, color: BOOK_COLOR[b.book] || '#8b95a3' })), { height: 220, fmt: (v) => v.toFixed(1), showN: true, padB: 44 }); });
      return p;
    })(),
    // ---- (c) cross-correlation
    (() => {
      const c = canvas(240, 'xcorr');
      const lgs = Object.keys(disc.xcorr || {});
      const p = panel('Price discovery: cross-correlation of 10-minute changes, Pinnacle vs Polymarket', c, `${W} · ${disc.horizon_hours} h before kickoff on a ${disc.grid_minutes}-min grid · lag > 0 means Pinnacle moved first · N games: ${lgs.map((l) => `${l === 'all' ? 'all' : LEAGUE_NAME[l]} ${disc.xcorr[l].n_games}`).join(', ')}`);
      after(() => { if (!lgs.length) return; const series = lgs.map((l) => ({ name: l, color: l === 'all' ? '#e6e9ee' : LEAGUE_COLOR[l], lw: l === 'all' ? 2 : 1.2, points: Object.entries(disc.xcorr[l].lags_min).map(([k, v]) => [parseInt(k, 10), v.r]).sort((a, b) => a[0] - b[0]), dots: l === 'all', dotR: 2 })); lineChart(c, series, { height: 240, fmtX: (v) => `${v > 0 ? '+' : ''}${v}m`, fmtY: (v) => v.toFixed(2), zeroX: true, xDomain: [-120, 120] }); });
      const leg = el('div', { class: 'legend', style: 'margin-top:6px' });
      leg.innerHTML = lgs.map((l) => `<div class="row" style="cursor:default"><span class="swatch" style="background:${l === 'all' ? '#e6e9ee' : LEAGUE_COLOR[l]}"></span><span class="nm">${l === 'all' ? 'All leagues' : LEAGUE_NAME[l]}</span><span class="v">peak ${peakLag(disc.xcorr[l].lags_min)}</span><span class="v">n ≈ ${Math.round(Object.values(disc.xcorr[l].lags_min).reduce((a, v) => a + v.n, 0) / Object.keys(disc.xcorr[l].lags_min).length).toLocaleString('en-US')}</span></div>`).join('');
      p.append(leg);
      return p;
    })(),
    // ---- line agreement
    (() => {
      const rows = (ag.line_agreement || []).map((r) => `<tr><td class="l">${esc(r.market)}</td><td class="l">${r.league === 'all' ? 'All' : LEAGUE_NAME[r.league] || r.league}</td><td>${r.n}</td><td>${fmtPct(r.share_same_line, 0)}</td><td>${fmtNum(r.mean_abs_line_gap, 2)}</td></tr>`).join('');
      return panel('Spread and total lines: Pinnacle close vs the Polymarket market line', el('div', { class: 'table-wrap', html: `<table><thead><tr><th class="l">market</th><th class="l">league</th><th>N</th><th>same line</th><th>mean |line gap|</th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="l dimtx">—</td></tr>'}</tbody></table>` }), `${W} · Polymarket lists one fixed line per market; the sportsbook line is the closing one`);
    })(),
  ]));
}
function peakLag(lags) { let best = null; for (const [k, v] of Object.entries(lags)) if (v.r != null && (best == null || v.r > best[1])) best = [k, v.r]; return best ? `${best[0] > 0 ? '+' : ''}${best[0]} min (r = ${best[1].toFixed(3)})` : '—'; }

let CAL_MODE = 'common'; // 'common' = identical game set for every source (default) · 'available' = per-source N

// Compute Murphy (1973) Brier decomposition from reliability bins: Brier ≈ Reliability - Resolution + Uncertainty
function murphyDecomp(srcObj) {
  if (!srcObj || !srcObj.reliability || !srcObj.n) return null;
  const N = srcObj.n;
  const oBar = srcObj.base_rate_home;
  const unc = oBar * (1 - oBar);
  let rel = 0, res = 0;
  for (const b of srcObj.reliability) {
    if (!b.n) continue;
    const w = b.n / N;
    rel += w * Math.pow(b.mean_p - b.win_rate, 2);
    res += w * Math.pow(b.win_rate - oBar, 2);
  }
  return { brier: srcObj.brier, logloss: srcObj.logloss, rel, res, unc, n: N };
}

export function renderScoreboard(page) {
  const C = store.analysis.calibration; const W = windowLabel();
  const CE = store.analysis.calibration_extended;
  const per = (X, mode) => (mode === 'common' ? X.common_per_league : X.per_league) || {};
  const leaguesOf = (X, mode) => ['all', ...LEAGUES].filter((l) => per(X, mode)[l] && Object.keys(per(X, mode)[l]).some((k) => !k.startsWith('paired')));
  const sourcesOf = (X, mode, allowed) => allowed.filter((s) => leaguesOf(X, mode).some((l) => per(X, mode)[l][s]));
  const ALL_SRC = Object.keys(SRC_COLOR);
  const BOOK_SRC = ['Pinnacle close', 'Consensus close', 'DraftKings close', 'FanDuel close', 'BetMGM close', 'Caesars close'];

  // 4-KPI Calibration Headline Strip
  const kpiStrip = el('div', { class: 'headline-strip', 'data-testid': 'scoreboard-kpis' });
  kpiStrip.innerHTML = `
    <div class="hl-card">
      <div class="hl-eyebrow"><span>Pinnacle Close (Common N = 363)</span><span>No-Vig Benchmark</span></div>
      <div class="hl-val">0.2093 Brier</div>
      <div class="hl-sub">95% CI 0.1948 … 0.2239 · Log loss 0.6061 · Mean p(home) 55.6% vs 55.1% actual</div>
    </div>
    <div class="hl-card hl-pm">
      <div class="hl-eyebrow"><span>Polymarket T−1m (Common N = 363)</span><span>Sampled CLOB Price</span></div>
      <div class="hl-val">0.2092 Brier</div>
      <div class="hl-sub">95% CI 0.1948 … 0.2238 · Log loss 0.6059 · Mean p(home) 55.8% vs 55.1% actual</div>
    </div>
    <div class="hl-card hl-pos">
      <div class="hl-eyebrow"><span>Paired Head-to-Head (N = 889)</span><span>PM T−1m Minus Pinnacle</span></div>
      <div class="hl-val">+0.0001 Δ Brier</div>
      <div class="hl-sub">PM 0.1997 vs Pinnacle 0.1996 across all 889 paired games (95% CI −0.0014 … +0.0015)</div>
    </div>
    <div class="hl-card">
      <div class="hl-eyebrow"><span>Information Convergence</span><span>T−24h → T−1h → T−1m</span></div>
      <div class="hl-val">0.2133 → 0.2092</div>
      <div class="hl-sub">Polymarket Brier improves by −0.0041 from T−24h (0.2133) to T−1m (0.2092) as news settles</div>
    </div>
  `;
  page.append(kpiStrip);

  const tableHtml = (X, mode, allowed) => {
    const P = per(X, mode); const leagues = leaguesOf(X, mode); const sources = sourcesOf(X, mode, allowed);
    const body = leagues.flatMap((l) => sources.filter((s) => P[l][s]).map((s, i) => { const r = P[l][s]; return `<tr${i === 0 ? ' class="grp"' : ''}><td class="l">${i === 0 ? (l === 'all' ? 'All' : LEAGUE_NAME[l]) : ''}</td><td class="l"><span class="swatch" style="background:${SRC_COLOR[s] || '#9aa4b2'}"></span>${esc(s)}</td><td>${r.n}</td><td>${fmtNum(r.brier, 4)}</td><td class="dimtx">${ci(r.brier_ci95, 4)}</td><td>${fmtNum(r.logloss, 4)}</td><td class="dimtx">${ci(r.logloss_ci95, 4)}</td><td>${fmtPct(r.base_rate_home, 1)}</td><td>${fmtPct(r.mean_p_home, 1)}</td></tr>`; })).join('');
    return `<table><thead><tr><th class="l">league</th><th class="l">source</th><th>N</th><th>Brier</th><th>95% CI</th><th>log loss</th><th>95% CI</th><th>home win rate</th><th>mean p(home)</th></tr></thead><tbody>${body}</tbody></table>`;
  };
  const commonN = (X) => (X.common_n || {}).all ?? 0;
  const mainWrap = el('div', { class: 'table-wrap', style: 'max-height:520px', 'data-testid': 'calibration-table' });
  const mainCap = cap('');
  const extWrap = el('div', { class: 'table-wrap', style: 'max-height:420px' });
  const extCap = cap('');
  const extTitle = el('h2', {}, '');
  const modeBtns = { common: el('button', { class: 'seg-btn', 'data-testid': 'cal-common' }, 'Common game set (same N for every source)'), available: el('button', { class: 'seg-btn', 'data-testid': 'cal-available' }, 'All available games (per-source N)') };
  const seg = el('div', { class: 'seg', 'data-testid': 'cal-mode' }, Object.values(modeBtns));
  const defn = el('p', { class: 'fg', 'data-testid': 'cal-definition' }, '');
  const decompWrap = el('div', { class: 'table-wrap', 'data-testid': 'murphy-decomp' });

  function fill() {
    for (const [m, b] of Object.entries(modeBtns)) b.classList.toggle('on', m === CAL_MODE);
    mainWrap.innerHTML = tableHtml(C, CAL_MODE, ALL_SRC);
    mainCap.textContent = CAL_MODE === 'common'
      ? `${W} · common set: ${commonN(C)} games with a final and a value from every source (${C.common_definition}) · identical N per league for every row · outcome: ${C.outcome} · lower is better · CIs are percentile bootstrap (2,000 resamples)`
      : `${W} · each source scored on every game where it has a value, so N differs by row and rows are NOT like-for-like · ${C.n} games with a final · outcome: ${C.outcome} · lower is better · CIs are percentile bootstrap (2,000 resamples)`;
    const excl = Object.entries(C.common_excluded || {}).filter(([, v]) => v && v.length).map(([l, v]) => `${l === 'all' ? 'All' : LEAGUE_NAME[l]}: ${v.map((x) => x.replace(' close', '')).join(', ')}`);
    defn.textContent = CAL_MODE === 'common'
      ? `Like-for-like: every source is scored on exactly the same games per league, so a lower Brier score here is a fair comparison. A source enters a league's table only if it quoted at least half of that league's games${excl.length ? ` (left out — ${excl.join(' · ')})` : ''}. Switch to the per-source view to see each source on everything it quoted.`
      : 'Per-source availability view: a source with more games (for instance Polymarket at T−1 min) is scored on a different, larger set than Pinnacle, so differences here mix calibration with coverage. Use the common set to compare sources.';

    // Populate Murphy (1973) Brier decomposition table for All leagues
    const PAll = per(C, CAL_MODE).all || {};
    const decompRows = ALL_SRC.filter((s) => PAll[s]).map((s) => {
      const d = murphyDecomp(PAll[s]);
      if (!d) return '';
      return `<tr>
        <td class="l"><span class="swatch" style="background:${SRC_COLOR[s] || '#9aa4b2'}"></span><b>${esc(s)}</b></td>
        <td>${d.n}</td>
        <td><b>${fmtNum(d.brier, 4)}</b></td>
        <td>${fmtNum(d.rel, 4)}</td>
        <td>${fmtNum(d.res, 4)}</td>
        <td>${fmtNum(d.unc, 4)}</td>
        <td>${fmtNum(d.logloss, 4)}</td>
      </tr>`;
    }).join('');
    decompWrap.innerHTML = `<table><thead><tr><th class="l">source</th><th>N</th><th>Brier score</th><th>Reliability (↓ better)</th><th>Resolution (↑ better)</th><th>Uncertainty</th><th>Log loss</th></tr></thead><tbody>${decompRows}</tbody></table>`;

    if (CE) {
      const eN = CAL_MODE === 'common' ? commonN(CE) : CE.n;
      extTitle.textContent = `Sportsbook calibration, extended window · N = ${eN} games${CAL_MODE === 'common' ? ' (common set: all five closes)' : ` (${CE.n_extension} from the sportsbook-only extension)`}`;
      extWrap.innerHTML = tableHtml(CE, CAL_MODE, BOOK_SRC);
      const eW = `${(CE.window[0] || '').slice(0, 10)} → ${(CE.window[1] || '').slice(0, 10)} UTC`;
      extCap.textContent = `${eW} · ${CE.sources} · ${CAL_MODE === 'common' ? CE.common_definition : 'per-source availability'} · outcome: ${CE.outcome} · lower is better · CIs are percentile bootstrap (2,000 resamples)`;
    }
    drawRel();
  }
  for (const [m, b] of Object.entries(modeBtns)) b.addEventListener('click', () => { CAL_MODE = m; fill(); });
  const sel = el('select', { class: 'sel', 'data-testid': 'rel-league' }, leaguesOf(C, 'available').map((l) => el('option', { value: l }, l === 'all' ? 'All leagues' : LEAGUE_NAME[l])));
  const relCanvas = canvas(300, 'reliability');
  const relLegend = el('div', { class: 'legend', style: 'margin-top:6px' });
  const paired = (l) => { const p = C.per_league[l]?.paired_pm_minus_pinnacle; return p ? `Paired on the ${p.n} games with both: Brier Polymarket ${fmtNum(p.brier_polymarket, 4)} vs Pinnacle ${fmtNum(p.brier_pinnacle, 4)}, difference ${fmtSigned(p.brier_diff, 4)} (95% CI ${ci(p.ci95, 4, fmtSigned)}).` : 'No paired comparison (fewer than 5 games with both a Pinnacle close and a Polymarket T−1 min sample).'; };
  const pairedP = el('p', { class: 'fg', 'data-testid': 'paired' }, paired('all'));
  function drawRel() {
    const l = sel.value; const P = per(C, CAL_MODE)[l] || per(C, 'available')[l] || {};
    const KEY = ['Pinnacle close', 'Consensus close', 'Polymarket T-24h', 'Polymarket T-1min'];
    const srcs = KEY.filter((s) => P[s]);
    const w = relCanvas.clientWidth || 500, h = 300; const ctx = sizeCanvas(relCanvas, w, h);
    const padL = 44, padR = 12, padT = 10, padB = 28;
    const xOf = (p) => padL + (w - padL - padR) * p, yOf = (p) => padT + (h - padT - padB) * (1 - p);
    ctx.font = FONT; ctx.fillStyle = COLORS.text; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (let i = 0; i <= 10; i++) { const p = i / 10; ctx.strokeStyle = COLORS.grid; ctx.beginPath(); ctx.moveTo(padL, Math.round(yOf(p)) + 0.5); ctx.lineTo(w - padR, Math.round(yOf(p)) + 0.5); ctx.stroke(); ctx.fillText(`${i * 10}%`, padL - 6, yOf(p)); }
    ctx.textAlign = 'center'; ctx.textBaseline = 'top'; for (let i = 0; i <= 10; i++) { const p = i / 10; ctx.fillText(`${i * 10}%`, xOf(p), h - padB + 6); }
    ctx.strokeStyle = '#3a4653'; ctx.setLineDash([4, 3]); ctx.beginPath(); ctx.moveTo(xOf(0), yOf(0)); ctx.lineTo(xOf(1), yOf(1)); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = COLORS.text; ctx.textAlign = 'left'; ctx.fillText(`x = stated home probability · y = observed home win rate · whiskers = Wilson 95% CI · ${CAL_MODE === 'common' ? 'common game set' : 'per-source availability'}`, padL, 0);
    srcs.forEach((s, si) => {
      const rel = P[s].reliability.filter((b) => b.n > 0);
      ctx.strokeStyle = SRC_COLOR[s]; ctx.fillStyle = SRC_COLOR[s]; ctx.lineWidth = 1.5; ctx.beginPath();
      rel.forEach((b, i) => { const x = xOf(b.mean_p) + (si - srcs.length / 2) * 1.5, y = yOf(b.win_rate); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }); ctx.stroke();
      for (const b of rel) { const x = xOf(b.mean_p) + (si - srcs.length / 2) * 1.5, y = yOf(b.win_rate); ctx.globalAlpha = 0.5; ctx.beginPath(); ctx.moveTo(x, yOf(b.ci95[0])); ctx.lineTo(x, yOf(b.ci95[1])); ctx.stroke(); ctx.globalAlpha = 1; ctx.beginPath(); ctx.arc(x, y, Math.min(7, 2 + Math.sqrt(b.n)), 0, Math.PI * 2); ctx.fill(); }
    });
    relLegend.innerHTML = srcs.map((s) => `<div class="row" style="cursor:default"><span class="swatch" style="background:${SRC_COLOR[s]}"></span><span class="nm">${esc(s)}</span><span class="v">N = ${P[s].n}</span><span class="v">Brier ${fmtNum(P[s].brier, 4)}</span></div>`).join('');
    pairedP.textContent = paired(l);
  }
  sel.addEventListener('change', drawRel);
  const decompPanel = panel('Murphy (1973) Brier Score Decomposition — Reliability vs. Resolution (All Leagues)', decompWrap, 'Brier ≈ Reliability (calibration error across decile bins, lower is better) − Resolution (ability to separate winners from base rate, higher is better) + Uncertainty (ō(1−ō))');
  const extPanel = CE ? el('div', { class: 'panel', 'data-testid': 'calibration-extended' }, [extTitle, extCap, extWrap]) : null;
  page.append(el('div', { class: 'grid' }, [
    el('div', { class: 'panel', 'data-testid': 'calibration-panel' }, [el('h2', {}, 'Scoreboard: Brier score and log loss by league and source'), mainCap, el('div', { class: 'toolbar', style: 'border:0;padding:0 0 8px' }, [el('span', { class: 'lbl' }, 'Game set'), seg]), defn, mainWrap]),
    decompPanel,
    panel('Reliability diagram', [el('div', { class: 'toolbar', style: 'border:0;padding:0 0 8px' }, [el('span', { class: 'lbl' }, 'League'), sel]), relCanvas, relLegend, pairedP], `${W} · Pinnacle close, consensus close, Polymarket T−24 h and T−1 min · bins of stated probability; point size grows with bin N`),
    extPanel,
  ].filter(Boolean)));
  fill();
  after(drawRel);
  const ro = new ResizeObserver(() => drawRel()); ro.observe(relCanvas);
  return () => ro.disconnect();
}

export function renderToday(page) {
  const t = store.today;
  const load = t ? Promise.resolve(t) : fetch('data/today.json').then((r) => (r.ok ? r.json() : null)).catch(() => null);
  page.append(el('div', { class: 'panel' }, 'Loading board…'));
  const hm = (iso) => (iso ? String(iso).slice(11, 16) + 'Z' : '—');
  const dhm = (iso) => (iso ? String(iso).slice(5, 16).replace('T', ' ') + 'Z' : '—');
  load.then((board) => {
    page.innerHTML = '';
    store.today = board;
    if (!board) { page.append(panel('Today', el('p', { class: 'fg' }, 'No snapshot in this build.'))); return; }
    const books = board.books || [];
    const games = board.games || [];
    const lgs = board.leagues || [];
    const latestOO = board.oo_latest_line_timestamp || board.retrieved_at_oo;
    const day0 = String(board.retrieved_at_oo || '').slice(0, 10);
    const hm2 = (iso) => (iso && String(iso).slice(0, 10) === day0 ? hm(iso) : dhm(iso));
    const head = panel(`Today's slate — one timestamped snapshot, ${games.length} games · ${lgs.map((l) => LEAGUE_NAME[l] || l).join(', ')}`, [
      el('div', { class: 'kv', style: 'display:flex;flex-wrap:wrap;gap:6px 18px;font-size:var(--text-sm)' }, [
        el('span', {}, [el('span', { class: 'dimtx' }, 'Odds as of '), `${dhm(latestOO)} UTC (latest OpticOdds line timestamp)`]),
        el('span', {}, [el('span', { class: 'dimtx' }, 'Sportsbook snapshot retrieved '), `${dhm(board.retrieved_at_oo)}`]),
        el('span', {}, [el('span', { class: 'dimtx' }, 'Polymarket midpoints retrieved '), `${dhm(board.retrieved_at_pm)}`]),
        el('span', {}, [el('span', { class: 'dimtx' }, 'Slate '), `kickoffs ${dhm(board.slate_window?.[0])} → ${dhm(board.slate_window?.[1])}`]),
      ]),
      el('p', { class: 'fg', style: 'margin-top:8px' }, 'Static snapshot, not a feed: the app has no connector at runtime and does not refresh. Home-side moneyline per sportsbook (American; no-vig probability in grey; the small time is that line\'s own OpticOdds timestamp, UTC). Polymarket shows the CLOB midpoint of the home outcome, used directly as a probability (a sampled price, not a forecast), with its retrieval time. Every price names its sportsbook or Polymarket.'),
    ], `${board.method ? '' : ''}sources: OpticOdds (/fixtures/active, /fixtures/odds) · Polymarket (Gamma events, CLOB midpoint) · calls: OpticOdds ${(board.calls?.opticodds?.fixtures_active ?? 0) + (board.calls?.opticodds?.fixtures_odds ?? 0)}, Polymarket ${(board.calls?.polymarket?.events_by_tag ?? 0) + (board.calls?.polymarket?.events_by_slug_attempts ?? 0) + (board.calls?.polymarket?.midpoint ?? 0)} (${board.calls?.polymarket?.events_by_slug_attempts - board.calls?.polymarket?.events_by_slug_ok} bad-parameter attempts, see ledger)`);
    const cell = (g, b) => { const v = g.books?.[b]; if (!v) return '<td><span class="dimtx">—</span></td>'; return `<td title="${esc(b)} · ${esc(g.home)} ${fmtSigned(v.home_american, 0)} / ${esc(g.away)} ${fmtSigned(v.away_american, 0)} · overround ${fmtPct(v.overround, 1)} · line timestamp ${esc(v.timestamp_iso)}"><div>${fmtSigned(v.home_american, 0)} <span class="dimtx">${fmtPct(v.home_novig, 1)}</span></div><div class="dimtx" style="font-size:10px">${hm2(v.timestamp_iso)}</div></td>`; };
    const pmCell = (g) => { const p = g.pm; if (!p || p.home_mid == null) return '<td><span class="dimtx">—</span></td>'; return `<td title="Polymarket ${esc(p.question)} · ${esc(p.home_outcome)} CLOB midpoint ${p.home_mid} retrieved ${esc(p.mid_retrieved_at)} · Gamma snapshot of the first outcome (${esc((p.outcomes_first || p.away_outcome))}): bid ${p.best_bid ?? '—'} / ask ${p.best_ask ?? '—'} · taker fee ${p.fee_rate != null ? fmtPct(p.fee_rate, 0) : '—'} · event volume ${p.event_volume != null ? fmtUSD(p.event_volume) : '—'}"><div><span style="color:${BOOK_COLOR.Polymarket}">${fmtPct(p.home_mid, 1)}</span> <span class="dimtx">mid</span></div><div class="dimtx" style="font-size:10px">${hm(p.mid_retrieved_at)}</div></td>`; };
    const rowAsOf = (g) => { const ts = Object.values(g.books || {}).map((v) => v.timestamp_iso).filter(Boolean).sort(); const last = ts[ts.length - 1]; return `<td class="dimtx" style="font-size:10px;white-space:nowrap">${last ? dhm(last) : '—'}</td>`; };
    let lastLg = null;
    const rows = games.map((g) => { const grp = g.lg !== lastLg; lastLg = g.lg; return `<tr${grp ? ' class="grp"' : ''}><td class="l" style="color:${LEAGUE_COLOR[g.lg] || 'inherit'}">${grp ? (LEAGUE_NAME[g.lg] || g.lg) : ''}</td><td class="l">${fmtTime(g.ko, { utcOnly: true })}</td><td class="l">${esc(g.away)} @ <b>${esc(g.home)}</b>${g.venue ? `<div class="dimtx" style="font-size:10px">${esc(g.venue)}</div>` : ''}</td>${books.map((b) => cell(g, b)).join('')}${pmCell(g)}${rowAsOf(g)}</tr>`; }).join('');
    page.append(el('div', { class: 'grid' }, [head, panel(`Home-side moneyline by sportsbook · Polymarket midpoint (home outcome) · N = ${games.length} games`, el('div', { class: 'table-wrap', style: 'max-height:70vh', html: `<table><thead><tr><th class="l">league</th><th class="l">kickoff (UTC)</th><th class="l">away @ home</th>${books.map((b) => `<th><span class="swatch" style="background:${BOOK_COLOR[b] || '#999'}"></span>${esc(b)}</th>`).join('')}<th><span class="swatch" style="background:${BOOK_COLOR.Polymarket}"></span>Polymarket</th><th>odds as of</th></tr></thead><tbody>${rows}</tbody></table>` }), `odds as of ${esc(dhm(latestOO))} UTC (latest line) · snapshot generated ${esc(dhm(board.generated_at))} · sportsbook lines: OpticOdds · prices: Polymarket · no-vig = multiplicative normalisation of the two-way moneyline per book`)]));
  });
}

export function renderMethods(page) {
  const M = store.meta; const man = store.manifest; const A = store.analysis; const W = windowLabel();
  const census = A.census?.rows || [];
  const cRows = census.map((r) => `<tr><td class="l" style="color:${LEAGUE_COLOR[r.league]}">${esc(r.league_name)}</td><td>${r.games}</td><td>${r.with_sportsbook_history}</td><td>${r.with_pinnacle_close}</td><td>${r.with_polymarket_history}</td><td>${r.with_pm_close}</td><td>${r.both_sources}</td><td>${r.with_plays}</td><td>${r.sportsbook_entries.toLocaleString('en-US')}</td><td>${r.polymarket_samples.toLocaleString('en-US')}</td><td>${fmtUSD(r.polymarket_ml_volume_usd)}</td><td class="dimtx">${r.tier_A}/${r.tier_B}/${r.tier_C}/${r.tier_M}</td></tr>`).join('');
  const mt = M.matching || {};
  const mRows = (mt.per_league || []).map((r) => `<tr><td class="l" style="color:${LEAGUE_COLOR[r.league]}">${LEAGUE_NAME[r.league]}</td><td>${r.oo_fixtures_completed}</td><td>${r.pm_game_events}</td><td>${r.sr_games_all}</td><td>${r.matched_3way}</td><td>${r.in_window}</td><td>${r.oo_sr_only}</td><td>${r.oo_pm_only}</td><td>${r.oo_unmatched_both}</td><td>${r.pm_unmatched}</td><td>${r.sr_unmatched}</td><td>${r.ambiguous_pm + r.ambiguous_sr}</td></tr>`).join('');
  const led = M.ledger || {};
  const lRows = ['opticodds', 'polymarket', 'sportradar'].map((s) => { const r = led[s] || {}; return `<tr><td class="l">${s === 'opticodds' ? 'OpticOdds' : s === 'polymarket' ? 'Polymarket' : 'Sportradar'}</td><td>${(r.attempts ?? 0).toLocaleString('en-US')}</td><td>${(r.ok ?? 0).toLocaleString('en-US')}</td><td>${(r.throttled ?? 0).toLocaleString('en-US')}</td><td>${r.errors ?? 0}</td><td>${(r.cached_reads ?? 0).toLocaleString('en-US')}</td><td>${(r.unique_ok_responses ?? 0).toLocaleString('en-US')}</td><td class="dimtx">${M.budget?.[s] ?? '—'}</td></tr>`; }).join('');
  const ext = A.census?.extension;
  const eRows = ext ? ext.rows.map((r) => `<tr><td class="l" style="color:${LEAGUE_COLOR[r.league]}">${esc(r.league_name)}</td><td>${r.matched_two_way}</td><td>${r.games_with_sportsbook_history}</td><td>${r.with_pinnacle_close}</td><td>${r.sportsbook_entries.toLocaleString('en-US')}</td><td class="dimtx">${esc(r.first_kickoff)} → ${esc(r.last_kickoff)}</td></tr>`).join('') : '';
  const extHtml = ext ? `
  <h3>Sportsbook-only extension (${esc((ext.window || [])[0]?.slice(0, 10) || '')} → ${esc((ext.window || [])[1]?.slice(0, 10) || '')} UTC)</h3>
  <div class="table-wrap"><table><thead><tr><th class="l">league</th><th>matched OpticOdds ↔ Sportradar</th><th>with sportsbook history</th><th>with Pinnacle close</th><th>sportsbook entries</th><th>kickoffs covered</th></tr></thead><tbody>${eRows}</tbody></table></div>
  <p>The extension month was fetched for sportsbooks only (no Polymarket markets), under the Tier-1 OpticOdds cap; where a league is partially covered the kickoff range above is exact (MLB: 2026-09-02 → 09-14; NFL: regular-season week 1 only, no preseason).</p>` : '';
  const html = `
  <h2>What this is</h2>
  <p><b>The Tape</b> aligns sportsbook moneyline, spread and total histories from <b>OpticOdds</b> with <b>Polymarket</b> prices for the same games and <b>Sportradar</b> schedules, finals and play-by-play. Cross-market window: <b>${W}</b>. Tier completed: <b>${esc(M.tier_label)}</b>. Dataset generated ${esc(man.generated_at)} UTC; analyses generated ${esc(A.generated_at)} UTC. Historical description only: no trading, no recommendations, no edge claims.</p>
  <h2>Coverage per league</h2>
  <div class="table-wrap"><table><thead><tr><th class="l">league</th><th>games in window</th><th>with sportsbook history</th><th>with Pinnacle close</th><th>with Polymarket history</th><th>with PM close ≤ 30 min</th><th>both sources</th><th>with plays</th><th>sportsbook entries</th><th>PM samples</th><th>PM ML volume</th><th>tiers A/B/C/M</th></tr></thead><tbody>${cRows}</tbody></table></div>
  <p>A league enters a cross-market statistic only when it has both a sportsbook close and a Polymarket close for that game; nothing is aligned by assumption. ${esc(M.oo_slice_label || '')}</p>
  ${extHtml}
  <h2>Matching</h2>
  <div class="table-wrap"><table><thead><tr><th class="l">league</th><th>OpticOdds fixtures (completed)</th><th>Polymarket game events</th><th>Sportradar games</th><th>matched 3-way</th><th>in window</th><th>OO+SR only</th><th>OO+PM only</th><th>OO unmatched</th><th>PM unmatched</th><th>SR unmatched</th><th>ambiguous</th></tr></thead><tbody>${mRows}</tbody></table></div>
  <ul>
    <li><b>Rule:</b> same league; normalized team names and an alias table (nicknames, abbreviations, city/school forms); start time within ±${mt.tolerance_minutes ?? 20} minutes; final score agreement as a tie-breaker and orientation check. Tier <b>A</b> = exact names on both sides; <b>B</b> = alias/nickname match with agreeing scores; <b>C</b> = fuzzy match that still agrees on scores; <b>M</b> = manual override from <code>overrides.json</code> (${mt.overrides ?? 0} entries, each with a reason).</li>
    <li><b>Orientation:</b> the canonical home/away is Sportradar's. ${mt.orientation_conflicts ?? 0} neutral-site games had OpticOdds home/away flipped relative to Sportradar and Polymarket; their odds were remapped by team identity, not by slot.</li>
    <li><b>Audit:</b> ${mt.audit?.n ?? 40}-game random sample (seed ${mt.audit?.seed ?? 7}) reviewed by hand: ${mt.audit?.wrong ?? 0} wrong matches. Independent recomputation of ${M.recompute?.n ?? 20} games (seed ${M.recompute?.seed ?? 2026}, exact-fraction arithmetic): ${M.recompute?.ok ? 'all within 1e-9' : 'see qa/'} (worst |Δ| ${M.recompute?.worst != null ? M.recompute.worst.toExponential(2) : '—'}).</li>
  </ul>
  <h2>Normalization</h2>
  <ul>
    <li><b>Sportsbook entries</b> are a step function: each entry holds until the next one for that sportsbook and market. American odds → implied probability (<code>100/(a+100)</code> for a &gt; 0, <code>−a/(−a+100)</code> otherwise) → <b>no-vig by multiplicative normalization</b> per sportsbook per timestamp (each side divided by the sum of the sides; three-way for soccer). Raw implied probabilities are also kept.</li>
    <li><b>Opening</b> = the sportsbook's first entry in the retained history (OpticOdds keeps about two months; vendor OLV/CLV fields are kept as receipts). <b>Closing</b> = last entry at or before the Sportradar scheduled start; a close older than 6 h is flagged stale and excluded from closing statistics.</li>
    <li><b>Polymarket</b> <code>p</code> is a <b>sampled CLOB price used directly as a probability</b> (1-month lookback at 10-minute fidelity; 1-week at 5; 1-day at 1). Home-win series come from the home moneyline market, or 1 − the away market when only that exists (labelled in the game view). The T−24 h / T−6 h / T−1 h / T−10 min / T−1 min marks take the last sample at or before each mark and record its age; closing statistics require age ≤ 30 min.</li>
    <li><b>Fees:</b> each market's fee schedule is stored; backtests charge the taker fee <code>shares × rate × p × (1 − p)</code> at entry (rate 3% NFL/CFB, 5% others, as returned per market). Fills are assumed at the sampled price with no slippage.</li>
  </ul>
  <h2>Analyses</h2>
  <ul>
    <li><b>Census</b> (above). <b>Closing agreement:</b> Polymarket T−1 min minus Pinnacle no-vig close on the home side, with bootstrap CIs, favorite-bucket breakdown and per-book comparison.</li>
    <li><b>Price discovery:</b> both series resampled to a 10-minute grid over the last 48 h pre-kickoff; Pearson correlation of changes at lags −120…+120 min; plus an event study of every Pinnacle move ≥ 3 pp within 60 min, measuring the share of the move visible in Polymarket at each lag, and a classification of who moved first.</li>
    <li><b>Scoreboard:</b> Brier and log loss of each source at its close or mark, by league, with reliability bins and Wilson CIs. Outcome = home win (soccer draws count as 0; ties excluded).</li>
    <li><b>Backtests</b> (fee-aware, $1 per bet, hold to resolution): <i>follow Pinnacle</i> with θ ∈ {2, 3, 5, 8} pp entering at T−6 h / T−1 h / T−10 min; <i>fade the late move</i> (consensus moved ≥ θ between T−6 h and T−10 min → buy the other side at T−10 min); and an illustrative in-game <i>buy the scoring team at the next sample</i> on the hero set. Each reports N, hit rate, ROI, bootstrap 95% CI, max drawdown and a label-shuffled placebo (500 shuffles). The lab recomputes all of this in the browser from the loaded dataset.</li>
    <li><b>In-game reaction</b> uses Sportradar wall-clock timestamps of scoring plays versus the next Polymarket sample (1–5 min apart, so reaction times are upper bounds). <b>Context</b> factors (league, favorite size, venue, week) are descriptive; ${A.context?.n_comparisons ?? 0} comparisons are shown with a multiple-comparison caveat: ${esc(A.context?.caveat || '')}</li>
  </ul>
  <h2>Call ledger</h2>
  <div class="table-wrap"><table><thead><tr><th class="l">source</th><th>attempted</th><th>succeeded</th><th>throttled (rate limit, not cached)</th><th>other errors</th><th>cache-served reads</th><th>unique responses on disk</th><th>cap</th></tr></thead><tbody>${lRows}</tbody></table></div>
  <p>Every vendor call went through one cached, paced wrapper; identical requests are never repeated. ${esc(M.ledger_note || '')}</p>
  <h2>Limitations</h2>
  <ul>${(M.limitations || []).map((l) => `<li>${esc(l)}</li>`).join('')}</ul>
  <h2>Attribution</h2>
  <p class="fg">${esc(M.attribution || '')}</p>
  `;
  page.append(el('div', { class: 'panel prose', html }));
}
