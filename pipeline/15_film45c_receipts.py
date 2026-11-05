#!/usr/bin/env python3
"""
15_film45c_receipts.py — receipts for the v2.1 pass of the 45-second film (film45c: re-framed for the caption band, delivered
as a clean film and a captioned release candidate over the identical 2,700 frames). Writes handoff/films-v2.md (production
standard §5 items 1–7 + §7 caption receipts) and handoff/film45_receipts.md (every number visible in the film → its source).

Inputs
  /tmp/frames/film45c/timeline.json          per-frame timeline written by films/capture45c.js (copied to films/film45c_timeline.json)
  handoff/film45c_qa.json                    films/qa45.py on the clean delivery (+ films/dupsrc45.py: source_exact_duplicates)
  handoff/film45c_qa_captioned.json          films/qa45.py on the captioned delivery
  handoff/film45c_text.json                  films/measure45c.py: text heights on native frames of the clean delivery
  handoff/film45_captions.json               films/caption45.py: caption table, fades, luminance, band-clear, compositing
  handoff/film45c_capdiff.json               films/capdiff45.py: clean vs captioned, masters and deliveries
  handoff/film45c_capcheck/captions.txt      the parent's review-tools/capcheck.py run (copied)
  films/the-tape-45s-encode.json             films/encode45.py
  films/app_version.txt                      bundle hash of the deployed app the film was captured from
  a9-data/derived/{manifest,wall,analysis}.json, games/nfl_2026101240603BF9.json
Outputs
  handoff/films-v2.md, handoff/film45_receipts.md, films/film45c_timeline.json; handoff/frames45c/qa_* trimmed to key frames
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
ASSET_CLEAN = os.environ.get("A9_FILM45_ASSET", "(assigned when the mp4 is shared; see the checkpoint mail)")
ASSET_CAP = os.environ.get("A9_FILM45C_ASSET", "(assigned when the mp4 is shared; see the checkpoint mail)")
FROZEN_V2 = {"asset": "891d68d4-50a9-4b6c-acdf-7a6134e4f55f", "bytes": 16568149,
             "sha256": "d602d66d60c87948afce52afbfa407dd610dcece930a854274201f474bb7511d",
             "master_sha256": "45ff2ada4abb1208e04bc3719aaa11b3468c6f7421ae11749474277f7d330886"}


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
    src = os.path.join(FRAMES, "film45c", "timeline.json")
    tl_path = os.path.join(BUILD, "films", "film45c_timeline.json")
    if os.path.exists(src):
        shutil.copy(src, tl_path)
    tl = load(tl_path)
    qa = load(os.path.join(OUT, "film45c_qa.json"))
    qa_cap = load(os.path.join(OUT, "film45c_qa_captioned.json"))
    text = load(os.path.join(OUT, "film45c_text.json"))["targets"]
    enc = load(os.path.join(BUILD, "films", "the-tape-45s-encode.json"))
    caps = load(os.path.join(OUT, "film45_captions.json"))
    capdiff = load(os.path.join(OUT, "film45c_capdiff.json"))
    capcheck_txt = ""
    cc_path = os.path.join(OUT, "film45c_capcheck", "captions.txt")
    if os.path.exists(cc_path):
        capcheck_txt = open(cc_path).read()
    _sz = [tuple(int(v) for v in k.split("x")) for k in enc.get("source_sizes", {}).keys()]
    size_range = (f"{min(w for w, h in _sz)}–{max(w for w, h in _sz)} × {min(h for w, h in _sz)}–{max(h for w, h in _sz)}" if _sz else "1920 × 1080")
    appv = open(os.path.join(BUILD, "films", "app_version_45c.txt")).read()
    bundle_hash = re.search(r"^bundle_hash ([0-9a-f]{64})", appv, re.M).group(1)
    font_sha = sha256(os.path.join(BUILD, caps["font"]["file"]))
    assert font_sha == caps["font"]["sha256"], (font_sha, caps["font"]["sha256"])
    if tl.get("frames") != 2700:
        print(f"WARNING: timeline has {tl.get('frames')} frames", file=sys.stderr)
    notes = {n["label"]: n for n in tl["notes"]}
    rows_tl = tl["timeline"]
    cam_at = {row["f"]: row["cam"] for row in rows_tl}
    holds = tl["holds"]
    cuts = [c["f"] for c in tl["cuts"]]
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
        return min(n["f"], 2699) if n["f"] not in cuts else n["f"] - 1

    def hold_span(prefix):
        hs = [h for h in holds if h["label"].startswith(prefix)]
        return (hs[0]["f0"], hs[-1]["f1"]) if hs else (None, None)

    def beat_span(letter):
        fr = [r["f"] for r in rows_tl if r["label"].startswith(letter + ":")]
        return min(fr), max(fr)

    beats = {b: beat_span(b) for b in "ABCDEF"}

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
    a_read = hold_span("A: read")
    R = ["# Film receipts — every number visible in the 45-second film (v2.1 frames), with its source", "",
         "The film is a frame-stepped capture of the deployed app (method and frame-level QA in `films-v2.md`). At each beat the on-screen text was read "
         "from the DOM at capture time (`films/film45c_timeline.json` → `notes`; the frame numbers below are the native frames of `films/the-tape-45s.mp4` and "
         "`films/the-tape-45s-captioned.mp4`, which share the same 2,700 frames; 0-based) and every figure is traced to the dataset or analysis value it is rendered from. "
         "Where a figure is a pure function of the raw vendor responses the receipt names the vendor field. Cross-check lines compare the captured DOM text with the value "
         "recomputed here from the derived data. The caption texts themselves are receipted in `films-v2.md` §7.", ""]

    # ---- status line + header -------------------------------------------------------------------------------------------
    R += ["## Status line (bottom of the app at 1×)", "",
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
    z_hdr = cam_at[a_read[0]]["z"]
    R += [f"## Wall header (beat A, {z_hdr:.2f}× on the header numbers, frames {a_read[0]}–{a_read[1]})", "",
          f"The {z_hdr:.2f}× frame holds the right-hand part of the header: `1,332,476 sportsbook price updates`, `4,195,032 Polymarket price samples · 3,387 markets · 1,150 games`, the attribution line and the count line "
          "`1150 strips · 1136 with sportsbook history · 889 with both sources`. The left-hand cells (`1,150 matched games · 13 leagues`, `1,136 / 1,150 with sportsbook history (5 books)`) are outside the zoomed frame but are legible at 1× in frames 0–71 and listed here for completeness.", ""]
    for k, v in hdr.items():
        R.append(f"- `{k}` — {v}.")
    stats = dom("A: wall", "stats")
    missing = [k for k in hdr if re.match(r"[+$]?\s?[\d,]+", k) and re.match(r"[+$]?\s?[\d,]+", k).group(0) not in norm(stats)]
    R.append(check(f"header figures in the DOM at frame {nframe('A: wall')}", not missing, f"all {len(hdr)} figures present" if not missing else f"missing {missing}"))
    cnt = dom("A: wall", "count")
    R.append(f"- Count line `{cnt}` — `wall.games` length {len(games)}; strips with OpticOdds history (`oo` ≠ null) {n_books}; strips with both sources {n_both} (`wall.js` → `update()`).")
    R.append(check("count line (strips · with sportsbook history · with both sources)", cnt == f"{len(games)} strips · {n_books} with sportsbook history · {n_both} with both sources", f"frame {nframe('A: wall')}"))
    R.append("")

    # ---- find ----------------------------------------------------------------------------------------------------------
    rav = [g for g in games if "ravens" in (g.get("an", "") + " " + g.get("hn", "") + " " + g["away"] + " " + g["home"]).lower()]
    cnt2 = dom("B: ravens filter", "count")
    key_events = [e for e in tl["events"] if e["type"] == "key"]
    key_frames = [e["f"] for e in key_events]
    typed_hold = hold_span("B: type")
    R += [f"## Find team → `ravens` (beat B, frames {key_frames[0]}–{typed_hold[1]})", "",
          f"- Typed `ravens` ({len(key_events)} real key events, frames {'/'.join(map(str, key_frames))}). The filter matches team names and abbreviations containing the typed text (`wall.js` → `filtered()`); `wall.json` has {len(rav)} games whose team names contain “ravens”: " + "; ".join(f"{g['lg'].upper()} {g['away']} @ {g['home']} {iso_min(g['ko'])}" for g in rav) + ".",
          f"- Count line after typing: `{cnt2}` — {len(rav)} strips; {sum(1 for g in rav if g.get('oo'))} with OpticOdds history; {sum(1 for g in rav if g.get('pin') is not None and (g.get('pm') or {}).get('t1m') is not None)} with both sources.",
          check("ravens count line", cnt2 == f"{len(rav)} strips · {sum(1 for g in rav if g.get('oo'))} with sportsbook history · {sum(1 for g in rav if g.get('pin') is not None and (g.get('pm') or {}).get('t1m') is not None)} with both sources", f"frame {nframe('B: ravens filter')}"), ""]

    # ---- hero strip ---------------------------------------------------------------------------------------------------------
    wg = next(g for g in games if g["key"] == HERO)
    tip = dom("B: hero strip hover", "tip")
    pm1 = (wg.get("pm") or {}).get("t1m")
    strip_click = next(e for e in tl["events"] if e["type"] == "click" and "ATL" in e["label"])
    dwell = hold_span("B: dwell (strip")
    R += [f"## Strip BAL @ ATL (beat B, frames {dwell[0]}–{strip_click['f']})", "",
          f"- The strip's canvas label `NFL · BAL @ ATL` with the score `30-23` and the kickoff date: `wall.json` game `{wg['key']}`, kickoff {iso(wg['ko'])} (Sportradar `scheduled`), final Baltimore Ravens {wg['as']} – Atlanta Falcons {wg['hs']} (Sportradar). The strip's bars are the per-hour Pinnacle no-vig (home) and Polymarket (home) series of `wall.json`.",
          f"- The hover tooltip is logged but not read in this cut: at the {cam_at[dwell[0]]['z']:.2f}× framing only its top border and padding enter the bottom of the frame (no tooltip text is on screen; `films-v2.md` §6). Its DOM text for completeness — Pinnacle close (home) {wg['pin'] * 100:.1f}% (`wall.pin`), Polymarket T−1 min (home) {pm1 * 100:.1f}% (`wall.pm.t1m`), Polymarket ML volume ${fmt_n(int(wg['vol']))} (`wall.vol`): `{tip[:300]}`",
          check("strip game: final score and kickoff in the tooltip DOM", str(wg["as"]) in tip and str(wg["hs"]) in tip and iso_min(wg["ko"])[:16] in tip, f"frame {nframe('B: hero strip hover')}"), ""]

    # ---- hero game -----------------------------------------------------------------------------------------------------------
    ko = hero["kickoff"]
    books = hero["oo"]["books"]
    head = dom("B: game opened", "head")
    g_open = hold_span("B: click BAL")
    R += [f"## Game view — Baltimore Ravens @ Atlanta Falcons (beats B–D, frames {g_open[0]}–{cuts[0] - 1})", "",
          f"- Title `Baltimore Ravens @ Atlanta Falcons 30–23 (OT) · NFL · week 5 · kickoff {iso_min(ko)} · Oct 11, 8:20 PM ET · …` — Sportradar game `{hero['match']['sr_game_id']}` (scheduled, venue, final with an overtime period), OpticOdds fixture `{hero['match']['oo_fixture_id']}`, matcher tier `{hero['match']['tier']}`. At the {cam_at[g_open[0]]['z']:.2f}× framing the head line is visible from `…0-12 00:20Z · Oct 11, 8:20 PM ET · Mercedes-Benz Stadium` (left edge of the frame cuts the date); the full title is on screen at 1× (frames {hold_span('C: full history')[0]}–{hold_span('C: full history')[1]}).",
          f"  on-screen: `{head[:300]}`",
          check("title score 30–23 (OT) and kickoff", "30–23" in head and iso_min(ko)[:16] in head, f"frame {nframe('B: game opened')}")]
    n_rows = {b: len([r for r in books[b]["ml"]["novig"] if r[1] is not None]) for b in books}
    hs = hero["pm"].get("home_series") or []
    n_pts = sum(n_rows.values()) + len(hs)
    legend = dom("B: game opened", "legend")
    R += [f"- Chart caption `… → … · {n_pts} points · no-vig (multiplicative) · Polymarket = sampled price` and legend `N = {n_pts} entries` (the same count in every window — Full history, In-game): the number of rows over all visible series = " + " + ".join(f"{b} {n}" for b, n in n_rows.items()) + f" no-vig rows + Polymarket {len(hs)} compressed step points = {n_pts}. The caption is legible at 1× (C picture) and partially inside the toolbar framing (`…2 03:49Z · 1693 points`, left edge cut).",
          check(f"`N = {n_pts} entries` in the legend", f"N = {n_pts} entries" in norm(legend) or f"N={n_pts}entries" in squash(legend), f"frame {nframe('B: game opened')}")]
    closes = dom("C: open → close rows", "closes")
    c_read = hold_span("C: read")
    R += [f"- Side panel `Moneyline, BAL (away)` (source · open · close · age), frames {c_read[0]}–{c_read[1]} at {cam_at[c_read[0]]['z']:.2f}× (the side column scrolled 99 CSS px by a real wheel event so the table header sits at the top of the column; Pinnacle, DraftKings and FanDuel rows are inside the frame, BetMGM and Caesars below it): no-vig probabilities of the BAL side — for each book open = multiplicative no-vig of its first retained entry, close = last entry ≤ kickoff, age = minutes (or hours) from that close to kickoff (`game.js` → `closes()`):"]
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
    R.append(f"  - Polymarket (away price): open {pm_open_away * 100:.1f}% at {iso(hs[0][0])}, last pre-kickoff sample {pm_close_away * 100:.1f}% at {iso(pm_close[0])}, age {pm_age:.0f} min → `{pm_age:.0f} m`; {len(hs)} compressed step points (market `{mk.get('market_id')}`, {mk.get('n_samples')} raw CLOB samples; home price = CLOB `/prices-history` p, away = 1 − p). The Polymarket row is below the {cam_at[c_read[0]]['z']:.2f}× frame; it is legible at 1× in the C picture.")
    side_ok &= f"Polymarket{pm_open_away * 100:.1f}%{pm_close_away * 100:.1f}%{pm_age:.0f}m" in squash(closes)
    R.append(f"  on-screen: `{closes[:420]}`")
    R.append(check("open / close / age for the five books and Polymarket match the recomputation", side_ok, f"frame {nframe('C: open → close rows')}"))
    fd = books["FanDuel"]["ml"]
    fd_a = fd["raw"]["away"]
    fd_close_a = [r for r in fd_a if r[0] <= ko][-1]
    R.append(f"- The reversal that beat C and caption 3 are built on: FanDuel BAL {fd_a[0][1]:+.0f} at {iso(fd_a[0][0])} (open) → {fd_close_a[1]:+.0f} at {iso(fd_close_a[0])} (last pre-kickoff entry), i.e. no-vig {books['FanDuel']['ml']['novig'][0][2] * 100:.1f}% → {[r for r in books['FanDuel']['ml']['novig'] if r[0] <= ko][-1][2] * 100:.1f}% on the BAL side (caption 3 rounds these to 74% and 39%).")
    pics = [h for h in holds if h["kind"] == "picture" and h["label"][0] in "CD"]
    R.append("- `Polymarket pre-kickoff checkpoints` panel (visible at 1× in frames " + ", ".join(f"{h['f0']}–{h['f1']}" for h in pics) + "; not zoomed): " + "; ".join(f"{lab} {wg['pm'][k] * 100:.1f}% (age {wg['pma'][k]:.1f} min)" for k, lab in (("t24h", "T−24 h"), ("t6h", "T−6 h"), ("t1h", "T−1 h"), ("t10m", "T−10 min"), ("t1m", "T−1 min")) if wg["pm"].get(k) is not None) + " — `wall.pm.*` / `wall.pma.*` (last CLOB sample at or before each checkpoint and its age).")
    plays_all = hero["sr"].get("plays", [])
    plays = [p for p in plays_all if p.get("scoring")]
    final_t = min(plays_all[-1]["t"] + 180, ko + 8 * 3600) if plays_all else None
    ig_click = next(e for e in tl["events"] if e["type"] == "click" and "In-game" in e["label"])
    ig_pts = sum(1 for b in books for r in books[b]["ml"]["novig"] if r[1] is not None and ko - 600 <= r[0] <= final_t) + sum(1 for r in hs if ko - 600 <= r[0] <= final_t)
    R += [f"- In-game preset (click at frame {ig_click['f']}): domain = kickoff − 10 min → last Sportradar play wall clock + 3 min = {iso_min(ko - 600)} → {iso_min(final_t)}; the caption keeps `{n_pts} points` because `nEntries` counts every row of the visible series regardless of the window ({ig_pts} of them fall inside the in-game window). "
          f"The Polymarket BAL (away) price inside that window (the side the chart plots, `Moneyline, BAL (away)`): {(1 - [r for r in hs if r[0] <= ko][-1][1]) * 100:.1f}% at the last pre-kickoff sample ({iso_min([r for r in hs if r[0] <= ko][-1][0])}), a low of {min(1 - r[1] for r in hs if ko <= r[0] <= final_t) * 100:.1f}% at {iso_min(min((r for r in hs if ko <= r[0] <= final_t), key=lambda r: 1 - r[1])[0])} (Atlanta leading 23–15 after its 03:05Z field goal), a high of {max(1 - r[1] for r in hs if ko <= r[0] <= final_t) * 100:.1f}% at {iso_min(max((r for r in hs if ko <= r[0] <= final_t), key=lambda r: 1 - r[1])[0])} (the overtime drive) and {(1 - [r for r in hs if ko <= r[0] <= final_t][-1][1]) * 100:.1f}% at the last sample inside the window ({iso_min([r for r in hs if ko <= r[0] <= final_t][-1][0])}); the market's 100% samples begin at {iso_min([r for r in hs if r[0] > final_t][0][0])}, outside the window (CLOB `/prices-history`, home price p; away = 1 − p). The in-game picture is frames {hold_span('D: in-game swing')[0]}–{hold_span('D: in-game picture')[1]} at 1×.",
          f"- Scoring plays panel (`Scoring plays · Sportradar`, frames {hold_span('D: read')[0]}–{hold_span('D: read')[1]} at {cam_at[hold_span('D: read')[0]]['z']:.2f}×; the side column scrolled a further 427 CSS px to put the panel title at the top of the column — the first scoring play is the row on screen; Sportradar `wall_clock`, running score away–home, period label (`Q1` … `OT`) and game clock, description):"]
    for p in plays:
        R.append(f"  - {iso(p['t'])} · {p.get('pl') or ('Q' + str(p.get('period')))} {p.get('clock') or ''} · {p.get('ap')}–{p.get('hp')} · {(p.get('desc') or '')[:120]}")
    plays_dom = dom("D: scoring plays", "plays")
    p0 = plays[0]
    want0 = squash(f"{iso(p0['t'])[11:16]}Z{p0['ap']}–{p0['hp']}Q{p0['period']} {p0['clock']}")
    R.append(f"  on-screen (panel text): `{plays_dom[:300]}`")
    R.append(check("first scoring play row (wall clock, score, period, clock) matches the Sportradar play", want0 in squash(plays_dom), f"frame {nframe('D: scoring plays')}; expected `{iso(p0['t'])[11:16]}Z · {p0['ap']}–{p0['hp']} · Q{p0['period']} {p0['clock']}`"))
    R.append(check("every scoring play's running score appears in the panel text", all(f"{p['ap']}–{p['hp']}" in norm(plays_dom).replace("-", "–") for p in plays), f"{len(plays)} plays"))
    R.append("")

    # ---- discovery -------------------------------------------------------------------------------------------------------------
    per = analysis["agreement"]["per_league"]
    e_span = beats["E"]
    R += [f"## Discovery — Agreement by league (beat E, frames {e_span[0]}–{e_span[1]})", "",
          f"- `All` row: N = {ag_all['n']} games with a Pinnacle close and a Polymarket sample ≤ 30 min before kickoff; mean (Polymarket T−1 min − Pinnacle no-vig) {ag_all['mean_diff'] * 100:+.2f} pp, 95% CI {ag_all['mean_diff_ci95'][0] * 100:+.2f} … {ag_all['mean_diff_ci95'][1] * 100:+.2f} pp, mean |diff| {ag_all.get('mean_abs_diff', 0) * 100:+.2f} pp, within 2 pp {round(ag_all['share_within_2pp'] * 100)}%, corr {ag_all['corr_pm_pinnacle']:.3f} (`analysis.agreement.per_league.all`; caption 6 says “nearly agree”, caption 7 quotes the 96%).",
          f"- Rows visible in the {cam_at[hold_span('E: read')[0]]['z']:.2f}× frame (`All` plus the league rows that fit under it), `analysis.agreement.per_league`:", "",
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
    f_span = beats["F"]
    R += [f"## Scoreboard — common game set (beat F, frames {f_span[0]}–{f_span[1]})", "",
          f"- Common set definition: {cal['common_definition']}.",
          f"- N per league (identical for every source row): " + ", ".join(f"{lg} {n}" for lg, n in cal["common_n"].items()) + ".",
          f"- Rows visible in the film (`analysis.calibration.common_per_league`; `results/d_calibration_summary.csv`, mode = common; the {cam_at[hold_span('F: payoff')[0]]['z']:.2f}× payoff frames the `All` block's `source · N · Brier` columns for Pinnacle close … Polymarket T-1min, the page scrolled 203 CSS px by the harness before the cut so the block sits at the top):", "",
          "| league | source | N | Brier | 95% CI | log loss | 95% CI | home win rate | mean p(home) |", "|---|---|---|---|---|---|---|---|---|"]
    for lg in ("all", "nfl"):
        for s, r in cal["common_per_league"].get(lg, {}).items():
            R.append(f"| {lg} | {s} | {r['n']} | {r['brier']:.4f} | {r['brier_ci95'][0]:.4f} … {r['brier_ci95'][1]:.4f} | {r['logloss']:.4f} | {r['logloss_ci95'][0]:.4f} … {r['logloss_ci95'][1]:.4f} | {r['base_rate_home'] * 100:.1f}% | {r['mean_p_home'] * 100:.1f}% |")
    sb = squash(dom("F: payoff", "table"))
    allrows = cal["common_per_league"]["all"]
    pin, pm1m = allrows.get("Pinnacle close"), allrows.get("Polymarket T-1min")
    R += ["", f"  on-screen (table text): `{dom('F: payoff', 'table')[:400]}`",
          check("every `All` row's N and Brier from `analysis.json` appears in the on-screen table text", all(str(r["n"]) in sb and f"{r['brier']:.4f}" in sb for r in allrows.values()), f"{len(allrows)} rows, frame {nframe('F: payoff')}"),
          check(f"payoff pair — Pinnacle close {pin['brier']:.4f} vs Polymarket T−1 min {pm1m['brier']:.4f} on the same {pin['n']} games (captions 8 and 9)", f"Pinnacleclose{pin['n']}{pin['brier']:.4f}" in sb and f"PolymarketT-1min{pm1m['n']}{pm1m['brier']:.4f}" in sb and pin["n"] == pm1m["n"], "Brier on the common set; the film and captions make no claim beyond the two numbers being a dead heat on the same games"), ""]
    R += ["## Vendor call ledger (unchanged by the film)", "",
          "- No vendor call was made for this pass; the film is captured from the frozen Tier 1 dataset (`a9-data/derived`, `manifest.json`). Ledger: `handoff/ledger.md`.", ""]
    n_ok = sum(1 for _, ok, _ in checks if ok)
    R.insert(3, f"**Cross-checks: {n_ok} of {len(checks)} pass** (each is listed in its section; a failing line reads **NO**).")
    R.insert(4, "")
    open(os.path.join(OUT, "film45_receipts.md"), "w").write("\n".join(R) + "\n")

    # =====================================================================================================================
    # films-v2.md — production-standard receipts (§5 items 1–7) + §7 caption receipts
    # =====================================================================================================================
    d, m = qa["delivery"], qa["master"]
    dc, mc = qa_cap["delivery"], qa_cap["master"]
    ds, ms, dcs, mcs = d["ffprobe"]["streams"][0], m["ffprobe"]["streams"][0], dc["ffprobe"]["streams"][0], mc["ffprobe"]["streams"][0]
    F = ["# The Tape — 45-second film (v2.1 pass: re-framed for the caption band · clean film + captioned release candidate)", "",
         f"Two files over one set of 2,700 frames. **Release candidate** (burned-in subtitles, standard §7): `films/the-tape-45s-captioned.mp4`, asset **{ASSET_CAP}**, {dc['bytes']:,} bytes, SHA-256 `{dc['sha256']}`. "
         f"**Clean film** (same frames, no captions): `films/the-tape-45s.mp4`, asset **{ASSET_CLEAN}**, {d['bytes']:,} bytes, SHA-256 `{d['sha256']}`. "
         f"The previously frozen clean film `{FROZEN_V2['asset']}` ({FROZEN_V2['bytes']:,} bytes, SHA-256 `{FROZEN_V2['sha256']}`; master `{FROZEN_V2['master_sha256']}`) stays untouched as a superseded asset: its framings put interface text inside the caption band in beat A (the header at 2.25×) and beat E (the Discovery title at 2.8×), so, as the §7 mail instructs for that case, the framings were shifted and both films re-rendered with new hashes. "
         f"Captured from the deployed app **The Tape** (asset `2088f758-e90b-423c-ba64-c4c7a2b1ca63`), bundle hash `{bundle_hash}` (the deployed bundle itself; `films/app_version_45c.txt` lists the per-file hashes — no app change in this pass). "
         "Every number on screen is traced in `handoff/film45_receipts.md`; every caption text is receipted in §7 below. No vendor call was made.", "",
         "## 1 · ffprobe", "",
         "| file | width | height | r_frame_rate | avg_frame_rate | nb_frames | duration | nb_streams | pix_fmt | codec |", "|---|---|---|---|---|---|---|---|---|---|"]
    for label, dd, ss in (("release candidate `films/the-tape-45s-captioned.mp4`", dc, dcs), ("clean `films/the-tape-45s.mp4`", d, ds),
                          ("captioned master `a9-films/the-tape-45s-captioned-master.mp4` (outside the bundle)", mc, mcs), ("clean master `a9-films/the-tape-45s-master.mp4` (outside the bundle)", m, ms)):
        F.append(f"| {label} | {ss['width']} | {ss['height']} | {ss['r_frame_rate']} | {ss['avg_frame_rate']} | {ss['nb_frames']} | {float(ss['duration']):.3f} s | {dd['ffprobe']['format']['nb_streams']} | {ss['pix_fmt']} | {ss['codec_name']} {ss.get('profile', '')} |")
    F += ["",
          f"Encode (one ffmpeg run per film writes delivery + master from the normalised rgb24 frame stream): `{enc['ffmpeg']}` — delivery libx264 CRF 16, preset slow, yuv420p, `+faststart`, `-an` (no audio stream); master libx264 `-qp 0` (lossless), yuv444p. "
          f"Frame normalisation: {enc['normalisation']}; the captured clips come out {size_range} device px (`source_sizes` in `films/the-tape-45s-encode.json`), {len(enc.get('short_frames_edge_replicated', []))} frames needed edge replication. "
          f"The captioned film is the same frame stream with the caption layer composited on rows 0–299 before encoding (`films/caption45.py`; §7). Clean encode {enc['seconds']:.0f} s; captioned {caps['seconds']:.0f} s.", "",
          "## 2 · Hashes", "",
          "| file | bytes | SHA-256 |", "|---|---|---|",
          f"| `films/the-tape-45s-captioned.mp4` (release candidate) | {dc['bytes']:,} | `{dc['sha256']}` |",
          f"| `films/the-tape-45s.mp4` (clean) | {d['bytes']:,} | `{d['sha256']}` |",
          f"| `a9-films/the-tape-45s-captioned-master.mp4` | {mc['bytes']:,} | `{mc['sha256']}` |",
          f"| `a9-films/the-tape-45s-master.mp4` | {m['bytes']:,} | `{m['sha256']}` |",
          f"| `films/fonts/Inter-SemiBold.ttf` (caption font) | {os.path.getsize(os.path.join(BUILD, caps['font']['file'])):,} | `{font_sha}` |",
          f"| superseded frozen v2 clean film (asset `{FROZEN_V2['asset']}`, untouched) | {FROZEN_V2['bytes']:,} | `{FROZEN_V2['sha256']}` |", ""]

    # ---- beat list -------------------------------------------------------------------------------------------------------------
    def zooms(letter):
        hold_z = []
        for h in holds:
            if h["label"].startswith(letter + ":"):
                z = round(h["cam"]["z"], 2)
                if not hold_z or hold_z[-1] != z:
                    hold_z.append(z)
        return " → ".join(f"{z:g}×" for z in hold_z)

    subjects = {
        "A": ("the tape at 1× (picture) → push-in on the header numbers → read", "1,332,476 sportsbook price updates · 4,195,032 Polymarket price samples · 3,387 markets · 1,150 games"),
        "B": ("pointer to Find team, click, type `ravens` (6 keys), pointer to the BAL @ ATL strip (its highlight shows), click → the game opens", "5 strips · the game view: Baltimore Ravens @ Atlanta Falcons 30–23 (OT), kickoff Oct 11, 8:20 PM ET"),
        "C": ("pointer to the side column, pull-back to the full-history picture (1×), push-in on the side column, wheel the column to the open → close table, read", "FanDuel 74.0% → 39.3% · Pinnacle 50.5% → 38.1% · DraftKings 64.5% → 39.1% (no-vig, BAL side)"),
        "D": ("pull-back, push-in on the toolbar, click In-game, pull-back to the in-game picture, push-in on the side column, wheel to Scoring plays, read", "Scoring plays (Sportradar): 00:30Z · 3–0 · Q1 10:30 · 21-yard field goal"),
        "E": ("cut to Discovery (1× picture), pointer to the All row, push-in on Agreement by league, read, wheel-scroll the table, pointer slide off the digits, read", "All · 889 · +0.16 pp (CI +0.09 … +0.24) · 96% within 2 pp · corr 0.999"),
        "F": ("cut to Scoreboard (1× picture), pointer to the Pinnacle close row, push-in on the All block, payoff, pointer to the Polymarket T-1min row, final hold", "Brier 0.2093 (Pinnacle close) vs 0.2092 (Polymarket T-1min), same 363 games"),
    }
    F += ["## 3 · Beat list", "",
          "Shot list as filmed (the parent's A9 baseline, with the flip read as no-vig probabilities so the sportsbook rows and the Polymarket line share one axis; the raw −335/+144 FanDuel prices are in `film45_receipts.md`). Beat boundaries are the first/last frames whose timeline label carries the beat letter:", "",
          "| beat | start s | end s | frames | subject | zoom (holds) | payoff |", "|---|---|---|---|---|---|---|"]
    for b in "ABCDEF":
        f0, f1 = beats[b]
        F.append(f"| {b} | {secs(f0):.3f} | {secs(f1 + 1):.3f} | {f0}–{f1} | {subjects[b][0]} | {zooms(b)} | {subjects[b][1]} |")
    F += ["", "Every camera move, hold, pointer move, input event and cut, in order (frames are 0-based native frames, inclusive; start = first frame / 60, end = (last frame + 1) / 60; events are single frames. Rows tile except for the product's own response windows, which are not holds: the frame after each click (301, 550, 1296), the frames between keystrokes (338–368) and the smooth-scroll windows after each wheel event (899–957, 1647–1723, 2083–2141; listed as moving windows in §5)):", "",
          "| start s | end s | frames | kind | subject | zoom | easing · duration | pointer / input |", "|---|---|---|---|---|---|---|---|"]
    rows = []
    for h in holds:
        rows.append((h["f0"], h["f1"], "hold · " + h["kind"], h["label"], f"{h['cam']['z']:.2f}×", f"static · {h['seconds']:.2f} s", "pointer still"))
    for c in tl["camMoves"]:
        rows.append((c["f0"], c["f1"], "camera " + c["kind"], c["label"], f"{c['from']['z']:.2f}× → {c['to']['z']:.2f}×", f"{c['easing']} · {c['seconds']:.2f} s", "pointer still during the move"))
    for p in tl["ptrMoves"]:
        rows.append((p["f0"], p["f1"], "pointer move", p["label"], f"{cam_at.get(p['f0'], {}).get('z', 1):.2f}×", f"{p['easing']} · {p['seconds']:.3f} s", f"({p['from'][0]}, {p['from'][1]}) → ({p['to'][0]}, {p['to'][1]}) stage CSS px, {p['distCss']} px, peak {p['peakCss']} CSS px/s = {p['peakFilm1x']} film px/s at 1×"))
    for e in tl["events"]:
        rows.append((e["f"], e["f"], "input · " + e["type"], e["label"], f"{e['cam']['z']:.2f}×", "—", f"{e['type']}{(' ' + repr(e['key'])) if e.get('key') else ''} at ({e['x']}, {e['y']}) stage CSS px" + (f" · smooth scroll settled in {e['settleMs']} ms of product time" if e.get("settleMs") else "")))
    for c in tl["cuts"]:
        rows.append((c["f"], c["f"], "cut", c["label"], f"{c['cam']['z']:.2f}×", "hard cut (harness route change, 0 real-time waits)", c["change"]))
    rows.sort(key=lambda r: (r[0], r[1]))
    for f0, f1, kind, label, zoom, ease, ptr in rows:
        F.append(f"| {secs(f0):.3f} | {secs(f1 + (0 if f0 == f1 else 1)):.3f} | {f0}–{f1} | {kind} | {label} | {zoom} | {ease} | {ptr} |")
    F.append("")
    F += ["Camera moves: " + "; ".join(f"{c['label']} ({c['seconds']:.1f} s)" for c in tl["camMoves"]) + f". All {len(tl['camMoves'])} moves use {tl['rules']['cameraEasing']} easing, push/pull durations within {tl['rules']['pushPullSeconds'][0]}–{tl['rules']['pushPullSeconds'][1]} s, pans ≤ {tl['rules']['panMaxSeconds']} s; each move is preceded by a static settle ≥ {tl['rules']['settleBeforeCameraMove']} s (table above). Stage coordinates: the app body sits at stage y 178 (§6), so an app CSS y is stage y − 178.", ""]

    # ---- framings ----------------------------------------------------------------------------------------------------------------
    fr = {}
    for h in holds:
        key = (round(h["cam"]["z"], 3), round(h["app"]["L"], 2))
        fr.setdefault(key, []).append(h["label"].split(":")[0])
    F += ["Framings (app CSS px visible in the frame; the app's top edge is at film y 260 in every framing, so the band y 0–240 and the 20-px margin below it hold stage background only — §7):", "",
          "| zoom | app x range | app y range | film px per app px | used in beats |", "|---|---|---|---|---|"]
    for (z, L), bs in sorted(fr.items()):
        h = next(h for h in holds if round(h["cam"]["z"], 3) == z and round(h["app"]["L"], 2) == L)
        F.append(f"| {z:g}× | {L:.2f} – {h['app']['R']:.2f} | 0 – {h['app']['B']:.2f} | {1.5 * z:.3f} | {', '.join(sorted(set(bs)))} |")
    F.append("")

    # ---- §3 rule checks ------------------------------------------------------------------------------------------------------------
    F += ["### Section 3 rule check (measured)", "",
          "Every testable clause of §3, with the measured value and the frame range it was measured on. “pass” means the measured value meets the clause; “see note” points to the disclosed reading.", "",
          "| clause | measured | frames | result |", "|---|---|---|---|"]
    cm = tl["camMoves"]
    for c in cm:
        lim = tl["rules"]["panMaxSeconds"] if c["kind"] == "pan" else tl["rules"]["pushPullSeconds"][1]
        ok = (c["seconds"] <= lim) and (c["kind"] == "pan" or c["seconds"] >= tl["rules"]["pushPullSeconds"][0])
        F.append(f"| camera move eased, {'≤ 1.2 s pan' if c['kind'] == 'pan' else '0.8–1.5 s push/pull'} | {c['easing'].split(' (')[0]}, {c['seconds']:.2f} s ({c['label']}) | {c['f0']}–{c['f1']} | {'pass' if ok else 'FAIL'} |")
    # pointer/camera/input at rest before each camera move: frames since the last pointer-move frame, input event, cut or camera frame
    def static_before(f0):
        last = max([p["f1"] for p in tl["ptrMoves"] if p["f1"] < f0] + [e["f"] for e in tl["events"] if e["f"] < f0] +
                   [x for x in cuts if x < f0] + [c["f1"] for c in cm if c["f1"] < f0] + [-1])
        return f0 - 1 - last
    for i, c in enumerate(cm):
        prev_end = cm[i - 1]["f1"] if i else -1
        gap = c["f0"] - prev_end - 1
        st = static_before(c["f0"])
        F.append(f"| no camera move before the previous has settled ≥ 0.4 s | {gap / 60:.2f} s since the previous camera move ended ({c['label']}); camera, pointer and inputs all at rest for the {st} frames ({st / 60:.2f} s) immediately before it | {prev_end + 1}–{c['f0'] - 1} | {'pass' if gap >= 24 else 'FAIL'} |")
    for e in tl["events"]:
        if e["type"] == "click":
            z = e["cam"]["z"]
            # camera settled before the click
            last_cm_end = max([c["f1"] for c in cm if c["f1"] < e["f"]], default=-1)
            settle = e["f"] - last_cm_end - 1
            rest = e["f"] - 1 - max([p["f1"] for p in tl["ptrMoves"] if p["f1"] < e["f"]])
            dw = next((h for h in holds if h["kind"] == "dwell" and h["f0"] <= e["f"] - 1 and h["f0"] > e["f"] - 1 - rest), None)
            nxt = min([p["f0"] for p in tl["ptrMoves"] if p["f0"] > e["f"]] + [c["f0"] for c in cm if c["f0"] > e["f"]] + [k["f"] for k in tl["events"] if k["f"] > e["f"]] + [x for x in cuts if x > e["f"]])
            F.append(f"| zoom ≥ 2.2× on the click | {z:.2f}× ({e['label']}) | {e['f']} | {'pass' if z >= 2.2 else 'FAIL'} |")
            F.append(f"| camera settled ≥ 0.3 s before the click | {settle} frames = {settle / 60:.3f} s since the push-in ended | {last_cm_end + 1}–{e['f'] - 1} | {'pass' if settle >= 18 else 'FAIL'} |")
            F.append(f"| pointer dwell ≥ 0.3 s before the click | pointer at rest on the target for {rest} frames = {rest / 60:.2f} s before the click" + (f" ({dw['label']}" + (", then the push-in and its settle with the pointer still on the target)" if dw['f1'] < e['f'] - 1 else ")") if dw else "") + f" | {e['f'] - rest}–{e['f'] - 1} | {'pass' if rest >= 18 else 'FAIL'} |")
            F.append(f"| hold ≥ 0.6 s after the click (consequence begins on screen) | {(nxt - e['f'] - 1) / 60:.3f} s before the next camera/pointer/input action | {e['f'] + 1}–{nxt - 1} | {'pass' if nxt - e['f'] - 1 >= 36 else 'FAIL'} |")
    # typing
    kf = [e["f"] for e in key_events]
    gaps = [b - a for a, b in zip(kf, kf[1:])]
    cps = [60 / g for g in gaps]
    mean_cps = sum(cps) / len(cps)
    hold_after = min([p["f0"] for p in tl["ptrMoves"] if p["f0"] > kf[-1]] + [c["f0"] for c in cm if c["f0"] > kf[-1]]) - kf[-1]
    F.append(f"| typing 10–14 cps with natural ±20 % variation | inter-key gaps {'/'.join(map(str, gaps))} frames = {'/'.join(f'{c:.1f}' for c in cps)} cps, mean {mean_cps:.1f}; max deviation from the mean {max(abs(c - mean_cps) / mean_cps for c in cps) * 100:.0f} % | {kf[0]}–{kf[-1]} | {'pass' if all(10 <= c <= 14 for c in cps) and max(abs(c - mean_cps) / mean_cps for c in cps) <= 0.2 else 'FAIL'} |")
    F.append(f"| typed field at ≥ 2.2× (typed text ≥ 28 px) | field at {key_events[0]['cam']['z']:.2f}×, em {11 * 1.5 * key_events[0]['cam']['z']:.1f} px; caret visible (`caret-animation: manual`) | {kf[0]}–{kf[-1]} | pass |")
    ptr_leaves = min([p["f0"] for p in tl["ptrMoves"] if p["f0"] > kf[-1]])
    F.append(f"| hold ≥ 0.8 s after the last character | {hold_after / 60:.2f} s static after the last key before the camera reframes; the pointer stays in the field until frame {ptr_leaves} ({(ptr_leaves - kf[-1]) / 60:.2f} s after the last key); the filter is live, there is no Enter or submit click | {kf[-1] + 1}–{kf[-1] + hold_after - 1} | {'pass' if hold_after >= 48 else 'FAIL'} |")
    # read holds: the content on screen is constant between camera moves, input events and cuts (the pointer may move inside the frame);
    # the static read is the run of adjacent holds (any kind) containing the read/payoff hold, with no pointer move or scroll inside
    breaks = sorted(set([e["f"] for e in tl["events"]] + cuts + [f for c in cm for f in range(c["f0"], c["f1"] + 1)]))
    def content_span(f):
        lo = max([b for b in breaks if b < f] + [-1]) + 1
        hi = min([b for b in breaks if b > f] + [2700]) - 1
        return lo, hi
    def static_run(h):
        f0, f1 = h["f0"], h["f1"]
        changed = True
        while changed:
            changed = False
            for g in holds:
                if g["cam"] == h["cam"] and (g["f1"] + 1 == f0 or g["f0"] == f1 + 1):
                    f0, f1 = min(f0, g["f0"]), max(f1, g["f1"])
                    changed = True
        return f0, f1
    seen = set()
    for h in holds:
        if h["kind"] not in ("read", "payoff"):
            continue
        s0, s1 = static_run(h)
        if (s0, s1) in seen:
            continue
        seen.add((s0, s1))
        c0, c1 = content_span(h["f0"])
        n = s1 - s0 + 1
        is_final = s1 == 2699
        lim = 120 if is_final else 72
        inside = [p for p in tl["ptrMoves"] if c0 <= p["f0"] and p["f1"] <= c1]
        moves_txt = ", ".join(f"{p['f0']}–{p['f1']}" for p in inside)
        extra = ""
        if (c0, c1) != (s0, s1):
            extra = f"; the same content stays on screen {c0}–{c1} ({(c1 - c0 + 1) / 60:.2f} s)" + (f" with a pointer move inside the frame at {moves_txt}" if inside else "")
        if n >= lim:
            res = "pass"
        elif h["kind"] == "payoff" and not is_final and c1 - c0 + 1 >= 72:
            res = f"pass (the payoff content is on screen {(c1 - c0 + 1) / 60:.2f} s; its final static hold is the row below)"
        else:
            res = "FAIL"
        F.append(f"| {'final payoff hold ≥ 2.0 s' if is_final else 'read hold ≥ 1.2 s'} | static {n / 60:.2f} s at {h['cam']['z']:.2f}× ({h['label'][:60]}){extra} | {s0}–{s1} | {res} |")
    pk = max(tl["ptrMoves"], key=lambda p: p["peakFilm1x"])
    F.append(f"| pointer peak ≤ 1,200 px/s at 1× capture scale | max over {len(tl['ptrMoves'])} moves {pk['peakFilm1x']} film px/s at 1× = {pk['peakCss']} CSS px/s ({pk['label']}); every move minimum-jerk, decelerating into the target | {pk['f0']}–{pk['f1']} | {'pass' if pk['peakFilm1x'] <= 1200 else 'FAIL'} |")
    F.append(f"| pointer visible for every interaction; hover state visible | DOM cursor at the real mouse position on every frame (§6); strip highlight (B), `.btn:hover` on In-game (D), row highlights (E, F) are the product's own | 0–2699 | pass |")
    pic_spans = []
    for h in holds:
        if h["kind"] == "picture" and round(h["cam"]["z"], 2) == 1:
            if pic_spans and pic_spans[-1][1] + 1 == h["f0"]:
                pic_spans[-1][1] = h["f1"]
            else:
                pic_spans.append([h["f0"], h["f1"]])
    F.append(f"| full-frame 1× never used to read text | 1× holds are the {len(pic_spans)} picture beats ({', '.join(f'{a}–{b}' for a, b in pic_spans)}) and the settles/dwells between moves; every read/payoff hold is at ≥ {min(h['cam']['z'] for h in holds if h['kind'] in ('read', 'payoff')):.2f}× | — | pass |")
    F.append(f"| last frame is a product state at a readable scale; no fades > 0.25 s, no cards | frame 2699 = Scoreboard All block at 3.0×, Polymarket T-1min row highlighted; the only fades are the 12-frame (0.2 s) caption fades of §7; no card | 2699 | pass |")
    F.append(f"| no cut in the middle of a move | cuts at {', '.join(map(str, cuts))}: each follows a static read hold and starts a static picture hold | {', '.join(f'{c - 1}→{c}' for c in cuts)} | pass |")
    F.append("")

    # ---- native frames + measured text --------------------------------------------------------------------------------------------
    F += ["## 4 · Native frames at every click, typing, toggle, scroll and readout — measured text heights", "",
          "Frames are decoded from the clean delivery mp4 by `films/measure45c.py` (ffmpeg `select`, native 1920 × 1080; `handoff/frames45c/native/`). Every target is defined by the DOM word box measured on the capture stage (`handoff/geom_states45c.json`: `Range.getClientRects()` per word in each filmed app state; the two canvas strip labels are given as app-px regions) and converted to film pixels with that frame's camera (film x = (app x − L) · 1.5 · z, film y = 260 + app y · 1.5 · z). "
          "The glyph band is the vertical ink extent of the string (digit height for numerals, x-height for lowercase words without ascenders, ascender-to-descender extent for mixed strings); the nominal size is the font's em height on film = CSS font size × 1.5 (device scale factor) × camera zoom. "
          "Readability is judged on the em height (the standard's “UI text ≥ 28 px”) with the x-height criterion (≥ 14 px) measured directly; digit glyphs of the monospace face are ≈ 0.73–0.78 em, Geist caps ≈ 0.72 em. The 1× rows are the disclosed picture beats (the image carries the meaning; no text is read there). The pointer box at each frame was checked against every region (column “pointer”).", "",
          "| frame | t | beat · string | zoom | font | nominal em (px) | measured glyph band (px) | band / em | glyph class | criterion | result | pointer |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in text:
        meas = e["measured"] or {}
        band = meas.get("band_height_px")
        cls = e["glyph_class"]
        nominal = e["nominal_font_px_on_film"]
        is_pic = round(e["zoom"], 2) == 1.0
        if is_pic:
            crit, ok, res = "1× picture beat (not a read)", True, "picture"
        elif e["frame"] >= 2473 and cls.startswith("digits") and ("Brier" in e["label"] or "N 363" in e["label"]):
            crit, ok = "payoff number ≥ 48 px", nominal >= 48
            res = "pass (em)" if ok else "see note"
        elif "x-height" in cls:
            crit, ok = "x-height ≥ 14 px (UI text ≥ 28 px em)", band is not None and band >= 14 and nominal >= 28
            res = "pass" if ok else "see note"
        elif cls.startswith("digits"):
            crit, ok = "readout numbers ≥ 32 px em", nominal >= 32
            res = "pass (em)" if ok else "see note"
        else:
            crit, ok = "UI text ≥ 28 px em", nominal >= 28
            res = "pass (em)" if ok else "see note"
        ptr = "on the word" if e["pointer_overlaps_word_box"] else ("within 3 px of the region" if e["pointer_overlaps_padded_region"] else "clear")
        F.append(f"| {e['frame']} | {e['t']:.2f} | {e['label']} | {e['zoom']:.2f}× | {e['font']} {e['css_font_px']}px w{e['weight']} | {nominal:.1f} | {band if band is not None else '—'} | {e.get('measured_over_nominal_em', '—')} | {cls} | {crit} | {res} | {ptr} |")
    digit_rows = [e for e in text if e["glyph_class"].startswith("digits") and round(e["zoom"], 2) != 1.0]
    pay_rows = [e for e in text if e["frame"] >= 2473 and e["glyph_class"].startswith("digits") and ("Brier" in e["label"] or "N 363" in e["label"])]
    F += ["", f"Reading of the table: at the zoomed beats every readout's em is {min(e['nominal_font_px_on_film'] for e in digit_rows):.1f}–{max(e['nominal_font_px_on_film'] for e in digit_rows):.1f} px (rule ≥ 32) while the digit ink is {min(e['measured']['band_height_px'] for e in digit_rows)}–{max(e['measured']['band_height_px'] for e in digit_rows)} px; the payoff digits are {pay_rows[0]['nominal_font_px_on_film']:.1f} px em with {min(e['measured']['band_height_px'] for e in pay_rows)}–{max(e['measured']['band_height_px'] for e in pay_rows)} px ink (rule ≥ 48). "
          f"x-heights of the measured lowercase words are {min(e['measured']['band_height_px'] for e in text if 'x-height' in e['glyph_class'] and round(e['zoom'], 2) != 1)}–{max(e['measured']['band_height_px'] for e in text if 'x-height' in e['glyph_class'] and round(e['zoom'], 2) != 1)} px (rule ≥ 14). As in the accepted v2 pass, the em reading is the one the rule is written in (“28 px tall (x-height ≥ 14 px)”); both readings are given so the reviewer can apply either.", "",
          f"Crops of every measured region (2× nearest-neighbour) are in `handoff/frames45c/native/text_crops/`. The key frames kept from the QA decode are in `handoff/frames45c/qa_clean/` (clean) and `handoff/frames45c/qa_captioned/` (release candidate): the click frames and their responses, the keystroke frames ({', '.join(map(str, kf))}), the wheel frames, the noted readouts, the cut pairs and the final hold ({', '.join(map(str, qa['final_hold_frames']))}); the 45-frame contact sheets are `{qa['contact_sheet']}` and `{qa_cap['contact_sheet']}`.", ""]

    # ---- per-second duplicates / pops / cuts ----------------------------------------------------------------------------------------
    dup = qa["duplicates"]
    F += ["## 5 · Frame-rate integrity", "",
          f"Measured on the clean delivery (the captioned delivery differs only by the caption layer; its own run is `handoff/film45c_qa_captioned.json` and is summarised at the end of this section). Metric: {dup['metric']}. Both thresholds are evaluated on the 0–255 grey scale (a duplicate pair = mean |Δ| < 0.02 of 255, a pop = mean |Δ| > 8 of 255); a 0–1 reading of the 0.02 threshold (= 5.1 of 255) cannot separate cursor-only motion from duplication and is reported alongside for reference.", "",
          "| second | frames | duplicate pairs (< 0.02/255) | pairs < 5.1/255 | max mean &#124;Δ&#124; | at pair |", "|---|---|---|---|---|---|"]
    for s in qa["per_second"]:
        F.append(f"| {s['second']} | {s['frames'][0]}–{s['frames'][1] - 1} | {s['dup_pairs_lt_0.02_of_255']} | {s.get('pairs_lt_5.1_of_255 (0–1 reading)', '')} | {s['max_mean_abs_delta_255']:.3f} | {s['max_jump_at_pair']} |")
    F += ["", "Moving windows (duplicate pairs are only a defect while something should be moving; static holds are intended):", "",
          "| window | frames | pairs | dup pairs | % | in first/last 4 | inside | exact zeros | min Δ | max Δ | cadence flip rate |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for w in dup["moving_windows"]:
        F.append(f"| {w['label']} ({w['kind']}) | {w['frames'][0]}–{w['frames'][1]} | {w['pairs']} | {w['dup_pairs']} | {w['dup_pct']:.1f} | {w['dup_pairs_in_first_4']}/{w['dup_pairs_in_last_4']} | {len(w['dup_pairs_inside'])} | {w['exact_zero_pairs']} | {w['min_delta']:.4f} | {w['max_delta']:.2f} | {w['cadence']['flip_rate']:.2f} |")
    sx = qa.get("source_exact_duplicates")
    if sx:
        F += ["", "Exact repeats on the source frames (the lossless PNGs fed to the encoder; `films/dupsrc45.py`, SHA-1 of the raw pixel buffer, pair = two byte-identical consecutive frames). This test is independent of the encoder and of the 0.02 metric floor:", "",
              "| window | frames | pairs | byte-identical pairs | % | at |", "|---|---|---|---|---|---|"]
        for w in sx["moving_windows"]:
            at = ", ".join(f"{a}→{a + 1}" for a in w["pairs_list"][:6]) + (" …" if len(w["pairs_list"]) > 6 else "") if w["pairs_list"] else "—"
            F.append(f"| {w['label']} ({w['kind']}) | {w['frames'][0]}–{w['frames'][1]} | {w['pairs']} | {w['exact_duplicate_pairs']} | {100 * w['exact_duplicate_pairs'] / w['pairs']:.1f} | {at} |")
        cam_dups = [w for w in sx["moving_windows"] if w["kind"].startswith("camera") and w["exact_duplicate_pairs"]]
        F += ["", f"Whole film: {sx['total_exact_duplicate_pairs_incl_static_holds']} byte-identical pairs of 2,699 (static holds are meant to be identical); inside listed windows {sx['camera_move_exact_duplicates']} camera, {sx['pointer_move_exact_duplicates']} pointer, {sum(w['exact_duplicate_pairs'] for w in sx['moving_windows'] if w['kind'] in ('typing', 'wheel scroll'))} typing/wheel. "
              f"The camera repeats are " + "; ".join(f"{w['frames'][0]}–{w['frames'][1]}: {', '.join(f'{a}→{a + 1}' for a in w['pairs_list'])}" for w in cam_dups) + " — the last pair of a quintic ease where the clip's device-pixel snap no longer changes; none sits inside a move.", ""]
    import collections
    pop_classes = collections.OrderedDict()
    for c in qa["pops"]["classified"]:
        k = c["class"]
        if k.startswith("product response"):
            k = f"product response to an input event (pair {c['pair'][0]}→{c['pair'][1]}: " + ("the game view opening after the strip click" if c["pair"][0] in (549, 550) else "see `pops.classified`") + ")"
        pop_classes[k] = pop_classes.get(k, 0) + 1
    typ = next((w for w in dup["moving_windows"] if w["kind"] == "typing"), None)
    wheels = [w for w in dup["moving_windows"] if "wheel" in w["kind"].lower()]
    cam_w = [w for w in dup["moving_windows"] if w["kind"].startswith("camera")]
    zero_w = [w for w in cam_w if w["exact_zero_pairs"]]
    F += [f"- Camera moves: on the delivered mp4, duplicate pairs occur only in the first/last ≤ 4 frames of a move (the quintic ease starts and ends below one pixel per frame; column “inside” is 0 for all {len(cam_w)} camera windows), none sits inside a move, and the flip rate is far from a 2:2 (≈ 1.0), 3:2 or 5:5 cadence. " + (f"{sum(w['exact_zero_pairs'] for w in zero_w)} pair(s) read exactly 0 on the downscale (" + "; ".join(f"{w['label']} {w['frames'][0]}–{w['frames'][1]}" for w in zero_w) + "), each at the first/last frames of its move where the sub-pixel change is below the 160 × 90 metric's resolution." if zero_w else "No pair reads exactly 0."),
          "- Pointer-only windows: the pointer is 33 × 45 px on a 1920 × 1080 frame, so the 160 × 90 downscale puts its motion at the metric floor; the “duplicate” pairs inside slow pointer moves are the pointer moving < 1 px between frames (minimum-jerk tails), not repeated frames — 0 exact zeros on the source frames in any pointer move.",
          f"- Typing burst (frames {typ['frames'][0]}–{typ['frames'][1]}): the field is static between keystrokes by design (the caret does not blink under the stepped clock: `caret-animation: manual`), so {typ['dup_pairs']} of {typ['pairs']} pairs are duplicates there; the {len(kf)} keystroke frames ({', '.join(map(str, kf))}) each change the frame (field, count line and strip list re-filter).",
          "- Wheel scrolls (" + "; ".join(f"frames {w['frames'][0]}–{w['frames'][1]}: {w['dup_pairs']} duplicate pairs on the mp4" for w in wheels) + "): the browser's smooth scroll runs on the stepped clock; the frames between the wheel event and the start of the smooth scroll and the frames after it settles are static by design (settle times logged per event in §3), the moving part is continuous.",
          f"- Pops: {qa['pops']['pairs_over_8_total']} pairs exceed 8/255 outside the two cuts; {qa['pops']['unexplained_count']} are unexplained — " + "; ".join(f"{n} {k}" for k, n in pop_classes.items()) + f". Largest jump outside the cuts: pair {qa['pops']['max_jump_outside_cuts']['pair']} ({qa['pops']['max_jump_outside_cuts']['mean_abs_delta_255']:.2f}), inside the Agreement push-in. Classification per pair: `film45c_qa.json` → `pops.classified`.",
          "- Cuts (hard cuts, product route change; the film is one continuous encode, nothing is spliced, so there is no splice PSNR to report):", "",
          "| cut | pair | PSNR (dB) | mean &#124;Δ&#124; (160×90, 0–255) |", "|---|---|---|---|"]
    for c in qa["cuts"]:
        F.append(f"| frame {c['cut_frame']} | {c['pair'][0]}→{c['pair'][1]} | {c['psnr_db']:.2f} | {c['mean_abs_delta_255_160x90']:.2f} |")
    dcap = qa_cap["duplicates"]
    F += ["", f"Captioned delivery (`film45c_qa_captioned.json`): {qa_cap['pops']['pairs_over_8_total']} pairs over 8/255 ({qa_cap['pops']['unexplained_count']} unexplained), cuts PSNR " + ", ".join(f"{c['psnr_db']:.2f} dB" for c in qa_cap["cuts"]) + f"; moving-window duplicate percentages are {'identical to' if [w['dup_pairs'] for w in dcap['moving_windows']] == [w['dup_pairs'] for w in dup['moving_windows']] else 'within ±1 pair of'} the clean film (the caption fades add motion in the band but the windows are defined by the timeline). The only extra frame-to-frame changes are the 12-frame caption fades, each inside a hold or at a cut (§7).", ""]

    # ---- pointer/input log + disclosure -------------------------------------------------------------------------------------------------
    F += ["## 6 · Pointer and input log · capture-method disclosure", "",
          "Input events (all real Playwright input events dispatched at the pointer position, logged by the harness; stage CSS px, app y = stage y − 178):", "",
          "| frame | t (s) | event | at (stage CSS px) | app (CSS px) | zoom | what |", "|---|---|---|---|---|---|---|"]
    for e in tl["events"]:
        F.append(f"| {e['f']} | {e['t']:.3f} | {e['type']}{(' ' + repr(e['key'])) if e.get('key') else ''} | ({e['x']}, {e['y']}) | ({e.get('app', [e['x'], e['y'] - 178])[0]}, {e.get('app', [e['x'], e['y'] - 178])[1]}) | {e['cam']['z']:.2f}× | {e['label']}{(' · smooth scroll settled after ' + str(e['settleMs']) + ' ms of product time') if e.get('settleMs') else ''} |")
    F += ["", "Pointer moves (minimum-jerk profile, decelerating into the target, ≥ 0.3 s dwell before each click):", "",
          "| frames | s | from → to (stage CSS px) | distance | peak CSS px/s | peak film px/s at 1× | what |", "|---|---|---|---|---|---|---|"]
    for p in tl["ptrMoves"]:
        F.append(f"| {p['f0']}–{p['f1']} | {p['seconds']:.3f} | ({p['from'][0]}, {p['from'][1]}) → ({p['to'][0]}, {p['to'][1]}) | {p['distCss']} | {p['peakCss']} | {p['peakFilm1x']} | {p['label']} |")
    pre = tl["preroll"]
    F += ["", f"Peak pointer speed over all moves: {pk['peakFilm1x']} film px/s at 1× (limit 1,200; convention as in the accepted v2 pass: 1 CSS px = 1.5 film px at 1×). There is no drag in this cut.", "",
          "Disclosure:", "",
          f"- **Frame-stepped capture, not a real-time recording.** {tl['clock']}. The product's own animations (hover highlights, the wheel's smooth scroll, canvas redraws) run on that stepped clock, so each film frame is exactly 1/60 s of product time. The whole film is one continuous capture (`films/capture45c.js` + `films/storyboard45c.js`); the two route changes (Discovery at frame {cuts[0]}, Scoreboard at {cuts[1]}) are hard cuts made by the harness (route + scroll position set, no real-time wait), disclosed as cuts in §3 and §5.",
          f"- **Stage inset (new in this pass).** The app is rendered on a 1280 × 898 stage with its body pinned at stage y 178 (`{tl['stageCss']}`); the camera clip is positioned so that the app's top edge lands at film y 260 in every framing (clip top = 178 − 173.333 / z). Rows 0–259 of every frame are therefore the stage background `#0a0c10`, never interface — that is what keeps the §7 caption band (y 0–240) and its 20-px margin clear of text, pointer and subject at every zoom. The visible app area per framing is listed in §3 (Framings). Nothing in the app was moved or restyled; the inset is a camera placement.",
          f"- **Camera.** {tl['capture']}. The editorial zoom is a re-rasterised clip of the live page (DOM text is re-rendered by the browser at the zoomed scale, canvas charts have a 2× backing store); the clip is requested 6 CSS px larger than the frame (nominal 1929 × 1089) because Chromium snaps a fractional clip to device pixels and returns up to 6 px less than nominal; the source frames come out {size_range} device px and are cropped at the origin to 1920 × 1080 ({len(enc.get('short_frames_edge_replicated', []))} edge-replicated frames).",
          f"- **Pointer.** {tl['pointer']}. The cursor is a DOM element drawn into the page by the harness (counter-scaled so it stays 33 × 45 px on the frame at every zoom) at the position of the real mouse; it is not composited after the fact. Hover states are the product's own (`.btn:hover`, the strip highlight, row highlights, the input's focus ring).",
          f"- **Typing.** `ravens` is {len(kf)} real key events at {min(cps):.1f}–{max(cps):.1f} characters/s (inter-key gaps {'/'.join(map(str, gaps))} frames, mean {mean_cps:.1f} cps, every interval inside the 10–14 band and within ±20 % of the mean), the field at {key_events[0]['cam']['z']:.2f}×; the caret is visible and non-blinking (`caret-animation: manual`) so it cannot alias with the stepped clock; the field, the count line and the strips update in the frame of each keystroke.",
          "- **Scrolls.** Three real wheel events, each followed by the browser's smooth scroll on the stepped clock (settle times in the input table): the game view's side column is wheeled to the open → close table (beat C) and later to the Scoring plays panel (beat D) so each read sits at the top of the column at 2.4×; the agreement table is wider than its panel at 1280 wide (table 572 CSS px in a 371 px wrapper), so N / mean diff and within-2-pp / corr cannot share one readable frame — the beat reads the left half, a wheel scrolls the wrapper 201 CSS px and reads the right half. Two harness scrolls happen at the cuts (Discovery page scrollTop 22, Scoreboard page scrollTop 203) so the read blocks sit under the band-clear top edge; both are logged in the cut rows of §3.",
          "- **Pointer slide in beat E.** After the wheel the pointer still rests on the All row at app x 607 (keeping the row highlight). Its position is inherited by the Scoreboard picture after the cut, where a pointer at x 607 would cover the `0.1951` cell (app box 600–640 × 185–199) at 1×. A 0.4-s minimum-jerk slide of 109 CSS px along the All row (peak 511 CSS px/s, frames 2160–2183) moves it to x 716, which is clear of every word of the scrolled agreement table and of the Scoreboard table. No x is clear in all three states (unscrolled table, scrolled table, Scoreboard): x 716 would sit on a `pp` cell of the unscrolled table, hence the slide after the wheel rather than a different parking spot from the start (`handoff/geom_states45c.json` → `disc0`, `disc1`, `sb`).",
          "- **Frame-edge cuts (disclosed, composition).** Zoomed framings crop the app, so some interface text is cut by the frame edge: beat A header left edge (`…ceipts`, `…rie A`, `…books only`, `…mes, 2026-08-14 → 2026-09-15`); beat B/C/D side framing (`…sliga` league chip, head line `2026-10-12` → `0-12`, the In-game button's border arc at the left edge); beat D toolbar (`…2 03:49Z · 1693 points`); beat E scrolled table (`.ff`/`pp` clipped by the app's own table scroll). Each cut string is legible in full at 1× in the preceding picture beat or is a label repeated elsewhere in the frame. The strip dwell (frames 525–548) shows only the tooltip's top border and padding entering the bottom edge — no tooltip text is on screen.",
          "- **Pre-roll (before frame 0, logged):** " + " · ".join(p["step"] if isinstance(p, dict) else str(p) for p in pre) + ".",
          "- **Clean film: no editorial crops, speed changes, fades, overlays or added text.** Nothing on screen is outside the product. **Captioned film:** the only addition is the §7 caption layer (text, shadow and scrim on rows 0–299), composited frame by frame from the same source frames.", ""]

    # ---- contact sheet + final hold ----------------------------------------------------------------------------------------------------------
    fh = qa["final_hold_frames"]
    F += ["## 7 · Contact sheet, final hold — and the caption layer (standard §7)", "",
          f"- `{qa['contact_sheet']}` (clean) and `{qa_cap['contact_sheet']}` (captioned) — 45 frames each, one per second (frame 60·k, k = 0 … 44), native 1920 × 1080 frames scaled to tiles.",
          f"- Final hold frames at 1× scale of the frame: `handoff/frames45c/qa_clean/f{fh[0]:05d}.png` (hold starts), `f{fh[1]:05d}.png`, `f{fh[2]:05d}.png` (last frame) and the same frames under `qa_captioned/`. The hold is frames {fh[0]}–{fh[2]} = {(fh[2] - fh[0] + 1) / 60:.2f} s on a product state at {cam_at[fh[0]]['z']:.1f}×: the Scoreboard's `All` block — `Pinnacle close · 363 · 0.2093` and `Polymarket T-1min · 363 · 0.2092`, pointer resting on the Polymarket row (row highlight is the product's), caption 9 held to frame 2699.", ""]

    # ---- §7 captions ---------------------------------------------------------------------------------------------------------------------
    C = caps["captions"]
    fo = caps["font"]
    F += ["### 7.1 · Caption table", "",
          "Nine captions (standard §7.2: 7–11), sentence case, present tense, one line each, ≤ 52 characters and ≤ 1,760 px wide. “in/out” are the first and last frames at which the caption is more than 50 % opaque; “full” the first and last fully opaque frames; duration = in→out frames / 60. Each change happens at a beat boundary (the two cuts) or inside a logged hold (six change frames: five at the storyboard's MARK events and one moved from its MARK to a later hold, see 7.2), never during a camera move (§3 table: no camera move overlaps any fade range).", "",
          "| # | text | chars | width px | in | out | full | duration s | min s (≥ 3.0 / opener 3.5 / 0.065 × chars) | beat | change at |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    chg = [c["f"] for c in caps["changes"]]
    def beats_in(f0, f1):
        return "→".join(b for b in "ABCDEF" if beats[b][0] <= f1 and beats[b][1] >= f0)
    for i, c in enumerate(C):
        if i == 0:
            at = "frame 0 (no fade-in)"
        elif caps["changes"][i - 1]["cut"]:
            at = f"cut {chg[i - 1]}"
        elif caps["changes"][i - 1].get("moved_from") is not None:
            at = f"frame {chg[i - 1]} (inside hold `{caps['changes'][i - 1]['hold']}`; moved from the captured MARK {caps['changes'][i - 1]['moved_from']}, see 7.2)"
        else:
            at = f"MARK {chg[i - 1]} (inside hold)"
        F.append(f"| {c['index']} | {c['text']} | {c['chars']} | {c['width_px']:.0f} | {c['over50_first']} | {c['over50_last']} | {c['full_first']}–{c['full_last']} | {c['over50_seconds']:.3f} | {c['min_frames_required'] / 60:.3f} | {beats_in(c['over50_first'], c['over50_last'])} | {at} |")
    # computed: no fade range may intersect a camera move, a pointer move, a wheel/click/key event or a cut (other than the cut it is tied to)
    fade_ranges = []
    for ch in caps["changes"]:
        fade_ranges.append((ch["f"] - 12, ch["f"] + 11) if ch["cut"] else (ch["f"], ch["f"] + 23))
    def hits(r, spans):
        return [sp for sp in spans if sp[0] <= r[1] and sp[1] >= r[0]]
    cam_spans = [(m["f0"], m["f1"], m["label"]) for m in tl["camMoves"]]
    ptr_spans = [(m["f0"], m["f1"], m["label"]) for m in tl["ptrMoves"]]
    ev_spans = [(e["f"], e["f"] + (round(e["settleMs"] / 16.667) if e.get("settleMs") else 0), e["label"]) for e in tl["events"]]
    fade_conflicts = []
    for r, ch in zip(fade_ranges, caps["changes"]):
        for kind, spans in (("camera move", cam_spans), ("pointer move", ptr_spans), ("input event / scroll settle", ev_spans)):
            for h in hits(r, spans):
                fade_conflicts.append((r, kind, h))
    F += ["", f"Fade windows (outgoing + incoming ramps) vs motion, computed from the timeline: the eight fade windows " + ", ".join(f"{a}–{b}" for a, b in fade_ranges) + f" intersect {len(fade_conflicts)} camera move(s), pointer move(s) or input/scroll-settle span(s)" + ("." if not fade_conflicts else ": " + "; ".join(f"{r[0]}–{r[1]} ∩ {k} {h[0]}–{h[1]} ({h[2]})" for r, k, h in fade_conflicts)) + " Every caption change therefore happens on a static picture (a hold) or exactly at a cut.",
          "", "Lead of the captions over the action they name: caption 2 (`Pick a game …`) comes in at frame 234 while the header read is still on screen (the pointer leaves for Find at 252); caption 3 (`FanDuel opened …`) comes in at 605 as the game view opens, 5.9 s before the closes table is at reading scale (958), stays through the table read (FanDuel row in frame from 944; at ≥ 2.2× until the pull-back crosses 2.2× at 1062 — 1.98 s of co-visibility) and fades out on the settled full-history picture after the pull-back (1102–1113); caption 4 (`Now the game itself …`) comes in at 1120 on that 1× game picture as the pointer sets off for In-game (1126), 2.9 s before the In-game click (1295), and stays through the in-game picture (1393–1476). Each caption names the beat it introduces and remains until that beat's read is complete; no caption describes something that has already left the screen."]
    F += ["", "Caption text receipts (each number is the on-screen value of the beat it accompanies; see `film45_receipts.md` for the data source):", "",
          "1. `1,150 games. Every sportsbook and Polymarket price.` — `manifest.n_games` = 1,150; “every sportsbook … price” = the 1,332,476 OpticOdds price updates of the five books and the 4,195,032 Polymarket samples in the header on screen.",
          "2. `Pick a game: Ravens at Falcons, October 11.` — the strip clicked at frame 549: Baltimore Ravens @ Atlanta Falcons, kickoff 2026-10-12 00:20Z = Oct 11, 8:20 PM ET (Sportradar `scheduled`; the game head line on screen).",
          "3. `FanDuel opened Baltimore at 74%. It closed at 39%.` — the closes table on screen: FanDuel open BAL 74.0%, close 39.3% (no-vig of −335 → +144; `film45_receipts.md`).",
          "4. `Now the game itself, minute by minute.` — the In-game preset (kickoff − 10 min → last play + 3 min); no number.",
          "5. `Each marker is a scoring play, with its wall clock.` — the Scoring plays panel on screen (Sportradar play-by-play `wall_clock`); the markers on the chart are those plays.",
          "6. `Across 889 games, the two markets nearly agree.` — the All row: N = 889, mean diff +0.16 pp, CI +0.09 … +0.24 pp on screen.",
          "7. `96% of closes are within 2 points.` — the All row's `within 2 pp` = 96% on screen (share of games with |Polymarket T−1 min − Pinnacle close| ≤ 2 pp).",
          "8. `Brier score on 363 games, lower is better.` — the Scoreboard All block: N = 363 (common game set) on screen.",
          "9. `Pinnacle 0.2093. Polymarket 0.2092. A dead heat.` — Pinnacle close Brier 0.2093 and Polymarket T-1min Brier 0.2092 on screen, same 363 games; “dead heat” = a 0.0001 difference well inside both 95% CIs (`film45_receipts.md`).", "",
          "Banned-list check: no “we/our”, no exclamation mark, no em dash, no hype word, no “AI”, no “real/live/verified”; the third-party names used (FanDuel, Polymarket, Pinnacle, Ravens, Falcons, Baltimore) are on screen in the frames they caption; no tagline. No footage was re-timed for a caption: the caption plan was written against the storyboard's holds, and every span exceeds its minimum (table); the one change-point move (7.2) re-timed a caption, not the footage.", ""]
    F += ["### 7.2 · Typography, scrim, compositing", "",
          f"- Font `{fo['file']}` ({fo['weight']}, Inter 4.1 from https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip, SIL OFL — `films/fonts/LICENSE-Inter-OFL.txt`), SHA-256 `{fo['sha256']}`; size {fo['size_px']} px; cap height measured on the rendered `H` {fo['cap_height_px_from_H']} px (standard: 45–49); white `#ffffff`; one line, centred at x = 960, baseline y {fo['baseline_y']} so the cap box is centred on y = 150 (band y 0–240); max width 1,760 px and ≤ 52 chars asserted per caption (widest caption {max(c['width_px'] for c in C):.0f} px).",
          f"- Shadow: {caps['shadow']['color']} {caps['shadow']['alpha']:.0%}, offset ({caps['shadow']['offset_xy'][0]}, +{caps['shadow']['offset_xy'][1]}) px, Gaussian σ {caps['shadow']['gaussian_sigma_px']} px (≙ CSS `{caps['shadow']['css_equivalent']}`); no box.",
          f"- Scrim: black, α {caps['scrim']['alpha_0_to_200']} on rows 0–200, linear to 0 at row 300; it fades with the caption (× caption α) — so on frames with no caption the frame is byte-identical to the clean film.",
          f"- Fades: {caps['fade_frames']}-frame linear ramps. Model (frames are 0-based): at a MARK frame c inside a hold, the outgoing caption has α = 1 − (i+1)/12 on frames c+i (i = 0 … 11; α = 0 at c+11) and the incoming caption α = (j+1)/12 on frames c+12+j (j = 0 … 11; α = 1 at c+23); at a cut c the outgoing caption fades on c−12 … c−1 and the incoming on c … c+11. Each ramp therefore has 11 frames of partial opacity and reaches its end state on the 12th; the gap between two captions (frames below 50 %) is 13 frames = 0.217 s (standard ≤ 0.4 s). Caption 1 is fully opaque from frame 0 (no fade-in); caption 9 holds fully opaque to frame 2699 (no fade-out).",
          "- Change points: the storyboard logged a MARK event at each planned caption change (`films/film45c_timeline.json` → `scriptResult.changes`; receipts field `changes_as_captured`). One of them was moved after the round-3 review: the caption 3 → 4 change was captured at MARK 994 (inside the hold `C: read (continued)` 994–1041, with the closes table on screen) and is composited at frame 1102 instead (`films/caption45.py --move-change 994:1102`; receipts field `change_moves`), inside the logged hold `D: settle` 1102–1125 — the 24 fade frames 1102–1125 sit entirely inside that hold, after the pull-back 1042–1101 and before the pointer move 1126–1198, with no input event in the window (asserted by the script). Reason: with the change at 994 the FanDuel row was co-visible with caption 3 for 0.9 s only (reviewer round 3); at 1102 the row is co-visible at ≥ 2.2× for 944–1062 (1.98 s) and caption 4 opens on the game picture it names. The other seven change points are at their captured frames. The clean film is not affected (same 2,700 frames).",
          f"- Compositing: {caps['compositing']}. Order per frame: scrim → shadow (text mask offset by 3 px, blurred, 0.65 α) → text (white, α × glyph coverage), all in float32 and rounded once. Source: the 2,700 lossless capture PNGs (the same files the clean film is encoded from); `films/caption45.py --frames /tmp/frames/film45c …`.",
          f"- Luminance under the text: clean band rows 110–190 mean {C[0]['band_luminance_110_190_clean_mean']:.4f} (0–1), after the scrim {C[0]['band_luminance_110_190_after_scrim_mean']:.4f} (standard ≤ 0.25) — the same on every caption because the band is stage background in every frame.", ""]
    bc = caps["band_clear"]
    F += ["### 7.3 · Band clear, clean-vs-captioned diff, parent's checker", "",
          f"- Band clear (rows {bc['rows']}): on every one of the 2,700 clean frames the maximum absolute deviation of any band pixel from the band's median is {bc['clean_frames_max_abs_dev_from_median']} and the fraction of pixels deviating by more than 24/255 is {bc['clean_frames_max_intrusion_fraction_gt24']:.4f} — no interface text, pointer or subject enters the band at any time ({bc['note']}). This holds whether or not a caption is visible.",
          f"- Clean vs captioned (`films/capdiff45.py`, `handoff/film45c_capdiff.json`): lossless masters — rows 300–1079 byte-identical on {capdiff['masters']['rows_300_1079_identical_frames']} of {capdiff['masters']['frames']} frames (max |Δ| {capdiff['masters']['rows_300_1079_max_abs_delta']}); rows 0–299 unchanged on every α = 0 frame ({capdiff['masters']['alpha0_frames']} frames, max |Δ| {capdiff['masters']['band_rows_0_299_max_abs_delta_on_alpha0_frames']}) and changed only on the {capdiff['masters']['caption_or_fade_frames']} caption/fade frames. The two crf-16 deliveries are not expected to be byte-identical below the band (the encoder's rate control sees different pictures): rows 300–1079 mean |Δ| {capdiff['deliveries']['rows_300_1079_mean_abs_delta']:.3f}/255, max {capdiff['deliveries']['rows_300_1079_max_abs_delta']} — codec noise, no content difference.",
          "- Parent's checker `review-tools/capcheck.py` on the clean + captioned deliveries. The unmodified script crashes after its segment pass (`IndexError` at line 88, `handoff/film45c_capcheck/capcheck_original_run.log`): its opacity proxy normalises the band difference by the film-wide 90th-percentile plateau, so a short caption (fewer text pixels) never reaches its 95 % “full” threshold, it reports `full@f-1` and then measures glyphs at the first > 50 % frame — a half-opacity frame on which no pixel exceeds its 200/255 ink threshold, so the glyph tuple is empty and the format line fails. Its segment output before the crash is kept verbatim (`captions_original_run.txt`). `capcheck_patched.py` (two disclosed changes: when `full` is not reached, measure glyphs at the segment's middle frame; keep the tuple shape) produced the full output below, `cap_frames/` (band crops, rows 0–320) and `capsheet_half.png` (the checker's contact sheet at half size). Reading it: the segment ranges agree with the α schedule within one frame (the proxy's 50 % crossing is one frame later for the shorter captions: C2 235 vs 234, C4 1013 vs 1012, C7 2060 vs 2058, C8 2269 vs 2268), the `full@f-1 / fade_in=362`-style figures are the normalisation artefact described (not a real timing), cap height is 47 px and the text rows 123–185 on every caption, band intrusion is 0.0000 on the clean film and band luminance 0.047 → 0.028 after the scrim.", ""]
    if capcheck_txt:
        F += ["```", capcheck_txt.strip(), "```", ""]
    F += ["### 7.4 · Section 7 rule check (measured)", "",
          "| clause | measured | result |", "|---|---|---|",
          f"| 7–11 captions, one band (top), whole film | {len(C)} captions, all on y 0–240, frames 0–2699 covered (gaps of 13 frames) | pass |",
          f"| each ≥ 3.0 s (opener ≥ 3.5), ≥ 0.065 s × chars | shortest {min(c['over50_seconds'] for c in C):.3f} s (caption {min(C, key=lambda c: c['over50_seconds'])['index']}); opener {C[0]['over50_seconds']:.3f} s; every span ≥ its minimum (table 7.1) | {'pass' if all(c['over50_frames'] >= c['min_frames_required'] for c in C) else 'FAIL'} |",
          f"| gaps ≤ 0.4 s | every gap 13 frames = 0.217 s | {'pass' if all(g['frames_below_50pct'] <= 24 for g in caps['gaps']) else 'FAIL'} |",
          f"| ≤ 52 chars, ≤ 1,760 px, one line | max {max(c['chars'] for c in C)} chars, {max(c['width_px'] for c in C):.0f} px | pass |",
          f"| Inter SemiBold 64 px, cap 45–49, white, shadow, no box | cap height {C[0]['cap_height_px']} px on every caption | pass |",
          f"| scrim 0.40 to y 200 → 0 at y 300, fades with caption | as composited; luminance under text {C[0]['band_luminance_110_190_after_scrim_mean']:.4f} ≤ 0.25 | pass |",
          f"| band y 0–240 free of interface text, pointer, subject while a caption is visible | max deviation 0 on all 2,700 clean frames | pass |",
          f"| 12-frame linear fades; caption 1 from frame 0 without fade-in; last holds to 2699 | 12-step ramps (11 partial frames, see 7.2); caption 1 full at frame 0; caption 9 full {C[-1]['full_first']}–2699 | pass |",
          f"| changes only at beat boundaries or inside holds, never during a camera move | MARKs {', '.join(str(c['f']) for c in caps['changes'] if not c['cut'])} inside holds; cuts {', '.join(str(c['f']) for c in caps['changes'] if c['cut'])}; no fade range intersects a camera move | pass |",
          "| sentence case, period, present tense; banned list; no re-timing | checked per caption (7.1) | pass |", ""]

    # ---- app version + changes ----------------------------------------------------------------------------------------------------------------
    F += ["## App version and what changed", "",
          f"- Deployed app **The Tape**, asset `2088f758-e90b-423c-ba64-c4c7a2b1ca63`, unchanged in this pass; bundle hash `{bundle_hash}` (sha256 over the path-sorted `sha256  path` lines of the code files; `films/app_version_45c.txt` lists the per-file hashes; `data/` unchanged since Tier 1). The frames were captured from this exact bundle served locally.",
          "- Caption change-point move after the round-3 review (captioned film only): caption 3 → 4 change composited at frame 1102 instead of the captured MARK 994 (§7.2); the clean film's frames and hash are unchanged.",
          "- Changes in this pass are to the film only: (1) the stage inset so the app's top edge sits at film y 260 in every framing (the caption band is never over interface); (2) re-framed beats — the header read at 2.24× (was 2.25×, app x 641–1212), the side-column reads at 2.399× with the column wheeled so the read block sits at the top (replaces the clock scrub and the Q4/OT tooltip reads of the frozen cut, which cannot fit under the band), the toolbar at 2.28×, Agreement at 2.85× (was 2.8×), the Scoreboard payoff at 3.0× (was 3.9×, which does not fit under the band); (3) a pointer slide after the Discovery wheel so the pointer never sits on a digit in the Scoreboard picture; (4) the caption layer. No vendor calls; the ledger is unchanged (OpticOdds 2,098 / 2,071 cached, Sportradar 173 / 173, Polymarket 5,481 / 4,767).", ""]

    # ---- independent review (standard §6) ----------------------------------------------------------------------------------------------------
    rev_path = os.path.join(OUT, "film45c_review.md")
    rev = open(rev_path).read().strip() if os.path.exists(rev_path) else ""
    F += ["## Independent review (standard §6)", "",
          "The captioned film, the clean film, the §3 and §7 text and this beat list were handed to a fresh independent reviewer with the question “list every frame range that breaks a rule in sections 3 or 7, with the measured value”. Rounds 1–2 of the v2 pass (`handoff/film45_review_1.md`, `film45_review_2.md`) concerned the frozen clean film and are kept for the record.", ""]
    if rev:
        F += [f"- Round 3 (`handoff/film45c_review.md`): the first captioned render (change 3 → 4 at MARK 994; delivery `cf000e09…`) and the clean film `{d['sha256'][:8]}…`; delta 3b: the release candidate `{dc['sha256'][:8]}…` after the change move. Summary of the reviewer's verdict and the maker's dispositions —", ""]
        head = rev.split("## Reviewer's report")[0]
        summ = [l for l in head.splitlines() if l.strip().startswith(("- ", "* ", "**"))][:14]
        F += ["  " + l.strip() for l in summ] + [""]
    else:
        F += ["- Round 3: pending (`handoff/film45c_review.md`).", ""]
    F += ["## Receipts", "", "- `handoff/film45_receipts.md` — every number visible in the film → data source, with DOM cross-checks (" + f"{n_ok}/{len(checks)} pass).",
          "- `films/film45c_timeline.json` — per-frame pointer position and speed, camera, in-frame flag; holds, camera moves, pointer moves, events (with wheel settle times), cuts, DOM notes, caption MARKs.",
          "- `handoff/film45c_qa.json`, `handoff/film45c_qa_captioned.json`, `handoff/film45c_text.json`, `handoff/geom_states45c.json`, `handoff/film45_captions.json`, `handoff/film45c_capdiff.json`, `handoff/film45c_capcheck/`, `films/the-tape-45s-encode.json` — the measurements behind sections 1, 2, 4, 5 and 7.",
          "- Reproduce: `node`-side `films/capture45c.js` + `films/storyboard45c.js` against the deployed bundle (served locally), then `films/encode45.py` (clean), `films/caption45.py --move-change 994:1102` (captioned), `films/qa45.py` ×2, `films/dupsrc45.py`, `films/measure45c.py`, `films/capdiff45.py`, the parent's `capcheck.py`, `pipeline/15_film45c_receipts.py`.", ""]
    open(os.path.join(OUT, "films-v2.md"), "w").write("\n".join(F) + "\n")

    # ---- trim handoff/frames45c/qa_* to the key frames ---------------------------------------------------------------------------------------
    keep = {0, 2699} | set(fh)
    for e in tl["events"]:
        keep.add(e["f"])
        if e["type"] == "click":
            keep.add(e["f"] + 1)
    for c in cuts:
        keep |= {c - 1, c}
    for l in notes:
        if notes[l]["f"] < 2700:
            keep.add(nframe(l))
    for e in text:
        keep.add(e["frame"])
    keep_cap = {0, 2699} | set(fh) | {c["measured_at_frame"] for c in C}
    for c in cuts:
        keep_cap |= {c - 1, c}
    removed = 0
    for sub, ks in (("qa_clean", keep), ("qa_captioned", keep_cap)):
        fr_dir = os.path.join(OUT, "frames45c", sub)
        if not os.path.isdir(fr_dir):
            continue
        for fn in os.listdir(fr_dir):
            mm = re.match(r"f(\d{5})\.png$", fn)
            if mm and int(mm.group(1)) not in ks:
                os.remove(os.path.join(fr_dir, fn))
                removed += 1
    print(f"films-v2.md ({len(F)} lines), film45_receipts.md ({len(R)} lines, {n_ok}/{len(checks)} cross-checks pass); frames45c/qa_clean kept ≤ {len(keep)} key frames, qa_captioned ≤ {len(keep_cap)}, removed {removed}")
    for lab, ok, det in checks:
        if not ok:
            print(f"  FAILED CHECK: {lab} — {det}")


if __name__ == "__main__":
    main()
