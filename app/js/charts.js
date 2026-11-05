// Small canvas chart helpers shared by the game view and the analysis panels.
import { sizeCanvas, probToAmerican, probToDecimal } from './common.js';

export const FONT = '13.5px Geist Mono';
export const COLORS = { axis: '#2d3744', grid: '#1b222b', text: '#8b95a3', textStrong: '#e6e9ee' };

export function stepValue(series, t, idx = 0) {
  // series: sorted arrays [t, v...]; returns the row with the largest time <= t (binary search) or null
  let lo = 0, hi = series.length - 1, ans = -1;
  while (lo <= hi) { const mid = (lo + hi) >> 1; if (series[mid][0] <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
  return ans >= 0 ? series[ans] : null;
}

export function timeTicks(t0, t1, width) {
  const span = t1 - t0;
  const target = Math.max(3, Math.floor(width / 110));
  const steps = [60, 300, 600, 900, 1800, 3600, 7200, 3 * 3600, 6 * 3600, 12 * 3600, 86400, 2 * 86400, 7 * 86400];
  let step = steps.find((s) => span / s <= target) || 7 * 86400;
  const out = [];
  for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) out.push(t);
  const fmt = (t) => {
    const d = new Date(t * 1000);
    const hh = String(d.getUTCHours()).padStart(2, '0'), mm = String(d.getUTCMinutes()).padStart(2, '0');
    if (step >= 86400) return `${d.toISOString().slice(5, 10)}`;
    if (hh === '00' && mm === '00') return `${d.toISOString().slice(5, 10)} 00Z`;
    return `${hh}:${mm}Z`;
  };
  return { ticks: out, fmt, step };
}

export function probTicks(unit) {
  if (unit === 'prob') return [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1].map((p) => [p, `${Math.round(p * 100)}%`]);
  const ps = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
  return ps.map((p) => [p, unit === 'american' ? probToAmerican(p) : probToDecimal(p)]);
}

// Draw a step line (hold-last) for rows [[t, v]] within x range; optional sample dots.
export function drawStep(ctx, rows, xOf, yOf, color, lw = 1.5, opts = {}) {
  if (!rows || !rows.length) return;
  ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineJoin = 'miter'; ctx.lineCap = 'butt';
  ctx.beginPath();
  let started = false, lastY = 0, lastX = 0;
  const vIdx = opts.vIdx ?? 1;
  const tMin = opts.tMin ?? -Infinity, tMax = opts.tMax ?? Infinity;
  // find the first row at or before tMin so the line enters from the left edge
  let i0 = 0;
  while (i0 + 1 < rows.length && rows[i0 + 1][0] <= tMin) i0++;
  for (let i = i0; i < rows.length; i++) {
    const t = rows[i][0], v = rows[i][vIdx];
    if (v == null) continue;
    if (t > tMax) break;
    const x = xOf(Math.max(t, tMin)), y = yOf(v);
    if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, lastY); ctx.lineTo(x, y); }
    lastY = y; lastX = x;
  }
  if (started) ctx.lineTo(xOf(Math.min(tMax, opts.tEnd ?? tMax)), lastY);
  ctx.stroke();
  if (opts.dots) {
    ctx.fillStyle = color;
    for (let i = i0; i < rows.length; i++) { const t = rows[i][0]; if (t < tMin) continue; if (t > tMax) break; const v = rows[i][vIdx]; if (v == null) continue; ctx.beginPath(); ctx.arc(xOf(t), yOf(v), 1.6, 0, Math.PI * 2); ctx.fill(); }
  }
}

export function axisLeft(ctx, x, y0, y1, ticks, yOf, opts = {}) {
  ctx.strokeStyle = COLORS.axis; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x + 0.5, y0); ctx.lineTo(x + 0.5, y1); ctx.stroke();
  ctx.font = FONT; ctx.fillStyle = COLORS.text; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
  for (const [v, label] of ticks) {
    const y = Math.round(yOf(v)) + 0.5;
    ctx.strokeStyle = COLORS.grid; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(opts.gridTo ?? x, y); ctx.stroke();
    ctx.fillText(label, x - 6, y);
  }
}

export function axisBottom(ctx, y, x0, x1, ticks, xOf, fmt) {
  ctx.strokeStyle = COLORS.axis; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(x0, y + 0.5); ctx.lineTo(x1, y + 0.5); ctx.stroke();
  ctx.font = FONT; ctx.fillStyle = COLORS.text; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  // a label centred on an edge tick is pulled inside the canvas (it used to lose its last glyph at the right edge, e.g. "bet 9")
  const cw = ctx.canvas.clientWidth || x1 + 12;
  for (const t of ticks) { const x = Math.round(xOf(t)) + 0.5; ctx.strokeStyle = COLORS.axis; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + 4); ctx.stroke(); const label = fmt(t), tw = ctx.measureText(label).width; ctx.fillText(label, Math.min(Math.max(x, tw / 2 + 1), cw - tw / 2 - 1), y + 7); }
}

// Simple bar chart: items [{label, value, color?, ci?:[lo,hi], n?}]
export function barChart(canvas, items, opts = {}) {
  const w = canvas.clientWidth || 400, h = opts.height || 200;
  const ctx = sizeCanvas(canvas, w, h);
  const padL = opts.padL ?? 44, padR = 12, padT = 10, padB = opts.padB ?? 40;
  const vals = items.flatMap((d) => [d.value, ...(d.ci || [])]).filter((v) => v != null && isFinite(v));
  let vmin = Math.min(0, ...vals), vmax = Math.max(0, ...vals);
  if (opts.domain) [vmin, vmax] = opts.domain;
  if (vmax === vmin) vmax = vmin + 1;
  const yOf = (v) => padT + (h - padT - padB) * (1 - (v - vmin) / (vmax - vmin));
  const bw = (w - padL - padR) / Math.max(1, items.length);
  ctx.font = FONT;
  const ticks = niceTicks(vmin, vmax, 5).map((v) => [v, opts.fmt ? opts.fmt(v) : String(v)]);
  axisLeft(ctx, padL, padT, h - padB, ticks, yOf, { gridTo: w - padR });
  items.forEach((d, i) => {
    const x = padL + i * bw + bw * 0.15, bwi = bw * 0.7;
    if (d.value != null) {
      ctx.fillStyle = d.color || '#8b95a3';
      const y0 = yOf(0), y1 = yOf(d.value);
      ctx.fillRect(x, Math.min(y0, y1), bwi, Math.max(1, Math.abs(y1 - y0)));
    }
    if (d.ci && d.ci[0] != null) {
      ctx.strokeStyle = '#e6e9ee'; ctx.lineWidth = 1; const cx = x + bwi / 2;
      ctx.beginPath(); ctx.moveTo(cx, yOf(d.ci[0])); ctx.lineTo(cx, yOf(d.ci[1])); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx - 3, yOf(d.ci[0])); ctx.lineTo(cx + 3, yOf(d.ci[0])); ctx.moveTo(cx - 3, yOf(d.ci[1])); ctx.lineTo(cx + 3, yOf(d.ci[1])); ctx.stroke();
    }
    ctx.fillStyle = COLORS.text; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    const lab = d.label.length > 12 && bw < 60 ? d.label.slice(0, 11) + '…' : d.label;
    ctx.save(); ctx.translate(x + bwi / 2, h - padB + 6);
    if (bw < 48) { ctx.rotate(-Math.PI / 4); ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; }
    ctx.fillText(lab, 0, 0); ctx.restore();
    if (d.n != null && opts.showN) {
      ctx.fillStyle = '#5b6572';
      if (bw < 48) { // rotated category labels: the n= label is a second rotated line parallel to the first, so neither runs through the other
        ctx.save(); ctx.translate(x + bwi / 2, h - padB + 6); ctx.rotate(-Math.PI / 4); ctx.font = '12px Geist Mono'; ctx.textAlign = 'right'; ctx.textBaseline = 'middle'; ctx.fillText(`n=${d.n}`, 0, bw * Math.SQRT1_2 / 2); ctx.restore(); ctx.font = FONT; // halfway between this label's baseline and the next bar's
      } else { ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillText(`n=${d.n}`, x + bwi / 2, h - padB + 20); }
    }
  });
  // zero line
  ctx.strokeStyle = '#3a4653'; ctx.beginPath(); ctx.moveTo(padL, Math.round(yOf(0)) + 0.5); ctx.lineTo(w - padR, Math.round(yOf(0)) + 0.5); ctx.stroke();
}

// Line chart over x values (numbers): series [{name, color, points:[[x,y]], band?:[[x,lo,hi]]}]
export function lineChart(canvas, series, opts = {}) {
  const w = canvas.clientWidth || 400, h = opts.height || 220;
  const ctx = sizeCanvas(canvas, w, h);
  const padR = 12, padT = 10, padB = 28;
  const xs = series.flatMap((s) => s.points.map((p) => p[0]));
  const ys = series.flatMap((s) => s.points.map((p) => p[1]).concat((s.band || []).flatMap((b) => [b[1], b[2]]))).filter((v) => v != null && isFinite(v));
  let xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
  if (opts.xDomain) [xmin, xmax] = opts.xDomain;
  if (opts.yDomain) [ymin, ymax] = opts.yDomain;
  if (ymax === ymin) { ymax += 1; ymin -= 1; }
  const yt = niceTicks(ymin, ymax, 5).map((v) => [v, opts.fmtY ? opts.fmtY(v) : String(v)]);
  // the left padding grows with the widest y label (right-aligned 6 px left of the axis), so a label such as "−10.0 $" is never
  // clipped at the canvas edge (it used to lose its sign when the labels grew past 38 px)
  ctx.font = FONT; const padL = opts.padL ?? Math.max(44, Math.ceil(Math.max(0, ...yt.map(([, l]) => ctx.measureText(l).width))) + 10);
  const xOf = (x) => padL + (w - padL - padR) * (x - xmin) / (xmax - xmin);
  const yOf = (y) => padT + (h - padT - padB) * (1 - (y - ymin) / (ymax - ymin));
  axisLeft(ctx, padL, padT, h - padB, yt, yOf, { gridTo: w - padR });
  const xt = niceTicks(xmin, xmax, Math.floor(w / 80));
  axisBottom(ctx, h - padB, padL, w - padR, xt, xOf, (v) => (opts.fmtX ? opts.fmtX(v) : String(v)));
  if (opts.zeroX) { ctx.strokeStyle = '#3a4653'; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(Math.round(xOf(0)) + 0.5, padT); ctx.lineTo(Math.round(xOf(0)) + 0.5, h - padB); ctx.stroke(); ctx.setLineDash([]); }
  if (ymin < 0 && ymax > 0) { ctx.strokeStyle = '#3a4653'; ctx.beginPath(); ctx.moveTo(padL, Math.round(yOf(0)) + 0.5); ctx.lineTo(w - padR, Math.round(yOf(0)) + 0.5); ctx.stroke(); }
  if (opts.diagonal) { ctx.strokeStyle = '#3a4653'; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(xOf(Math.max(xmin, ymin)), yOf(Math.max(xmin, ymin))); ctx.lineTo(xOf(Math.min(xmax, ymax)), yOf(Math.min(xmax, ymax))); ctx.stroke(); ctx.setLineDash([]); }
  for (const s of series) {
    if (s.band) {
      ctx.fillStyle = s.color + '33'; ctx.beginPath();
      s.band.forEach((b, i) => { const x = xOf(b[0]), y = yOf(b[1]); if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
      for (let i = s.band.length - 1; i >= 0; i--) ctx.lineTo(xOf(s.band[i][0]), yOf(s.band[i][2]));
      ctx.closePath(); ctx.fill();
    }
    ctx.strokeStyle = s.color; ctx.lineWidth = s.lw || 1.5; ctx.beginPath();
    let pen = false;
    for (const [x, y] of s.points) { if (y == null) { pen = false; continue; } const px = xOf(x), py = yOf(y); if (!pen) { ctx.moveTo(px, py); pen = true; } else ctx.lineTo(px, py); }
    ctx.stroke();
    if (s.dots) { ctx.fillStyle = s.color; for (const [x, y] of s.points) { if (y == null) continue; ctx.beginPath(); ctx.arc(xOf(x), yOf(y), s.dotR || 2.5, 0, Math.PI * 2); ctx.fill(); } }
  }
  return { xOf, yOf, ctx, w, h };
}

export function niceTicks(min, max, n) {
  const span = max - min || 1;
  const raw = span / Math.max(1, n);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(Math.abs(v) < 1e-12 ? 0 : +v.toFixed(10));
  return out;
}

export function legendRow(color, name, value, extra) {
  return `<div class="row"><span class="swatch" style="background:${color}"></span><span class="nm">${name}</span><span class="v">${value ?? ''}</span><span class="v">${extra ?? ''}</span></div>`;
}
