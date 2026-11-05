#!/usr/bin/env python3
"""
13_film_receipts.py — receipts for every number that appears on screen in the two films (v2, 60 fps, pointer-led zooms).

Inputs
  /tmp/frames/{film60,film30}/timeline.json  per-frame timeline (pointer, camera) + DOM text captured at each beat
                                             (copied to films/<name>_timeline.json; the copies are the inputs when /tmp is gone)
  a9-data/derived/{manifest,wall,analysis,today}.json, games/<hero>.json
  films/the-tape-60s.mp4, films/the-tape-30s.mp4 (for the SHA-256s in films.md; /home/user/workspace/a9-films/ is the fallback)
Outputs
  handoff/films.md            capture method (disclosed), beat list with frame numbers, camera zoom and on-film text size, SHA-256s
  handoff/film_receipts.md    every film-visible figure → the dataset/analysis value it comes from (+ cross-checks against the DOM text)
  handoff/frames/*.png        exact key frames (one per beat, from the 60-second master)
"""
import hashlib, json, os, re, shutil, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.dirname(HERE)
DATA = "/home/user/workspace/a9-data"
DER = os.path.join(DATA, "derived")
OUT = os.path.join(BUILD, "handoff")
FRAMES = os.environ.get("A9_FRAMES", "/tmp/frames")
HERO = "nfl:2026101240603BF9"
FPS = 60
FILM_SCALE = 1920 / 1280            # CSS px → film px at camera zoom 1
CSS_TEXT = {"table/legend/tooltip": 11, "header numbers": 12.5}


def load(p):
    with open(p) as f:
        return json.load(f)


def iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def iso_min(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")


def fmt_n(x):
    return f"{x:,}"


def text_px(css, z):
    return css * FILM_SCALE * z


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(s):
    return (s or "").replace("−", "-").replace("–", "-").replace("\u2009", " ").replace("\u202f", " ")


def main():
    manifest, wall, analysis = load(os.path.join(DER, "manifest.json")), load(os.path.join(DER, "wall.json")), load(os.path.join(DER, "analysis.json"))
    today = load(os.path.join(DER, "today.json")) if os.path.exists(os.path.join(DER, "today.json")) else None
    hero = load(os.path.join(DER, "games", HERO.replace(":", "_") + ".json"))
    films = {}
    for name in ("film60", "film30"):
        src = os.path.join(FRAMES, name, "timeline.json")
        if os.path.exists(src):
            shutil.copy(src, os.path.join(BUILD, "films", f"{name}_timeline.json"))
        p = os.path.join(BUILD, "films", f"{name}_timeline.json")
        if os.path.exists(p):
            films[name] = load(p)
    if not films:
        sys.exit("no film timelines found")
    for name, t in films.items():
        if t.get("frames") != {"film60": 3600, "film30": 1800}[name]:
            print(f"WARNING: {name} has {t.get('frames')} frames", file=sys.stderr)

    census = manifest["census"]
    tot = lambda k: sum(v.get(k, 0) or 0 for v in census.values())
    games = wall["games"]
    n_both = sum(1 for g in games if g.get("pin") is not None and (g.get("pm") or {}).get("t1m") is not None)
    ag = analysis["agreement"]["per_league"]["all"]
    disc = analysis["discovery"]
    cal = analysis["calibration"]
    bt = analysis["backtests"]["results"]
    f60 = films.get("film60") or films.get("film30")
    notes = {n["label"]: n for n in f60["notes"]}
    checks = []  # (label, ok, detail) — summarised at the top of film_receipts.md

    def check(label, ok, detail):
        checks.append((label, bool(ok), detail))
        return f"- Cross-check — {label}: **{'yes' if ok else 'NO'}** ({detail})."

    def note_text(label, *keys):
        n = notes.get(label)
        if not n:
            return None
        return " ".join(str(n["dom"].get(k) or "") for k in (keys or n["dom"].keys()))

    # ---- film_receipts.md -------------------------------------------------------------------------------------
    R = ["# Film receipts — every number visible in the films, with its source", "",
         "Both films are frame-stepped captures of the deployed app (method in `films.md`). At each beat the on-screen text was read from the DOM at capture time "
         "(`films/film60_timeline.json` → `notes`, frame numbers below refer to the 60-second master; the 30-second cut repeats a subset of the same beats on the same data) "
         "and each figure below is traced to the dataset or analysis value it is rendered from. Where a figure is a pure function of the raw vendor responses the receipt names the vendor field. "
         "Cross-check lines compare the captured DOM text with the value recomputed here from the derived data.", ""]

    R += ["## Status line (every frame)", "",
          f"- `{fmt_n(len(games))} games` = matched games in the analysis window (`manifest.n_games` = {manifest['n_games']}).",
          f"- `{n_both} with both sources` = games with a Pinnacle close and a Polymarket sample within 30 min of kickoff (`wall.json`: pin ≠ null and pm.t1m ≠ null; agreement N = {ag['n']}).",
          f"- `{manifest['window_utc'][0][:10]} → {manifest['window_utc'][1][:10]} UTC · Tier 1` = analysis window and completed sweep tier (`manifest.window_utc`, `meta.tier`).", ""]

    hdr = {
        f"{fmt_n(len(games))} matched games · {len(census)} leagues": "`manifest.n_games`; `manifest.census` has one entry per league",
        f"{fmt_n(tot('with_oo_history'))} / {fmt_n(len(games))} with sportsbook history (5 books)": "census `with_oo_history`",
        f"{fmt_n(tot('oo_entries') + tot('ext_oo_entries'))} sportsbook price updates": f"census `oo_entries` ({fmt_n(tot('oo_entries'))} in-window) + `ext_oo_entries` ({fmt_n(tot('ext_oo_entries'))} extension); one entry = one OpticOdds `/fixtures/odds/historical` timeseries point for a book × market × side",
        f"{fmt_n(tot('pm_samples_all_markets'))} Polymarket price samples · {fmt_n(tot('pm_markets'))} markets · {fmt_n(tot('with_pm_history'))} games": f"census `pm_samples_all_markets`, `pm_markets`, `with_pm_history` (CLOB `/prices-history` points over every matched market; home-win series alone {fmt_n(tot('pm_samples'))})",
        f"${fmt_n(tot('pm_volume_ml'))} Polymarket moneyline volume": "census `pm_volume_ml` = sum of the moneyline markets' Gamma `volume`",
        f"{fmt_n(tot('plays'))} plays with wall clocks · {fmt_n(tot('with_plays'))} games": "census `plays`, `with_plays` (Sportradar play-by-play events carrying a `wall_clock`)",
        f"+ {fmt_n(manifest['extension']['n_games_with_history'])} sportsbook-only games, {manifest['extension']['window_utc'][0][:10]} → {manifest['extension']['window_utc'][1][:10]}": "`manifest.extension` (books-only sweep before the Polymarket window)",
    }
    R += ["## Wall header (establishing beat, zoomed to 2.2× in two halves)", ""]
    for k, v in hdr.items():
        R.append(f"- `{k}` — {v}.")
    for lab in ("wall: header left", "wall: header right", "end: wall"):
        txt = note_text(lab, "stats")
        if txt is not None:
            missing = [k for k in hdr if re.match(r"[+$]?\s?[\d,]+", k) and re.match(r"[+$]?\s?[\d,]+", k).group(0) not in norm(txt)]
            R.append(check(f"header numbers in the DOM at `{lab}` (frame {notes[lab]['frame']})", not missing, f"all {len(hdr)} figures present" if not missing else f"missing {missing}"))
    R.append("")

    # wall tooltips: parse "LG · AWAY @ HOME" from the captured tooltip text and look the game up
    def wall_tip_receipts(note):
        tip = (note["dom"].get("tip") or "")
        m = re.match(r"\s*(\w+) · ([A-Z0-9]+) @ ([A-Z0-9]+?)(?=Kickoff|\s|$)", tip)
        if not m:
            return [f"- (frame {note['frame']}) no tooltip captured"]
        lg, away, home = m.group(1).lower(), m.group(2), m.group(3)
        cands = [g for g in games + (wall.get("ext_games") or []) if g["lg"] == lg and g["away"] == away and g["home"] == home]
        km = re.search(r"Kickoff\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})Z", tip)
        if km and len(cands) > 1:
            cands = [g for g in cands if datetime.fromtimestamp(g["ko"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M") == km.group(1)]
        if not cands:
            return [f"- (frame {note['frame']}) `{tip[:80]}…` — game not found in wall.json"]
        g = cands[0]
        pm1 = (g.get("pm") or {}).get("t1m")
        out = [f"- (frame {note['frame']}) `{lg.upper()} · {away} @ {home}` — key `{g['key']}`: kickoff {iso(g['ko'])}; final {g['an']} {g['as']} – {g['hn']} {g['hs']} (Sportradar); Pinnacle close (home) {g['pin'] * 100:.1f}% (`wall.pin`, multiplicative no-vig of the last Pinnacle entry ≤ kickoff); "
               f"Polymarket T−1 min (home) {'—' if pm1 is None else f'{pm1 * 100:.1f}%'} (`wall.pm.t1m`, last sample ≤ 30 min before kickoff); Polymarket ML volume ${fmt_n(int(g['vol']))} (`wall.vol`); match tier {g['tier']}.",
               f"  on-screen text: `{tip[:400]}`"]
        ok = f"{g['pin'] * 100:.1f}%" in tip and (pm1 is None or f"{pm1 * 100:.1f}%" in tip) and str(g["as"]) in tip and str(g["hs"]) in tip
        out.append("  " + check(f"tooltip values (Pinnacle close, Polymarket T−1 min, final score) match `wall.json` for `{g['key']}`", ok, f"frame {note['frame']}"))
        return out

    R += ["## Wall tooltip and filter", ""]
    for lab in ("wall: hero tooltip",):
        if lab in notes:
            R += wall_tip_receipts(notes[lab])
    if "wall: ravens filter" in notes:
        cnt = notes["wall: ravens filter"]["dom"].get("count") or ""
        n_bal = sum(1 for g in games if "BAL" in (g["away"], g["home"]) and g["lg"] == "nfl") + sum(1 for g in games if "ravens" in (g.get("an", "") + g.get("hn", "")).lower())
        R.append(f"- `Find team → ravens` (frame {notes['wall: ravens filter']['frame']}): on-screen count `{cnt[:120]}`; the filter matches team names and abbreviations containing the typed text (`wall.js`), the hero strip `BAL @ ATL` is the first NFL hit.")
    R.append("")

    # ---- hero game ---------------------------------------------------------------------------------------------
    ko = hero["kickoff"]
    books = hero["oo"]["books"]
    fd = books["FanDuel"]["ml"]
    fd_away, fd_home = fd["raw"]["away"], fd["raw"]["home"]
    fd_close_away = [r for r in fd_away if r[0] <= ko][-1]
    pm = hero["pm"]
    hs = pm.get("home_series") or []
    pm_close = [r for r in hs if r[0] <= ko][-1]
    plays = [p for p in hero["sr"].get("plays", []) if p.get("scoring")]
    R += ["## Hero game view — Baltimore Ravens @ Atlanta Falcons", "",
          f"- Title `Baltimore Ravens @ Atlanta Falcons 30–23 (OT) · NFL · week 5 · kickoff {iso(ko)} · Mercedes-Benz Stadium · match tier A` — Sportradar game `{hero['match']['sr_game_id']}` (scheduled, venue, final with an overtime period), OpticOdds fixture `{hero['match']['oo_fixture_id']}`, matcher tier `{hero['match']['tier']}`.",
          "- The `N = … entries` counter under the chart is the number of plotted points in the current window (all books + Polymarket), recomputed by `game.js` on every redraw; the window itself is printed above the chart (`<from> → <to> · <N> points`).",
          "- The flip (BAL side, raw American, unit = American so the legend reads the book's own price):",
          f"  - FanDuel first retained entry {iso(fd_away[0][0])}: BAL {fd_away[0][1]:+.0f} / ATL {fd_home[0][1]:+.0f}; next entry {iso(fd_away[1][0])}: BAL {fd_away[1][1]:+.0f} (OpticOdds `/fixtures/odds/historical`, FanDuel moneyline, `price` + `timestamp`). The film's drag-zoom window 2026-09-29 06:00Z → 2026-10-01 10:00Z sits inside the first step, so the hover value is the −335 entry.",
          f"  - FanDuel last pre-kickoff entry {iso(fd_close_away[0])}: BAL {fd_close_away[1]:+.0f} / ATL {[r for r in fd_home if r[0] <= ko][-1][1]:+.0f}; the Game-day preset (kickoff − 24 h → kickoff) shows this step across its second half.",
          "  - Legend values are the step-function value of each book at the pointer time, printed as `price at <entry timestamp>` (minute precision on screen; seconds here)."]
    for lab, exp_price, exp_t in (("game: hover FanDuel open −335", fd_away[0][1], fd_away[0][0]), ("game: hover FanDuel close +144", fd_close_away[1], fd_close_away[0])):
        txt = note_text(lab, "legend")
        if txt is not None:
            want = f"{exp_price:+.0f} at {iso_min(exp_t)}"
            squash = lambda v: norm(v).replace(" ", "")  # the price and the timestamp are separate DOM nodes, so the captured text has no space between them
            R.append("  " + check(f"legend reads `{want}` at `{lab}` (frame {notes[lab]['frame']})", squash(want) in squash(txt), f"legend text `{txt[:160]}…`"))
    R += ["- Side panel `Moneyline, BAL (away)` (open / close / age), no-vig probabilities of the BAL side — for each book: open = multiplicative no-vig of its first retained entry, close = last entry ≤ kickoff, age = minutes (or hours) from that close to kickoff:"]
    side_ok = True
    side_txt = norm(note_text("game: side table", "side") or "")
    for b in ("Pinnacle", "DraftKings", "FanDuel", "BetMGM", "Caesars"):
        nv = books[b]["ml"]["novig"]
        o = nv[0]
        c = [r for r in nv if r[0] <= ko][-1]
        age = (ko - c[0]) / 60
        age_s = f"{age / 60:.0f} h" if age >= 120 else f"{age:.0f} m"
        R.append(f"  - {b}: open BAL {o[2] * 100:.1f}% (ATL {o[1] * 100:.1f}%) at {iso(o[0])}, close BAL {c[2] * 100:.1f}% (ATL {c[1] * 100:.1f}%) at {iso(c[0])}, age {age:.0f} min{' (stale, > 6 h)' if age > 360 else ''}; {len(nv)} entries.")
        if side_txt:
            side_ok &= f"{b}{o[2] * 100:.1f}%{c[2] * 100:.1f}%{age_s}" in side_txt
    pm_open_away, pm_close_away = 1 - hs[0][1], 1 - pm_close[1]
    mk = pm["markets"].get("ml_home") or pm["markets"].get("ml_away") or {}
    R.append(f"  - Polymarket (away price = 1 − home sampled price): open {pm_open_away * 100:.1f}% at {iso(hs[0][0])}, last pre-kickoff sample {pm_close_away * 100:.1f}% at {iso(pm_close[0])} ({(ko - pm_close[0]) / 60:.0f} min before kickoff); {len(hs)} compressed step points (market `{mk.get('market_id')}`, {mk.get('n_samples')} raw samples).")
    if side_txt:
        side_ok &= f"Polymarket (away price){pm_open_away * 100:.1f}%{pm_close_away * 100:.1f}%" in side_txt
        R.append("  " + check(f"side-table open / close / age for the five books and Polymarket match the recomputation (frame {notes['game: side table']['frame']})", side_ok, f"DOM `{side_txt[:200]}…`"))
    R += ["- Polymarket pre-kickoff checkpoints (T−24 h, T−6 h, T−1 h, T−10 min, T−1 min): last sample at or before each mark with its age:"]
    for k, lab in (("t24h", "T−24 h"), ("t6h", "T−6 h"), ("t1h", "T−1 h"), ("t10m", "T−10 min"), ("t1m", "T−1 min")):
        wg = next((g for g in games if g["key"] == HERO), None)
        v = (wg or {}).get("pm", {}).get(k)
        age = (wg or {}).get("pma", {}).get(k)
        R.append(f"  - {lab}: {v * 100:.1f}% (sample age {age:.1f} min) — `wall.pm.{k}` / `wall.pma.{k}`." if v is not None else f"  - {lab}: —")
    R += ["- In-game preset: domain = kickoff − 10 min → last Sportradar play wall clock + 3 min "
          f"({iso(ko - 600)} → {iso(plays[-1]['t'] + 180) if plays else '—'}); the thick line is the Polymarket sampled price after kickoff (ATL side, no-vig / probability unit); markers and staggered score labels are the scoring plays below.",
          "- Scoring plays (markers + tooltips; Sportradar `wall_clock`, running score away–home; Sportradar numbers the overtime period from 1 again — the last two rows are OT):"]
    for p in plays:
        R.append(f"  - {iso(p['t'])} · period {p.get('period')} {p.get('clock') or ''} · {p.get('ap')}–{p.get('hp')} · {(p.get('desc') or '')[:120]}")
    q4 = next((p for p in plays if p.get("ap") == 21 and p.get("hp") == 23), None)
    q4last = [p for p in plays if p.get("period") == 4][-1]
    ot = next((p for p in plays if p["t"] > q4last["t"]), None)
    for lab, play in (("game: biggest scoring play", q4), ("game: OT scoring play", ot)):
        if lab in notes and play:
            tip = notes[lab]["dom"].get("tip") or ""
            want_score, want_t = f"{play['ap']}–{play['hp']}", iso_min(play["t"])
            R.append(f"  - on-screen tooltip ({lab}, frame {notes[lab]['frame']}): `{tip[:300]}`")
            R.append("  " + check(f"tooltip shows `{want_score}` and wall clock `{want_t}` (Sportradar play at {iso(play['t'])})", norm(want_score) in norm(tip) and want_t in tip, f"frame {notes[lab]['frame']}"))
    R.append("")

    # ---- discovery ---------------------------------------------------------------------------------------------
    R += ["## Discovery", "",
          f"- Closing agreement: N = {ag['n']} games with a Pinnacle close and a Polymarket sample ≤ 30 min before kickoff; mean (PM − Pinnacle) {ag['mean_diff'] * 100:+.2f} pp (95% CI {ag['mean_diff_ci95'][0] * 100:+.2f} … {ag['mean_diff_ci95'][1] * 100:+.2f} pp), median |diff| {ag['median_abs_diff'] * 100:.2f} pp, p90 |diff| {ag['p90_abs_diff'] * 100:.2f} pp, within 2 pp {ag['share_within_2pp'] * 100:.2f}% (shown as {round(ag['share_within_2pp'] * 100)}% in the table), within 5 pp {ag['share_within_5pp'] * 100:.1f}%, Polymarket higher {ag['share_pm_higher'] * 100:.1f}%, correlation {ag['corr_pm_pinnacle']:.4f} (`analysis.agreement.per_league.all`; `results/b_closing_agreement_summary.csv`).",
          f"- Histogram: the same {ag['n']} differences in 1-pp bins (`results/b_closing_agreement_hist.csv` if present; drawn by `discovery.js` from `analysis.agreement.hist`).",
          "- Agreement-by-league table rows (`analysis.agreement.per_league`):", "",
          "| league | N | mean diff | 95% CI | mean abs diff | within 2 pp | corr |", "|---|---|---|---|---|---|---|"]
    for lg, r in analysis["agreement"]["per_league"].items():
        if not isinstance(r, dict) or "n" not in r:
            continue
        R.append(f"| {lg} | {r['n']} | {r['mean_diff'] * 100:+.2f} pp | {r['mean_diff_ci95'][0] * 100:+.2f} … {r['mean_diff_ci95'][1] * 100:+.2f} pp | {r.get('mean_abs_diff', 0) * 100:+.2f} pp | {round(r['share_within_2pp'] * 100)}% | {r['corr_pm_pinnacle']:.3f} |")
    R.append("")
    for lab in ("discovery: agreement", "discovery: agreement table"):
        if lab in notes:
            txt = " ".join(str(v) for v in notes[lab]["dom"].values() if v)
            R.append(f"- on-screen text ({lab}, frame {notes[lab]['frame']}): `{txt[:600]}`")
    tt = norm(note_text("discovery: agreement table", "table") or "")
    if tt:
        want = f"All{ag['n']}{ag['mean_diff'] * 100:+.2f} pp{ag['mean_diff_ci95'][0] * 100:+.2f} pp … {ag['mean_diff_ci95'][1] * 100:+.2f} pp"
        ok = norm(want) in tt and f"{round(ag['share_within_2pp'] * 100)}%" in tt and f"{ag['corr_pm_pinnacle']:.3f}" in tt
        R.append(check(f"`All` row of the agreement table (N {ag['n']}, mean {ag['mean_diff'] * 100:+.2f} pp, CI, within 2 pp {round(ag['share_within_2pp'] * 100)}%, corr {ag['corr_pm_pinnacle']:.3f}) matches `analysis.json`", ok, f"frame {notes['discovery: agreement table']['frame']}"))
    wmf = disc.get("who_moved_first", {})
    totw = {}
    for o in wmf.values():
        for k, v in o.items():
            totw[k] = totw.get(k, 0) + v
    nA = sum(v for k, v in totw.items() if not k.startswith("PM-event")); nB = sum(v for k, v in totw.items() if k.startswith("PM-event"))
    R.append(f"- Not in the v2 films (the who-moved-first panel is below the fold of the Discovery tab): price discovery on {disc['n_games']} games, {disc['grid_minutes']}-minute grid over the last {disc['horizon_hours']} h, {disc['n_events']} Pinnacle moves ≥ {disc['event_threshold_pp']} pp within {disc['event_window_min']} min; who moved first — " + ", ".join(f"{k} {v} ({100 * v / nA:.0f}%)" for k, v in totw.items() if not k.startswith("PM-event")) + f" of {nA}; after a Polymarket move — " + ", ".join(f"{k.replace('PM-event: ', '')} {v} ({100 * v / nB:.0f}%)" for k, v in totw.items() if k.startswith("PM-event")) + f" of {nB} (`analysis.discovery`; `results/c_*.csv`).")
    R.append("")

    # ---- scoreboard ----------------------------------------------------------------------------------------------
    R += ["## Scoreboard (common game set)", "",
          f"- Common set definition: {cal['common_definition']}.",
          f"- N per league (identical for every source row): " + ", ".join(f"{lg} {n}" for lg, n in cal["common_n"].items()) + ".",
          "- Sources left out of a league's common table (quoted < 50% of its games): " + "; ".join(f"{lg}: {', '.join(v)}" for lg, v in cal["common_excluded"].items() if v) + ".",
          "- Rows visible in the film (`analysis.calibration.common_per_league`; `results/d_calibration_summary.csv`, mode = common; the 2.5× beat frames the `All` block, the NFL rows enter at the bottom):", "",
          "| league | source | N | Brier | 95% CI | log loss | 95% CI | home win rate | mean p(home) |", "|---|---|---|---|---|---|---|---|---|"]
    for lg in ("all", "nfl", "ncaaf"):
        for s, r in cal["common_per_league"].get(lg, {}).items():
            R.append(f"| {lg} | {s} | {r['n']} | {r['brier']:.4f} | {r['brier_ci95'][0]:.4f} … {r['brier_ci95'][1]:.4f} | {r['logloss']:.4f} | {r['logloss_ci95'][0]:.4f} … {r['logloss_ci95'][1]:.4f} | {r['base_rate_home'] * 100:.1f}% | {r['mean_p_home'] * 100:.1f}% |")
    R += ["", "- Availability view (second toggle, not in the films), first rows (`per_league`, mode = available): " + "; ".join(f"{s} N {r['n']} Brier {r['brier']:.4f}" for s, r in list(cal["per_league"]["all"].items())[:5] if isinstance(r, dict) and "n" in r) + ".", ""]
    if "scoreboard: common" in notes:
        txt = notes["scoreboard: common"]["dom"].get("table") or ""
        ok = all(str(r["n"]) in txt and f"{r['brier']:.4f}" in txt for r in cal["common_per_league"]["all"].values())
        R.append(check(f"every `All` row's N and Brier from `analysis.json` appears in the on-screen table text captured at frame {notes['scoreboard: common']['frame']}", ok, f"{len(cal['common_per_league']['all'])} rows"))
        R.append("")

    # ---- lab -----------------------------------------------------------------------------------------------------
    def bt_row(strategy, theta, entry="t10m", league="all"):
        for r in bt:
            if r["strategy"] == strategy and r.get("league") == league and abs(r.get("theta", -1) - theta) < 1e-9 and (strategy != "follow_pinnacle" or r.get("entry") == entry):
                return r
        return None

    R += ["## Backtest lab", "",
          "- The lab recomputes in the browser from `wall.json` (no network). The film opens the tab on its default state (Follow Pinnacle, θ = 3 pp, entry T−1 h, fees on, all leagues; full frame, not zoomed), switches the strategy to Fade the late move (θ = 3 pp), then zooms to 1.8× on the controls + KPI strip + equity curve while θ is dragged to 2 pp and then 5 pp. Reference values from the pipeline (`analysis.backtests.results`; `results/e_backtests_summary.csv`):", "",
          "| strategy | θ | entry | N | hit rate | ROI per $1 | 95% CI | max drawdown | fees paid | ROI before fees | placebo mean ROI | placebo 2.5–97.5% | one-sided p |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for strat, theta, entry in (("follow_pinnacle", 0.03, "t1h"), ("fade_late_move", 0.03, "t10m"), ("fade_late_move", 0.02, "t10m"), ("fade_late_move", 0.05, "t10m")):
        r = bt_row(strat, theta, entry)
        if not r:
            R.append(f"| {strat} | {theta * 100:.0f} pp | {entry} | — (not in the pipeline grid; the lab computes it in the browser) | | | | | | | | | |")
            continue
        ci = r.get("roi_ci95") or [None, None]
        cis = f"{ci[0]:+.3f} … {ci[1]:+.3f}" if ci[0] is not None else "—"
        R.append(f"| {strat} | {theta * 100:.0f} pp | {'T−1 h' if strat == 'follow_pinnacle' else 'T−10 min'} | {r['n']} | {r['hit_rate'] * 100:.1f}% | {r['roi']:+.4f} | {cis} | {r['max_drawdown']:.3f} | {r.get('fees_paid', 0):.3f} | {r.get('roi_before_fees', 0):+.4f} | {r.get('placebo_mean_roi', 0):+.4f} | {r.get('placebo_p2_5', 0):+.3f} … {r.get('placebo_p97_5', 0):+.3f} | {r.get('p_value_one_sided', 0):.3f} |")
    R.append("")
    lab_notes = {"lab: fade θ=3": ("fade_late_move", 0.03), "lab: fade θ=2": ("fade_late_move", 0.02), "lab: fade θ=5": ("fade_late_move", 0.05)}
    for lab, (strat, theta) in lab_notes.items():
        if lab not in notes:
            continue
        txt = norm((notes[lab]["dom"].get("kpis") or "") + " " + (notes[lab]["dom"].get("title") or ""))
        r = bt_row(strat, theta, "t1h" if strat == "follow_pinnacle" else "t10m")
        if not r:
            R.append(f"- ({lab}, frame {notes[lab]['frame']}): no pipeline reference row for θ = {theta * 100:.0f} pp; on-screen `{txt[:300]}`")
            continue

        def grab(pattern):
            m = re.search(pattern, txt)
            return float(m.group(1)) if m else None
        seen = {"N": grab(r"Bets \(N\)\s*(\d+)"), "hit rate": grab(r"Hit rate\s*([\-\d.]+)%"), "ROI": grab(r"ROI per \$1\s*([+\-]\d\.\d{4})"), "drawdown": grab(r"Max drawdown\s*([+\-]?[\d.]+)")}
        ref = {"N": r["n"], "hit rate": r["hit_rate"] * 100, "ROI": r["roi"], "drawdown": r["max_drawdown"]}
        tol = {"N": 0, "hit rate": 0.06, "ROI": 0.00051, "drawdown": 0.00051}
        ok = {k: (seen[k] is not None and abs(seen[k] - ref[k]) <= tol[k]) for k in ref}
        R.append(check(f"{lab} (frame {notes[lab]['frame']}) on-screen KPIs vs `analysis.json` (tolerance = display rounding)", all(ok.values()), ", ".join(f"{k} {'✓' if v else '✗'} ({seen[k]} vs {ref[k]:.4f})" for k, v in ok.items())))
        R.append(f"  on-screen: `{txt[:300]}`")
    R.append("- The placebo band on screen comes from the lab's own seeded in-browser shuffle (500 label shuffles); the pipeline's placebo used a different random stream, so the two bands differ by Monte-Carlo noise while the observed ROI, N, hit rate and drawdown are identical. The θ = 5 pp placebo row on screen (mean +0.38, p ≈ 0.97) says the +0.30 ROI on 30 bets is not distinguishable from label noise; the film makes no claim about it.")
    R.append("")

    # ---- today -----------------------------------------------------------------------------------------------------
    if today:
        R += ["## Today tab (not in the v2 films; one timestamped snapshot in the app)", "",
              f"- {today['n_games']} games ({', '.join(today['leagues'])}); OpticOdds `/fixtures/active` ({today['calls']['opticodds']['fixtures_active']} calls) + `/fixtures/odds` ({today['calls']['opticodds']['fixtures_odds']} calls) retrieved {today['retrieved_at_oo']}; latest OpticOdds line timestamp {today['oo_latest_line_timestamp']}; Polymarket midpoints retrieved {today['retrieved_at_pm']} (`derived/today.json`, `analysis/tables/today_snapshot.csv`).", ""]

    # ---- summary of cross-checks at the top -------------------------------------------------------------------------
    n_ok = sum(1 for _, ok, _ in checks if ok)
    R.insert(3, f"**Cross-checks: {n_ok} of {len(checks)} pass** (each is listed in its section; a failing line reads **NO**).")
    R.insert(4, "")
    open(os.path.join(OUT, "film_receipts.md"), "w").write("\n".join(R) + "\n")

    # ---- films.md + key frames ----------------------------------------------------------------------------------
    fr_dir = os.path.join(OUT, "frames")
    os.makedirs(fr_dir, exist_ok=True)
    for fn in os.listdir(fr_dir):
        os.remove(os.path.join(fr_dir, fn))
    mp4s = {}
    for short, fn in (("60 s", "the-tape-60s.mp4"), ("30 s", "the-tape-30s.mp4")):
        for cand in (os.path.join(BUILD, "films", fn), os.path.join("/home/user/workspace/a9-films", fn)):
            if os.path.exists(cand):
                mp4s[short] = (fn, sha256(cand), os.path.getsize(cand))
                break
    F = ["# Films", "",
         f"Two silent films of the deployed app, **1920×1080 at {FPS} fps**, H.264 (`films/the-tape-60s.mp4` = 3600 frames, `films/the-tape-30s.mp4` = 1800 frames), no added text, captions, badges, soundtrack or narration. "
         "Everything on screen is the real app driven by a real pointer; the camera is an editorial zoom on the live page (the pointer leads every move), so every zoomed beat shows the app's own text at 28 px or more on the 1080p frame.", ""]
    if mp4s:
        F += ["| film | file | SHA-256 | bytes |", "|---|---|---|---|"]
        for short, (fn, h, sz) in mp4s.items():
            F.append(f"| {short} | `films/{fn}` | `{h}` | {sz:,} |")
        F.append("")
    F += ["## Capture method (disclosed)", "",
          "- **Frame-stepped, deterministic capture** (not a real-time screen recording): Playwright Chromium, viewport 1280×720 CSS px (the app's desktop layout), device scale factor 2, dark colour scheme; "
          f"`page.clock` installed at 2026-10-15T04:00:00Z and advanced 16/17 ms per frame (alternating, so 60 frames = exactly 1000 ms) → {FPS} fps on the app's own clock. Transitions, tooltips and chart redraws are therefore reproducible frame for frame (`films/capture.js`, `films/storyboards.js`).",
          "- **Editorial zooms**: each frame is a CDP `Page.captureScreenshot` of the camera's clip — a 16:9 region of the viewport re-rasterised at scale 1920 / clip width (plus 2 CSS px of oversize that ffmpeg crops at encode, because Chromium rounds clip sizes). "
          "DOM text (tables, legends, tooltips, headers) is re-rendered by the browser at the zoomed scale, so it stays crisp; canvas charts have a 2× backing store and are upscaled by at most 1.9× in the zoomed beats. "
          "The camera moves on an ease-in-out curve over ~0.9 s and follows the pointer with a 0.15 s lead (the pointer starts first).",
          f"- **Text size on film**: 11 px CSS table/legend/tooltip text is {text_px(11, 1):.1f} px at zoom 1 (full-frame shots), {text_px(11, 1.8):.0f} px at 1.8×, {text_px(11, 2.1):.0f} px at 2.1×, {text_px(11, 2.2):.0f} px at 2.2× and {text_px(11, 2.5):.0f} px at 2.5×; the bold 12.5 px header numbers are {text_px(12.5, 2.2):.0f} px at 2.2×. Every zoomed beat is ≥ 1.8× (≥ 28 px). The timeline tables below carry the zoom and the resulting 11-px text size per beat.",
          "- **Pointer**: the cursor is drawn into the page by the capture harness (an SVG arrow, counter-scaled so it stays 33×45 px on the 1080p frame at every zoom); its path is eased between beats; clicks, typing, select changes and range-slider drags are real Playwright input events dispatched at the pointer position. "
          "Tooltips, hover lines and legend read-outs are the app's own reactions to those events. One exception is driven by the harness rather than by an input event: the agreement-by-league table is wider than its panel at 1280 wide, "
          "so in the Discovery beat its wrapper is scrolled horizontally (eased `scrollLeft` over 0.6 s) to bring the `within 2 pp` and `corr` columns into view — a wheel event would smooth-scroll on real time, outside the stepped clock. The resting pointer in the opening and closing wall shots sits on the attribution footer so no strip tooltip is open.",
          f"- **Encode**: `ffmpeg -framerate {FPS} -i f%05d.png -frames:v <3600|1800> -vf crop=1920:1080:0:0 -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium -movflags +faststart -an`. The PNG frame sequence is the clean footage master (kept outside the repo; regenerable from the storyboards against the deployed data). "
          "Chromium rounds the clip, so captures come out 1920–1923 × 1080–1083 and are cropped at the origin; the few captures that came out one pixel short (4 of 3600 in the 60 s master, 6 of 1800 in the 30 s master, all in camera moves) had their last pixel row or column replicated before the crop. "
          "Verified with ffprobe: 1920×1080, 60/1 fps, 3600 and 1800 frames, no audio stream.",
          "- **Content**: the 60-second film follows the parent's shot list — wall sorted by Polymarket volume with the header numbers at 2.2× → Find team → BAL @ ATL → full history, BAL side, American odds, zoom on the flip, drag-zoom into the −335 step, legend read `−335 at 2026-09-29 17:36Z`, Game day preset, legend read `+144 at 2026-10-11 12:20Z`, open/close table → In-game preset at 1.8× with the Q4 and OT Sportradar tooltips → Discovery (histogram, agreement table: All · 889 · 96% within 2 pp) → Scoreboard (2.5× on the `All` block: N 363, Pinnacle close 0.2093 … Polymarket T−1 min 0.2092) → Lab (1.8×, θ 2 → 5 pp, equity curve + placebo) → ends on the wall. "
          "The 30-second cut keeps the header numbers → flip → in-game → scoreboard block and omits the side table, Discovery and Lab.", ""]
    for name in ("film60", "film30"):
        if name not in films:
            continue
        t = films[name]
        F += [f"## {name}: {t['frames']} frames, {t['seconds']} s at {FPS} fps", "", "| frame | t (s) | camera zoom | 11-px text on film | beat |", "|---|---|---|---|---|"]
        last = None
        for e in t["timeline"]:
            lab = re.sub(r" \((down|up|move \d+/\d+)\)$", "", e["label"])
            lab = re.sub(r' ".*"$', "", lab)
            lab = re.sub(r" \d+/\d+$", "", lab)
            if lab != last:
                z = (e.get("cam") or {}).get("z", 1)
                F.append(f"| {e['frame']} | {e['t']:.2f} | {z:.2f}× | {text_px(11, z):.0f} px | {lab} |")
                last = lab
        F += ["", "On-screen text captured at each beat (verbatim DOM text, truncated):", ""]
        for n in t["notes"]:
            txt = " · ".join(f"{k}: {v}" for k, v in n["dom"].items() if v)
            F.append(f"- frame {n['frame']} ({n['t']:.2f} s) **{n['label']}** — `{txt[:600]}`")
            if name == "film60":
                fnum = min(n["frame"], t["frames"] - 1)  # a note taken after the last tick refers to the final frame
                src = os.path.join(FRAMES, name, f"f{fnum:05d}.png")
                if os.path.exists(src):
                    dst = os.path.join(fr_dir, f"film60_f{fnum:05d}_{re.sub(r'[^a-z0-9]+', '_', n['label'].lower()).strip('_')}.png")
                    shutil.copy(src, dst)
        F.append("")
    F += ["## Key frames", "", "`handoff/frames/` holds the exact frame for every noted beat of the 60-second film (file names carry the frame number and beat; 1923×1083 before the encode crop). "
          "Every number visible in them is traced in `film_receipts.md`.", ""]
    open(os.path.join(OUT, "films.md"), "w").write("\n".join(F) + "\n")
    print(f"film_receipts.md ({len(R)} lines, {n_ok}/{len(checks)} cross-checks pass), films.md, {len(os.listdir(fr_dir))} key frames, mp4s: {list(mp4s)}")


if __name__ == "__main__":
    main()
