// The Tape — entry point: hash router and boot.
import { store, LEAGUE_NAME, el, esc, hideTip, setStatus, windowLabel, loadGame } from './common.js';
import { renderWall } from './wall.js';
import { renderGame } from './game.js';
import { renderDiscovery, renderScoreboard, renderMethods, renderToday } from './panels.js';
import { renderLab } from './lab.js';

const $view = document.getElementById('view');
// Router -------------------------------------------------------------------------
const routes = { wall: renderWall, game: renderGame, discovery: renderDiscovery, scoreboard: renderScoreboard, lab: renderLab, today: renderToday, methods: renderMethods };
let current = { dispose: null };
export function route() {
  const hash = location.hash.replace(/^#\/?/, '') || 'wall';
  const [name, ...rest] = hash.split('/');
  const fn = routes[name] || routes.wall;
  if (current.dispose) { try { current.dispose(); } catch {} }
  hideTip();
  $view.innerHTML = '';
  for (const a of document.querySelectorAll('#nav a')) a.classList.toggle('active', a.dataset.route === (routes[name] ? name : 'wall'));
  const page = el('div', { class: 'page' });
  $view.append(page);
  const res = fn(page, decodeURIComponent(rest.join('/')));
  current.dispose = typeof res === 'function' ? res : (res && res.dispose) || null;
}

async function boot() {
  try {
    const [wall, analysis, manifest, meta] = await Promise.all([
      fetch('data/wall.json').then((r) => r.json()), fetch('data/analysis.json').then((r) => r.json()), fetch('data/manifest.json').then((r) => r.json()), fetch('data/meta.json').then((r) => r.json()),
    ]);
    store.wall = wall; store.analysis = analysis; store.manifest = manifest; store.meta = meta;
    for (const g of wall.games.concat(wall.ext_games || [])) { g.label = `${g.away} @ ${g.home}`; g.search = `${g.an} ${g.hn} ${g.away} ${g.home} ${LEAGUE_NAME[g.lg]}`.toLowerCase(); }
    const nBoth = wall.games.filter((g) => g.pin != null && g.pm.t1m != null).length;
    setStatus(`${wall.games.length.toLocaleString('en-US')} games · ${nBoth.toLocaleString('en-US')} with both sources · ${windowLabel()}`, meta.tier);
    window.addEventListener('hashchange', route);
    route();
    window.__tape = { store, route, loadGame, ready: true };
    document.dispatchEvent(new CustomEvent('tape:ready'));
  } catch (e) {
    setStatus('failed to load data');
    $view.innerHTML = `<div class="page"><div class="panel"><h2>Data failed to load</h2><p>${esc(e.message)}</p></div></div>`;
  }
}
boot();
