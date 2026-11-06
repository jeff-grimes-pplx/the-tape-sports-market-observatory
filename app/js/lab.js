// Backtest lab: recomputes the fee-aware strategies in the browser from wall.json (no network).
import { store, LEAGUES, LEAGUE_NAME, LEAGUE_COLOR, el, esc, fmtPct, fmtSigned, fmtNum, fmtTime, rng, windowLabel, sizeCanvas } from './common.js';
import { lineChart, FONT } from './charts.js';

const LAB = { strategy: 'fade_late_move', theta: 0.02, entry: 't10m', leagues: new Set(LEAGUES), fees: true, bootstrap: 2000, shuffles: 500 };
const ENTRY_MAX_AGE = { t6h: 120, t1h: 60, t10m: 20 };
const ENTRY_LABEL = { t6h: 'T−6 h', t1h: 'T−1 h', t10m: 'T−10 min' };

const LAB_PRESETS = [
  {
    id: 'fade_2pp',
    label: '01 · Fade Late Move (θ = 2 pp, T−10m, Fees On) · N=197 · +$0.0096',
    strategy: 'fade_late_move',
    theta: 0.02,
    entry: 't10m',
    fees: true,
  },
  {
    id: 'follow_2pp_10m',
    label: '02 · Follow Pinnacle 1h Out (θ = 2 pp, T−1h, Fees On) · N=36 · −$0.0403',
    strategy: 'follow_pinnacle',
    theta: 0.02,
    entry: 't1h',
    fees: true,
  },
  {
    id: 'follow_3pp_1h',
    label: '03 · Follow Pinnacle 6h Out (θ = 2 pp, T−6h, Fees On) · N=38 · −$0.2115',
    strategy: 'follow_pinnacle',
    theta: 0.02,
    entry: 't6h',
    fees: true,
  },
  {
    id: 'fade_2pp_nofee',
    label: '04 · Zero-Fee Counterfactual (Fade θ = 2 pp, Fees Off) · N=197 · +$0.0251',
    strategy: 'fade_late_move',
    theta: 0.02,
    entry: 't10m',
    fees: false,
  },
];

export function settle(q, win, rate) { const shares = 1 / q; const fee = shares * rate * q * (1 - q); return { q, shares, fee, win, pnl: shares * win - 1 - fee }; }

export function runStrategy(games, opt) {
  const rate = (w) => (opt.fees ? (w.fee ?? 0) : 0);
  const bets = [];
  const ws = games.filter((w) => opt.leagues.has(w.lg) && w.hw != null && w.fee != null).sort((a, b) => a.ko - b.ko);
  if (opt.strategy === 'follow_pinnacle') {
    const maxAge = ENTRY_MAX_AGE[opt.entry];
    for (const w of ws) {
      const pin = w.pin_at?.[opt.entry], pm = w.pm?.[opt.entry], age = w.pma?.[opt.entry];
      if (pin == null || pm == null || age == null || age > maxAge || pm <= 0.005 || pm >= 0.995) continue;
      const edge = pin - pm;
      let b, side;
      if (edge >= opt.theta) { b = settle(pm, w.hw, rate(w)); side = 'home'; }
      else if (-edge >= opt.theta) { b = settle(1 - pm, 1 - w.hw, rate(w)); side = 'away'; }
      else continue;
      bets.push({ ...b, key: w.key, lg: w.lg, side, edge, ko: w.ko, label: `${w.away} @ ${w.home}` });
    }
  } else {
    for (const w of ws) {
      const c6 = w.cons_at?.t6h, c10 = w.cons_at?.t10m, pm = w.pm?.t10m, age = w.pma?.t10m;
      if (c6 == null || c10 == null || pm == null || age == null || age > 20 || pm <= 0.005 || pm >= 0.995) continue;
      const mv = c10 - c6;
      let b, side;
      if (mv >= opt.theta) { b = settle(1 - pm, 1 - w.hw, rate(w)); side = 'away'; }
      else if (-mv >= opt.theta) { b = settle(pm, w.hw, rate(w)); side = 'home'; }
      else continue;
      bets.push({ ...b, key: w.key, lg: w.lg, side, edge: mv, ko: w.ko, label: `${w.away} @ ${w.home}` });
    }
  }
  return bets;
}

export function summarize(bets, opt = {}) {
  const n = bets.length;
  if (!n) return { n: 0 };
  const pnls = bets.map((b) => b.pnl);
  const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
  const roi = mean(pnls);
  // bootstrap CI (percentile), seeded
  const r1 = rng(opt.seed ?? 9); const stats = [];
  for (let i = 0; i < (opt.bootstrap ?? 2000); i++) { let s = 0; for (let j = 0; j < n; j++) s += pnls[Math.floor(r1() * n)]; stats.push(s / n); }
  stats.sort((a, b) => a - b);
  const q = (a, p) => a[Math.min(a.length - 1, Math.max(0, Math.round(p * (a.length - 1))))];
  // drawdown
  let cum = 0, peak = 0, mdd = 0; const curve = [];
  for (const x of pnls) { cum += x; peak = Math.max(peak, cum); mdd = Math.min(mdd, cum - peak); curve.push(cum); }
  // label-shuffled placebo
  const r2 = rng(opt.seed2 ?? 17); const wins = bets.map((b) => b.win); const rois = [];
  for (let s = 0; s < (opt.shuffles ?? 500); s++) {
    for (let i = wins.length - 1; i > 0; i--) { const j = Math.floor(r2() * (i + 1)); [wins[i], wins[j]] = [wins[j], wins[i]]; }
    let tot = 0; for (let i = 0; i < n; i++) tot += bets[i].shares * wins[i] - 1 - bets[i].fee; rois.push(tot / n);
  }
  rois.sort((a, b) => a - b);
  const pval = rois.filter((r) => r >= roi).length / rois.length;
  return { n, hit: mean(bets.map((b) => b.win)), roi, ci: [q(stats, 0.025), q(stats, 0.975)], mdd, fees: bets.reduce((a, b) => a + b.fee, 0), roiBefore: mean(bets.map((b) => b.pnl + b.fee)), avgPrice: mean(bets.map((b) => b.q)), curve, placebo: { mean: mean(rois), lo: q(rois, 0.025), hi: q(rois, 0.975), p: pval, rois } };
}

export function renderLab(page) {
  const games = store.wall.games;
  const presetsBar = el('div', { class: 'moments-bar', 'data-testid': 'lab-presets', style: 'margin-bottom:8px' }, [
    el('span', { class: 'm-lbl' }, 'Empirical Strategy Presets'),
  ]);
  const controls = el('div', { class: 'controls panel' });
  const results = el('div', { class: 'grid', style: 'align-content:start' });
  page.append(presetsBar, el('div', { class: 'lab' }, [controls, results]));

  const ctl = (label, node) => el('label', { class: 'ctl' }, [el('span', {}, label), node]);
  const stratSel = el('select', { class: 'sel', 'data-testid': 'lab-strategy' }, [el('option', { value: 'follow_pinnacle' }, 'Follow Pinnacle'), el('option', { value: 'fade_late_move' }, 'Fade the late move')]);
  const stratDesc = el('div', { class: 'desc', 'data-testid': 'lab-strategy-desc' }, '');
  const STRAT_DESC = { follow_pinnacle: 'Buy the Polymarket side that Pinnacle\'s no-vig probability puts at least θ above the Polymarket price at entry.', fade_late_move: 'When the sportsbook consensus moved by at least θ between T−6 h and T−10 min, buy the other side on Polymarket at T−10 min.' };

  const THETAS = [0.02, 0.03, 0.05, 0.08];
  const thetaSel = el('input', { type: 'range', min: '0', max: '3', step: '1', class: 'range', 'data-testid': 'lab-theta', 'aria-label': 'Threshold θ (2, 3, 5 or 8 pp)', title: 'Threshold θ: 2, 3, 5 or 8 pp' });
  const thetaOut = el('span', { class: 'range-val', 'data-testid': 'lab-theta-value' }, '');
  const thetaStops = el('datalist', { id: 'lab-theta-stops' }, THETAS.map((t, i) => el('option', { value: String(i), label: `${(t * 100).toFixed(0)} pp` })));
  thetaSel.setAttribute('list', 'lab-theta-stops');
  const thetaWrap = el('div', { class: 'range-wrap inline', 'data-testid': 'lab-theta-wrap' }, [el('span', { class: 'range-label' }, 'θ'), thetaSel, thetaOut, thetaStops]);
  const entrySel = el('select', { class: 'sel', 'data-testid': 'lab-entry' }, Object.entries(ENTRY_LABEL).map(([k, v]) => el('option', { value: k }, `${v} (sample age ≤ ${ENTRY_MAX_AGE[k]} min)`)));
  const feeSeg = el('div', { class: 'seg', 'data-testid': 'lab-fees' }, [el('button', { 'data-fee': '1' }, 'Taker fees on'), el('button', { 'data-fee': '0' }, 'Fees off')]);
  const lgWrap = el('div', { class: 'group', 'data-testid': 'lab-leagues' });
  for (const lg of LEAGUES) { const b = el('button', { class: 'chip', style: `--chip:${LEAGUE_COLOR[lg]}`, 'data-lg': lg }, LEAGUE_NAME[lg]); b.addEventListener('click', () => { LAB.leagues.has(lg) ? LAB.leagues.delete(lg) : LAB.leagues.add(lg); if (!LAB.leagues.size) LAB.leagues = new Set(LEAGUES); run(); }); lgWrap.append(b); }
  const allBtn = el('button', { class: 'btn' }, 'All leagues'); allBtn.addEventListener('click', () => { LAB.leagues = new Set(LEAGUES); run(); });

  for (const p of LAB_PRESETS) {
    const btn = el('button', { class: 'moment-btn', 'data-pid': p.id, 'data-testid': `preset-${p.id}` }, p.label);
    btn.addEventListener('click', () => {
      LAB.strategy = p.strategy;
      LAB.theta = p.theta;
      LAB.entry = p.entry;
      LAB.fees = p.fees;
      LAB.leagues = new Set(LEAGUES);
      stratSel.value = LAB.strategy;
      thetaSel.value = String(Math.max(0, THETAS.indexOf(LAB.theta)));
      entrySel.value = LAB.entry;
      run();
    });
    presetsBar.append(btn);
  }

  stratSel.value = LAB.strategy; thetaSel.value = String(Math.max(0, THETAS.indexOf(LAB.theta))); entrySel.value = LAB.entry;
  stratSel.addEventListener('change', () => {
    LAB.strategy = stratSel.value;
    if (LAB.strategy === 'fade_late_move') { LAB.entry = 't10m'; entrySel.value = 't10m'; }
    run();
  });
  thetaSel.addEventListener('input', () => { LAB.theta = THETAS[parseInt(thetaSel.value, 10)]; run(); });
  entrySel.addEventListener('change', () => { LAB.entry = entrySel.value; run(); });
  for (const b of feeSeg.querySelectorAll('button')) b.addEventListener('click', () => { LAB.fees = b.dataset.fee === '1'; run(); });
  controls.append(el('h2', {}, 'Backtest lab'), el('p', {}, 'Recomputed in your browser from the loaded dataset; no network requests. $1 per bet, hold to resolution, fill at the sampled Polymarket price; taker fee = shares × rate × p(1−p) charged at entry. Historical description only.'),
    ctl('Strategy', el('div', {}, [stratSel, stratDesc])), ctl('Entry checkpoint', entrySel), ctl('Fees', feeSeg), ctl('Leagues (click to toggle)', el('div', {}, [lgWrap, allBtn])));

  const head = el('div', { class: 'panel', 'data-testid': 'lab-head' });
  const eqCap = el('div', { class: 'cap' });
  const eq = el('canvas', { 'data-testid': 'lab-equity', style: 'height:220px' });
  const eqPanel = el('div', { class: 'panel', 'data-testid': 'lab-equity-panel' }, [el('div', { class: 'panel-head' }, [el('h2', {}, 'Cumulative P&L, $1 stakes'), thetaWrap]), eqCap, eq]);
  const histCap = el('div', { class: 'cap' });
  const hist = el('canvas', { 'data-testid': 'lab-placebo', style: 'height:160px' });
  const histPanel = el('div', { class: 'panel', 'data-testid': 'lab-placebo-panel' }, [el('h2', {}, 'Placebo distribution of ROI'), histCap, hist]);
  const tbl = el('div', { class: 'table-wrap' });
  results.append(head, el('div', { class: 'grid lab-charts' }, [eqPanel, histPanel]), el('div', { class: 'panel' }, [el('h2', {}, 'Bets'), el('div', { class: 'cap' }, 'every bet in kickoff order; click a game to open its tape'), tbl]));
  let frame = 0;

  function run() {
    if (LAB.strategy === 'fade_late_move') { LAB.entry = 't10m'; entrySel.value = 't10m'; }
    stratSel.value = LAB.strategy;
    thetaSel.value = String(Math.max(0, THETAS.indexOf(LAB.theta)));
    stratDesc.textContent = STRAT_DESC[LAB.strategy]; thetaOut.textContent = `θ = ${(LAB.theta * 100).toFixed(0)} pp`;
    for (const b of feeSeg.querySelectorAll('button')) b.classList.toggle('on', (b.dataset.fee === '1') === LAB.fees);
    for (const b of lgWrap.querySelectorAll('.chip')) b.classList.toggle('on', LAB.leagues.has(b.dataset.lg));
    for (const b of presetsBar.querySelectorAll('.moment-btn')) {
      const p = LAB_PRESETS.find((x) => x.id === b.dataset.pid);
      b.classList.toggle('active', Boolean(p && p.strategy === LAB.strategy && p.theta === LAB.theta && p.entry === LAB.entry && p.fees === LAB.fees && LAB.leagues.size === LEAGUES.length));
    }
    entrySel.disabled = LAB.strategy !== 'follow_pinnacle';
    const t0 = performance.now();
    const bets = runStrategy(games, LAB);
    const s = summarize(bets, { bootstrap: LAB.bootstrap, shuffles: LAB.shuffles });
    const ms = performance.now() - t0;
    const lgLabel = LAB.leagues.size === LEAGUES.length ? 'all leagues' : [...LAB.leagues].map((l) => LEAGUE_NAME[l]).join(', ');
    const title = `${LAB.strategy === 'follow_pinnacle' ? `Follow Pinnacle · θ ${(LAB.theta * 100).toFixed(0)} pp · entry ${ENTRY_LABEL[LAB.entry]}` : `Fade the late move · θ ${(LAB.theta * 100).toFixed(0)} pp · entry T−10 min`} · ${LAB.fees ? 'taker fees on' : 'fees off'} · ${lgLabel}`;
    const kpis = el('div', { class: 'kpis', 'data-testid': 'lab-kpis' });
    const kpi = (k, v, sub) => el('div', { class: 'kpi' }, [el('div', { class: 'k' }, k), el('div', { class: 'v' }, v), sub ? el('div', { class: 's' }, sub) : null]);
    const eligible = games.filter((w) => LAB.leagues.has(w.lg) && w.hw != null && w.fee != null).length;
    window.__tapeLab = { state: LAB, bets, summary: s };
    head.innerHTML = '';
    const my = ++frame;
    if (!s.n) {
      kpis.append(kpi('Bets (N)', '0', 'no game met the entry rule'));
      head.append(el('h2', { 'data-testid': 'lab-title' }, title), el('div', { class: 'cap' }, `${windowLabel()} · N = 0 bets · ${eligible} eligible games`), kpis);
      eqCap.textContent = 'N = 0 · no bets at this threshold'; histCap.textContent = 'N = 0';
      tbl.innerHTML = '';
      requestAnimationFrame(() => {
        if (my !== frame) return;
        eq.style.width = ''; const ctx = sizeCanvas(eq, eq.clientWidth || 400, 220); ctx.font = FONT; ctx.fillStyle = '#8b95a3'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('no game met the entry rule', (eq.clientWidth || 400) / 2, 110);
        hist.style.width = ''; sizeCanvas(hist, hist.clientWidth || 400, 160);
      });
      return;
    }
    const beatsPlacebo = s.placebo.p < 0.05 && s.roi > s.placebo.mean;
    const verdict = el('div', { class: 'verdict-banner', 'data-testid': 'lab-verdict' });
    verdict.innerHTML = `<span class="vb-tag" style="color:${beatsPlacebo ? 'var(--pos)' : 'var(--neg)'}">${beatsPlacebo ? 'Placebo Check: p < 0.05' : `Fails Placebo Check (p = ${s.placebo.p.toFixed(3)})`}</span><span>Observed ROI <b>${fmtSigned(s.roi, 4)}</b> per $1 (${s.n} bets) vs. 500-shuffle placebo mean <b>${fmtSigned(s.placebo.mean, 4)}</b> (95% band ${fmtSigned(s.placebo.lo, 3)} … ${fmtSigned(s.placebo.hi, 3)}). ${LAB.fees ? `Polymarket taker fees cost $${fmtNum(s.fees, 3)} (${fmtSigned(s.roi - s.roiBefore, 4)} per $1).` : 'Taker fees disabled (counterfactual).'}</span>`;

    kpis.append(kpi('Bets (N)', String(s.n)), kpi('ROI per $1', fmtSigned(s.roi, 4), `95% CI ${fmtSigned(s.ci[0], 3)} … ${fmtSigned(s.ci[1], 3)} (bootstrap)`), kpi('Placebo ROI', fmtSigned(s.placebo.mean, 4), `shuffled labels 2.5–97.5%: ${fmtSigned(s.placebo.lo, 3)} … ${fmtSigned(s.placebo.hi, 3)} · one-sided p = ${s.placebo.p.toFixed(3)}`), kpi('Hit rate', fmtPct(s.hit)), kpi('Max drawdown', fmtNum(s.mdd, 3) + ' $', 'cumulative, bets in kickoff order'), kpi('Fees paid', fmtNum(s.fees, 3) + ' $', `ROI before fees ${fmtSigned(s.roiBefore, 4)}`));
    head.append(el('h2', { 'data-testid': 'lab-title' }, title), el('div', { class: 'cap' }, `${windowLabel()} · N = ${s.n} bets · ${eligible} eligible games · computed in ${ms.toFixed(0)} ms, offline`), verdict, kpis);
    eqCap.textContent = `N = ${s.n} · band = 2.5–97.5% of ${LAB.shuffles} label-shuffled placebo runs`;
    eqCap.title = `${windowLabel()} · shaded band = 2.5–97.5% of ${LAB.shuffles} label-shuffled placebo runs (final value scaled along the path)`;
    histCap.textContent = `${LAB.shuffles} label shuffles, same ${s.n} bets · dashed = observed ROI`;
    histCap.title = `${LAB.shuffles} shuffles of outcome labels across the same ${s.n} bets · dashed = observed ROI`;
    tbl.innerHTML = `<table><thead><tr><th class="l">kickoff (UTC)</th><th class="l">game</th><th class="l">league</th><th class="l">side</th><th>${LAB.strategy === 'follow_pinnacle' ? 'Pinnacle − PM' : 'consensus move'}</th><th>price</th><th>fee</th><th>won</th><th>P&L</th></tr></thead><tbody>${bets.map((b) => `<tr><td class="l">${fmtTime(b.ko, { utcOnly: true })}</td><td class="l"><a href="#/game/${encodeURIComponent(b.key)}">${esc(b.label)}</a></td><td class="l">${LEAGUE_NAME[b.lg]}</td><td class="l">${b.side}</td><td>${fmtSigned(b.edge * 100, 1)} pp</td><td>${fmtPct(b.q)}</td><td>${fmtNum(b.fee, 4)}</td><td>${b.win ? 'yes' : 'no'}</td><td class="${b.pnl >= 0 ? 'pos' : 'neg'}">${fmtSigned(b.pnl, 3)}</td></tr>`).join('')}</tbody></table>`;
    requestAnimationFrame(() => {
      if (my !== frame) return;
      const pts = s.curve.map((v, i) => [i + 1, v]);
      const band = s.curve.map((_, i) => [i + 1, s.placebo.lo * (i + 1), s.placebo.hi * (i + 1)]);
      eq.style.width = ''; hist.style.width = '';
      lineChart(eq, [{ name: 'placebo', color: '#8b95a3', points: [[1, 0], [s.n, 0]], band, lw: 0 }, { name: 'equity', color: '#f2a93b', points: pts, lw: 1.8 }], { height: 220, fmtX: (v) => `bet ${Math.round(v)}`, fmtY: (v) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1) + ' $', xDomain: [1, Math.max(2, s.n)] });
      drawHist(hist, s.placebo.rois, s.roi);
    });
  }
  run();
  return () => { };
}

function drawHist(canvas, values, observed) {
  const w = canvas.clientWidth || 400, h = 160; const ctx = sizeCanvas(canvas, w, h);
  const lo = Math.min(...values, observed), hi = Math.max(...values, observed); const nb = 30; const span = hi - lo || 1;
  const bins = new Array(nb).fill(0); for (const v of values) bins[Math.min(nb - 1, Math.floor((v - lo) / span * nb))]++;
  const mx = Math.max(...bins); const padL = 8, padB = 22, padT = 6;
  const bw = (w - padL * 2) / nb;
  ctx.fillStyle = '#5b6572';
  bins.forEach((c, i) => { const bh = (h - padT - padB) * c / mx; ctx.fillRect(padL + i * bw + 1, h - padB - bh, bw - 2, bh); });
  const x = padL + (observed - lo) / span * (w - padL * 2);
  ctx.strokeStyle = '#f2a93b'; ctx.setLineDash([4, 3]); ctx.beginPath(); ctx.moveTo(x, padT + 17); ctx.lineTo(x, h - padB); ctx.stroke(); ctx.setLineDash([]);
  ctx.font = FONT; ctx.fillStyle = '#8b95a3'; ctx.textBaseline = 'top'; ctx.textAlign = 'left'; ctx.fillText(fmtSigned(lo, 3), padL, h - padB + 6); ctx.textAlign = 'right'; ctx.fillText(fmtSigned(hi, 3), w - padL, h - padB + 6);
  const label = `observed ${fmtSigned(observed, 4)}`; const half = ctx.measureText(label).width / 2 + 2;
  ctx.textAlign = 'center'; ctx.fillStyle = '#f2a93b'; ctx.fillText(label, Math.max(padL + half, Math.min(w - padL - half, x)), padT);
}
