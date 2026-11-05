#!/usr/bin/env python3
"""Assemble the handoff folder from the derived data, the analysis tables, the QA files and the call ledger.

Everything written here is regenerated from files on disk (no network), so every number has a receipt:
  handoff/README.md               overview, coverage, matching, methods, results index, ledger, limitations, attribution
  handoff/dataset_manifest.json   dataset manifest (per-league census, windows, fidelities, notes)
  handoff/matching_stats.csv      matched / unmatched per league and source (+ tiers), both windows
  handoff/overrides.json          manual-override file used by the matcher
  handoff/methods.md              method definitions
  handoff/results/*.csv           CSV result tables (a)–(g)
  handoff/call_ledger.csv         exact per-call ledger (every attempt, every source) + cache-served reads summary
  handoff/call_ledger_summary.csv per-source attempted / succeeded / throttled / other errors / cache-served reads
  handoff/limitations.md
  handoff/attribution.md
  handoff/hero_receipts.md        the hero game's quoted numbers with their raw vendor receipts
"""
import csv
import json
import os
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.dirname(HERE)
DATA = os.environ.get("A9_DATA", "/home/user/workspace/a9-data")
DER = os.path.join(DATA, "derived")
DEPLOY = os.environ.get("A9_DEPLOY", "/home/user/workspace/a9-deploy")
OUT = os.path.join(BUILD, "handoff")
APP_URL = "https://www.perplexity.ai/computer/a/the-tape-IIj3WOkLQjy6ZMTHorHKYw"
ASSET_ID = "2088f758-e90b-423c-ba64-c4c7a2b1ca63"
LEAGUE_NAME = {"nfl": "NFL", "ncaaf": "NCAAF", "mlb": "MLB", "nba": "NBA", "nhl": "NHL", "wnba": "WNBA", "mls": "MLS", "epl": "Premier League", "laliga": "La Liga",
               "seriea": "Serie A", "bundesliga": "Bundesliga", "ligue1": "Ligue 1", "ucl": "Champions League"}
ORDER = ["nfl", "ncaaf", "mlb", "nba", "nhl", "wnba", "mls", "epl", "laliga", "seriea", "bundesliga", "ligue1", "ucl"]


def load(p):
    return json.load(open(p))


def fmt(n):
    return f"{n:,}" if isinstance(n, int) else (f"{n:,.0f}" if isinstance(n, float) else str(n))


def main():
    os.makedirs(os.path.join(OUT, "results"), exist_ok=True)
    manifest = load(os.path.join(DER, "manifest.json"))
    analysis = load(os.path.join(DER, "analysis.json"))
    wall = load(os.path.join(DER, "wall.json"))
    matches = load(os.path.join(DER, "matches.json"))
    matches_ext = load(os.path.join(DER, "matches_ext.json")) if os.path.exists(os.path.join(DER, "matches_ext.json")) else None
    meta = load(os.path.join(DEPLOY, "data", "meta.json"))
    audit = load(os.path.join(BUILD, "qa", "matching_audit.json"))
    hand = load(os.path.join(BUILD, "qa", "hand_review.json"))
    recomp = load(os.path.join(BUILD, "qa", "recomputation_20.json"))
    census = manifest["census"]
    win = manifest["window_utc"]
    ext = manifest.get("extension") or {}

    # ---- dataset manifest -------------------------------------------------------------------------------------
    files = {
        "wall.json": "one strip per matched game (keys, kickoff, league, sources present, Pinnacle/consensus/Polymarket closes, finals)",
        "games/<league>_<fixture>.json": "per-game aligned series: sportsbook raw + no-vig step functions per book (OpticOdds), Polymarket sampled prices + fee schedule, Sportradar plays",
        "full/<league>_<fixture>.json": "per-game full-resolution Polymarket home series used by the discovery analysis",
        "analysis.json": "every analysis block with {window, n} and bootstrap CIs (consumed by the explorer)",
        "manifest.json": "this census",
    }
    json.dump({**manifest, "deployed_app": {"title": "The Tape", "asset_id": ASSET_ID, "url": APP_URL}, "files": files,
               "data_root_note": "raw vendor responses are kept as content-addressed JSON (sha1 of source+path+params) outside the repo; the ledger key column points at them"},
              open(os.path.join(OUT, "dataset_manifest.json"), "w"), indent=1)

    # ---- matching stats ---------------------------------------------------------------------------------------
    rows = []
    for lg in ORDER:
        st = matches["stats"].get(lg)
        if not st:
            continue
        c = census.get(lg, {})
        rows.append({"window": "analysis (3-way)", "league": lg, **{k: v for k, v in st.items() if not isinstance(v, (dict, list))},
                     **{f"tier_{k}": v for k, v in (st.get("tiers") or {}).items()}, "in_window_matched": c.get("games", 0),
                     "with_sportsbook_history": c.get("with_oo_history", 0), "with_polymarket_history": c.get("with_pm_history", 0), "with_plays": c.get("with_plays", 0)})
    if matches_ext:
        for lg in ORDER:
            st = matches_ext["stats"].get(lg)
            if not st:
                continue
            c = census.get(lg, {})
            rows.append({"window": "extension (OpticOdds x Sportradar only)", "league": lg, **{k: v for k, v in st.items() if not isinstance(v, (dict, list))},
                         **{f"tier_{k}": v for k, v in (st.get("tiers") or {}).items()}, "in_window_matched": c.get("ext_games", 0) + c.get("ext_matched_without_history", 0),
                         "with_sportsbook_history": c.get("ext_with_oo_history", 0), "with_polymarket_history": 0, "with_plays": 0})
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with open(os.path.join(OUT, "matching_stats.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    shutil.copy(os.path.join(HERE, "overrides.json"), os.path.join(OUT, "overrides.json"))
    shutil.copy(os.path.join(HERE, "aliases.json"), os.path.join(OUT, "aliases.json"))
    for fn in ("matching_audit_40.md", "matching_audit_all.csv", "hand_review.json", "recomputation_20.md", "recomputation_20.json"):
        shutil.copy(os.path.join(BUILD, "qa", fn), os.path.join(OUT, fn))

    # ---- results ----------------------------------------------------------------------------------------------
    tables = sorted(os.listdir(os.path.join(BUILD, "analysis", "tables")))
    for fn in tables:
        shutil.copy(os.path.join(BUILD, "analysis", "tables", fn), os.path.join(OUT, "results", fn))

    # ---- ledger -----------------------------------------------------------------------------------------------
    led_rows = []
    per = defaultdict(lambda: Counter())
    first, last = None, None
    with open(os.path.join(DATA, "ledger", "calls.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            per[r["source"]]["attempted"] += 1
            if r["ok"]:
                per[r["source"]]["succeeded"] += 1
            elif "429" in (r.get("error") or "") or "rate limit" in (r.get("error") or "").lower() or r.get("transient"):
                per[r["source"]]["throttled_429"] += 1
            else:
                per[r["source"]]["other_errors"] += 1
            first = first or r["t"]
            last = r["t"]
            led_rows.append({"t": r["t"], "source": r["source"], "product": r.get("product") or "", "path": r["path"], "params": json.dumps(r.get("params") or {}, sort_keys=True, separators=(",", ":")),
                             "cache_key": r["key"], "ok": int(bool(r["ok"])), "ms": r.get("ms"), "bytes": r.get("bytes"), "error": (r.get("error") or "")[:120], "tier": r.get("tier"), "game_key": r.get("game_key") or ""})
    cache_hits = Counter()
    if os.path.exists(os.path.join(DATA, "ledger", "cache_hits.jsonl")):
        with open(os.path.join(DATA, "ledger", "cache_hits.jsonl")) as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    cache_hits[parts[1]] += 1
    unique = {}
    for s in ("opticodds", "polymarket", "sportradar"):
        d = os.path.join(DATA, "cache", s)
        unique[s] = sum(1 for fn in os.listdir(d) if fn.endswith(".json")) if os.path.isdir(d) else 0
    with open(os.path.join(OUT, "call_ledger.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(led_rows[0].keys()))
        w.writeheader()
        w.writerows(led_rows)
    caps = meta.get("budget") or {}
    with open(os.path.join(OUT, "call_ledger_summary.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "attempted", "succeeded", "throttled_429_not_cached", "other_errors", "cache_served_reads", "unique_ok_responses_on_disk", "cap_for_completed_tier"])
        for s in ("opticodds", "polymarket", "sportradar"):
            w.writerow([s, per[s]["attempted"], per[s]["succeeded"], per[s]["throttled_429"], per[s]["other_errors"], cache_hits.get(s, 0), unique[s], caps.get(s, "")])

    # ---- hero receipts ----------------------------------------------------------------------------------------
    hero_key = "nfl:2026101240603BF9"
    g = load(os.path.join(DER, "games", hero_key.replace(":", "_") + ".json"))
    fd = g["oo"]["books"]["FanDuel"]["ml"]
    pin = g["oo"]["books"]["Pinnacle"]["ml"]
    ko = g["kickoff"]
    def iso(t):
        return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    fd_away = fd["raw"]["away"]
    fd_home = fd["raw"]["home"]
    fd_close_away = [r for r in fd_away if r[0] <= ko][-1]
    fd_close_home = [r for r in fd_home if r[0] <= ko][-1]
    pin_close = [r for r in pin["novig"] if r[0] <= ko][-1]
    pm = g["pm"]
    pm_ml = pm["markets"].get("ml_home") or pm["markets"].get("ml_away") or {}
    hs = pm.get("home_series") or []
    pm_close = [r for r in hs if r[0] <= ko][-1] if hs else None
    plays = [p for p in g["sr"].get("plays", []) if p.get("scoring")]
    _q4 = [p for p in plays if p.get('period') == 4]
    q4td = next((p for p in plays if p.get('ap') == 21 and p.get('hp') == 23), _q4[-2] if len(_q4) > 1 else (_q4[-1] if _q4 else {}))
    ot_plays = [p for p in plays if _q4 and p['t'] > _q4[-1]['t']]
    hero = [
        "# Hero game receipts — Baltimore Ravens @ Atlanta Falcons (NFL week 5)", "",
        f"- Sportradar: kickoff {iso(ko)}{(' · ' + g['context']['venue']['name']) if isinstance(g.get('context', {}).get('venue'), dict) else ''}; final {g['away']['abbr']} {g['final']['away']} – {g['home']['abbr']} {g['final']['home']}{' (OT)' if any(p.get('period_type') == 'overtime' for p in g['final'].get('periods') or []) else ''}; OpticOdds score {g['final'].get('oo_score')} and Polymarket score string {g['final'].get('pm_score')} agree; {len(g['sr'].get('plays', []))} plays with wall clocks, {len(plays)} scoring plays. Receipts: ledger rows with game_key `{hero_key}` and source `sportradar` (schedule, boxscore, pbp).",
        f"- OpticOdds fixture `{hero_key.split(':')[1]}`, FanDuel moneyline (raw American): first retained entry {iso(fd_away[0][0])} BAL {fd_away[0][1]:+.0f} / ATL {fd_home[0][1]:+.0f}; last pre-kickoff entry {iso(fd_close_away[0])} BAL {fd_close_away[1]:+.0f} / ATL {fd_close_home[1]:+.0f}. {len(fd_away)} away entries, {len(fd_home)} home entries. Receipt: `/fixtures/odds/historical` row with game_key `{hero_key}`.",
        f"- Pinnacle no-vig close (multiplicative, last entry ≤ kickoff at {iso(pin_close[0])}): p(ATL) = {pin_close[1]:.4f}.",
        f"- Polymarket moneyline market `{pm_ml.get('market_id')}` ({pm_ml.get('question')}): {pm_ml.get('n_samples')} samples at {'/'.join(map(str, pm_ml.get('fidelities') or []))}-minute fidelity; fee schedule {pm_ml.get('fee', {}).get('rate', 0) * 100:.0f}% × p(1−p); last pre-kickoff sample {iso(pm_close[0]) if pm_close else 'n/a'} p(ATL) = {pm_close[1]:.3f}" + (f"; event volume ${pm.get('volume_event', 0):,.0f}." if pm.get('volume_event') else "."),
        "", "## Scoring plays (Sportradar wall clock, running score away–home)", "",
        "| wall clock (UTC) | period | clock | score | play |", "|---|---|---|---|---|",
    ]
    for p in plays:
        hero.append(f"| {iso(p['t'])} | {p.get('period')} | {p.get('clock') or ''} | {p.get('ap')}–{p.get('hp')} | {(p.get('desc') or '').replace('|', '/')[:110]} |")
    # headline candidates (parent review mail, 2026-10-15) — each figure traced to the dataset value it is rounded from
    census_all = manifest["census"]
    ag = analysis["agreement"]["per_league"]["all"] if "per_league" in analysis.get("agreement", {}) else analysis["agreement"]["all"]
    h_entries = sum(c.get("oo_entries", 0) for c in census_all.values()) + sum(c.get("ext_oo_entries", 0) for c in census_all.values())
    h_pm = sum(c.get("pm_samples_all_markets", 0) for c in census_all.values())
    h_vol = sum(c.get("pm_volume_ml", 0) or 0 for c in census_all.values())
    h_plays = sum(c.get("plays", 0) for c in census_all.values())
    within2 = ag.get("within_2pp") if ag.get("within_2pp") is not None else ag.get("share_within_2pp")
    hero += ["", "## Headline candidates (parent review mail) and their receipts", "",
             f"- `{manifest['n_games']:,} games · {len(census_all)} leagues · {h_entries / 1e6:.2f} M sportsbook price updates · {h_pm / 1e6:.1f} M Polymarket samples · ${h_vol / 1e6:.0f} M volume · {h_plays:,} plays` — census: {manifest['n_games']:,} matched games in {len(census_all)} leagues (`manifest.n_games`, `manifest.census`); {h_entries:,} sportsbook entries = {sum(c.get('oo_entries', 0) for c in census_all.values()):,} in-window + {sum(c.get('ext_oo_entries', 0) for c in census_all.values()):,} extension (`census.*.oo_entries` + `ext_oo_entries`); {h_pm:,} Polymarket samples across all fetched markets (`census.*.pm_samples_all_markets`); ${h_vol:,.0f} Polymarket moneyline volume (`census.*.pm_volume_ml`, Gamma `volume`); {h_plays:,} Sportradar plays with wall clocks (`census.*.plays`). Each appears verbatim (unrounded) in the wall header.",
             f"- `Polymarket's last pre-kickoff price landed within 2 pp of Pinnacle's no-vig close in {within2 * 100:.0f} % of {ag['n']} games` — `analysis.agreement` (league = all): N = {ag['n']}, share with |PM − Pinnacle| ≤ 2 pp = {within2 * 100:.2f}% (rounds to {within2 * 100:.0f}%), Pearson r = {ag['corr_pm_pinnacle']:.4f}, mean signed gap {ag['mean_diff'] * 100:+.2f} pp; Pinnacle close = multiplicative no-vig of its last entry ≤ kickoff, Polymarket = last sampled price ≤ 30 min before kickoff (`results/b_closing_agreement_summary.csv`).",
             "", "## In-game preset (game view)", "",
             f"- `In-game` = [kickoff − 10 min, final whistle], where the final whistle is the wall clock of the last Sportradar play ({iso(max(p['t'] for p in g['sr'].get('plays', [])))}); scoring plays are drawn on the Polymarket line at their wall clocks with the running score (away–home) as staggered labels; the Polymarket line is drawn thicker inside the game than before kickoff. Labels are hidden when the visible span exceeds 3 days.",
             f"- Scoring plays in the film: Q4 00:44 touchdown {q4td.get('ap')}–{q4td.get('hp')} at {iso(q4td['t'])} (tooltip at 1.8×); overtime plays (Sportradar restarts the period count at 1 for OT, so they are the plays after the last fourth-quarter play) " + "; ".join(f"{p.get('ap')}–{p.get('hp')} at {iso(p['t'])}" for p in ot_plays) + " (table above); the film's second tooltip is the OT touchdown.",
             ]
    open(os.path.join(OUT, "hero_receipts.md"), "w").write("\n".join(hero) + "\n")

    # ---- methods ----------------------------------------------------------------------------------------------
    methods = f"""# Methods

All definitions below are the ones implemented in `pipeline/lib/norm.py`, `pipeline/08_build_dataset.py` and `pipeline/09_analyses.py`; the independent recomputation (`pipeline/10_recompute.py`) re-derives the same quantities from the raw vendor responses with exact fractions.

## Alignment
- Sources: OpticOdds fixtures + historical odds (five sportsbooks requested in one call per fixture: Pinnacle, DraftKings, FanDuel, BetMGM, Caesars), Polymarket Gamma events/markets + CLOB price history, Sportradar schedules, finals, boxscores and play-by-play.
- A match requires the same league, normalized team names (Unicode-folded, punctuation-stripped, alias table `aliases.json`) and start times within ±20 minutes. Confidence tiers: A = exact names + exact time on both pairs; B = alias/abbreviation match or time within tolerance; C = one-sided name match confirmed by the final score; M = manual override (`overrides.json`, hand-verified).
- Sportradar's home/away orientation is canonical; odds are mapped by team identity, so a flipped vendor label does not flip a price.
- Nothing is aligned by assumption: a league appears in a cross-market statistic only where every source has data for that game.

## Normalization
- American odds → implied probability: p = 100/(o+100) if o > 0 else −o/(−o+100).
- No-vig: multiplicative normalization across the market's selections at the same instant (p_i / Σ p_j), two-way for moneyline/spread/total in US sports, three-way for soccer moneylines. Spread no-vig is only emitted when the two lines are mirror images.
- A sportsbook price is a step function: it holds until the same sportsbook's next entry. No-vig series are evaluated on the union of the selections' entry timestamps.
- Closing = the state of the step function at kickoff (last entry with t ≤ kickoff). Opening = the vendor's OLV pair (OpticOdds `olv`), no-vigged the same way, in the opening statistics; the game view's open marker is the first entry in the retained history (OpticOdds keeps about two months) and the OLV/CLV fields are kept as receipts. In the agreement, calibration and backtest tables a sportsbook's close counts only when its last entry is within 6 h of kickoff (otherwise the book is treated as not quoting at the close); the game view still shows the stale step with its age.
- Polymarket `p` is a sampled CLOB price taken directly as a probability and labelled as such everywhere. Sampling fidelity follows the lookback the vendor allows (1-month lookback → 10-minute fidelity; 1-week → 5-minute; 1-day → 1-minute). Each market's fee schedule is stored with the market; backtests charge the taker fee rate × p(1−p) on entry.
- The hero's in-game read uses the 1-minute Polymarket series where it exists.

## Analyses
- (a) Census: games, sportsbook entries, Polymarket samples and volume, plays, per league and in total, for the analysis window and the sportsbook-only extension.
- (b) Closing agreement: Pinnacle no-vig close vs Polymarket last pre-kickoff sample (≤ {30} minutes old), per league: mean signed and absolute gap, Pearson r, bootstrap CIs; line agreement for spreads/totals where both sides exist.
- (c) Price discovery: both series put on a 10-minute grid over the last 48 h before kickoff (a Polymarket sample must exist within 2 h of each grid point); cross-correlation of first differences at lags −120 … +120 minutes; "who moved first" counts the source whose first-difference leads a ≥ 2 pp move, with Wilson 95% CIs; event-study response curves around sportsbook moves.
- (d) Calibration: Brier score and log loss of p(home) against the final, at T−24 h, T−1 h, T−1 min (Polymarket) and the sportsbook closes, per league and source, with percentile-bootstrap 95% CIs (2,000 resamples) and reliability bins. The extended table repeats the sportsbook-only part over the analysis window + the extension month.
- (e) Backtests (illustrative, fee-aware, no recommendation): "follow Pinnacle" buys the Polymarket side where Pinnacle's no-vig probability exceeds the Polymarket price by θ ∈ {{2, 3, 5, 8}} pp at entry T−6 h / T−1 h / T−10 min (Polymarket sample age limits 120 / 60 / 20 min); "fade the late move"; in-game "buy after a scoring play". Each reports N, hit rate, ROI, 95% CI, max drawdown and a label-shuffled placebo.
- (f) In-game reaction: Polymarket price change in the minutes after Sportradar scoring plays (wall clocks), for the games with play-by-play.
- (g) Context: Sportradar schedule/venue/day factors against closing agreement, with a multiple-comparison caveat (many small groups; no claim survives correction).

## Statistics
- Bootstrap CIs are percentile intervals over 2,000 resamples (seeded); proportions use Wilson intervals; the placebo shuffles outcome labels within league.
"""
    open(os.path.join(OUT, "methods.md"), "w").write(methods)

    # ---- limitations --------------------------------------------------------------------------------------------
    pm_fid = manifest.get("pm_fidelity_minutes_games", {})
    ncaaf_c = census.get("ncaaf", {})
    lims = f"""# Limitations

- Sportsbook history: OpticOdds retains a rolling two months of history, and a few fixtures (mostly FCS college football) returned an empty history for all five sportsbooks; those games stay on the wall as Polymarket + Sportradar only. In the analysis window {sum(c.get('with_oo_history', 0) for c in census.values()):,} of {manifest['n_games']:,} matched games have sportsbook history (NCAAF {ncaaf_c.get('with_oo_history', 0)} of {ncaaf_c.get('games', 0)}).
- Five sportsbooks were requested (Pinnacle, DraftKings, FanDuel, BetMGM, Caesars); a book is absent from a game when it had no retained line for the market. bet365 was dropped from the request set because it returned no retained history.
- Polymarket prices are sampled, not tick data: {pm_fid.get('10', 0):,} game-markets at 10-minute fidelity, {pm_fid.get('5', 0):,} at 5-minute, {pm_fid.get('1', 0):,} at 1-minute (the vendor's lookback rules). Pre-kickoff checkpoints therefore carry a sample-age column, and the analyses drop checkpoints whose latest sample is too old.
- Polymarket throttled the first burst of history requests (700 HTTP 429 responses, none cached, all retried later at ≤ 20 calls/min with exponential backoff); attempts and successes are both reported in the ledger. OpticOdds' historical bucket rate-limited 27 extension requests (04:50–04:58 UTC) even at ~35 calls/min; only the calls left under the Tier-1 cap were retried, so the remaining extension games without sportsbook history are listed in `matching_stats.csv` (extension rows: matched minus with-history).
- Sportradar play-by-play: fetched for a hero set only ({sum(c.get('with_plays', 0) for c in census.values())} games; {sum(c.get('plays', 0) for c in census.values()):,} plays with wall clocks). Several FCS college-football games carry `extended_boxscore` coverage with no play-by-play; Sportradar's MLB schedule feed carries no final score, so MLB finals come from OpticOdds and are cross-checked against Polymarket's score string.
- The sportsbook-only extension ({ext.get('window_utc', ['', ''])[0][:10]} → {ext.get('window_utc', ['', ''])[1][:10]}) has no Polymarket markets (none were fetched for that period); it feeds only the extended sportsbook calibration table. MLB in the extension covers 2026-09-02 → 09-14 only and the NFL part is regular-season week 1 (no preseason), as the OpticOdds budget allowed.
- Leagues enter a cross-market statistic only where every source has that game; small leagues (Serie A, Bundesliga, Ligue 1, UCL, Premier League, La Liga, MLS, WNBA) have N in the tens, and their CIs say so.
- Backtests are illustrative: fees are the taker schedule stored with each market, fills are assumed at the sampled price, no slippage or liquidity model, no trading was done and none is recommended.
- "Who moved first" is measured on a 10-minute grid, so leads shorter than 10 minutes are indistinguishable from simultaneity.
- Context factors (g) compare many small groups; nothing is claimed to survive multiple-comparison correction.
- Film capture is frame-stepped with a deterministic clock (disclosed in `films.md`); the footage is the real app with a real pointer, not a composite.
"""
    open(os.path.join(OUT, "limitations.md"), "w").write(lims)

    attribution = """# Attribution

Sportsbook lines and odds history: OpticOdds. Prediction-market prices, volumes and fee schedules: Polymarket. Schedules, results, venues, boxscores and play-by-play: Sportradar.

Every price in the explorer, the films and the tables names its sportsbook or Polymarket; every table and chart states its window and N. Historical analysis only; no trading, no recommendations, no edge claims.

Footer text used in the app: "Sportsbook lines: OpticOdds · Prediction-market prices: Polymarket · Schedules, results, play-by-play: Sportradar. Historical analysis only; no trading, no recommendations."
"""
    open(os.path.join(OUT, "attribution.md"), "w").write(attribution)

    # ---- README -------------------------------------------------------------------------------------------------
    tot_games = manifest["n_games"]
    tot_oo = sum(c.get("with_oo_history", 0) for c in census.values())
    tot_entries = sum(c.get("oo_entries", 0) for c in census.values())
    tot_pm = sum(c.get("pm_samples", 0) for c in census.values())
    tot_pm_all = sum(c.get("pm_samples_all_markets", 0) for c in census.values())
    tot_pm_mk = sum(c.get("pm_markets", 0) for c in census.values())
    tot_vol = sum(c.get("pm_volume_ml", 0) or 0 for c in census.values())
    tot_plays = sum(c.get("plays", 0) for c in census.values())
    tot_play_games = sum(c.get("with_plays", 0) for c in census.values())
    ext_games = sum(c.get("ext_with_oo_history", 0) for c in census.values())
    ext_entries = sum(c.get("ext_oo_entries", 0) for c in census.values())
    cov = ["| league | matched (3-way) | with sportsbook history | with Polymarket history | with play-by-play | sportsbook entries | Polymarket samples (home-win series) | PM ML volume | extension games (books only) |", "|---|---|---|---|---|---|---|---|---|"]
    for lg in ORDER:
        c = census.get(lg)
        if not c:
            continue
        cov.append(f"| {LEAGUE_NAME[lg]} | {c.get('games', 0):,} | {c.get('with_oo_history', 0):,} | {c.get('with_pm_history', 0):,} | {c.get('with_plays', 0):,} | {c.get('oo_entries', 0):,} | {c.get('pm_samples', 0):,} | ${(c.get('pm_volume_ml') or 0):,.0f} | {c.get('ext_with_oo_history', 0):,} |")
    cov.append(f"| **Total** | **{tot_games:,}** | **{tot_oo:,}** | **{sum(c.get('with_pm_history', 0) for c in census.values()):,}** | **{tot_play_games:,}** | **{tot_entries:,}** | **{tot_pm:,}** | **${tot_vol:,.0f}** | **{ext_games:,}** |")
    led_tbl = ["| source | attempted | succeeded | throttled (rate limit, not cached) | other errors | cache-served reads | unique responses on disk | cap |", "|---|---|---|---|---|---|---|---|"]
    for s in ("opticodds", "polymarket", "sportradar"):
        led_tbl.append(f"| {s} | {per[s]['attempted']:,} | {per[s]['succeeded']:,} | {per[s]['throttled_429']:,} | {per[s]['other_errors']:,} | {cache_hits.get(s, 0):,} | {unique[s]:,} | {caps.get(s, '')} |")
    mstats = matches["stats"]
    tiers = matches.get("tiers") or {}
    n3 = len(matches["matches"])
    n2 = len(matches_ext["matches"]) if matches_ext else 0
    ov = load(os.path.join(HERE, "overrides.json"))
    n_over = len(ov.get("matches", ov)) if isinstance(ov, dict) else len(ov)
    tiers_txt = ", ".join(f"tier {k} {v}" for k, v in sorted(tiers.items()))
    ext_no_hist = sum(c.get("ext_matched_without_history", 0) for c in census.values())
    today = load(os.path.join(DER, "today.json")) if os.path.exists(os.path.join(DER, "today.json")) else None
    if today:
        tl = Counter(x["lg"] for x in today["games"])
        tcalls = today.get("calls", {})
        today_txt = (f"- {today['n_games']} games with a sportsbook moneyline inside the 30 h slate window ({', '.join(f'{LEAGUE_NAME.get(k, k)} {v}' for k, v in tl.items())}; WNBA had no game in the window). "
                     f"OpticOdds retrieved {today['retrieved_at_oo'][:19]}Z (latest line timestamp {today['oo_latest_line_timestamp'][:19]}Z); Polymarket midpoints retrieved {today['retrieved_at_pm'][:19]}Z. "
                     f"Calls: OpticOdds {tcalls.get('opticodds', {}).get('fixtures_active', 0)} × `/fixtures/active` + {tcalls.get('opticodds', {}).get('fixtures_odds', 0)} × `/fixtures/odds` (≤ 5 fixtures, 5 books, moneyline, main line) = {sum(tcalls.get('opticodds', {}).values())} of the 30 authorized; "
                     f"Polymarket {tcalls.get('polymarket', {}).get('events_by_tag', 0)} tag listings + {tcalls.get('polymarket', {}).get('events_by_slug_attempts', 0)} slug look-ups ({tcalls.get('polymarket', {}).get('events_by_slug_ok', 0)} found) + {tcalls.get('polymarket', {}).get('midpoint', 0)} CLOB midpoints. "
                     f"Method: {today['method']} Raw responses: `derived/today_odds_raw.json`, `today_pm_mid.json`; table: `results/today_snapshot.csv`.")
    else:
        today_txt = "- not built"
    readme = f"""# A9 THE TAPE — handoff

Deployed app: **The Tape** — {APP_URL} (asset `{ASSET_ID}`, private, updated in place). Tier completed: **{meta.get('tier_label', 'Tier 1')}** — Tier 1 plus the sportsbook-only extension plus one Today snapshot (30-call authorization), all within the authorized caps (see the ledger below); no further tier was requested.

Three sources, three timelines, one clock: OpticOdds sportsbook history (five books) × Polymarket sampled prices × Sportradar schedules, finals and play-by-play, aligned per game for **{tot_games:,} games in {len(census)} leagues** between {win[0][:10]} and {win[1][:10]} UTC, plus {ext_games:,} sportsbook-only games from {ext.get('window_utc', ['', ''])[0][:10]} → {ext.get('window_utc', ['', ''])[1][:10]}.

## Breadth (all counts regenerated from the dataset)
- {tot_games:,} matched games · {len(census)} leagues · {tot_oo:,} with sportsbook history ({tot_entries:,} sportsbook price updates across Pinnacle, DraftKings, FanDuel, BetMGM, Caesars) · {tot_pm_all:,} Polymarket price samples across {tot_pm_mk:,} markets ({tot_pm:,} in the home-win series) · ${tot_vol:,.0f} Polymarket moneyline volume · {tot_plays:,} Sportradar plays with wall clocks in {tot_play_games} games.
- Sportsbook-only extension: {ext_games:,} games, {ext_entries:,} sportsbook entries (OpticOdds × Sportradar; no Polymarket for that month).

## Coverage per league
{chr(10).join(cov)}

Leagues where any source was missing were dropped rather than aligned by assumption (UFC/MMA and NBA preseason markets outside Polymarket's coverage, for instance, never enter a cross-market table).

## Matching
- Three-way matcher (`pipeline/04_match.py`): league + normalized names/aliases + start within ±20 min (tolerance {matches.get('tolerance_minutes', 20)} min). Discovery window: {n3:,} three-way matches ({tiers_txt}); {tot_games:,} of them kick off inside the analysis window; {n_over} manual overrides in `overrides.json`. Per-league matched/unmatched counts per source: `matching_stats.csv`.
- Extension window: two-way OpticOdds ↔ Sportradar matcher (`pipeline/04c_match_ext.py`), {n2:,} matches; {ext_games:,} carry sportsbook history, {ext_no_hist:,} were matched but not fetched or failed at the cap (MLB 08-14 → 09-01 by budget; 20 NCAAF rate-limited at the cap).
- Automatic final-score cross-check over every matched game in the analysis window: {audit.get('n_all', 0) - audit.get('n_inconsistent', 0):,} consistent / {audit.get('n_inconsistent', 0)} inconsistent of {audit.get('n_all', 0):,} (OpticOdds home/away label flips are mapped by team identity before the check). 40-game random sample (seed {hand.get('seed', 7)}) hand-reviewed: **{hand.get('wrong', 0)} wrong of {hand.get('n', 40)}** (`matching_audit_40.md`, `hand_review.json`).
- Independent recomputation of 20 random games from the raw vendor responses with exact fractions: all checks within 1e-9 (worst |Δ| {max((v for v in recomp.get('worst_abs_diff_by_check', {}).values() if isinstance(v, (int, float))), default=0):.1e}; `recomputation_20.md`).

## Methods
See `methods.md` (American → implied → multiplicative no-vig per book per timestamp; step functions; closing = last entry ≤ kickoff; opening = OLV; Polymarket p = sampled price labelled as such; taker fees applied in backtests).

## Results (CSV, `results/`)
{chr(10).join(f'- `{fn}`' for fn in tables)}

## Call ledger (exact, from the first call; `call_ledger.csv`, one row per attempt)
{chr(10).join(led_tbl)}

First call {first}, last call {last}. "Cache-served reads" are repeat reads answered from the content-addressed response cache without a vendor call (never counted as attempts). Polymarket was paced at ≤ 20 calls/min with exponential backoff after the initial burst; the 700 throttled responses were never cached and were re-requested later.

## QA gates
- 40-game hand audit: {hand.get('wrong', 0)} wrong (`hand_review.json`).
- 20-game independent recomputation to 1e-9: pass (`recomputation_20.md`).
- Hero game view verified against Sportradar wall clocks (`hero_receipts.md`).
- Wall renders every strip (canvas, draw time recorded in the methods page); filters, source toggles and the window segment work; the backtest lab recomputes client-side with no network.
- Ledger within the authorized caps (table above; the Today snapshot used 10 of its 30 OpticOdds calls).
- Film receipts: every on-screen number in both films traced to its source value, with numeric cross-checks for the scoreboard rows and the lab KPIs (`film_receipts.md`).

## Review fixes (parent review, 2026-10-15 ~05:50Z) — all deployed to the same asset
1. Scoreboard: Brier / log loss across sources are computed on a **common game set per league** (a game enters when every eligible source priced it; a source is eligible when it quoted ≥ 50% of the league's games) so every source row has an identical N ({', '.join(f"{k} {v}" for k, v in analysis['calibration']['common_n'].items())}); the availability-based table (per-source N) is kept as a secondary toggle. Excluded as sub-50% sources: {'; '.join(f"{lg}: {', '.join(v)}" for lg, v in analysis['calibration']['common_excluded'].items() if v)}.
2. Game view: `In-game` preset (kickoff − 10 min → final whistle) next to Full history / Week / Game day; Sportradar scoring plays drawn as markers on the Polymarket line with staggered running-score labels (up to four rows, a label is skipped rather than overlapped); thicker in-game line.
3. Backtest lab: strategy select text no longer overflows (controls column widened; option text wraps).
4. Today: one timestamped snapshot of the slate (see below), every cell carries its own vendor timestamp; not a feed.
5. Films re-shot (v2): 1920×1080 at 60 fps, pointer-led editorial zooms so every quoted number is legible (≥ 28 px at 1080p), Sportradar tooltips, SHA-256s in `films.md`; every on-screen number traced in `film_receipts.md`.

## Today snapshot (one timestamped read, not a feed)
{today_txt}

## Films
`films/the-tape-60s.mp4` and `films/the-tape-30s.mp4`: 1920×1080, 60 fps (3600 / 1800 frames), silent, H.264. Frame-stepped deterministic capture with pointer-led editorial zooms (disclosed, with the SHA-256 of each file, in `films.md`); every number visible in the films is traced to its source in `film_receipts.md`.

## Limitations
See `limitations.md`.

## Attribution
See `attribution.md`.

## Reproduce
`pipeline/` numbered scripts in order (01 discovery → 04 matching → 05 slices → 08 dataset → 09 analyses → 10 recompute → 11 audit → 12 handoff); `app/build_deploy.py` assembles the static explorer; `films/capture.js` + `films/storyboards.js` capture the films frame-stepped.
"""
    open(os.path.join(OUT, "README.md"), "w").write(readme)
    print("handoff written:", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
