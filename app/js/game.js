// Game view: five sportsbooks (OpticOdds) + Polymarket on one time axis, with Sportradar scoring plays.
import { store, LEAGUE_NAME, LEAGUE_COLOR, BOOK_COLOR, BOOK_ORDER, el, esc, fmtPct, fmtTime, fmtUSD, probToAmerican, probToDecimal, loadGame, sizeCanvas, showTip, hideTip, windowLabel } from './common.js';
import { stepValue, timeTicks, probTicks, drawStep, axisLeft, axisBottom, FONT, COLORS } from './charts.js';

export const HERO_KEY = 'nfl:2026101240603BF9';
const VIEW = { mode: 'novig', unit: 'prob', market: 'ml', side: 'home', hidden: new Set(), full: false };

const HERO_MOMENTS = [
  {
    id: 'open',
    label: '01 · Open: BAL 74.0%',
    t: 1790703414,
    side: 'away',
    zoom: 'full',
    title: 'Sep 29 17:36Z · Opening Moneyline',
    detail: 'FanDuel opens Baltimore at 74.0% no-vig (−335 raw) 12 days before kickoff; DraftKings opens at 64.5% and Polymarket at 61.5%.'
  },
  {
    id: 'drop',
    label: '02 · Oct 6 Flip: 64% → 39.5%',
    t: 1791298220,
    side: 'away',
    zoom: 'week',
    title: 'Oct 06 14:50Z · Pre-Game Line Flip',
    detail: 'Synchronized pre-game repricing: sportsbooks and Polymarket reprice Baltimore from ~64% down to 39.5% inside one morning session.'
  },
  {
    id: 'close',
    label: '03 · Close: 38.1% vs 37.5%',
    t: 1791763971,
    side: 'away',
    zoom: 'day',
    title: 'Oct 12 00:12Z (T−7 min) · Closing Consensus',
    detail: 'Pinnacle closes Baltimore at 38.1% no-vig (+156) and Polymarket closes at 37.5% across $7.30M volume — a 0.6 pp closing gap.'
  },
  {
    id: 'trough',
    label: '04 · Q4 Trough: 12.0% (15–23)',
    t: 1791774619,
    side: 'away',
    zoom: 'ingame',
    title: 'Oct 12 03:10Z (Q4 2:35) · In-Game Probability Trough',
    detail: 'Trailing 15–23 late in Q4 after Nick Folk’s 48-yd field goal, Baltimore’s live Polymarket win probability bottoms at 12.0%.'
  },
  {
    id: 'tie',
    label: '05 · Q4 00:44 Tie: 50.5% (23–23)',
    t: 1791775520,
    side: 'away',
    zoom: 'ingame',
    title: 'Oct 12 03:15Z–03:25Z (Q4 00:44) · Walker 7-yd TD + Henry 2PT',
    detail: 'Huntley hits Devontez Walker for a 7-yd TD (03:15Z) and Derrick Henry converts the 2-pt rush (23–23), lifting Baltimore to 50.5%.'
  },
  {
    id: 'ot',
    label: '06 · OT 03:01 Winner: 83.5% (30–23)',
    t: 1791776420,
    side: 'away',
    zoom: 'ingame',
    title: 'Oct 12 03:41Z (OT 03:01) · Huntley 1-yd Overtime Touchdown',
    detail: 'Huntley rushes 1 yd for the overtime touchdown (30–23 final); Polymarket surges to 83.5% on the drive and settles at 99.95%.'
  }
];

function americanToProb(a) { return a == null ? null : a > 0 ? 100 / (a + 100) : -a / (-a + 100); }
function fmtUnit(p, unit) { return p == null ? '—' : unit === 'prob' ? fmtPct(p) : unit === 'american' ? probToAmerican(p) : probToDecimal(p); }
function fmtLine(x) { return x == null ? '' : (x > 0 ? '+' : '') + x; }

export function renderGame(page, key) {
  page.classList.add('game-page');
  if (!key) key = HERO_KEY;
  const meta = store.wall.games.find((g) => g.key === key) || (store.wall.ext_games || []).find((g) => g.key === key);
  if (!meta) { page.append(picker(key)); return; }
  page.append(el('div', { class: 'panel' }, `Loading ${meta.away} @ ${meta.home}…`));
  let disposed = false, cleanup = null;
  loadGame(key).then((g) => { if (disposed) return; page.innerHTML = ''; cleanup = build(page, g, meta); }).catch((e) => { page.innerHTML = ''; page.append(el('div', { class: 'panel' }, [el('h2', {}, 'Game data not found'), el('p', {}, esc(e.message))]), picker(key)); });
  return () => { disposed = true; if (cleanup) cleanup(); };
}

function picker(current) {
  const games = store.wall.games.concat(store.wall.ext_games || []).slice().sort((a, b) => b.ko - a.ko);
  const sel = el('select', { class: 'sel', 'data-testid': 'game-picker' });
  for (const g of games) sel.append(el('option', { value: g.key, selected: g.key === current ? '' : null }, `${LEAGUE_NAME[g.lg]} · ${g.away} @ ${g.home} · ${fmtTime(g.ko, { utcOnly: true })}${g.ext ? ' · books only' : g.oo ? ' · books+PM' : ' · PM only'}`));
  sel.addEventListener('change', () => { location.hash = '#/game/' + encodeURIComponent(sel.value); });
  const idx = games.findIndex((g) => g.key === current);
  const nav = (d) => { const n = games[(idx + d + games.length) % games.length]; location.hash = '#/game/' + encodeURIComponent(n.key); };
  return el('div', { class: 'gamepick' }, [
    el('span', { class: 'lbl mono', style: 'color:var(--muted);font-size:var(--text-xs)' }, 'Game'), sel,
    el('button', { class: 'btn', 'data-testid': 'prev-game', onclick: () => nav(1) }, '← earlier'), el('button', { class: 'btn', 'data-testid': 'next-game', onclick: () => nav(-1) }, 'later →'),
    el('a', { class: 'btn', href: '#/game/' + encodeURIComponent(HERO_KEY) }, 'Hero game'),
  ]);
}

function seriesFor(g, market, mode, side = 'home') {
  const out = [];
  const away = side === 'away';
  const books = g.oo?.books || {};
  for (const b of BOOK_ORDER) {
    const m = books[b]?.[market];
    if (!m) continue;
    let rows;
    if (mode === 'novig') {
      rows = m.novig.map((r) => [r[0], market === 'ml' ? (away ? r[2] : r[1]) : (away ? 1 - r[1] : r[1]), market === 'ml' ? null : (away && market === 'spread' && r[2] != null ? -r[2] : r[2])]);
    } else {
      const raw = market === 'total' ? (away ? m.raw.under : m.raw.over) : (away ? m.raw.away : m.raw.home);
      rows = (raw || []).map((r) => [r[0], americanToProb(r[1]), r[2]]);
    }
    rows = rows.filter((r) => r[1] != null);
    if (!rows.length) continue;
    const closeRow = m.close ? stepValue(rows, m.close[0]) : null;
    out.push({ name: b, vendor: 'OpticOdds', color: BOOK_COLOR[b] || '#aaa', rows, open: rows[0], close: closeRow, closeAge: m.close_age_min, isPM: false, n: m.n_entries, vendor_olv: m.vendor_olv, vendor_clv: m.vendor_clv });
  }
  const pm = g.pm || {};
  let pmRows = null, pmLine = null, pmMarket = null, pmLabel = 'Polymarket';
  if (market === 'ml') {
    pmRows = (pm.home_series || []).map((r) => [r[0], away ? 1 - r[1] : r[1], null]); pmMarket = pm.markets?.ml_home || pm.markets?.ml_away;
    const fromAway = pm.home_series_source === '1-ml_away';
    pmLabel = away ? (fromAway ? 'Polymarket (away price)' : 'Polymarket (1 − home price)') : (fromAway ? 'Polymarket (1 − away price)' : 'Polymarket');
  } else if (pm.markets?.[market]) {
    const mk = pm.markets[market]; pmMarket = mk; pmLine = mk.line;
    const wantSide = market === 'spread' ? (away ? 'away' : 'home') : (away ? 'under' : 'over');
    const flip = mk.side !== wantSide;
    pmRows = (mk.p_side || []).map((r) => [r[0], flip ? 1 - r[1] : r[1], mk.line]);
    if (flip) pmLabel = `Polymarket (1 − ${mk.side} price)`;
  }
  if (pmRows && pmRows.length) {
    const pre = pmRows.filter((r) => r[0] <= g.kickoff);
    out.push({ name: pmLabel, vendor: 'Polymarket', color: BOOK_COLOR.Polymarket, rows: pmRows, open: pmRows[0], close: pre.length ? pre[pre.length - 1] : null, closeAge: pre.length ? (g.kickoff - pre[pre.length - 1][0]) / 60 : null, isPM: true, n: pmRows.length, market: pmMarket, line: pmLine });
  }
  return out;
}

function build(page, g, meta) {
  const acc = LEAGUE_COLOR[g.league];
  page.style.setProperty('--accent', acc);
  const head = el('div', { class: 'game-head' }, [
    el('span', { class: 'teams', 'data-testid': 'game-title' }, `${g.away.name} @ ${g.home.name}`),
    el('span', { class: 'score mono' }, g.final?.home != null ? `${g.final.away}–${g.final.home}${g.final.periods?.some((p) => p.period_type === 'overtime') ? ' (OT)' : ''}` : '—'),
    el('span', { class: 'meta' }, `${LEAGUE_NAME[g.league]}${g.context?.week ? ' · week ' + g.context.week : ''} · kickoff ${fmtTime(g.kickoff)}${g.context?.venue?.name ? ' · ' + g.context.venue.name : ''}${g.context?.neutral ? ' · neutral site' : ''} · match tier ${g.match.tier}`),
    picker(g.key),
  ]);

  // toolbar
  const tb = el('div', { class: 'toolbar', style: 'border:1px solid var(--line);border-radius:4px' });
  const segs = {};
  let closesPanel = null;
  let activeMomentId = null;
  const mkSeg = (name, opts) => { const s = el('div', { class: 'seg', 'data-testid': `seg-${name}` }); for (const [k, lab] of opts) { const b = el('button', { 'data-testid': `${name}-${k}` }, lab); b.addEventListener('click', () => { VIEW[name] = k; sync(); draw(); }); s.append(b); } segs[name] = s; return s; };
  const hasMarket = (m) => Object.values(g.oo?.books || {}).some((b) => b[m]) || (m === 'ml' ? (g.pm?.home_series || []).length : g.pm?.markets?.[m]);
  tb.append(el('div', { class: 'group' }, [el('span', { class: 'lbl' }, 'Market'), mkSeg('market', [['ml', 'Moneyline'], ['spread', g.sport === 'baseball' ? 'Run line' : g.sport === 'hockey' ? 'Puck line' : 'Spread'], ['total', 'Total']].filter(([m]) => hasMarket(m)))]));
  tb.append(el('div', { class: 'group' }, [el('span', { class: 'lbl' }, 'Side'), mkSeg('side', [['home', g.home.abbr || 'Home'], ['away', g.away.abbr || 'Away']])]));
  tb.append(el('div', { class: 'group' }, [el('span', { class: 'lbl' }, 'Books'), mkSeg('mode', [['novig', 'No-vig'], ['raw', 'Raw']])]));
  tb.append(el('div', { class: 'group' }, [el('span', { class: 'lbl' }, 'Unit'), mkSeg('unit', [['prob', 'Probability'], ['american', 'American'], ['decimal', 'Decimal']])]));

  const weekBtn = el('button', { class: 'btn', 'data-testid': 'zoom-week' }, 'Week');
  weekBtn.addEventListener('click', () => { domain = [Math.max(fullDomain[0], ko - 7 * 86400), endT()]; draw(); });
  const dayBtn = el('button', { class: 'btn', 'data-testid': 'zoom-day' }, 'Game day');
  dayBtn.addEventListener('click', () => { domain = [Math.max(fullDomain[0], ko - 24 * 3600), endT()]; draw(); });
  const fullBtn = el('button', { class: 'btn', 'data-testid': 'full-history' }, 'Full history');
  fullBtn.addEventListener('click', () => { setDefaultDomain(); draw(); });
  const inGameBtn = el('button', { class: 'btn', 'data-testid': 'zoom-ingame' }, 'In-game');
  inGameBtn.addEventListener('click', () => { domain = [ko - 600, finalT()]; draw(); });
  const resetBtn = el('button', { class: 'btn', 'data-testid': 'reset-zoom' }, 'Reset zoom');
  resetBtn.addEventListener('click', () => { activeMomentId = null; hoverT = null; syncMoments(); setDefaultDomain(); draw(); });
  const pngBtn = el('button', { class: 'btn', 'data-testid': 'export-png' }, 'Export PNG');
  tb.append(el('div', { class: 'group', style: 'margin-left:auto' }, [fullBtn, weekBtn, dayBtn, inGameBtn, resetBtn, pngBtn]));

  // Interactive Key Moments Bar (for Hero game or games with play-by-play)
  const momentsBar = el('div', { class: 'moments-bar', 'data-testid': 'moments-bar' });
  const momentCallout = el('div', { class: 'verdict-banner', 'data-testid': 'moment-callout', style: 'display:none;margin-top:2px' });

  // chart area
  const main = el('canvas', { class: 'main', 'data-testid': 'game-canvas' });
  const brush = el('canvas', { class: 'brush', 'data-testid': 'brush-canvas' });
  const mainWrap = el('div', { class: 'main-wrap' }, [main]);
  const brushWrap = el('div', { class: 'brush-wrap' }, [brush]);
  const legend = el('div', { class: 'legend', 'data-testid': 'legend' });
  const chartChildren = [tb];
  if (g.key === HERO_KEY) chartChildren.push(momentsBar, momentCallout);
  chartChildren.push(mainWrap, brushWrap, legend);
  const chartWrap = el('div', { class: 'chart-wrap' }, chartChildren);
  const side = el('div', { class: 'side' });
  const body = el('div', { class: 'game-body' }, [chartWrap, side]);
  page.append(head, body);

  // ---- data
  let series = [], domain = [0, 1], fullDomain = [0, 1], brushDomain = [0, 1], hoverT = null, drag = null, playHits = [];
  const ko = g.kickoff;
  const plays = (g.sr?.plays || []).filter((p) => p.scoring);
  function recompute() { series = seriesFor(g, VIEW.market, VIEW.mode, VIEW.side); for (const s of series) s.hidden = VIEW.hidden.has(s.name); }
  function endT() { let e = ko + 3 * 3600; for (const s of series) e = Math.max(e, s.rows[s.rows.length - 1][0]); return Math.min(e, ko + 8 * 3600); }
  function finalT() {
    const all = g.sr?.plays || [];
    if (all.length) return Math.min(all[all.length - 1].t + 180, ko + 8 * 3600);
    const pm = series.find((x) => x.isPM); const last = pm ? pm.rows[pm.rows.length - 1][0] : ko + 3 * 3600;
    return Math.min(Math.max(last, ko + 3600), ko + 8 * 3600);
  }
  function setDomainFull() { let first = Infinity; for (const s of series) first = Math.min(first, s.rows[0][0]); if (!isFinite(first)) first = ko - 7 * 86400; fullDomain = [Math.min(first, ko - 3600), endT()]; brushDomain = fullDomain.slice(); domain = [Math.max(domain[0], fullDomain[0]), Math.min(domain[1], fullDomain[1])]; if (domain[1] - domain[0] < 600) setDefaultDomain(); }
  function setDefaultDomain() { domain = fullDomain.slice(); }
  recompute(); setDomainFull(); setDefaultDomain();

  // Populate Hero Key Moments Bar
  function syncMoments() {
    if (g.key !== HERO_KEY) return;
    for (const b of momentsBar.querySelectorAll('.moment-btn')) {
      b.classList.toggle('active', b.dataset.mid === activeMomentId);
    }
    const m = HERO_MOMENTS.find((x) => x.id === activeMomentId);
    if (m) {
      momentCallout.style.display = 'flex';
      momentCallout.innerHTML = `<span class="vb-tag">${esc(m.title)}</span><span>${esc(m.detail)}</span>`;
    } else {
      momentCallout.style.display = 'none';
    }
  }
  if (g.key === HERO_KEY) {
    momentsBar.append(el('span', { class: 'm-lbl' }, 'Key Replay Moments'));
    for (const m of HERO_MOMENTS) {
      const btn = el('button', { class: 'moment-btn', 'data-mid': m.id, 'data-testid': `moment-${m.id}` }, m.label);
      btn.addEventListener('click', () => {
        activeMomentId = m.id;
        VIEW.market = 'ml';
        VIEW.side = m.side;
        sync();
        setDomainFull();
        if (m.zoom === 'full') setDefaultDomain();
        else if (m.zoom === 'week') domain = [Math.max(fullDomain[0], ko - 7 * 86400), endT()];
        else if (m.zoom === 'day') domain = [Math.max(fullDomain[0], ko - 24 * 3600), endT()];
        else if (m.zoom === 'ingame') domain = [ko - 600, finalT()];
        hoverT = m.t;
        syncMoments();
        draw();
      });
      momentsBar.append(btn);
    }
  }

  // ---- drawing
  let W = 0, H = 0, ctx = null, bctx = null, BW = 0, BH = 48;
  const padL = 60, padR = 14, padT = 22, padB = 30;
  const xOf = (t) => padL + (W - padL - padR) * (t - domain[0]) / (domain[1] - domain[0]);
  const tOf = (x) => domain[0] + (x - padL) / (W - padL - padR) * (domain[1] - domain[0]);
  const yOf = (p) => padT + (H - padT - padB) * (1 - p);
  function layout() { W = mainWrap.clientWidth; H = mainWrap.clientHeight; ctx = sizeCanvas(main, W, H); BW = brushWrap.clientWidth; bctx = sizeCanvas(brush, BW, BH); }
  function draw() {
    if (!ctx) return;
    ctx.clearRect(0, 0, W, H);
    // in-game shading
    if (ko < domain[1]) { ctx.fillStyle = 'rgba(255,255,255,0.025)'; const x0 = Math.max(padL, xOf(ko)); ctx.fillRect(x0, padT, W - padR - x0, H - padT - padB); }
    axisLeft(ctx, padL, padT, H - padB, probTicks(VIEW.unit), yOf, { gridTo: W - padR });
    const tt = timeTicks(domain[0], domain[1], W - padL - padR);
    axisBottom(ctx, H - padB, padL, W - padR, tt.ticks, xOf, tt.fmt);
    ctx.save(); ctx.beginPath(); ctx.rect(padL, padT - 2, W - padL - padR, H - padT - padB + 4); ctx.clip();
    // kickoff line
    if (ko >= domain[0] && ko <= domain[1]) { const x = Math.round(xOf(ko)) + 0.5; ctx.strokeStyle = '#8b95a3'; ctx.setLineDash([4, 3]); ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, H - padB); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle = '#8b95a3'; ctx.font = FONT; ctx.textBaseline = 'top'; const flipLabel = x + 56 > W - padR; ctx.textAlign = flipLabel ? 'right' : 'left'; ctx.fillText('kickoff', flipLabel ? x - 4 : x + 4, padT); }
    const dense = (domain[1] - domain[0]) < 6 * 3600;
    for (const s of series) {
      if (s.hidden) continue;
      if (s.isPM) {
        const lastT = s.rows[s.rows.length - 1][0];
        drawStep(ctx, s.rows, xOf, yOf, s.color, 1.8, { tMin: domain[0], tMax: Math.min(domain[1], ko), tEnd: Math.min(lastT, ko) });
        if (lastT > ko && domain[1] > ko) drawStep(ctx, s.rows, xOf, yOf, s.color, 2.8, { tMin: Math.max(domain[0], ko), tMax: domain[1], tEnd: lastT, dots: dense });
      } else {
        drawStep(ctx, s.rows, xOf, yOf, s.color, 1.4, { tMin: domain[0], tMax: domain[1], tEnd: Math.min(domain[1], s.rows[s.rows.length - 1][0] > ko ? s.rows[s.rows.length - 1][0] : ko) });
      }
      // OLV circle / CLV square
      if (s.open && s.open[0] >= domain[0] && s.open[0] <= domain[1]) { ctx.fillStyle = s.color; ctx.beginPath(); ctx.arc(xOf(s.open[0]), yOf(s.open[1]), 3.5, 0, Math.PI * 2); ctx.fill(); }
      if (s.close && s.close[0] >= domain[0] && s.close[0] <= domain[1]) { const x = xOf(s.close[0]), y = yOf(s.close[1]); ctx.fillStyle = s.color; ctx.strokeStyle = s.color; ctx.lineWidth = 1.5; if (s.closeAge != null && s.closeAge > 360) ctx.strokeRect(x - 3.5, y - 3.5, 7, 7); else ctx.fillRect(x - 3.5, y - 3.5, 7, 7); }
    }
    // scoring plays (Sportradar wall clocks)
    playHits = [];
    const pmS = series.find((x) => x.isPM && !x.hidden);
    const visPlays = plays.filter((p) => p.t >= domain[0] && p.t <= domain[1]);
    const zoomedOut = (domain[1] - domain[0]) > 3 * 86400;
    ctx.font = '13.5px Geist Mono'; ctx.textAlign = 'center';
    const labelW = 46, rowH = 16, maxRows = 4; const rowLastX = new Array(maxRows).fill(-Infinity);
    for (const p of visPlays) {
      const x = Math.round(xOf(p.t)) + 0.5;
      ctx.strokeStyle = 'rgba(230,233,238,0.45)'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x, H - padB - 10); ctx.lineTo(x, H - padB); ctx.stroke();
      if (zoomedOut) continue;
      const r = pmS ? stepValue(pmS.rows, p.t) : null;
      const y = r && r[1] != null ? yOf(r[1]) : H - padB - 10;
      if (r && r[1] != null) {
        ctx.fillStyle = '#0b0e13'; ctx.beginPath(); ctx.arc(xOf(p.t), y, 5, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#e6e9ee'; ctx.beginPath(); ctx.arc(xOf(p.t), y, 3.2, 0, Math.PI * 2); ctx.fill();
      }
      const lx = Math.max(padL + labelW / 2, Math.min(W - padR - labelW / 2, x));
      const row = rowLastX.findIndex((rx) => lx - rx >= labelW);
      if (row < 0) { playHits.push({ p, x, lx, y, ly: null }); continue; }
      rowLastX[row] = lx;
      const ly = H - padB - 12 - row * rowH;
      ctx.fillStyle = 'rgba(11,14,19,0.85)'; ctx.fillRect(lx - labelW / 2 + 1, ly - 13, labelW - 2, 14);
      ctx.fillStyle = '#e6e9ee'; ctx.textBaseline = 'bottom'; ctx.fillText(`${p.ap}–${p.hp}`, lx, ly);
      playHits.push({ p, x, lx, y, ly });
    }
    // hover crosshair
    if (hoverT != null && hoverT >= domain[0] && hoverT <= domain[1]) {
      const x = Math.round(xOf(hoverT)) + 0.5; ctx.strokeStyle = '#f2a93b'; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, H - padB); ctx.stroke();
      for (const s of series) { if (s.hidden || hoverT > lineEnd(s)) continue; const r = stepValue(s.rows, hoverT); if (!r || r[1] == null) continue; ctx.fillStyle = s.color; ctx.beginPath(); ctx.arc(x, yOf(r[1]), 3.5, 0, Math.PI * 2); ctx.fill(); }
      const pmHover = series.find((s) => s.isPM && !s.hidden);
      const pr = pmHover ? stepValue(pmHover.rows, hoverT) : null;
      if (pr && pr[1] != null) {
        const txt = fmtUnit(pr[1], VIEW.unit); ctx.font = '600 13.5px Geist Mono'; const tw = Math.ceil(ctx.measureText(txt).width) + 10, th = 19;
        const stripTop = playHits.some((h) => h.ly != null) ? H - padB - 12 - (maxRows - 1) * rowH - 10 : H - padB;
        const yy = Math.round(yOf(pr[1])), onRight = x + 9 + tw <= W - padR, lx = onRight ? x + 9 : x - 9 - tw, ly = Math.max(padT, Math.min(stripTop - 2 - th, yy - th / 2));
        ctx.fillStyle = 'rgba(11,14,19,0.92)'; ctx.fillRect(lx, ly, tw, th); ctx.strokeStyle = pmHover.color; ctx.lineWidth = 1; ctx.strokeRect(lx + 0.5, ly + 0.5, tw - 1, th - 1);
        ctx.fillStyle = pmHover.color; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(txt, lx + 5, ly + th / 2 + 0.5);
      }
    }
    // drag rectangle
    if (drag && drag.x1 != null) { ctx.fillStyle = 'rgba(242,169,59,0.12)'; ctx.fillRect(Math.min(drag.x0, drag.x1), padT, Math.abs(drag.x1 - drag.x0), H - padT - padB); }
    ctx.restore();
    // caption (window + N) top-right
    ctx.fillStyle = '#5b6572'; ctx.font = FONT; ctx.textAlign = 'right'; ctx.textBaseline = 'top';
    const nEntries = series.filter((s) => !s.hidden).reduce((a, s) => a + s.rows.length, 0);
    const sideLabel = VIEW.market === 'total' ? (VIEW.side === 'away' ? 'under' : 'over') : `${VIEW.side === 'away' ? g.away.abbr : g.home.abbr} ${VIEW.market === 'ml' ? 'win' : 'cover'}`;
    const capFull = `${sideLabel} · ${fmtTime(domain[0], { utcOnly: true })} → ${fmtTime(domain[1], { utcOnly: true })} · ${nEntries} points · ${VIEW.mode === 'novig' ? 'no-vig (multiplicative)' : 'raw implied'} · Polymarket = sampled price`;
    const capShort = `${sideLabel} · ${fmtTime(domain[0], { utcOnly: true }).slice(0, 10)} → ${fmtTime(domain[1], { utcOnly: true }).slice(0, 10)} · N = ${nEntries}`;
    ctx.fillText(W >= 760 && ctx.measureText(capFull).width <= W - padL - padR ? capFull : capShort, W - padR, 2);
    drawBrush();
    renderLegend();
  }
  function drawBrush() {
    if (!bctx) return;
    bctx.clearRect(0, 0, BW, BH);
    const bx = (t) => 2 + (BW - 4) * (t - brushDomain[0]) / (brushDomain[1] - brushDomain[0]);
    const by = (p) => 4 + (BH - 8) * (1 - p);
    bctx.fillStyle = '#11151b'; bctx.fillRect(0, 0, BW, BH);
    for (const s of series) { if (s.hidden) continue; drawStep(bctx, s.rows, bx, by, s.isPM ? s.color : (s.name === 'Pinnacle' ? s.color : s.color + '66'), 1, { tMin: brushDomain[0], tMax: brushDomain[1], tEnd: s.rows[s.rows.length - 1][0] }); }
    if (ko >= brushDomain[0] && ko <= brushDomain[1]) { const x = Math.round(bx(ko)) + 0.5; bctx.strokeStyle = '#8b95a3'; bctx.setLineDash([3, 3]); bctx.beginPath(); bctx.moveTo(x, 0); bctx.lineTo(x, BH); bctx.stroke(); bctx.setLineDash([]); }
    const x0 = bx(domain[0]), x1 = bx(domain[1]);
    bctx.fillStyle = 'rgba(0,0,0,0.45)'; bctx.fillRect(0, 0, Math.max(0, x0), BH); bctx.fillRect(Math.min(BW, x1), 0, BW - x1, BH);
    bctx.strokeStyle = '#f2a93b'; bctx.lineWidth = 1; bctx.strokeRect(Math.round(x0) + 0.5, 0.5, Math.max(1, Math.round(x1 - x0)), BH - 1);
    bctx.fillStyle = '#8b95a3'; bctx.font = '13.5px Geist Mono'; bctx.textAlign = 'left'; bctx.textBaseline = 'top';
    bctx.fillText(BW < 640 ? fmtTime(brushDomain[0], { utcOnly: true }).slice(0, 10) : `${fmtTime(brushDomain[0], { utcOnly: true })} · overview, drag to zoom`, 4, 3); bctx.textAlign = 'right'; bctx.fillText(BW < 640 ? fmtTime(brushDomain[1], { utcOnly: true }).slice(0, 10) : `${fmtTime(brushDomain[1], { utcOnly: true })}`, BW - 4, 3);
  }
  function renderLegend() {
    const t = hoverT;
    const rows = series.map((s) => {
      const r = t != null ? stepValue(s.rows, t) : s.close;
      const v = r ? fmtUnit(r[1], VIEW.unit) : '—';
      const line = r && r[2] != null ? ` @ ${fmtLine(r[2])}` : (s.isPM && s.line != null ? ` @ ${fmtLine(s.line)}` : '');
      const when = r ? fmtTime(r[0], { utcOnly: true }) : '';
      const label = t != null ? (r ? `at ${when}` : 'no entry yet') : s.close ? `close ${when}${s.closeAge != null && s.closeAge > 360 ? ' (stale, >6 h)' : ''}` : 'no pre-kickoff entry';
      return `<div class="row${s.hidden ? ' off' : ''}" data-name="${esc(s.name)}" title="toggle"><span class="swatch" style="background:${s.color}"></span><span class="nm">${esc(s.name)} <span class="dimtx">· ${s.vendor}${s.isPM ? ' sampled price' : ''}</span></span><span class="v" style="color:var(--text)">${v}${line}</span><span class="v">${label}</span></div>`;
    });
    legend.innerHTML = `<div class="row" style="cursor:default;color:var(--muted)"><span></span><span class="nm dimtx">● open (first entry) · ■ close (last entry before kickoff) · ${t != null ? 'values at the hover time' : 'closing values'}</span><span></span><span class="v">N = ${series.reduce((a, s) => a + s.rows.length, 0)} entries</span></div>` + rows.join('');
    for (const row of legend.querySelectorAll('.row[data-name]')) row.addEventListener('click', () => { const n = row.dataset.name; VIEW.hidden.has(n) ? VIEW.hidden.delete(n) : VIEW.hidden.add(n); recompute(); draw(); });
  }
  function sync() {
    for (const [name, s] of Object.entries(segs)) for (const b of s.querySelectorAll('button')) b.classList.toggle('on', b.dataset.testid === `${name}-${VIEW[name]}`);
    recompute();
    if (closesPanel) closesPanel.innerHTML = closes();
  }
  // ---- side panels
  const closes = () => {
    const s = seriesFor(g, 'ml', 'novig', VIEW.side);
    const rows = s.map((x) => `<tr><td class="l"><span class="swatch" style="background:${x.color}"></span>${esc(x.isPM ? 'Polymarket' : x.name)}</td><td>${x.open ? fmtPct(x.open[1]) : '—'}</td><td>${x.close ? fmtPct(x.close[1]) : '—'}</td><td class="dimtx">${x.closeAge == null ? '—' : x.closeAge > 360 ? `${(x.closeAge / 60).toFixed(0)} h` : `${x.closeAge.toFixed(0)} m`}</td></tr>`).join('');
    const pmName = s.find((x) => x.isPM)?.name || 'Polymarket';
    const pmCap = pmName.startsWith('Polymarket (') ? 'Polymarket, ' + pmName.slice(12, -1) : pmName;
    return `<h2>Moneyline, ${VIEW.side === 'away' ? esc(g.away.abbr || 'away') + ' (away)' : esc(g.home.abbr || 'home') + ' (home)'}</h2><div class="cap">no-vig (books) · sampled price (${esc(pmCap)}) · open = first entry, close = last entry before kickoff, age = close to kickoff</div><table><thead><tr><th class="l">source</th><th>open</th><th>close</th><th>age</th></tr></thead><tbody>${rows}</tbody></table>`;
  };
  const pmPre = g.derived?.pm_pre || {};
  const pmTable = g.ext ? `<h2>Polymarket</h2><div class="cap">not fetched for this game: it belongs to the sportsbook-only extension (2026-08-14 → 09-14); sources are OpticOdds and Sportradar only</div>` : `<h2>Polymarket pre-kickoff checkpoints</h2><div class="cap">home-win price at T−24 h, T−6 h, T−1 h, T−10 min, T−1 min (last sample at or before each mark)</div><table><thead><tr><th class="l">mark</th><th>price</th><th>sample age</th></tr></thead><tbody>${['t24h', 't6h', 't1h', 't10m', 't1m'].map((k) => `<tr><td class="l">${k.replace('t', 'T−').replace('h', ' h').replace('m', ' min')}</td><td>${fmtPct(pmPre[k])}</td><td class="dimtx">${g.derived?.pm_age_min?.[k] == null ? '—' : g.derived.pm_age_min[k].toFixed(1) + ' min'}</td></tr>`).join('')}</tbody></table>`;
  const receipts = `<h2>Receipts</h2><dl class="kv">
    <dt>OpticOdds fixture</dt><dd>${esc(g.match.oo_fixture_id)} · ${g.oo?.meta?.n_entries ?? 0} entries · retrieved ${esc(g.oo?.meta?.retrieved_at || '—')}</dd>
    <dt>Polymarket event</dt><dd>${g.ext ? 'none (sportsbook-only extension)' : `${esc(g.match.pm_event_id)} · ${esc(g.match.pm_slug)} · ${fmtUSD(g.pm?.volume_event)} volume`}</dd>
    ${Object.entries(g.pm?.markets || {}).map(([k, m]) => `<dt>PM ${k}</dt><dd>market ${esc(m.market_id)} · ${esc(m.question)} · ${m.n_samples} samples · fidelity ${(m.fidelities || []).join('/')} min · fee ${m.fee ? (m.fee.rate * 100).toFixed(0) + '% × p(1−p)' : 'n/a'} · retrieved ${esc(m.retrieved_at || '')}</dd>`).join('')}
    <dt>Sportradar game</dt><dd>${esc(g.match.sr_game_id || '—')} · status ${esc(g.final?.sr_status || '—')} · ${g.sr?.plays ? g.sr.plays.length + ' plays with wall clocks' : 'play-by-play not fetched in this tier'}</dd>
    <dt>Match</dt><dd>tier ${esc(g.match.tier)} · PM ${g.ext ? 'n/a' : esc((g.match.pm_match || []).join('/'))} · SR ${esc((g.match.sr_match || []).join('/'))}${g.context?.oo_flipped ? ' · OpticOdds home/away flipped vs Sportradar (neutral site), normalized' : ''}</dd>
    <dt>Final</dt><dd>${esc(g.away.abbr)} ${g.final?.away ?? '—'} – ${esc(g.home.abbr)} ${g.final?.home ?? '—'}${g.final?.sr_status ? ' (Sportradar ' + esc(g.final.sr_status) + ')' : ''}${g.final?.pm_score ? ' · Polymarket score ' + esc(g.final.pm_score) : ''}</dd>
  </dl>`;
  const playsPanel = el('div', { class: 'panel', 'data-testid': 'plays-panel' });
  if (plays.length) {
    playsPanel.innerHTML = `<h2>Scoring plays <span class="tag">Sportradar · click to inspect</span></h2><div class="plays">${plays.map((p, idx) => `<div data-play-idx="${idx}" data-testid="play-row-${idx}"><span>${esc(fmtTime(p.t, { utcOnly: true }).slice(11))}</span><b>${p.ap}–${p.hp}</b><span>${esc(p.pl || ('Q' + p.period))} ${esc(p.clock || '')} · ${esc(p.desc.slice(0, 72))}</span></div>`).join('')}</div>`;
    for (const row of playsPanel.querySelectorAll('[data-play-idx]')) {
      row.addEventListener('click', () => {
        const idx = parseInt(row.dataset.playIdx, 10);
        const p = plays[idx];
        if (!p) return;
        for (const r of playsPanel.querySelectorAll('[data-play-idx]')) r.classList.toggle('active', r === row);
        if (domain[0] < ko - 3600 || domain[1] > ko + 6 * 3600) domain = [ko - 600, finalT()];
        hoverT = p.t;
        if (g.key === HERO_KEY) {
          activeMomentId = null;
          syncMoments();
          momentCallout.style.display = 'flex';
          momentCallout.innerHTML = `<span class="vb-tag">${esc(p.pl || ('Q' + p.period))} ${esc(p.clock || '')} · ${p.ap}–${p.hp}</span><span>${esc(p.desc)} (Wall clock ${fmtTime(p.t, { utcOnly: true })})</span>`;
        }
        draw();
      });
    }
  } else {
    playsPanel.innerHTML = `<h2>Scoring plays</h2><p>${g.sr?.plays ? 'No scoring plays with wall clocks in this feed.' : 'Play-by-play was not fetched for this game in the completed tier (hero set only).'}</p>`;
  }
  closesPanel = el('div', { class: 'panel', 'data-testid': 'closes-panel', html: closes() });
  side.append(closesPanel, el('div', { class: 'panel', html: pmTable }), playsPanel, el('div', { class: 'panel', html: receipts }));

  // ---- interactions
  main.addEventListener('mousemove', (ev) => {
    const r = main.getBoundingClientRect(); const x = ev.clientX - r.left;
    if (drag) { drag.x1 = Math.max(padL, Math.min(W - padR, x)); draw(); return; }
    hoverT = x >= padL && x <= W - padR ? tOf(x) : null;
    draw();
    const yy = ev.clientY - r.top;
    const hit = playHits.find((h) => (Math.abs(h.x - x) < 6 && Math.abs(h.y - yy) < 8) || (h.ly != null && Math.abs(h.lx - x) < 6 && yy > h.ly - 12 && yy < H - padB));
    const near = hit ? hit.p : null;
    if (near) showTip(ev.clientX, ev.clientY, `<div class="t-title">${esc(near.type)} · ${esc(near.pl || ('Q' + near.period))} ${esc(near.clock || '')} · ${near.ap}–${near.hp}</div><div>${esc(near.desc)}</div><div class="t-row"><span>wall clock</span><b>${fmtTime(near.t)}</b></div>`);
    else if (hoverT != null && hoverT >= domain[0] && hoverT <= domain[1]) showTip(ev.clientX, ev.clientY, hoverCard(hoverT));
    else hideTip();
  });
  function lineEnd(s) { const lastT = s.rows[s.rows.length - 1][0]; return s.isPM ? lastT : (lastT > ko ? lastT : ko); }
  function hoverCard(t) {
    const rows = series.filter((s) => !s.hidden && t <= lineEnd(s)).map((s) => { const r = stepValue(s.rows, t); return `<div class="t-row"><span><span class="swatch" style="background:${s.color}"></span>${esc(s.isPM ? 'Polymarket' : s.name)}</span><b>${r && r[1] != null ? fmtUnit(r[1], VIEW.unit) : '—'}</b></div>`; });
    return `<div class="t-title">${fmtTime(t, { utcOnly: true })}</div>${rows.join('')}`;
  }
  main.addEventListener('mouseleave', () => { hoverT = null; drag = null; hideTip(); draw(); });
  main.addEventListener('mousedown', (ev) => { const r = main.getBoundingClientRect(); drag = { x0: Math.max(padL, Math.min(W - padR, ev.clientX - r.left)), x1: null }; hideTip(); });
  window.addEventListener('mouseup', onUp);
  function onUp() { if (drag && drag.x1 != null && Math.abs(drag.x1 - drag.x0) > 6) { const a = tOf(Math.min(drag.x0, drag.x1)), b = tOf(Math.max(drag.x0, drag.x1)); domain = [a, b]; hoverT = tOf(drag.x1); } drag = null; draw(); }
  main.addEventListener('dblclick', () => { setDefaultDomain(); draw(); });
  let bdrag = null;
  const bt = (x) => brushDomain[0] + (x - 2) / (BW - 4) * (brushDomain[1] - brushDomain[0]);
  brush.addEventListener('mousedown', (ev) => { const r = brush.getBoundingClientRect(); bdrag = { x0: ev.clientX - r.left, x1: null }; });
  brush.addEventListener('mousemove', (ev) => { if (!bdrag) return; const r = brush.getBoundingClientRect(); bdrag.x1 = ev.clientX - r.left; domain = [Math.max(brushDomain[0], bt(Math.min(bdrag.x0, bdrag.x1))), Math.min(brushDomain[1], bt(Math.max(bdrag.x0, bdrag.x1)))]; if (domain[1] - domain[0] > 300) draw(); });
  window.addEventListener('mouseup', () => { bdrag = null; });
  brush.addEventListener('dblclick', () => { setDefaultDomain(); draw(); });
  pngBtn.addEventListener('click', () => exportPng());
  function exportPng() {
    const dpr = 2, legendRows = series.length + 1, lh = 18, headH = 54, outW = W;
    const footParts = [`Window ${fmtTime(domain[0], { utcOnly: true })} → ${fmtTime(domain[1], { utcOnly: true })}`, 'Sportsbook lines: OpticOdds', 'Prices: Polymarket', 'Results and plays: Sportradar', 'The Tape'];
    const meas = document.createElement('canvas').getContext('2d'); meas.font = FONT;
    const footLines = []; let cur = '';
    for (const part of footParts) { const next = cur ? `${cur} · ${part}` : part; if (cur && meas.measureText(next).width > outW - 24) { footLines.push(cur); cur = part; } else cur = next; }
    if (cur) footLines.push(cur);
    const footH = 10 + footLines.length * 14 + 10, outH = headH + H + lh * legendRows + footH;
    const c = document.createElement('canvas'); c.width = outW * dpr; c.height = outH * dpr; const o = c.getContext('2d'); o.scale(dpr, dpr);
    o.fillStyle = '#0a0c10'; o.fillRect(0, 0, outW, outH);
    o.fillStyle = '#e6e9ee'; o.font = '600 19px Geist'; o.textBaseline = 'top'; o.fillText(`${g.away.name} @ ${g.home.name} · ${g.final?.away ?? ''}–${g.final?.home ?? ''}`, 12, 10);
    o.fillStyle = '#8b95a3'; o.font = FONT; o.fillText(`${LEAGUE_NAME[g.league]} · kickoff ${fmtTime(g.kickoff)} · ${VIEW.market} · ${VIEW.side} side · ${VIEW.mode === 'novig' ? 'no-vig (multiplicative)' : 'raw implied'} · unit ${VIEW.unit}`, 12, 32);
    o.drawImage(main, 0, headH, W, H);
    let y = headH + H + 4;
    o.font = FONT; o.textBaseline = 'top';
    for (const s of series) { if (s.hidden) continue; o.fillStyle = s.color; o.fillRect(12, y + 4, 10, 10); o.fillStyle = '#e6e9ee'; const r = s.close; o.fillText(`${s.name} · ${s.vendor}${s.isPM ? ' (sampled price)' : ''} · close ${r ? fmtUnit(r[1], VIEW.unit) : '—'}${r && r[2] != null ? ' @ ' + fmtLine(r[2]) : ''} · N=${s.rows.length}`, 28, y); y += lh; }
    o.fillStyle = '#5b6572'; footLines.forEach((line, i) => o.fillText(line, 12, outH - footH + 10 + i * 14));
    const a = document.createElement('a'); a.download = `the-tape_${g.key.replace(':', '_')}_${VIEW.market}_${VIEW.mode}.png`; a.href = c.toDataURL('image/png'); document.body.append(a); a.click(); a.remove();
    window.__tapeLastExport = { w: c.width, h: c.height };
  }
  const ro = new ResizeObserver(() => { layout(); draw(); });
  ro.observe(mainWrap); ro.observe(brushWrap);
  layout(); sync(); draw();
  window.__tapeGame = { key: g.key, game: g, series: () => series, domain: () => domain, brushDomain: () => brushDomain, pads: { padL, padR, padT, padB }, setDomain: (a, b) => { domain = [a, b]; draw(); }, view: VIEW, hover: (t) => { hoverT = t; draw(); }, exportPng };
  return () => { ro.disconnect(); window.removeEventListener('mouseup', onUp); hideTip(); };
}
