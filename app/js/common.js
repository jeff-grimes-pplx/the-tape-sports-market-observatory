// The Tape — shared constants, data store and helpers (no view imports, so there is no import cycle).

export const LEAGUES = ['nfl', 'ncaaf', 'mlb', 'nba', 'nhl', 'wnba', 'mls', 'epl', 'laliga', 'seriea', 'bundesliga', 'ligue1', 'ucl'];
export const LEAGUE_NAME = { nfl: 'NFL', ncaaf: 'NCAAF', mlb: 'MLB', nba: 'NBA', nhl: 'NHL', wnba: 'WNBA', mls: 'MLS', epl: 'Premier League', laliga: 'La Liga', seriea: 'Serie A', bundesliga: 'Bundesliga', ligue1: 'Ligue 1', ucl: 'Champions League', ufc: 'UFC' };
export const LEAGUE_COLOR = { nfl: '#f2a93b', ncaaf: '#e8718a', mlb: '#5aa9ff', nba: '#ff8a5b', nhl: '#8fd6ff', wnba: '#f49ad1', mls: '#5fd68a', epl: '#b48cff', laliga: '#ff9f43', seriea: '#6fb1ff', bundesliga: '#ff6b6b', ligue1: '#3ccfb0', ucl: '#c58cff' };
export const BOOK_COLOR = { Pinnacle: '#f3f4f6', DraftKings: '#61d095', FanDuel: '#3b9cff', BetMGM: '#d4af37', bet365: '#ffe66d', Caesars: '#b48cff', Polymarket: '#ff7a9a' };
export const BOOK_ORDER = ['Pinnacle', 'DraftKings', 'FanDuel', 'BetMGM', 'bet365', 'Caesars'];

export const store = { wall: null, analysis: null, manifest: null, meta: null, games: new Map(), today: null };

const $status = document.getElementById('status');
const $tip = document.getElementById('tooltip');

export function fmtPct(p, d = 1) { return p == null ? '—' : (p * 100).toFixed(d) + '%'; }
export function fmtPP(p, d = 1) { return p == null ? '—' : ((p >= 0 ? '+' : '−') + Math.abs(p * 100).toFixed(d) + ' pp'); }
export function fmtNum(x, d = 3) { return x == null ? '—' : (x < 0 ? '−' : '') + Math.abs(x).toFixed(d); }
export function fmtSigned(x, d = 3) { return x == null ? '—' : (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(d); }
export function fmtUSD(x) { return x == null ? '—' : '$' + Math.round(x).toLocaleString('en-US'); }
export function probToAmerican(p) { if (p == null || p <= 0 || p >= 1) return '—'; const a = p >= 0.5 ? -100 * p / (1 - p) : 100 * (1 - p) / p; return (a > 0 ? '+' : '−') + Math.abs(Math.round(a)); }
export function probToDecimal(p) { return p == null || p <= 0 ? '—' : (1 / p).toFixed(p < 0.1 ? 1 : 2); }
export function fmtTime(ts, opts = {}) {
  const d = new Date(ts * 1000);
  const utc = d.toISOString().slice(0, 16).replace('T', ' ') + 'Z';
  if (opts.utcOnly) return utc;
  const et = d.toLocaleString('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true });
  return `${utc} · ${et} ET`;
}
export function fmtDate(ts) { return new Date(ts * 1000).toISOString().slice(0, 10); }
export function esc(s) { return String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
export function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k === 'html') e.innerHTML = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v != null) e.setAttribute(k, v);
  }
  for (const c of [].concat(children)) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
export function windowLabel() {
  const w = store.wall?.window || [];
  return w.length ? `${w[0].slice(0, 10)} → ${w[1].slice(0, 10)} UTC` : '';
}
export function showTip(x, y, html) {
  $tip.innerHTML = html; $tip.hidden = false;
  $tip.style.left = '0px'; $tip.style.top = '0px'; // measure at the natural width, not squeezed against the right edge from the previous position
  const r = $tip.getBoundingClientRect();
  // the card opens on the side of the pointer with more room: right of the pointer in the left half of the window, left of it in the right half
  const left = x > window.innerWidth / 2 && x - 14 - r.width >= 8;
  const px = left ? x - 14 - r.width : Math.max(8, Math.min(x + 14, window.innerWidth - r.width - 8)), py = Math.max(8, Math.min(y + 14, window.innerHeight - r.height - 8));
  $tip.style.left = px + 'px'; $tip.style.top = py + 'px';
}
export function hideTip() { $tip.hidden = true; }
export function setStatus(s, tier) {
  $status.textContent = s;
  if (tier != null) { const t = document.createElement('span'); t.className = 'tier'; t.textContent = ` · Tier ${tier}`; $status.appendChild(t); }
}

// Deterministic PRNG (mulberry32) for client-side bootstrap / placebo
export function rng(seed) { let a = seed >>> 0; return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

export async function loadGame(key) {
  if (store.games.has(key)) return store.games.get(key);
  const r = await fetch(`data/games/${key.replace(':', '_')}.json`);
  if (!r.ok) throw new Error(`game ${key} not found`);
  const g = await r.json();
  store.games.set(key, g);
  return g;
}

// Device pixel ratio aware canvas sizing
export function sizeCanvas(canvas, w, h) {
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.max(1, Math.round(w * dpr)); canvas.height = Math.max(1, Math.round(h * dpr));
  canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return ctx;
}

