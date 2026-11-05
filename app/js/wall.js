// The Wall: every matched game as a strip (Pinnacle no-vig home probability vs Polymarket home price, final 7 days).
import { store, LEAGUES, LEAGUE_NAME, LEAGUE_COLOR, BOOK_COLOR, el, fmtPct, fmtTime, fmtUSD, showTip, hideTip, sizeCanvas, windowLabel } from './common.js';

const STATE = { leagues: new Set(LEAGUES), source: 'all', sort: 'ko-desc', q: '', ext: false };
let wallCount = 0;

export function renderWall(page) {
  page.classList.add('wall-page');
  const games = store.wall.games;
  const extGames = (store.wall.ext_games || []).map((g) => ({ ...g, ext: true }));
  // ---- toolbar
  const chips = el('div', { class: 'group', 'data-testid': 'league-chips' });
  const allChip = el('button', { class: 'chip', 'data-testid': 'chip-all' }, 'All');
  chips.append(el('span', { class: 'lbl' }, 'League'), allChip);
  for (const lg of LEAGUES) {
    const b = el('button', { class: 'chip', 'data-testid': `chip-${lg}`, style: `--chip:${LEAGUE_COLOR[lg]}` }, LEAGUE_NAME[lg]);
    b.addEventListener('click', (ev) => {
      if (ev.shiftKey || ev.metaKey) { STATE.leagues.has(lg) ? STATE.leagues.delete(lg) : STATE.leagues.add(lg); }
      else if (STATE.leagues.size === 1 && STATE.leagues.has(lg)) { STATE.leagues = new Set(LEAGUES); }
      else { STATE.leagues = new Set([lg]); }
      update();
    });
    chips.append(b);
  }
  allChip.addEventListener('click', () => { STATE.leagues = new Set(LEAGUES); update(); });
  const seg = el('div', { class: 'seg', 'data-testid': 'source-filter' });
  for (const [k, label] of [['all', 'All games'], ['both', 'Both sources'], ['pm', 'Polymarket only']]) {
    const b = el('button', { 'data-testid': `source-${k}` }, label);
    b.addEventListener('click', () => { STATE.source = k; update(); });
    seg.append(b);
  }
  // window segment: matched analysis window vs. + sportsbook-only extension month
  const ew = store.wall.ext_window;
  const winSeg = el('div', { class: 'seg', 'data-testid': 'window-filter' });
  const winLabel = (iso) => iso.slice(5, 10).replace('-', '/');
  for (const [k, label] of [['window', `${winLabel(store.wall.window[0])} → ${winLabel(store.wall.window[1])}`], ['ext', ew ? `+ ${winLabel(ew[0])} → ${winLabel(ew[1])} books only` : '+ extension']]) {
    const b = el('button', { 'data-testid': `window-${k}`, disabled: (k === 'ext' && !extGames.length) ? 'disabled' : null }, label);
    b.addEventListener('click', () => { STATE.ext = k === 'ext'; update(); });
    winSeg.append(b);
  }
  const sort = el('select', { class: 'sel', 'data-testid': 'sort' });
  for (const [k, label] of [['ko-desc', 'Kickoff, newest first'], ['ko-asc', 'Kickoff, oldest first'], ['div', 'Largest Pinnacle–Polymarket gap'], ['vol', 'Polymarket volume'], ['swing', 'Largest in-game swing'], ['move', 'Largest pre-game move']]) sort.append(el('option', { value: k }, label));
  sort.value = STATE.sort;
  sort.addEventListener('change', () => { STATE.sort = sort.value; update(); });
  const q = el('input', { class: 'inp', type: 'search', placeholder: 'Find team…', 'data-testid': 'search', value: STATE.q });
  q.addEventListener('input', () => { STATE.q = q.value.trim().toLowerCase(); update(); });
  const count = el('span', { class: 'mono', 'data-testid': 'wall-count', style: 'color:var(--muted);font-size:var(--text-xs);margin-left:auto' });
  const toolbar = el('div', { class: 'toolbar wall-toolbar' }, [chips, el('div', { class: 'group row2' }, [el('span', { class: 'lbl' }, 'Show'), seg, el('span', { class: 'lbl', style: 'margin-left:8px' }, 'Window'), winSeg, el('span', { class: 'lbl', style: 'margin-left:8px' }, 'Sort'), sort, q, count])]);
  // ---- breadth line: true totals from the dataset manifest (per-league census summed)
  const census = store.manifest?.census || {};
  const tot = (k) => Object.values(census).reduce((a, r) => a + (r[k] || 0), 0);
  const nLeagues = Object.values(census).filter((r) => (r.games || 0) > 0).length;
  const fmtN = (n) => n.toLocaleString('en-US');
  const stat = (v, label) => el('span', { class: 'stat' }, [el('b', {}, v), ' ', label]);
  const sweep = store.meta?.sweep_state || 'complete';
  const stats = el('div', { class: 'tape-stats', 'data-testid': 'wall-stats' }, [
    stat(fmtN(games.length), `matched games · ${fmtN(nLeagues)} leagues · ${windowLabel()}`),
    stat(`${fmtN(tot('with_oo_history'))} / ${fmtN(games.length)}`, `with sportsbook history (5 books)${sweep !== 'complete' ? ' · sweep in progress' : ''}`),
    stat(fmtN(tot('oo_entries') + tot('ext_oo_entries')), 'sportsbook price updates'),
    stat(fmtN(tot('pm_samples_all_markets') || tot('pm_samples')), `Polymarket price samples · ${fmtN(tot('pm_markets'))} markets · ${fmtN(tot('with_pm_history'))} games`),
    stat(fmtUSD(tot('pm_volume_ml')), 'Polymarket moneyline volume'),
    stat(fmtN(tot('plays')), `plays with wall clocks · ${fmtN(tot('with_plays'))} games`),
    extGames.length ? stat(`+ ${fmtN(extGames.length)}`, `sportsbook-only games, ${ew[0].slice(0, 10)} → ${ew[1].slice(0, 10)}`) : null,
    el('span', { class: 'stat dimtx' }, 'OpticOdds · Polymarket · Sportradar'),
  ].filter(Boolean));

  // 4-Card Empirical Headline Findings Strip (instant orientation at 1x wide view)
  const hlStrip = el('div', { class: 'headline-strip', 'data-testid': 'headline-strip' });
  hlStrip.innerHTML = `
    <a class="hl-card" href="#/game/nfl:2026101240603BF9" data-testid="hl-card-game">
      <div class="hl-eyebrow"><span>01 · Hero Game Replay</span><span class="hl-cta">Inspect →</span></div>
      <div class="hl-val">BAL 30–23 ATL (OT)</div>
      <div class="hl-sub">74% open → 12% Q4 low → 99.95% OT across 1,693 ticks & 15 plays</div>
    </a>
    <a class="hl-card hl-pm" href="#/discovery" data-testid="hl-card-discovery">
      <div class="hl-eyebrow"><span>02 · Who Moves First?</span><span class="hl-cta">471 Events →</span></div>
      <div class="hl-val">Books 72.9% · PM 27.1%</div>
      <div class="hl-sub">Books led 153 of 210 moves ≥ 3 pp · median PM lag 10.2 min</div>
    </a>
    <a class="hl-card hl-pos" href="#/scoreboard" data-testid="hl-card-scoreboard">
      <div class="hl-eyebrow"><span>03 · Closing Calibration</span><span class="hl-cta">Scoreboard →</span></div>
      <div class="hl-val">0.2093 Pin vs 0.2092 PM</div>
      <div class="hl-sub">Brier dead heat (363 common games) · 96% within 2 pp (N = 889)</div>
    </a>
    <a class="hl-card hl-neg" href="#/lab" data-testid="hl-card-lab">
      <div class="hl-eyebrow"><span>04 · Arbitrage vs Placebo</span><span class="hl-cta">Backtest Lab →</span></div>
      <div class="hl-val">+$0.0096/$1 Real (p = 0.994)</div>
      <div class="hl-sub">197 late-lag bets (θ = 2 pp) trail 500-shuffle placebo (+$0.1317)</div>
    </a>
  `;

  // ---- canvas
  const scroll = el('div', { class: 'wall-scroll', 'data-testid': 'wall-scroll' });
  const spacer = el('div', { class: 'wall-spacer' });
  const canvas = el('canvas', { class: 'wall-canvas', 'data-testid': 'wall-canvas', 'aria-label': 'Wall of game strips' });
  spacer.append(canvas);
  scroll.append(spacer);
  page.append(stats, hlStrip, toolbar, scroll);

  let visible = [], cols = 1, stripW = 150, stripH = 72, gap = 8, pad = 12, hover = -1, ctx = null, W = 0, H = 0;

  function filtered() {
    let list = (STATE.ext ? games.concat(extGames) : games).filter((g) => STATE.leagues.has(g.lg));
    if (STATE.source === 'both') list = list.filter((g) => g.pin != null && g.pm.t1m != null);
    if (STATE.source === 'pm') list = list.filter((g) => g.pin == null);
    if (STATE.q) list = list.filter((g) => g.search.includes(STATE.q));
    const s = STATE.sort;
    const key = { 'ko-desc': (g) => -g.ko, 'ko-asc': (g) => g.ko, div: (g) => -(g.div ?? -1), vol: (g) => -g.vol, swing: (g) => -(g.pmin ? g.pmin.max - g.pmin.min : -1), move: (g) => -(g.spm && g.spm[0] != null && g.pm.t1m != null ? Math.abs(g.pm.t1m - g.spm[0]) : -1) }[s];
    return list.slice().sort((a, b) => key(a) - key(b) || a.ko - b.ko);
  }
  function layout() {
    W = scroll.clientWidth; H = scroll.clientHeight;
    const target = W < 520 ? 150 : 188;
    cols = Math.max(1, Math.floor((W - pad * 2 + gap) / (target + gap)));
    stripW = Math.floor((W - pad * 2 - gap * (cols - 1)) / cols);
    const rows = Math.ceil(visible.length / cols);
    spacer.style.height = Math.max(H, rows * (stripH + gap) + pad * 2) + 'px';
    ctx = sizeCanvas(canvas, W, H);
  }
  function update() {
    visible = filtered();
    for (const b of chips.querySelectorAll('.chip')) { const lg = b.dataset.testid.replace('chip-', ''); b.classList.toggle('on', lg === 'all' ? STATE.leagues.size === LEAGUES.length : STATE.leagues.has(lg) && STATE.leagues.size !== LEAGUES.length); }
    for (const b of seg.querySelectorAll('button')) b.classList.toggle('on', b.dataset.testid === `source-${STATE.source}`);
    for (const b of winSeg.querySelectorAll('button')) b.classList.toggle('on', b.dataset.testid === `window-${STATE.ext ? 'ext' : 'window'}`);
    const both = visible.filter((g) => g.pin != null && g.pm.t1m != null).length;
    const withBooks = visible.filter((g) => g.oo).length;
    count.textContent = `${fmtN(visible.length)} strips · ${fmtN(withBooks)} with sportsbook history · ${fmtN(both)} with both sources`;
    layout();
    scroll.scrollTop = 0;
    draw();
  }
  function stripAt(x, y) {
    const sy = y + scroll.scrollTop - pad, sx = x - pad;
    if (sx < 0 || sy < 0) return -1;
    const c = Math.floor(sx / (stripW + gap)), r = Math.floor(sy / (stripH + gap));
    if (c >= cols || sx - c * (stripW + gap) > stripW || sy - r * (stripH + gap) > stripH) return -1;
    const i = r * cols + c;
    return i < visible.length ? i : -1;
  }
  function draw() {
    if (!ctx) return;
    const t0 = performance.now();
    ctx.clearRect(0, 0, W, H);
    const top = scroll.scrollTop;
    const r0 = Math.max(0, Math.floor((top - pad) / (stripH + gap))), r1 = Math.ceil((top + H - pad) / (stripH + gap));
    for (let r = r0; r <= r1; r++) for (let c = 0; c < cols; c++) {
      const i = r * cols + c;
      if (i >= visible.length) break;
      drawStrip(ctx, visible[i], pad + c * (stripW + gap), pad + r * (stripH + gap) - top, stripW, stripH, i === hover);
    }
    if (!visible.length) {
      ctx.fillStyle = '#8b95a3'; ctx.font = '15.5px Geist Mono'; ctx.textAlign = 'center'; ctx.fillText('No games match these filters', W / 2, H / 2);
    }
    wallCount = visible.length;
    window.__tapeWallDrawMs = performance.now() - t0;
  }
  scroll.addEventListener('scroll', () => requestAnimationFrame(draw), { passive: true });
  const ro = new ResizeObserver(() => { layout(); draw(); });
  ro.observe(scroll);
  canvas.addEventListener('mousemove', (ev) => {
    const rect = canvas.getBoundingClientRect();
    const i = stripAt(ev.clientX - rect.left, ev.clientY - rect.top);
    if (i !== hover) { hover = i; draw(); canvas.style.cursor = i >= 0 ? 'pointer' : 'default'; }
    if (i >= 0) showTip(ev.clientX, ev.clientY, tipHtml(visible[i])); else hideTip();
  });
  canvas.addEventListener('mouseleave', () => { hover = -1; hideTip(); draw(); });
  canvas.addEventListener('click', (ev) => {
    const rect = canvas.getBoundingClientRect();
    const i = stripAt(ev.clientX - rect.left, ev.clientY - rect.top);
    if (i >= 0) location.hash = '#/game/' + encodeURIComponent(visible[i].key);
  });
  update();
  window.__tapeWall = { state: STATE, update, count: () => wallCount, visible: () => visible, stripAt: (x, y) => stripAt(x, y), draw, geometry: () => ({ cols, stripW, stripH, gap, pad }) };
  return () => { ro.disconnect(); hideTip(); };
}

function tipHtml(g) {
  const rows = [
    ['Kickoff', fmtTime(g.ko)], ['Final', `${g.an} ${g.as} – ${g.hn} ${g.hs}`],
    ['Pinnacle close (home)', g.pin == null ? 'no sportsbook history yet' : fmtPct(g.pin)], ['Polymarket T−1 min (home)', g.pm.t1m == null ? '—' : fmtPct(g.pm.t1m)],
    ['Max gap, last 24 h', g.div == null ? '—' : fmtPct(g.div)], ['Polymarket ML volume', fmtUSD(g.vol)], ['Match tier', g.tier],
  ];
  if (g.ext) { rows[3] = ['Polymarket', 'not fetched (sportsbook-only extension)']; rows[4] = ['Window', 'extension 2026-08-14 → 09-14']; rows[5] = ['Books', (g.books || []).join(', ') || '—']; }
  return `<div class="t-title">${LEAGUE_NAME[g.lg]} · ${g.away} @ ${g.home}${g.ext ? ' · books only' : ''}</div>` + rows.map(([k, v]) => `<div class="t-row"><span>${k}</span><b>${v}</b></div>`).join('');
}

export function drawStrip(ctx, g, x, y, w, h, hot) {
  const acc = LEAGUE_COLOR[g.lg];
  ctx.fillStyle = hot ? '#1a2029' : '#11151b';
  ctx.strokeStyle = hot ? acc : '#222a34';
  ctx.lineWidth = 1;
  roundRect(ctx, x + 0.5, y + 0.5, w - 1, h - 1, 3); ctx.fill(); ctx.stroke();
  ctx.fillStyle = acc; ctx.fillRect(x, y + 6, 2, h - 12);
  // header
  ctx.font = '600 13.5px Geist Mono'; ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
  ctx.fillStyle = '#e6e9ee';
  const label = `${g.away} @ ${g.home}`, score = `${g.as}–${g.hs}`;
  const labelW = ctx.measureText(label).width, scoreW = ctx.measureText(score).width;
  ctx.fillText(label, x + 8, y + 15);
  ctx.textAlign = 'right'; ctx.fillStyle = '#8b95a3';
  ctx.fillText(score, x + w - 6, y + 15);
  if (g.ko) {
    g._kod = g._kod || new Date(g.ko * 1000).toLocaleString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric' });
    ctx.font = '13.5px Geist Mono'; const kw = ctx.measureText(g._kod).width;
    const gl = x + 8 + labelW + 7, gr = x + w - 6 - scoreW - 7;
    if (gr - gl >= kw) { ctx.textAlign = 'center'; ctx.fillText(g._kod, (gl + gr) / 2, y + 15); }
  }
  // sparkline area
  const sx = x + 8, sw = w - 22, sy = y + 21, sh = h - 40;
  ctx.strokeStyle = '#2d3744'; ctx.setLineDash([2, 3]); ctx.beginPath(); ctx.moveTo(sx, sy + sh / 2 + 0.5); ctx.lineTo(sx + sw, sy + sh / 2 + 0.5); ctx.stroke(); ctx.setLineDash([]);
  const n = (g.sp || g.spm || []).length || 48;
  const px = (i) => sx + (sw * i) / (n - 1), py = (p) => sy + sh - p * sh;
  if (g.spm) polyline(ctx, g.spm, px, py, acc, 1.3);
  if (g.sp) polyline(ctx, g.sp, px, py, '#e6e9ee', 1.2);
  // result marker: home win → marker at top right, else bottom right
  ctx.fillStyle = g.hw === 1 ? '#4ade80' : g.hw === 0 ? '#f87171' : '#8b95a3';
  ctx.beginPath(); ctx.arc(x + w - 8, g.hw === 1 ? sy + 2 : sy + sh - 2, 2.2, 0, Math.PI * 2); ctx.fill();
  // footer
  ctx.font = '13.5px Geist Mono'; ctx.textAlign = 'left';
  if (g.pin != null) { ctx.fillStyle = '#e6e9ee'; ctx.fillText(`PIN ${(g.pin * 100).toFixed(1)}`, x + 8, y + h - 6); }
  else { ctx.fillStyle = '#5b6572'; ctx.fillText('PIN —', x + 8, y + h - 6); }
  if (g.pm.t1m != null) { ctx.fillStyle = acc; ctx.textAlign = 'right'; ctx.fillText(`PM ${(g.pm.t1m * 100).toFixed(1)}`, x + w - 6, y + h - 6); }
  else if (g.ext) { ctx.fillStyle = '#5b6572'; ctx.textAlign = 'right'; ctx.fillText('books only', x + w - 6, y + h - 6); }
}
function polyline(ctx, pts, px, py, color, lw) {
  ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineJoin = 'round'; ctx.beginPath();
  let pen = false;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    if (p == null) { pen = false; continue; }
    if (!pen) { ctx.moveTo(px(i), py(p)); pen = true; } else ctx.lineTo(px(i), py(p));
  }
  ctx.stroke();
}
export function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r); ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h); ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r); ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
}
export { BOOK_COLOR };
