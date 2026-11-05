#!/usr/bin/env python3
"""
14_film45_receipts.py — receipts for the 45-second film (v2 pass): films-v2.md (the production-standard receipts, §5 items 1–7)
and film45_receipts.md (every number visible in the film → the dataset / analysis value it is rendered from).

Inputs
  /tmp/frames/film45/timeline.json         per-frame timeline written by films/capture45.js (copied to films/film45_timeline.json)
  handoff/film45_qa.json                    films/qa45.py: ffprobe, SHA-256, per-second duplicate pairs / max jump, moving-window
                                            duplicate analysis, pop classification, cut PSNR, extracted native frames
  handoff/film45_text.json                  films/measure45.py: text heights measured on the native delivery frames
  films/the-tape-45s-encode.json            films/encode45.py: source frame sizes, edge-replicated frames, ffmpeg commands
  films/app_version.txt                     bundle hash of the deployed app the film was captured from
  a9-data/derived/{manifest,wall,analysis}.json, games/nfl_2026101240603BF9.json
Outputs
  handoff/films-v2.md, handoff/film45_receipts.md, films/film45_timeline.json, handoff/frames45/ trimmed to the key frames
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
FILM_SCALE = 1920 / 1280  # CSS px → film px at camera zoom 1
ASSET_ID = os.environ.get("A9_FILM45_ASSET", "(assigned when the mp4 is shared; see the checkpoint mail)")


def load(p):
    with open(p) as f:
        return json.load(f)


def iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def iso_min(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")


def fmt_n(x):
    return f"{x:,}"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def norm(s):
    return (s or "").replace("−", "-").replace("–", "-").replace("\u2009", " ").replace("\u202f", " ")


def squash(s):
    return norm(s).replace(" ", "")


def secs(f):
    return f / FPS


def main():
    manifest, wall, analysis = load(os.path.join(DER, "manifest.json")), load(os.path.join(DER, "wall.json")), load(os.path.join(DER, "analysis.json"))
    hero = load(os.path.join(DER, "games", HERO.replace(":", "_") + ".json"))
    src = os.path.join(FRAMES, "film45", "timeline.json")
    tl_path = os.path.join(BUILD, "films", "film45_timeline.json")
    if os.path.exists(src):
        shutil.copy(src, tl_path)
    tl = load(tl_path)
    qa = load(os.path.join(OUT, "film45_qa.json"))
    text = load(os.path.join(OUT, "film45_text.json"))
    enc = load(os.path.join(BUILD, "films", "the-tape-45s-encode.json"))
    _sz = [tuple(int(v) for v in k.split("x")) for k in enc.get("source_sizes", {}).keys()]
    size_range = (f"{min(w for w, h in _sz)}–{max(w for w, h in _sz)} × {min(h for w, h in _sz)}–{max(h for w, h in _sz)}" if _sz else "1920 × 1080")
    appv = open(os.path.join(BUILD, "films", "app_version.txt")).read()
    bundle_hash = re.search(r"^bundle_hash ([0-9a-f]{64})", appv, re.M).group(1)
    filmed_hash = re.search(r"^filmed_bundle_hash ([0-9a-f]{64})", appv, re.M).group(1)
    if tl.get("frames") != 2700:
        print(f"WARNING: timeline has {tl.get('frames')} frames", file=sys.stderr)
    notes = {n["label"]: n for n in tl["notes"]}
    cam_at = {row["f"]: row["cam"] for row in tl["timeline"]}
    checks = []

    def check(label, ok, detail):
        checks.append((label, bool(ok), detail))
        return f"- Cross-check — {label}: **{'yes' if ok else 'NO'}** ({detail})."

    def dom(label, key):
        n = notes.get(label)
        return (n or {}).get("dom", {}).get(key) or ""

    def nframe(label):
        """frame on which the noted state is visible: the note is taken after frame f-1 was captured; a note taken at a cut
        describes the frame before the cut."""
        n = notes[label]
        return min(n["f"], 2699) if n["f"] not in (c["f"] for c in tl["cuts"]) else n["f"] - 1

    # =====================================================================================================================
    # film45_receipts.md — every visible number → source
    # =====================================================================================================================
    census = manifest["census"]
    tot = lambda k: sum(v.get(k, 0) or 0 for v in census.values())
    games = wall["games"]
    n_both = sum(1 for g in games if g.get("pin") is not None and (g.get("pm") or {}).get("t1m") is not None)
    n_books = sum(1 for g in games if g.get("oo"))
    ag_all = analysis["agreement"]["per_league"]["all"]
    cal = analysis["calibration"]
    R = ["# Film receipts — every number visible in the 45-second film, with its source", "",
         "The film is a frame-stepped capture of the deployed app (method and frame-level QA in `films-v2.md`). At each beat the on-screen text was read "
         "from the DOM at capture time (`films/film45_timeline.json` → `notes`; the frame numbers below are the native frames of `films/the-tape-45s.mp4`, "
         "0-based) and every figure is traced to the dataset or analysis value it is rendered from. Where a figure is a pure function of the raw vendor "
         "responses the receipt names the vendor field. Cross-check lines compare the captured DOM text with the value recomputed here from the derived data.", ""]

    # ---- status line + header -------------------------------------------------------------------------------------------
    R += ["## Status line (bottom of every frame at 1×)", "",
          f"- `{len(games)} games · {n_both} with both sources · {manifest['window_utc'][0][:10]} → {manifest['window_utc'][1][:10]} UTC · Tier 1` — `manifest.n_games` = {manifest['n_games']}; games with a Pinnacle close and a Polymarket sample ≤ 30 min before kickoff (`wall.json`: pin ≠ null and pm.t1m ≠ null) = {n_both}; `manifest.window_utc`; `meta.tier`.",
          "  on-screen: `" + dom("A: wall", "status") + "`",
          check("status line matches manifest/wall", str(len(games)) in dom("A: wall", "status") and str(n_both) in dom("A: wall", "status"), f"frame {nframe('A: wall')}"), ""]
    hdr = {
        f"{fmt_n(len(games))} matched games · {len(census)} leagues": "`manifest.n_games`; `manifest.census` has one entry per league",
        f"{fmt_n(tot('with_oo_history'))} / {fmt_n(len(games))} with sportsbook history (5 books)": "census `with_oo_history`",
        f"{fmt_n(tot('oo_entries') + tot('ext_oo_entries'))} sportsbook price updates": f"census `oo_entries` ({fmt_n(tot('oo_entries'))} in-window) + `ext_oo_entries` ({fmt_n(tot('ext_oo_entries'))} extension); one entry = one OpticOdds `/fixtures/odds/historical` timeseries point for a book × market × side",
        f"{fmt_n(tot('pm_samples_all_markets'))} Polymarket price samples · {fmt_n(tot('pm_markets'))} markets · {fmt_n(tot('with_pm_history'))} games": f"census `pm_samples_all_markets`, `pm_markets`, `with_pm_history` (CLOB `/prices-history` points over every matched market; home-win series alone {fmt_n(tot('pm_samples'))})",
        f"${fmt_n(tot('pm_volume_ml'))} Polymarket moneyline volume": "census `pm_volume_ml` = sum of the moneyline markets' Gamma `volume`",
        f"{fmt_n(tot('plays'))} plays with wall clocks · {fmt_n(tot('with_plays'))} games": "census `plays`, `with_plays` (Sportradar play-by-play events carrying a `wall_clock`)",
        f"+ {fmt_n(manifest['extension']['n_games_with_history'])} sportsbook-only games, {manifest['extension']['window_utc'][0][:10]} → {manifest['extension']['window_utc'][1][:10]}": "`manifest.extension` (books-only sweep before the Polymarket window)",
    }
    R += ["## Wall header (beat A, 2.25× on the header numbers, frames 132–203)", "",
          "The 2.25× frame holds the right-hand part of the header: `1,332,476 sportsbook price updates`, `4,195,032 Polymarket price samples · 3,387 markets · 1,150 games`, the attribution line and the count line "
          "`1150 strips · 1136 with sportsbook history · 889 with both sources`. The left-hand cells (`1,150 matched games · 13 leagues`, `1,136 / 1,150 with sportsbook history (5 books)`) are outside the 2.25× frame but are legible at 1× in frames 0–71 and listed here for completeness.", ""]
    for k, v in hdr.items():
        R.append(f"- `{k}` — {v}.")
    stats = dom("A: header numbers", "stats")
    missing = [k for k in hdr if re.match(r"[+$]?\s?[\d,]+", k) and re.match(r"[+$]?\s?[\d,]+", k).group(0) not in norm(stats)]
    R.append(check(f"header figures in the DOM at frame {nframe('A: header numbers')}", not missing, f"all {len(hdr)} figures present" if not missing else f"missing {missing}"))
    cnt = dom("A: header numbers", "count")
    R.append(f"- Count line `{cnt}` — `wall.games` length {len(games)}; strips with OpticOdds history (`oo` ≠ null) {n_books}; strips with both sources {n_both} (`wall.js` → `update()`).")
    R.append(check("count line (strips · with sportsbook history · with both sources)", cnt == f"{len(games)} strips · {n_books} with sportsbook history · {n_both} with both sources", f"frame {nframe('A: header numbers')}"))
    R.append("")

    # ---- find ----------------------------------------------------------------------------------------------------------
    rav = [g for g in games if "ravens" in (g.get("an", "") + " " + g.get("hn", "") + " " + g["away"] + " " + g["home"]).lower()]
    cnt2 = dom("B: ravens filter", "count")
    R += ["## Find team → `ravens` (beat B, frames 290–368)", "",
          f"- Typed `ravens` (6 real key events, frames 290/295/301/306/310/316). The filter matches team names and abbreviations containing the typed text (`wall.js` → `filtered()`); `wall.json` has {len(rav)} games whose team names contain “ravens”: " + "; ".join(f"{g['lg'].upper()} {g['away']} @ {g['home']} {iso_min(g['ko'])}" for g in sorted(rav, key=lambda g: g['ko'])) + ".",
          f"- Count line after typing: `{cnt2}` — {len(rav)} strips; {sum(1 for g in rav if g.get('oo'))} with OpticOdds history; {sum(1 for g in rav if g.get('pin') is not None and (g.get('pm') or {}).get('t1m') is not None)} with both sources.",
          check("ravens count line", cnt2 == f"{len(rav)} strips · {sum(1 for g in rav if g.get('oo'))} with sportsbook history · {sum(1 for g in rav if g.get('pin') is not None and (g.get('pm') or {}).get('t1m') is not None)} with both sources", f"frame {nframe('B: ravens filter')}"), ""]

    # ---- hero strip tooltip -------------------------------------------------------------------------------------------------
    wg = next(g for g in games if g["key"] == HERO)
    tip = dom("B: hero tooltip", "tip")
    pm1 = (wg.get("pm") or {}).get("t1m")
    gap24 = wg.get("div")
    R += ["## Strip tooltip — BAL @ ATL (beat B, frames 419–490)", "",
          f"- `NFL · BAL @ ATL` key `{wg['key']}`: kickoff {iso(wg['ko'])} (Sportradar `scheduled`); final Baltimore Ravens {wg['as']} – Atlanta Falcons {wg['hs']} (Sportradar); Pinnacle close (home) {wg['pin'] * 100:.1f}% (`wall.pin` = multiplicative no-vig of the last Pinnacle moneyline entry ≤ kickoff); "
          f"Polymarket T−1 min (home) {pm1 * 100:.1f}% (`wall.pm.t1m`, last CLOB sample ≤ 30 min before kickoff); " + (f"max gap in the last 24 h {gap24 * 100:.1f}% (`wall.div`, largest |Polymarket − Pinnacle| over the hourly pre-kickoff grid); " if gap24 is not None else "") + f"Polymarket ML volume ${fmt_n(int(wg['vol']))} (`wall.vol`, Gamma `volume` of the moneyline market); match tier {wg['tier']} (`wall.tier`).",
          f"  on-screen: `{tip[:420]}`",
          check("tooltip values (final score, Pinnacle close, Polymarket T−1 min, volume, tier)", f"{wg['pin'] * 100:.1f}%" in tip and f"{pm1 * 100:.1f}%" in tip and str(wg["as"]) in tip and str(wg["hs"]) in tip and fmt_n(int(wg["vol"])) in tip, f"frame {nframe('B: hero tooltip')}"), ""]

    # ---- hero game -----------------------------------------------------------------------------------------------------------
    ko = hero["kickoff"]
    books = hero["oo"]["books"]
    head = dom("B: game opened", "head")
    R += ["## Game view — Baltimore Ravens @ Atlanta Falcons (beats C–D, frames 491–1775)", "",
          f"- Title `Baltimore Ravens @ Atlanta Falcons 30–23 (OT) · NFL · week 5 · kickoff {iso_min(ko)} · …` — Sportradar game `{hero['match']['sr_game_id']}` (scheduled, venue, final with an overtime period), OpticOdds fixture `{hero['match']['oo_fixture_id']}`, matcher tier `{hero['match']['tier']}`.",
          f"  on-screen: `{head[:300]}`",
          check("title score 30–23 (OT) and kickoff", "30–23" in head and iso_min(ko)[:16] in head, f"frame {nframe('B: game opened')}")]
    # chart caption: N points
    n_rows = {b: len([r for r in books[b]["ml"]["novig"] if r[1] is not None]) for b in books}
    hs = hero["pm"].get("home_series") or []
    n_pts = sum(n_rows.values()) + len(hs)
    legend = dom("B: game opened", "legend")
    R += [f"- Chart caption `… → … · {n_pts} points · no-vig (multiplicative) · Polymarket = sampled price` and legend `N = {n_pts} entries` (the same count in every window — Full history, Game day, In-game): the number of rows over all visible series = " + " + ".join(f"{b} {n}" for b, n in n_rows.items()) + f" no-vig moneyline rows + Polymarket {len(hs)} compressed home-price samples (`game.js` → `nEntries`; `games/<hero>.json` → `oo.books.*.ml.novig`, `pm.home_series`). "
          f"The window printed in the caption is `fullDomain` = min(first entry, kickoff − 1 h) → min(max(kickoff + 3 h, last point), kickoff + 8 h) = {iso_min(min(min(r[0] for b in books for r in books[b]['ml']['novig']), hs[0][0] if hs else ko) if True else ko)} → {iso_min(min(max(ko + 3 * 3600, max(max(r[0] for b in books for r in books[b]['ml']['novig']), hs[-1][0] if hs else 0)), ko + 8 * 3600))}.",
          check(f"`N = {n_pts} entries` in the legend", f"N = {n_pts} entries" in norm(legend) or f"N={n_pts}entries" in squash(legend), f"frame {nframe('B: game opened')}")]
    # closes table
    closes = dom("C: flip read", "closes")
    R += ["- Side panel `Moneyline, BAL (away)` (source · open · close · age), frames 709–935 at 2.4×: no-vig probabilities of the BAL side — for each book open = multiplicative no-vig of its first retained entry, close = last entry ≤ kickoff, age = minutes (or hours) from that close to kickoff (`game.js` → `closes()`):"]
    side_ok = True
    for b in ("Pinnacle", "DraftKings", "FanDuel", "BetMGM", "Caesars"):
        nv = books[b]["ml"]["novig"]
        o = nv[0]
        c = [r for r in nv if r[0] <= ko][-1]
        age = (ko - c[0]) / 60
        age_s = f"{age / 60:.0f} h" if age >= 120 else f"{age:.0f} m"
        raw_a, raw_h = books[b]["ml"]["raw"]["away"], books[b]["ml"]["raw"]["home"]
        ro = (raw_a[0][1], raw_h[0][1])
        rc = ([r for r in raw_a if r[0] <= ko][-1][1], [r for r in raw_h if r[0] <= ko][-1][1])
        R.append(f"  - {b}: open BAL {o[2] * 100:.1f}% at {iso(o[0])} (raw BAL {ro[0]:+.0f} / ATL {ro[1]:+.0f}), close BAL {c[2] * 100:.1f}% at {iso(c[0])} (raw BAL {rc[0]:+.0f} / ATL {rc[1]:+.0f}), age {age:.0f} min → `{age_s}`; {len(nv)} entries (OpticOdds `/fixtures/odds/historical`, `price` + `timestamp`).")
        side_ok &= f"{b}{o[2] * 100:.1f}%{c[2] * 100:.1f}%{age_s}".replace(" ", "") in squash(closes)
    pm_close = [r for r in hs if r[0] <= ko][-1]
    pm_open_away, pm_close_away = 1 - hs[0][1], 1 - pm_close[1]
    pm_age = (ko - pm_close[0]) / 60
    mk = hero["pm"]["markets"].get("ml_home") or hero["pm"]["markets"].get("ml_away") or {}
    R.append(f"  - Polymarket (away price): open {pm_open_away * 100:.1f}% at {iso(hs[0][0])}, last pre-kickoff sample {pm_close_away * 100:.1f}% at {iso(pm_close[0])}, age {pm_age:.0f} min → `{pm_age:.0f} m`; {len(hs)} compressed step points (market `{mk.get('market_id')}`, {mk.get('n_samples')} raw CLOB samples; home price = 1 − away price when the matched market is the away side: `pm.home_series_source` = `{hero['pm'].get('home_series_source')}`).")
    side_ok &= f"Polymarket{pm_open_away * 100:.1f}%{pm_close_away * 100:.1f}%{pm_age:.0f}m" in squash(closes)
    R.append(f"  on-screen: `{closes[:420]}`")
    R.append(check("open / close / age for the five books and Polymarket match the recomputation", side_ok, f"frame {nframe('C: flip read')}"))
    fd = books["FanDuel"]["ml"]
    fd_a = fd["raw"]["away"]
    fd_close_a = [r for r in fd_a if r[0] <= ko][-1]
    R.append(f"- The flip the beat is built on: FanDuel BAL {fd_a[0][1]:+.0f} at {iso(fd_a[0][0])} (open) → {fd_close_a[1]:+.0f} at {iso(fd_close_a[0])} (last pre-kickoff entry), i.e. no-vig {books['FanDuel']['ml']['novig'][0][2] * 100:.1f}% → {[r for r in books['FanDuel']['ml']['novig'] if r[0] <= ko][-1][2] * 100:.1f}% on screen. The film shows the no-vig probabilities (Unit = Probability) so the sportsbook lines and the Polymarket price share one axis; the American prices are the same OpticOdds entries.")
    # ATL side
    closes_atl = dom("D: ATL side", "closes")
    R.append("- After the `Side → ATL` click (frame 1216) the panel reads `Moneyline, ATL (home)` with the complementary no-vig values (ATL = 1 − BAL for the two-way market):")
    atl_ok = True
    for b in ("Pinnacle", "DraftKings", "FanDuel", "BetMGM", "Caesars"):
        nv = books[b]["ml"]["novig"]
        o = nv[0]
        c = [r for r in nv if r[0] <= ko][-1]
        R.append(f"  - {b}: open ATL {o[1] * 100:.1f}% → close ATL {c[1] * 100:.1f}%.")
        atl_ok &= f"{b}{o[1] * 100:.1f}%{c[1] * 100:.1f}%" in squash(closes_atl)
    atl_ok &= f"Polymarket{hs[0][1] * 100:.1f}%{pm_close[1] * 100:.1f}%" in squash(closes_atl)
    R.append(f"  - Polymarket (1 − away price): open {hs[0][1] * 100:.1f}% → last pre-kickoff {pm_close[1] * 100:.1f}%.")
    R.append(f"  on-screen: `{closes_atl[:300]}`")
    R.append(check("ATL-side open / close values", atl_ok, f"frame {nframe('D: ATL side')}"))
    # polymarket checkpoints (visible at 1× in the game view, panel below the closes table)
    R.append("- `Polymarket pre-kickoff checkpoints` panel (visible at 1× in frames 589–648 and 1428–1499; not zoomed): " + "; ".join(f"{lab} {wg['pm'][k] * 100:.1f}% (age {wg['pma'][k]:.1f} min)" for k, lab in (("t24h", "T−24 h"), ("t6h", "T−6 h"), ("t1h", "T−1 h"), ("t10m", "T−10 min"), ("t1m", "T−1 min")) if wg["pm"].get(k) is not None) + " — `wall.pm.*` / `wall.pma.*`.")
    # in-game
    plays_all = hero["sr"].get("plays", [])
    plays = [p for p in plays_all if p.get("scoring")]
    final_t = min(plays_all[-1]["t"] + 180, ko + 8 * 3600) if plays_all else None
    ig_pts = sum(1 for b in books for r in books[b]["ml"]["novig"] if r[1] is not None and ko - 600 <= r[0] <= final_t) + sum(1 for r in hs if ko - 600 <= r[0] <= final_t)
    R += [f"- In-game preset (click at frame 1330): domain = kickoff − 10 min → last Sportradar play wall clock + 3 min = {iso_min(ko - 600)} → {iso_min(final_t)}; the caption keeps `{n_pts} points` because `nEntries` counts every row of the visible series regardless of the window ({ig_pts} of them fall inside the in-game window: `game.js` → `inGameBtn`, `finalT()`, `nEntries`); the thick line is the Polymarket sampled price after kickoff (ATL side); markers and staggered score labels are the scoring plays below. "
          f"The Polymarket ATL price in that window runs {(1 - [r for r in hs if r[0] <= ko][-1][1]) * 100:.1f}% at the last pre-kickoff sample → max {max(1 - r[1] for r in hs if ko <= r[0] <= final_t) * 100:.0f}% → min {min(1 - r[1] for r in hs if ko <= r[0] <= final_t) * 100:.1f}% (the `88% → 17%` swing of the shot list; `pm.home_series`, ATL = 1 − BAL price).",
          "- Scoring plays (markers + tooltips; Sportradar `wall_clock`, running score away–home; Sportradar numbers the overtime period from 1 again — the last two rows are OT):"]
    for p in plays:
        R.append(f"  - {iso(p['t'])} · period {p.get('period')} {p.get('clock') or ''} · {p.get('ap')}–{p.get('hp')} · {(p.get('desc') or '')[:120]}")
    q4 = next((p for p in plays if p.get("ap") == 21 and p.get("hp") == 23), None)
    q4last = [p for p in plays if p.get("period") == 4][-1]
    ot = next((p for p in plays if p["t"] > q4last["t"]), None)
    for lab, play, nm in (("D: Q4 tooltip", q4, "Q4 00:44"), ("D: OT tooltip", ot, "OT 3:01")):
        t = dom(lab, "tip")
        want_score, want_t = f"{play['ap']}–{play['hp']}", iso_min(play["t"])
        R.append(f"  - on-screen tooltip ({lab}, frame {nframe(lab)}): `{t[:320]}`")
        R.append(check(f"tooltip `{nm}` shows `{want_score}` and wall clock `{want_t}` (Sportradar play at {iso(play['t'])})", norm(want_score) in norm(t) and want_t in t, f"frame {nframe(lab)}"))
    R.append("")

    # ---- discovery -------------------------------------------------------------------------------------------------------------
    per = analysis["agreement"]["per_league"]
    R += ["## Discovery — Agreement by league (beat E, frames 1776–2170)", "",
          f"- `All` row: N = {ag_all['n']} games with a Pinnacle close and a Polymarket sample ≤ 30 min before kickoff; mean (Polymarket T−1 min − Pinnacle no-vig) {ag_all['mean_diff'] * 100:+.2f} pp, 95% CI {ag_all['mean_diff_ci95'][0] * 100:+.2f} … {ag_all['mean_diff_ci95'][1] * 100:+.2f} pp, mean |diff| {ag_all.get('mean_abs_diff', 0) * 100:+.2f} pp, within 2 pp {ag_all['share_within_2pp'] * 100:.2f}% (shown rounded as {round(ag_all['share_within_2pp'] * 100)}%), correlation {ag_all['corr_pm_pinnacle']:.4f} (shown {ag_all['corr_pm_pinnacle']:.3f}) — `analysis.agreement.per_league.all`; `results/b_closing_agreement_summary.csv`.",
          "- Rows visible in the 2.8× frame (`All` plus the league rows that fit under it), `analysis.agreement.per_league`:", "",
          "| league | N | mean diff | 95% CI | mean abs diff | within 2 pp | corr |", "|---|---|---|---|---|---|---|"]
    for lg, r in per.items():
        if isinstance(r, dict) and "n" in r:
            R.append(f"| {lg} | {r['n']} | {r['mean_diff'] * 100:+.2f} pp | {r['mean_diff_ci95'][0] * 100:+.2f} … {r['mean_diff_ci95'][1] * 100:+.2f} pp | {r.get('mean_abs_diff', 0) * 100:+.2f} pp | {round(r['share_within_2pp'] * 100)}% | {r['corr_pm_pinnacle']:.3f} |")
    tt = squash(dom("E: agreement table (scroll 0)", "table"))
    want = squash(f"All{ag_all['n']}{ag_all['mean_diff'] * 100:+.2f} pp{ag_all['mean_diff_ci95'][0] * 100:+.2f} pp … {ag_all['mean_diff_ci95'][1] * 100:+.2f} pp{ag_all.get('mean_abs_diff', 0) * 100:+.2f} pp{round(ag_all['share_within_2pp'] * 100)}%{ag_all['corr_pm_pinnacle']:.3f}")
    R += ["", f"  on-screen (table text): `{dom('E: agreement table (scroll 0)', 'table')[:500]}`",
          check("`All` row (N, mean diff, CI, mean |diff|, within 2 pp, corr) matches `analysis.json`", want in tt, f"frame {nframe('E: agreement table (scroll 0)')}; the scrolled frame {nframe('E: agreement table (scrolled)')} shows the same DOM shifted 201 CSS px left"),
          check("every league row's N appears in the on-screen table", all(str(r["n"]) in tt for r in per.values() if isinstance(r, dict) and "n" in r), f"{sum(1 for r in per.values() if isinstance(r, dict) and 'n' in r)} rows"), ""]

    # ---- scoreboard -------------------------------------------------------------------------------------------------------------
    R += ["## Scoreboard — common game set (beat F, frames 2171–2699)", "",
          f"- Common set definition: {cal['common_definition']}.",
          f"- N per league (identical for every source row): " + ", ".join(f"{lg} {n}" for lg, n in cal["common_n"].items()) + ".",
          "- Rows visible in the film (`analysis.calibration.common_per_league`; `results/d_calibration_summary.csv`, mode = common; 2.5× frames the `All` block with the first NFL rows entering at the bottom; the 3.9× payoff frames `source · N · Brier` for Pinnacle close … FanDuel close):", "",
          "| league | source | N | Brier | 95% CI | log loss | 95% CI | home win rate | mean p(home) |", "|---|---|---|---|---|---|---|---|---|"]
    for lg in ("all", "nfl"):
        for s, r in cal["common_per_league"].get(lg, {}).items():
            R.append(f"| {lg} | {s} | {r['n']} | {r['brier']:.4f} | {r['brier_ci95'][0]:.4f} … {r['brier_ci95'][1]:.4f} | {r['logloss']:.4f} | {r['logloss_ci95'][0]:.4f} … {r['logloss_ci95'][1]:.4f} | {r['base_rate_home'] * 100:.1f}% | {r['mean_p_home'] * 100:.1f}% |")
    sb = squash(dom("F: payoff", "table"))
    allrows = cal["common_per_league"]["all"]
    pin, pm1m = allrows.get("Pinnacle close"), allrows.get("Polymarket T-1min")
    R += ["", f"  on-screen (table text): `{dom('F: payoff', 'table')[:400]}`",
          check("every `All` row's N and Brier from `analysis.json` appears in the on-screen table text", all(str(r["n"]) in sb and f"{r['brier']:.4f}" in sb for r in allrows.values()), f"{len(allrows)} rows, frame {nframe('F: payoff')}"),
          check(f"payoff pair — Pinnacle close {pin['brier']:.4f} vs Polymarket T−1 min {pm1m['brier']:.4f} on the same {pin['n']} games", f"Pinnacleclose{pin['n']}{pin['brier']:.4f}" in sb and f"PolymarketT-1min{pm1m['n']}{pm1m['brier']:.4f}" in sb and pin["n"] == pm1m["n"], "Brier on the common set; the film makes no claim beyond the two numbers"), ""]
    R += ["## Vendor call ledger (unchanged by the film)", "",
          "- No vendor call was made for this pass; the film is captured from the frozen Tier 1 dataset (`a9-data/derived`, `manifest.json`). Ledger: `handoff/ledger.md`.", ""]
    n_ok = sum(1 for _, ok, _ in checks if ok)
    R.insert(3, f"**Cross-checks: {n_ok} of {len(checks)} pass** (each is listed in its section; a failing line reads **NO**).")
    R.insert(4, "")
    open(os.path.join(OUT, "film45_receipts.md"), "w").write("\n".join(R) + "\n")

    # =====================================================================================================================
    # films-v2.md — production-standard receipts (§5 items 1–7)
    # =====================================================================================================================
    d, m = qa["delivery"], qa["master"]
    ds, ms = d["ffprobe"]["streams"][0], m["ffprobe"]["streams"][0]
    F = ["# The Tape — 45-second film (v2 pass)", "",
         f"One silent film replaces the 60 s and 30 s cuts (kept as superseded assets). Asset: **{ASSET_ID}**. File `films/the-tape-45s.mp4`, "
         f"{d['bytes']:,} bytes, SHA-256 `{d['sha256']}`. Captured from the deployed app **The Tape** (asset `2088f758-e90b-423c-ba64-c4c7a2b1ca63`), filmed bundle hash `{filmed_hash}`; final deployed bundle `{bundle_hash}` (differs only in the Export PNG footer wrap, `films/app_version.txt`). "
         "Every number on screen is traced in `handoff/film45_receipts.md`.", "",
         "## 1 · ffprobe", "",
         "| file | width | height | r_frame_rate | avg_frame_rate | nb_frames | duration | nb_streams | pix_fmt | codec |", "|---|---|---|---|---|---|---|---|---|---|",
         f"| delivery `films/the-tape-45s.mp4` | {ds['width']} | {ds['height']} | {ds['r_frame_rate']} | {ds['avg_frame_rate']} | {ds['nb_frames']} | {float(ds['duration']):.3f} s | {d['ffprobe']['format']['nb_streams']} | {ds['pix_fmt']} | {ds['codec_name']} {ds.get('profile', '')} |",
         f"| master `a9-films/the-tape-45s-master.mp4` (outside the bundle) | {ms['width']} | {ms['height']} | {ms['r_frame_rate']} | {ms['avg_frame_rate']} | {ms['nb_frames']} | {float(ms['duration']):.3f} s | {m['ffprobe']['format']['nb_streams']} | {ms['pix_fmt']} | {ms['codec_name']} {ms.get('profile', '')} |", "",
         f"Encode (one ffmpeg run writes both outputs from the normalised rgb24 frame stream): `{enc['ffmpeg']}` — delivery libx264 CRF 16, preset slow, yuv420p, `+faststart`, `-an` (no audio stream); master libx264 `-qp 0` (lossless), yuv444p. Frame normalisation: {enc['normalisation']}; source frame sizes and the edge-replicated short frames are listed in `films/the-tape-45s-encode.json`.", "",
         "## 2 · Hashes", "",
         "| file | bytes | SHA-256 |", "|---|---|---|",
         f"| `films/the-tape-45s.mp4` | {d['bytes']:,} | `{d['sha256']}` |",
         f"| `a9-films/the-tape-45s-master.mp4` | {m['bytes']:,} | `{m['sha256']}` |", ""]

    # ---- beat list -------------------------------------------------------------------------------------------------------------
    F += ["## 3 · Beat list", "",
          "Shot list as filmed (the parent's A9 baseline, with the flip read as no-vig probabilities so the sportsbook rows and the Polymarket line share one axis; the raw −335/+144 FanDuel prices are in `film45_receipts.md`):", "",
          "| beat | start | end | subject | zoom | payoff |", "|---|---|---|---|---|---|",
          "| A | 0.000 | 4.200 | the tape at 1× (picture, 1.2 s) → push-in on the header numbers → read | 1× → 2.25× | 1,332,476 sportsbook price updates · 4,195,032 Polymarket price samples · 3,387 markets · 1,150 games |",
          "| B | 4.200 | 8.817 | click Find team, type `ravens` (6 keys, 10–12 cps), pointer to the BAL @ ATL strip, tooltip read, click | 2.25× | 5 strips · tooltip: Final 30–23 · Pinnacle close 61.9% · Polymarket T−1 min 62.5% · $7,296,845 |",
          "| C | 8.817 | 16.600 | game opens (pull-back to 1×, full history), push-in on the last two weeks + open → close table, pointer scrubs the clock | 1× → 2.4× | FanDuel 74.0% → 39.3% (12 h) · Polymarket 61.5% → 37.5% (10 m) |",
          "| D | 16.600 | 29.600 | pull-back, push-in on the toolbar, click Side ATL (lines mirror), click In-game, pull-back to the in-game picture, push-in on the play markers, Q4 and OT tooltips | 1× → 2.2× → 1× → 2.4× | TD · Q4 00:44 · 21–23 · wall clock 03:15Z; TD · OT 3:01 · 29–23 · 03:41Z (Sportradar) |",
          "| E | 29.600 | 36.183 | cut to Discovery (1× picture), pointer to the All row, push-in on Agreement by league, read, wheel-scroll to the right-hand columns, read | 1× → 2.8× | All · 889 · +0.16 pp (CI +0.09 … +0.24) · 96% within 2 pp · corr 0.999 |",
          "| F | 36.183 | 45.000 | cut to Scoreboard (1× picture), pointer to the Pinnacle row, push-in on the All block, read, push-in on Pinnacle close vs Polymarket T−1 min, final hold 3.0 s | 1× → 2.5× → 3.9× | Brier 0.2093 (Pinnacle close) vs 0.2092 (Polymarket T−1 min), same 363 games |", "",
          "Every camera move, hold, pointer move, input event and cut, in order (frames are 0-based native frames, inclusive; start = first frame / 60, end = (last frame + 1) / 60, so consecutive rows tile; events are single frames):", "",
          "| start s | end s | frames | kind | subject | zoom | easing · duration | pointer / input |", "|---|---|---|---|---|---|---|---|"]
    rows = []
    for h in tl["holds"]:
        rows.append((h["f0"], h["f1"], "hold · " + h["kind"], h["label"], f"{h['cam']['z']:.2f}×", f"static · {h['seconds']:.2f} s", "pointer still" if h["kind"] != "read" or True else ""))
    for c in tl["camMoves"]:
        rows.append((c["f0"], c["f1"], "camera " + c["kind"], c["label"], f"{c['from']['z']:.2f}× → {c['to']['z']:.2f}×", f"{c['easing']} · {c['seconds']:.2f} s", "pointer still during the move"))
    for p in tl["ptrMoves"]:
        rows.append((p["f0"], p["f1"], "pointer move", p["label"], f"{cam_at.get(p['f0'], {}).get('z', 1):.2f}×", f"{p['easing']} · {p['seconds']:.3f} s", f"({p['from'][0]}, {p['from'][1]}) → ({p['to'][0]}, {p['to'][1]}) CSS px, {p['distCss']} px, peak {p['peakCss']} CSS px/s = {p['peakFilm1x']} film px/s at 1×"))
    for e in tl["events"]:
        rows.append((e["f"], e["f"], "input · " + e["type"], e["label"], f"{e['cam']['z']:.2f}×", "—", f"{e['type']}{(' ' + repr(e['key'])) if e.get('key') else ''} at ({e['x']}, {e['y']}) CSS px"))
    for c in tl["cuts"]:
        rows.append((c["f"], c["f"], "cut", c["label"], f"{c['cam']['z']:.2f}×", "hard cut (harness route change, 0 real-time waits)", c["change"]))
    rows.sort(key=lambda r: (r[0], r[1]))
    for f0, f1, kind, label, zoom, ease, ptr in rows:
        F.append(f"| {secs(f0):.3f} | {secs(f1 + (0 if f0 == f1 else 1)):.3f} | {f0}–{f1} | {kind} | {label} | {zoom} | {ease} | {ptr} |")
    F.append("")
    F += ["Camera moves: " + "; ".join(f"{c['label']} ({c['seconds']:.1f} s)" for c in tl["camMoves"]) + f". All {len(tl['camMoves'])} moves use {tl['rules']['cameraEasing']} easing, push/pull durations within {tl['rules']['pushPullSeconds'][0]}–{tl['rules']['pushPullSeconds'][1]} s, no pan-only moves, ≥ {tl['rules']['settleBeforeCameraMove']} s settle before every move, one subject per move (every push-in ends on the element the following read or click concerns; no move changes target mid-way).", ""]

    # ---- native frames + measured text --------------------------------------------------------------------------------------------
    F += ["## 4 · Native frames at every click, typing, toggle, scroll and readout — measured text heights", "",
          "Frames are decoded from the delivery mp4 (`films/qa45.py`, `ffmpeg … f%05d.png`) and kept in `handoff/frames45/`. Heights were measured by `films/measure45.py` on those native frames: the glyph band is the "
          "vertical ink extent of the listed string (digit height for numerals, x-height for lowercase words without ascenders, ascender-to-descender extent for mixed strings); the nominal size is the font's em height on film = CSS font size × 1.5 (device scale factor) × camera zoom. "
          "Readability here is judged on the em height (the standard's “UI text ≥ 28 px”) with the x-height criterion (≥ 14 px) measured directly; digit glyphs of the monospace face are ≈ 0.75–0.78 em.", "",
          "| frame | t | beat · string | zoom | nominal em (px) | measured glyph band (px) | glyph class | criterion | result |", "|---|---|---|---|---|---|---|---|---|"]
    for e in text:
        meas = e["measured"] or {}
        band = meas.get("band_height_px")
        cls = e["glyph_class"]
        nominal = e["nominal_font_px_on_film"]
        if e["frame"] == 2519 and ("Brier" in e["label"] or "N 363" in e["label"]):
            crit, ok = "payoff number ≥ 48 px", band is not None and band >= 48
        elif "x-height" in cls:
            crit, ok = "x-height ≥ 14 px (UI text ≥ 28 px em)", band is not None and band >= 14 and nominal >= 28
        elif cls.startswith("digits"):
            crit, ok = "readout numbers ≥ 32 px em", nominal >= 32
        else:
            crit, ok = "UI text ≥ 28 px em", nominal >= 28
        F.append(f"| {e['frame']} | {e['t']:.2f} | {e['label']} | {e['zoom']:.2f}× | {nominal:.1f} | {band if band is not None else '—'} | {cls} | {crit} | {'pass' if ok else 'see note'} |")
    F += ["", f"Crops of every measured region are in `handoff/frames45/text_crops/`. The key frames kept in `handoff/frames45/` are: f00000 (opening picture), the click frames and their responses (252/253, 491/492, 1216/1217, 1330/1331), the six key frames (290–316), the wheel frame (2039), the noted readouts (" + ", ".join(str(nframe(l)) for l in notes) + "), the cut pairs (1775/1776, 2170/2171) and the final hold (2519, 2609, 2699).", ""]

    # ---- per-second duplicates / pops / cuts ----------------------------------------------------------------------------------------
    dup = qa["duplicates"]
    F += ["## 5 · Frame-rate integrity", "",
          f"Metric: {dup['metric']}. Both thresholds are evaluated on the 0–255 grey scale (a duplicate pair = mean |Δ| < 0.02 of 255, a pop = mean |Δ| > 8 of 255); a 0–1 reading of the 0.02 threshold (= 5.1 of 255) cannot separate cursor-only motion from duplication and is reported alongside for reference.", "",
          "| second | frames | duplicate pairs (< 0.02/255) | pairs < 5.1/255 | max mean &#124;Δ&#124; | at pair |", "|---|---|---|---|---|---|"]
    for s in qa["per_second"]:
        F.append(f"| {s['second']} | {s['frames'][0]}–{s['frames'][1] - 1} | {s['dup_pairs_lt_0.02_of_255']} | {s.get('pairs_lt_5.1_of_255 (0–1 reading)', '')} | {s['max_mean_abs_delta_255']:.3f} | {s['max_jump_at_pair']} |")
    F += ["", "Moving windows (duplicate pairs are only a defect while something should be moving; static holds are intended):", "",
          "| window | frames | pairs | dup pairs | % | in first/last 4 | inside | exact zeros | min Δ | max Δ | cadence flip rate |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for w in dup["moving_windows"]:
        F.append(f"| {w['label']} ({w['kind']}) | {w['frames'][0]}–{w['frames'][1]} | {w['pairs']} | {w['dup_pairs']} | {w['dup_pct']:.1f} | {w['dup_pairs_in_first_4']}/{w['dup_pairs_in_last_4']} | {len(w['dup_pairs_inside'])} | {w['exact_zero_pairs']} | {w['min_delta']:.4f} | {w['max_delta']:.2f} | {w['cadence']['flip_rate']:.2f} |")
    key_events = [e for e in tl["events"] if e.get("type") == "key"]
    key_frames = ", ".join(str(e["f"]) for e in key_events)
    last_key_frame = max(e["f"] for e in key_events)
    next_move_frame = min(m["f0"] if "f0" in m else m["frames"][0] for m in tl["ptrMoves"] if (m["f0"] if "f0" in m else m["frames"][0]) > last_key_frame)
    hold_after_last_key_frames = next_move_frame - last_key_frame
    hold_after_last_key_s = hold_after_last_key_frames / 60
    _sx0 = qa.get("source_exact_duplicates") or {"moving_windows": []}
    _typ = next((w for w in _sx0["moving_windows"] if w["kind"] == "typing"), None)
    typ_frames = _typ["frames"] if _typ else [288, 323]
    typ_dup = _typ["exact_duplicate_pairs"] if _typ else "—"
    typ_pairs = _typ["pairs"] if _typ else "—"
    _cam = [w for w in _sx0["moving_windows"] if w["kind"].startswith("camera") and w["exact_duplicate_pairs"]]
    cam_dup_n = len(_cam)
    cam_dup_list = "; ".join(f"{w['frames'][0]}–{w['frames'][1]}: pair {w['pairs_list'][0]}→{w['pairs_list'][0] + 1}" for w in _cam)
    for w in _cam:
        assert w["exact_duplicate_pairs"] == 1 and w["pairs_list"] == [w["frames"][1] - 1], w
    sx = qa.get("source_exact_duplicates")
    if sx:
        F += ["", "Exact repeats on the source frames (the lossless PNGs fed to the encoder; `films/dupsrc45.py`, SHA-1 of the raw pixel buffer, pair = two byte-identical consecutive frames). This test is independent of the encoder and of the 0.02 metric floor:", "",
              "| window | frames | pairs | byte-identical pairs | % | at |", "|---|---|---|---|---|---|"]
        for w in sx["moving_windows"]:
            at = ", ".join(f"{a}→{a + 1}" for a in w["pairs_list"][:6]) + (" …" if len(w["pairs_list"]) > 6 else "") if w["pairs_list"] else "—"
            F.append(f"| {w['label']} ({w['kind']}) | {w['frames'][0]}–{w['frames'][1]} | {w['pairs']} | {w['exact_duplicate_pairs']} | {100 * w['exact_duplicate_pairs'] / w['pairs']:.1f} | {at} |")
        F += ["", f"Whole film: {sx['total_exact_duplicate_pairs_incl_static_holds']} byte-identical pairs of 2,699; {sx['camera_move_exact_duplicates'] + sx['pointer_move_exact_duplicates'] + sum(w['exact_duplicate_pairs'] for w in sx['moving_windows'] if w['kind'] in ('typing', 'wheel scroll'))} of them fall inside a listed window ({sx['camera_move_exact_duplicates']} camera, {sx['pointer_move_exact_duplicates']} pointer, {sum(w['exact_duplicate_pairs'] for w in sx['moving_windows'] if w['kind'] == 'typing')} typing, {sum(w['exact_duplicate_pairs'] for w in sx['moving_windows'] if w['kind'] == 'wheel scroll')} wheel), the rest are the intended static holds. In the camera moves the only byte-identical pairs are the final pair (frame f1−1 → f1) of {cam_dup_n} of the 7 push-ins ({cam_dup_list}): the quintic ease travels < 5 × 10⁻⁵ of the move in its final 1/60 s, below one device pixel, so the move lands on its target one frame early — 1 pair of 59–71 (1.4–1.7 %, under the 2 % bound), no cadence; no camera move has a repeat anywhere else. Pull-backs have none. The scrub has one (pair 862→863, the minimum-jerk tail). Typing: {typ_dup} of {typ_pairs} (the field is static between keystrokes by design). Wheel scroll: the static pairs are the three frames between the wheel event and the start of the browser's smooth scroll (2039–2043) and the frames after it settles (2090–2098); the moving part 2043–2089 has none."]
    F += ["", "- Camera moves: on the delivered mp4, duplicate pairs occur only in the first/last ≤ 4 frames of a move (the quintic ease starts and ends below one pixel per frame), none sits inside a move, there are no exact zeros, and the flip rate is far from a 2:2 (≈ 1.0), 3:2 or 5:5 cadence; the only byte-identical source pair is the final one of each push-in (table above).",
          "- Pointer-only windows: the pointer is 33 × 45 px on a 1920 × 1080 frame, so the 160 × 90 downscale puts its motion at the metric floor (max Δ 0.06–0.46 of 255); the “duplicate” pairs inside slow pointer moves are the pointer moving < 1 px between frames (minimum-jerk tails), not repeated frames — 0 exact zeros in any pointer move.",
          f"- Typing burst (frames {typ_frames[0]}–{typ_frames[1] - 1}): the field is static between keystrokes by design (the caret does not blink under the stepped clock: `caret-animation: manual`), so {typ_dup} of {typ_pairs} pairs are duplicates there; the 6 keystroke pairs (the frame of each key event: {key_frames}) each change the frame.",
          f"- Wheel scroll (frames 2039–2089): the browser's smooth scroll runs on the stepped clock; {next((w['dup_pairs'] for w in dup['moving_windows'] if 'wheel' in w['kind'].lower() or 'scroll' in w['label'].lower()), '—')} duplicate pairs on the mp4 — the frames between the wheel event and the start of the smooth scroll (2039–2043) and the frames after it settles (from 2090) are static; the moving part 2043–2089 has no exact repeat on the source frames.",
          f"- Pops: {qa['pops']['pairs_over_8_total']} pairs exceed 8/255; {qa['pops']['unexplained_count']} are unexplained — every one lies inside a camera move (continuous neighbours), is the product's response to an input (the strip list re-filtering on a keystroke, the game opening at pair 491) or is one of the two cuts. Classification per pair: `film45_qa.json` → `pops.classified`.",
          "- Cuts (hard cuts, product route change; the film is one continuous encode, nothing is spliced, so there is no splice PSNR to report):", "",
          "| cut | pair | PSNR (dB) | mean &#124;Δ&#124; (160×90, 0–255) |", "|---|---|---|---|"]
    for c in qa["cuts"]:
        F.append(f"| frame {c['cut_frame']} | {c['pair'][0]}→{c['pair'][1]} | {c['psnr_db']:.2f} | {c['mean_abs_delta_255_160x90']:.2f} |")
    F.append("")

    # ---- pointer/input log + disclosure -------------------------------------------------------------------------------------------------
    F += ["## 6 · Pointer and input log · capture-method disclosure", "",
          "Input events (all real Playwright input events dispatched at the pointer position, logged by the harness):", "",
          "| frame | t (s) | event | at (CSS px) | zoom | what |", "|---|---|---|---|---|---|"]
    for e in tl["events"]:
        F.append(f"| {e['f']} | {e['t']:.3f} | {e['type']}{(' ' + repr(e['key'])) if e.get('key') else ''} | ({e['x']}, {e['y']}) | {e['cam']['z']:.2f}× | {e['label']} |")
    F += ["", "Pointer moves (minimum-jerk profile, decelerating into the target, ≥ 0.3 s dwell before each click):", "",
          "| frames | s | from → to (CSS px) | distance | peak CSS px/s | peak film px/s at 1× | what |", "|---|---|---|---|---|---|---|"]
    for p in tl["ptrMoves"]:
        F.append(f"| {p['f0']}–{p['f1']} | {p['seconds']:.3f} | ({p['from'][0]}, {p['from'][1]}) → ({p['to'][0]}, {p['to'][1]}) | {p['distCss']} | {p['peakCss']} | {p['peakFilm1x']} | {p['label']} |")
    peak = max(p["peakFilm1x"] for p in tl["ptrMoves"] if "scrub" not in p["label"].lower())
    scrub = next((p for p in tl["ptrMoves"] if "scrub" in p["label"].lower()), None)
    F += ["", f"Peak pointer speed over all moves: {peak} film px/s at 1× (limit 1,200). The clock scrub (frames {scrub['f0']}–{scrub['f1']}) is a hover drag of the crosshair at {scrub['peakFilm1x']} film px/s at 1× (limit for drags 600) with the legend and the six dots recomputing on every frame." if scrub else "", "",
          "Disclosure:", "",
          f"- **Frame-stepped capture, not a real-time recording.** {tl['clock']}. The product's own animations (hover highlights, the wheel's smooth scroll, canvas redraws) run on that stepped clock, so each film frame is exactly 1/60 s of product time. The whole film is one continuous capture (`films/capture45.js` + `films/storyboard45.js`); the two route changes (Discovery at frame 1776, Scoreboard at 2171) are hard cuts executed by the harness with no real-time waits.",
          f"- **Camera.** {tl['capture']}. The editorial zoom is a re-rasterised clip of the live page (DOM text is re-rendered by the browser at the zoomed scale, canvas charts have a 2× backing store); the clip is requested 6 CSS px larger than the frame (nominal 1929 × 1089) because Chromium snaps a fractional clip to device pixels and returns up to 6 px less than nominal; the source frames come out {size_range} and are normalised to exactly 1920 × 1080 by cropping at the origin (no scaling, no padding: {len(enc.get('short_frames_edge_replicated', []))} short frames). Source frame sizes in `films/the-tape-45s-encode.json`.",
          f"- **Pointer.** {tl['pointer']}. The cursor is a DOM element drawn into the page by the harness (counter-scaled so it stays 33 × 45 px on the frame at every zoom) at the position of the real mouse; it is not composited after the fact. Hover states are the product's own (`.seg button:hover`, `.btn:hover`, row and strip highlights, the input's focus ring).",
          f"- **Typing.** `ravens` is six real key events at 10–12 characters/s (inter-key intervals 5/6/5/5/6 frames = 12.0/10.0/12.0/12.0/10.0 cps, mean 11.2, every interval inside the 10–14 band and within ±20 % of the mean), the field at 2.25×; the caret is visible and non-blinking (`caret-animation: manual`) so it cannot alias with the stepped clock; the field, the count line and the strips update in the frame of each key event (the input is dispatched before that frame is rasterised, so the six changed pairs are 289→290, 294→295, 300→301, 305→306, 310→311, 316→317); the hold after the last character is {hold_after_last_key_frames} frames = {hold_after_last_key_s:.2f} s (last key at frame {last_key_frame}, the pointer leaves for the strip at frame {next_move_frame}; no Enter is needed — the filter is live).",
          (lambda rg: f"- **Re-capture (this capture vs the one the independent reviewer measured).** The reviewer's report asked for two fixes — one typing interval at 15 cps (the 4-frame e→n gap) and 480 source frames whose clip had come back 1–3 device px short (1917–1923 × 1077–1083) and were edge-replicated by the encoder — so the film was re-captured with the same storyboard: inter-key gaps 5/6/5/5/6 frames and the clip oversized so no short frame occurs. Pixel regression on the native source frames (`handoff/film45_regression.json`): {rg['frames_identical']} of 2,700 frames byte-identical; {rg['frames_differing']} differ, of which only frames {', '.join(map(str, rg['frames_with_any_pixel_over_16_of_255']))} carry a visible change (the typing state moved one frame later: `rave`→`raven` and `raven`→`ravens`, so the Find field and the re-filtered strip list differ there); every other difference is ≤ {rg['max_abs_delta_outside_310_316']}/255 on at most {rg['max_changed_pixels_outside_310_316']:,} pixels per frame (sub-pixel anti-aliasing of the re-rasterised clip, {rg['differing_in_camera_moves']} such frames inside camera moves, {rg['differing_in_pointer_moves']} inside pointer moves, {rg['differing_elsewhere']} in holds where the shift is constant across the hold). Camera moves, pointer path, holds, clicks and cuts are frame-for-frame identical in `films/film45_timeline.json`.")(load(os.path.join(OUT, "film45_regression.json"))),
          "- **Scroll.** The agreement table is wider than its panel at 1280 wide (table 572 CSS px in a 371 px wrapper), so N / mean diff and within-2-pp / corr cannot share one readable frame; the beat reads the left half, then a real wheel event scrolls the wrapper 201 CSS px (browser smooth scroll on the stepped clock, +4 px overshoot clamped by the browser) and reads the right half.",
          "- **Pre-roll (before frame 0, logged):** " + " · ".join(p["step"] if isinstance(p, dict) else str(p) for p in tl["preroll"]) + ".",
          "- **No editorial crops, speed changes, fades, overlays or added text.** Nothing on screen is outside the product.", ""]

    # ---- contact sheet + final hold ----------------------------------------------------------------------------------------------------------
    F += ["## 7 · Contact sheet and final hold", "",
          f"- `{qa['contact_sheet']}` — 45 frames, one per second (frame 60·k, k = 0 … 44), native 1920 × 1080 frames scaled to tiles.",
          f"- Final hold frames at 1× scale of the frame: `handoff/frames45/f02519.png` (hold starts), `f02609.png`, `f02699.png` (last frame). The hold is frames 2519–2699 = {(2699 - 2519 + 1) / 60:.2f} s on a product state at 3.9×: the Scoreboard's `All` block — `Pinnacle close · 363 · 0.2093` and `Polymarket T-1min · 363 · 0.2092`, pointer resting on the Polymarket row (row highlight is the product's).", ""]

    # ---- app version + changes ----------------------------------------------------------------------------------------------------------------
    F += ["## App version and what changed", "",
          f"- Deployed app **The Tape**, asset `2088f758-e90b-423c-ba64-c4c7a2b1ca63`, redeployed in place. Filmed bundle hash `{filmed_hash}` (the bundle the 2,700 frames were captured from); final deployed bundle hash `{bundle_hash}` (sha256 over the sorted `sha256  path` lines of the code files; `films/app_version.txt` lists the per-file hashes; `data/` unchanged since Tier 1). The two differ only in `js/game.js` → `exportPng`: the Export PNG footer (window + attribution line, ~170 characters) now wraps on ` · ` instead of running past the right edge of the exported image (`The Tape` was cut off at 1280 and 1440 wide, everything after `Sportradar` at 390); exact diff in `films/app_version_game.js.patch` (2 hunks). The export is not exercised in the film, so no filmed pixel depends on it; the deployed game view is otherwise byte-identical to the filmed one.",
          "- Changes since the accepted v2 films (artifact pass, no new features, no vendor calls):",
          "  - tooltip: `max-width: min(380px, calc(100vw − 16px))`, `.t-row > span { white-space: nowrap }` and a position clamp in `showTip` — fixes the `wall clock` label wrap recorded against the build and keeps tooltips inside the viewport at 390 px;",
          "  - game view: `.gamepick` min-width / select max-width and 600-px media rules (no clipped picker at 390 × 844); play-label clamp `lx` and a hit test on the marker or its label (the Q4/OT labels were drawn past the right edge at 1280); the closes panel's Polymarket row is labelled `Polymarket` in both side modes;",
          "  - charts: `barChart` rotates the second-line `n=` label when a bar is narrower than 48 px (no overlapping N labels at 1280/1440);",
          "  - styles: `.seg button:hover { color: var(--text) }` so segment buttons (Side ATL/BAL, Books, Unit) show a hover state before the click (the standard's “hover state visible”; the only change made after the first 45 s capture, which is why the film was re-captured against this bundle).",
          "- Re-checked on this bundle at 1440 × 900, 1280 × 720 and 390 × 844 (`qa/layout_scan.js` → `qa/layout_scan_final.json`, 7 routes × 3 viewports): 0 console errors, 0 page errors, 0 failed requests; no viewport overflow, no clipped text, no wrapped single-line label, tooltip or banner. The scanner's only flags are two intended layouts: the Today table's two-line cells (price + timestamp, teams + venue; the same 176 cells at all three widths) and, at 390 px only, the two legend footnotes under the game chart (`● open (first entry) · ■ close …`, `Polymarket (1 − away price) · …`), which are prose captions that wrap onto a second line at phone width. The app's one native output, the game view's Export PNG, was triggered on the final bundle at all three widths (`[data-testid=export-png]`, real download event): valid PNGs of 1832 × 904, 2152 × 1236 and 716 × 1084 px with the full attribution footer (`Sportsbook lines: OpticOdds · Prices: Polymarket · Results and plays: Sportradar · The Tape`) inside the image.", ""]
    # ---- independent review (standard §6) ----------------------------------------------------------------------------------------------------
    F += ["## Independent review (standard §6)", "",
          "The film, the standard (§3 verbatim) and the beat list were handed to a fresh independent reviewer with the question “list every frame range that breaks a rule in section 3, with the measured value”. The reviewer measured the mp4 and the native PNGs (160 × 90 difference profile on all 2,699 pairs, byte-identity on the source frames, NCC cursor track against the input log, per-glyph ink heights, crop verification) and treated `timeline.json` as a claim.",
          "",
          "- Round 1 (`handoff/film45_review_1.md`, on the first reviewed capture): no hard breaks; two items to fix — one typing interval at 15 cps (4-frame e→n gap) and 480 source frames returned 1–3 device px short and edge-replicated by the encoder. Both fixed by re-capture (inter-key gaps 5/6/5/5/6; clip oversized 6 CSS px); see the re-capture regression above.",
          "- Round 2 (`handoff/film45_review_2.md`, on the delivered mp4 `d602d66d…`): typing passes outright (12.0/10.0/12.0/12.0/10.0 cps, mean 11.1; caret 42 px on every frame 252–370; 52-frame hold); all 2,700 source frames ≥ 1920 × 1080 and the mp4 is a verified top-left crop; every camera and pointer timing, peak speed (max 1,156 film px/s at 1×) and easing profile re-measured identical; two cuts (1775→1776 Δ 20.72, 2170→2171 Δ 14.92) unchanged; pops outside cuts and camera ramps are only the two product responses (310→311 keystroke refilter, 491→492 game opens); no cadence; every logged hold is a byte-identical run. **No hard breaks.**",
          "- Items the reviewer records as borderline or judgement calls, which stand as filmed (maker's position in brackets):",
          "  - the duplicate-pair clause read literally fails in every camera (6.8–14.1 %), pointer (8.7–32.8 %) and wheel (18.6 %) window, while native byte-identity passes [the 0.02/255 floor counts the sub-pixel tails of eased moves and the 33 × 45 px pointer moving < 1 px as “duplicates”; the source-frame test in §5 shows the only byte-identical pairs are the final pair of 5 push-ins, the scrub tail and the static frames around the wheel event — no repeated frames, no cadence];",
          "  - text heights fail on glyph ink and pass on em at the 2.2–2.5× beats (digits 26–31 px vs 32; caps 26 px vs 28; typed word 20 px x-height, cap 26) [§4 reports both readings; the rule's “28 px tall (x-height ≥ 14 px)” is an em-style measure, and the x-heights are 20–22 px];",
          "  - payoff glyphs 48/47/48/48 (two `2`s at 47 px ink; em 64) [reported in §4; the payoff is the largest readable scale the table allows — its ink spans x 25–1892 of 1920];",
          "  - dwell (18 frames), settle (18), read holds (72) and click holds (37) sit exactly at the thresholds [by design — the standard's minima];",
          "  - two composition calls: after the wheel scroll the `All` label is out of frame (the row highlight ties the values; the agreement table is 572 CSS px in a 371 px wrapper, §6 Scroll), and during the hover scrub the product's numeric readout sits below the 2.4× frame (the crosshair and the six per-series dots recompute in frame).",
          ""]
    F += ["## Receipts", "", "- `handoff/film45_receipts.md` — every number visible in the film → data source, with DOM cross-checks (" + f"{n_ok}/{len(checks)} pass).",
          "- `films/film45_timeline.json` — per-frame pointer position and speed, camera, in-frame flag; holds, camera moves, pointer moves, events, cuts, DOM notes.",
          "- `handoff/film45_qa.json`, `handoff/film45_text.json`, `films/the-tape-45s-encode.json` — the measurements behind sections 1, 2, 4 and 5.",
          "- Reproduce: `node`-side `films/capture45.js` + `films/storyboard45.js` against the deployed bundle (served locally), then `films/encode45.py`, `films/qa45.py`, `films/measure45.py`, `pipeline/14_film45_receipts.py`.", ""]
    open(os.path.join(OUT, "films-v2.md"), "w").write("\n".join(F) + "\n")

    # ---- trim handoff/frames45 to the key frames --------------------------------------------------------------------------------------------------
    keep = {0, 2519, 2609, 2699, 1775, 1776, 2170, 2171}
    for e in tl["events"]:
        keep.add(e["f"])
        if e["type"] == "click":
            keep.add(e["f"] + 1)
    for l in notes:
        keep.add(nframe(l))
    for e in text:
        keep.add(e["frame"])
    fr_dir = os.path.join(OUT, "frames45")
    removed = 0
    for fn in os.listdir(fr_dir):
        mm = re.match(r"f(\d{5})\.png$", fn)
        if mm and int(mm.group(1)) not in keep:
            os.remove(os.path.join(fr_dir, fn))
            removed += 1
    missing_frames = sorted(f for f in keep if not os.path.exists(os.path.join(fr_dir, f"f{f:05d}.png")))
    print(f"films-v2.md ({len(F)} lines), film45_receipts.md ({len(R)} lines, {n_ok}/{len(checks)} cross-checks pass); frames45: kept {len(keep)} key frames, removed {removed}; missing {missing_frames}")
    for lab, ok, det in checks:
        if not ok:
            print(f"  FAILED CHECK: {lab} — {det}")


if __name__ == "__main__":
    main()
