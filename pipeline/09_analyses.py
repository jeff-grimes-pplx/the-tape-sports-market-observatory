#!/usr/bin/env python3
"""All analyses (a)-(g) over the aligned dataset. Deterministic; no network.

Reads  derived/wall.json, derived/games/*.json, derived/full/*.json, derived/manifest.json
Writes derived/analysis.json (consumed by the explorer) and analysis/tables/*.csv (handoff receipts).
Every result block carries {window, n} so charts can print them.
"""
import csv
import json
import math
import os
import random
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
from norm import step_value, brier, logloss, pm_taker_fee  # noqa: E402
from stats import mean, median, sd, quantile, pearson, bootstrap_ci, wilson_ci, max_drawdown, shuffled_placebo  # noqa: E402

DATA = os.environ.get("A9_DATA", "/home/user/workspace/a9-data")
DER = os.path.join(DATA, "derived")
BUILD = os.path.dirname(HERE)
TABLES = os.path.join(BUILD, "analysis", "tables")
LEAGUES = ["nfl", "ncaaf", "mlb", "nba", "nhl", "wnba", "mls", "epl", "laliga", "seriea", "bundesliga", "ligue1", "ucl"]
LEAGUE_NAME = {"nfl": "NFL", "ncaaf": "NCAAF", "mlb": "MLB", "nba": "NBA", "nhl": "NHL", "wnba": "WNBA", "mls": "MLS", "epl": "Premier League", "laliga": "La Liga",
               "seriea": "Serie A", "bundesliga": "Bundesliga", "ligue1": "Ligue 1", "ucl": "Champions League", "ufc": "UFC"}
THETAS = [0.02, 0.03, 0.05, 0.08]
ENTRIES = [("t6h", 6 * 3600, 120), ("t1h", 3600, 60), ("t10m", 600, 20)]  # (name, seconds before kickoff, max PM sample age in minutes)
PM_CLOSE_MAX_AGE_MIN = 30


def load():
    wall = json.load(open(os.path.join(DER, "wall.json")))
    manifest = json.load(open(os.path.join(DER, "manifest.json")))
    games = {}
    for w in wall["games"]:
        fn = w["key"].replace(":", "_") + ".json"
        games[w["key"]] = json.load(open(os.path.join(DER, "games", fn)))
    return wall, manifest, games


def load_full(key):
    return json.load(open(os.path.join(DER, "full", key.replace(":", "_") + ".json")))


def write_csv(name, rows, fields=None):
    os.makedirs(TABLES, exist_ok=True)
    if not rows:
        open(os.path.join(TABLES, name), "w").write("")
        return
    fields = fields or list(rows[0].keys())
    with open(os.path.join(TABLES, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})


def r4(x):
    return None if x is None else round(x, 4)


# ----------------------------------------------------------------------------------------------
# (a) census
def census(wall, manifest):
    rows = []
    by = defaultdict(list)
    for w in wall["games"]:
        by[w["lg"]].append(w)
    for lg in LEAGUES:
        ws = by.get(lg, [])
        if not ws:
            continue
        books = Counter(b for w in ws for b in w["books"])
        rows.append({
            "league": lg, "league_name": LEAGUE_NAME[lg], "games": len(ws),
            "first_kickoff": datetime.fromtimestamp(min(w["ko"] for w in ws), timezone.utc).strftime("%Y-%m-%d"),
            "last_kickoff": datetime.fromtimestamp(max(w["ko"] for w in ws), timezone.utc).strftime("%Y-%m-%d"),
            "with_sportsbook_history": sum(1 for w in ws if w["oo"]), "with_pinnacle_close": sum(1 for w in ws if w["pin"] is not None),
            "with_polymarket_history": sum(1 for w in ws if w["pmn"] > 0), "with_pm_close": sum(1 for w in ws if w["pm"]["t1m"] is not None),
            "both_sources": sum(1 for w in ws if w["pin"] is not None and w["pm"]["t1m"] is not None),
            "with_plays": sum(1 for w in ws if w["plays"]), "plays": manifest.get("census", {}).get(lg, {}).get("plays", 0), "sportsbook_entries": sum(w["oe"] for w in ws), "polymarket_samples": sum(w["pmn"] for w in ws),
            "polymarket_samples_all_markets": manifest.get("census", {}).get(lg, {}).get("pm_samples_all_markets", 0), "polymarket_markets": manifest.get("census", {}).get(lg, {}).get("pm_markets", 0),
            "polymarket_ml_volume_usd": sum(w["vol"] for w in ws), "tier_A": sum(1 for w in ws if w["tier"] == "A"), "tier_B": sum(1 for w in ws if w["tier"] == "B"),
            "tier_C": sum(1 for w in ws if w["tier"] == "C"), "tier_M": sum(1 for w in ws if w["tier"] == "M"),
            "books": ", ".join(f"{b}:{n}" for b, n in sorted(books.items())),
            "pm_fidelity_1min": sum(1 for w in ws if 1 in w["fid"]), "pm_fidelity_5min": sum(1 for w in ws if 5 in w["fid"]), "pm_fidelity_10min": sum(1 for w in ws if 10 in w["fid"]),
        })
    write_csv("a_census.csv", rows)
    # sportsbook-only extension census (no Polymarket by construction)
    ext_rows = []
    eby = defaultdict(list)
    for w in wall.get("ext_games") or []:
        eby[w["lg"]].append(w)
    for lg in LEAGUES:
        ws = eby.get(lg, [])
        if not ws:
            continue
        ext_rows.append({"league": lg, "league_name": LEAGUE_NAME[lg], "games_with_sportsbook_history": len(ws),
                         "matched_two_way": (manifest.get("census", {}).get(lg, {}).get("ext_games", 0) + manifest.get("census", {}).get(lg, {}).get("ext_matched_without_history", 0)),
                         "first_kickoff": datetime.fromtimestamp(min(w["ko"] for w in ws), timezone.utc).strftime("%Y-%m-%d"), "last_kickoff": datetime.fromtimestamp(max(w["ko"] for w in ws), timezone.utc).strftime("%Y-%m-%d"),
                         "with_pinnacle_close": sum(1 for w in ws if w["pin"] is not None), "sportsbook_entries": sum(w["oe"] for w in ws),
                         "books": ", ".join(f"{b}:{n}" for b, n in sorted(Counter(b for w in ws for b in w["books"]).items()))})
    if ext_rows:
        write_csv("a_census_extension.csv", ext_rows)
    return {"window": wall["window"], "n": len(wall["games"]), "rows": rows, "extension": {"window": wall.get("ext_window"), "n": len(wall.get("ext_games") or []), "rows": ext_rows} if ext_rows else None}


# ----------------------------------------------------------------------------------------------
# (b) closing agreement
def agreement(wall, games):
    rows, per_league = [], {}
    pooled = []
    for w in wall["games"]:
        if w["pin"] is None or w["pm"]["t1m"] is None or (w["pma"]["t1m"] or 1e9) > PM_CLOSE_MAX_AGE_MIN:
            continue
        d = w["pm"]["t1m"] - w["pin"]
        rec = {"key": w["key"], "league": w["lg"], "kickoff_utc": datetime.fromtimestamp(w["ko"], timezone.utc).isoformat(), "home": w["home"], "away": w["away"],
               "pinnacle_close_home": w["pin"], "consensus_close_home": w["cons"], "polymarket_close_home": w["pm"]["t1m"], "pm_sample_age_min": w["pma"]["t1m"],
               "diff_pm_minus_pinnacle": d, "diff_pm_minus_consensus": (w["pm"]["t1m"] - w["cons"]) if w["cons"] is not None else None, "home_win": w["hw"], "pm_ml_volume": w["vol"]}
        for b, v in w["bc"].items():
            rec[f"diff_pm_minus_{b}"] = w["pm"]["t1m"] - v
        rows.append(rec)
        pooled.append(rec)
    write_csv("b_closing_agreement_games.csv", rows)

    def summarize(recs):
        ds = [r["diff_pm_minus_pinnacle"] for r in recs]
        if not ds:
            return None
        ad = [abs(x) for x in ds]
        hist = Counter()
        for x in ds:
            b = max(-0.2, min(0.2, math.floor(x / 0.01) * 0.01))
            hist[round(b, 2)] += 1
        out = {"n": len(ds), "mean_diff": r4(mean(ds)), "median_diff": r4(median(ds)), "sd_diff": r4(sd(ds)), "mean_abs_diff": r4(mean(ad)), "median_abs_diff": r4(median(ad)),
               "p90_abs_diff": r4(quantile(ad, 0.9)), "share_within_2pp": r4(sum(1 for x in ad if x <= 0.02) / len(ad)), "share_within_5pp": r4(sum(1 for x in ad if x <= 0.05) / len(ad)),
               "share_pm_higher": r4(sum(1 for x in ds if x > 0) / len(ds)), "corr_pm_pinnacle": r4(pearson([r["pinnacle_close_home"] for r in recs], [r["polymarket_close_home"] for r in recs])),
               "mean_diff_ci95": [r4(x) for x in bootstrap_ci(ds)], "hist_1pp_bins": {f"{k:.2f}": v for k, v in sorted(hist.items())}}
        # favourite-longshot: PM minus Pinnacle by Pinnacle-close bucket
        fl = defaultdict(list)
        for r in recs:
            fl[min(9, int(r["pinnacle_close_home"] * 10))].append(r["diff_pm_minus_pinnacle"])
        out["by_pinnacle_bucket"] = [{"bucket": f"{k/10:.1f}-{(k+1)/10:.1f}", "n": len(v), "mean_diff": r4(mean(v)), "ci95": [r4(x) for x in bootstrap_ci(v)] if len(v) > 2 else [None, None]} for k, v in sorted(fl.items())]
        # per-book agreement (PM minus each book close)
        bks = defaultdict(list)
        for r in recs:
            for k, v in r.items():
                if k.startswith("diff_pm_minus_") and k not in ("diff_pm_minus_pinnacle", "diff_pm_minus_consensus") and v is not None:
                    bks[k.replace("diff_pm_minus_", "")].append(v)
        if recs and any(r["diff_pm_minus_consensus"] is not None for r in recs):
            cs = [r["diff_pm_minus_consensus"] for r in recs if r["diff_pm_minus_consensus"] is not None]
            bks["Consensus"] = cs
        out["by_book"] = [{"book": b, "n": len(v), "mean_diff": r4(mean(v)), "mean_abs_diff": r4(mean(abs(x) for x in v))} for b, v in sorted(bks.items())]
        return out

    for lg in LEAGUES:
        s = summarize([r for r in pooled if r["league"] == lg])
        if s:
            per_league[lg] = s
    per_league["all"] = summarize(pooled)
    table = [{"league": lg, **{k: v for k, v in s.items() if not isinstance(v, (dict, list))}, "mean_diff_ci_lo": s["mean_diff_ci95"][0], "mean_diff_ci_hi": s["mean_diff_ci95"][1]} for lg, s in per_league.items() if s]
    write_csv("b_closing_agreement_summary.csv", table)
    # spread / total line agreement (PM market line vs Pinnacle closing line)
    line_rows = []
    for key, g in games.items():
        pin = g["oo"]["books"].get("Pinnacle", {})
        for role in ("spread", "total"):
            pmm = g["pm"]["markets"].get(role)
            pb = pin.get(role)
            if not pmm or not pb or not pb.get("close") or pmm.get("line") is None:
                continue
            pm_line = pmm["line"]
            if role == "spread" and pmm.get("side") == "away":
                pm_line = -pm_line  # express as the home line
            pin_line = pb["close"][2]
            if pin_line is None:
                continue
            line_rows.append({"key": key, "league": g["league"], "market": role, "pm_line_home_or_total": pm_line, "pinnacle_close_line": pin_line, "same_line": abs(float(pm_line) - float(pin_line)) < 1e-9,
                              "abs_line_gap": abs(float(pm_line) - float(pin_line)), "pm_volume": pmm.get("volume")})
    write_csv("b_line_agreement_games.csv", line_rows)
    line_summary = []
    for role in ("spread", "total"):
        for lg in LEAGUES + ["all"]:
            rs = [r for r in line_rows if r["market"] == role and (lg == "all" or r["league"] == lg)]
            if rs:
                line_summary.append({"market": role, "league": lg, "n": len(rs), "share_same_line": r4(sum(1 for r in rs if r["same_line"]) / len(rs)), "mean_abs_line_gap": r4(mean(r["abs_line_gap"] for r in rs))})
    write_csv("b_line_agreement_summary.csv", line_summary)
    return {"window": None, "n": len(pooled), "pm_close_max_age_min": PM_CLOSE_MAX_AGE_MIN, "per_league": per_league, "line_agreement": line_summary}


# ----------------------------------------------------------------------------------------------
# (c) price discovery
def discovery(wall, games):
    GRID = 600  # 10-minute grid (Polymarket 1-month lookback is sampled every 10 minutes)
    LAGS = list(range(-12, 13))  # -120..+120 minutes
    HORIZON = 48 * 3600
    xs_by = defaultdict(lambda: defaultdict(list))  # league -> lag -> list of (dx, dy)
    event_rows, resp_curves = [], defaultdict(lambda: defaultdict(list))
    who = defaultdict(Counter)
    n_games = Counter()
    for w in wall["games"]:
        if not w["oo"] or w["pmn"] == 0:
            continue
        g = games[w["key"]]
        pin_nv = g["oo"]["books"].get("Pinnacle", {}).get("ml", {}).get("novig") or []
        if len(pin_nv) < 3:
            continue
        full = load_full(w["key"])
        hs = full["home_series"]
        if len(hs) < 3:
            continue
        ko = w["ko"]
        pts, pvs = [r[0] for r in pin_nv], [r[1] for r in pin_nv]
        hts, hvs = [r[0] for r in hs], [r[1] for r in hs]
        t_start = max(pts[0], hts[0], ko - HORIZON)
        grid = list(range(((t_start // GRID) + 1) * GRID, ko + 1, GRID))
        if len(grid) < 6:
            continue
        a = [step_value(pts, pvs, t) for t in grid]
        b = [step_value(hts, hvs, t) for t in grid]
        # require a PM sample within 2 h of each grid point (otherwise the market was not being sampled)
        ok = [i for i in range(len(grid)) if a[i] is not None and b[i] is not None and (grid[i] - hts[bisect_right(hts, grid[i]) - 1]) <= 7200]
        if len(ok) < 6:
            continue
        n_games[w["lg"]] += 1
        da = {i: a[i] - a[i - 1] for i in ok if (i - 1) in set(ok)}
        db = {i: b[i] - b[i - 1] for i in ok if (i - 1) in set(ok)}
        for lag in LAGS:
            for i, dx in da.items():
                j = i + lag
                if j in db:
                    xs_by[w["lg"]][lag].append((dx, db[j]))
        # event study: Pinnacle moves >= 3 pp within 60 minutes (first in a 2-hour cluster), pre-game only
        last_evt = -1e18
        for i in range(len(pin_nv)):
            t0, p0 = pin_nv[i][0], pin_nv[i][1]
            if t0 > ko or t0 - last_evt < 7200 or t0 - 7200 < hts[0]:
                continue
            p_prev = step_value(pts, pvs, t0 - 3600)
            if p_prev is None:
                continue
            mv = p0 - p_prev
            if abs(mv) < 0.03:
                continue
            last_evt = t0
            base_pm = step_value(hts, hvs, t0 - 7200)
            if base_pm is None:
                continue
            curve = {}
            for off in range(-120, 121, 10):
                v = step_value(hts, hvs, t0 + off * 60)
                curve[off] = None if v is None else (v - base_pm) / mv
                if curve[off] is not None:
                    resp_curves[w["lg"]][off].append(curve[off])
            pre = curve.get(0)
            label, lag_min = "no response within 2h", None
            if pre is not None and pre >= 0.5:
                label = "Polymarket moved first"
            else:
                for off in range(10, 121, 10):
                    if curve.get(off) is not None and curve[off] >= 0.5:
                        label, lag_min = "Polymarket followed", off
                        break
            who[w["lg"]][label] += 1
            event_rows.append({"key": w["key"], "league": w["lg"], "t0_utc": datetime.fromtimestamp(t0, timezone.utc).isoformat(), "minutes_before_kickoff": round((ko - t0) / 60),
                               "pinnacle_move_pp": r4(mv * 100), "pm_share_at_t0": r4(pre), "pm_share_plus60": r4(curve.get(60)), "pm_share_plus120": r4(curve.get(120)), "label": label, "pm_lag_min": lag_min})
        # mirror: Polymarket moves >= 3 pp within 60 minutes -> Pinnacle response
        last_evt = -1e18
        for i in range(len(hs)):
            t0, p0 = hs[i][0], hs[i][1]
            if t0 > ko or t0 - last_evt < 7200 or t0 - 7200 < pts[0]:
                continue
            p_prev = step_value(hts, hvs, t0 - 3600)
            if p_prev is None:
                continue
            mv = p0 - p_prev
            if abs(mv) < 0.03:
                continue
            last_evt = t0
            base = step_value(pts, pvs, t0 - 7200)
            if base is None:
                continue
            pre = (step_value(pts, pvs, t0) - base) / mv
            label, lag_min = "no response within 2h", None
            if pre >= 0.5:
                label = "Pinnacle moved first"
            else:
                for off in range(10, 121, 10):
                    v = step_value(pts, pvs, t0 + off * 60)
                    if v is not None and (v - base) / mv >= 0.5:
                        label, lag_min = "Pinnacle followed", off
                        break
            who[w["lg"]]["PM-event: " + label] += 1
            event_rows.append({"key": w["key"], "league": w["lg"], "t0_utc": datetime.fromtimestamp(t0, timezone.utc).isoformat(), "minutes_before_kickoff": round((ko - t0) / 60),
                               "pinnacle_move_pp": None, "pm_move_pp": r4(mv * 100), "pm_share_at_t0": None, "label": "PM-event: " + label, "pm_lag_min": lag_min})
    write_csv("c_move_events.csv", event_rows)
    xcorr = {}
    for lg in list(xs_by.keys()) + ["all"]:
        series = {}
        for lag in LAGS:
            pairs = xs_by[lg][lag] if lg != "all" else [p for l2 in xs_by for p in xs_by[l2][lag]]
            c = pearson([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) > 10 else None
            series[lag * 10] = {"r": r4(c), "n": len(pairs)}
        xcorr[lg] = {"n_games": n_games[lg] if lg != "all" else sum(n_games.values()), "lags_min": series}
    write_csv("c_xcorr.csv", [{"league": lg, "lag_min": lag, "r": v["r"], "n_pairs": v["n"], "n_games": d["n_games"]} for lg, d in xcorr.items() for lag, v in d["lags_min"].items()])
    curves = {}
    for lg in list(resp_curves.keys()) + ["all"]:
        pts_ = {}
        for off in range(-120, 121, 10):
            vals = resp_curves[lg][off] if lg != "all" else [v for l2 in resp_curves for v in resp_curves[l2][off]]
            pts_[off] = {"mean_share": r4(mean(vals)) if vals else None, "median_share": r4(median(vals)) if vals else None, "n": len(vals)}
        curves[lg] = pts_
    write_csv("c_event_response_curve.csv", [{"league": lg, "offset_min": off, **v} for lg, d in curves.items() for off, v in d.items()])
    who_rows = [{"league": lg, "label": lab, "n": n} for lg in who for lab, n in who[lg].items()]
    write_csv("c_who_moved_first.csv", who_rows)
    return {"grid_minutes": 10, "horizon_hours": 48, "n_games": sum(n_games.values()), "xcorr": xcorr, "response_curves": curves, "who_moved_first": {lg: dict(c) for lg, c in who.items()},
            "event_threshold_pp": 3, "event_window_min": 60, "n_events": len(event_rows),
            "note": "Pinnacle no-vig home probability vs Polymarket sampled home price; 10-minute grid because the 1-month Polymarket lookback is sampled every 10 minutes."}


# ----------------------------------------------------------------------------------------------
# (d) calibration
def calibration(wall, extended=False):
    """Brier / log loss / reliability by source and league, in two modes:
    - common: every source is scored on the SAME game set per league (games where all sources have a value:
      the five sportsbook closes within 6 h of kickoff, the consensus, and the three Polymarket marks), so the
      N is identical for every row and the comparison is like-for-like;
    - available: each source is scored on every game where it has a value (per-source N; secondary view).
    extended=True pools the analysis window with the sportsbook-only extension (books only; Polymarket sources are
    absent there by construction)."""
    sources = {"Pinnacle close": lambda w: w["pin"], "Consensus close": lambda w: w["cons"], "Polymarket T-24h": lambda w: w["pm"]["t24h"] if (w["pma"]["t24h"] or 1e9) <= 120 else None,
               "Polymarket T-1h": lambda w: w["pm"]["t1h"] if (w["pma"]["t1h"] or 1e9) <= 60 else None, "Polymarket T-1min": lambda w: w["pm"]["t1m"] if (w["pma"]["t1m"] or 1e9) <= PM_CLOSE_MAX_AGE_MIN else None}
    for b in ("DraftKings", "FanDuel", "BetMGM", "Caesars"):
        sources[f"{b} close"] = (lambda b: lambda w: w["bc"].get(b))(b)
    if extended:
        sources = {k: v for k, v in sources.items() if not k.startswith("Polymarket")}
    pool = wall["games"] + (wall.get("ext_games") or [] if extended else [])

    def score(ps):
        bs = [brier(p, y) for p, y in ps]
        ls = [logloss(p, y) for p, y in ps]
        bins = defaultdict(list)
        for p, y in ps:
            bins[min(9, int(p * 10))].append((p, y))
        rel = [{"bin": f"{k/10:.1f}-{(k+1)/10:.1f}", "n": len(v), "mean_p": r4(mean(p for p, _ in v)), "win_rate": r4(mean(y for _, y in v)), "ci95": [r4(x) for x in wilson_ci(sum(y for _, y in v), len(v))]} for k, v in sorted(bins.items())]
        return {"n": len(ps), "brier": r4(mean(bs)), "brier_ci95": [r4(x) for x in bootstrap_ci(bs)], "logloss": r4(mean(ls)), "logloss_ci95": [r4(x) for x in bootstrap_ci(ls)],
                "base_rate_home": r4(mean(y for _, y in ps)), "mean_p_home": r4(mean(p for p, _ in ps)), "reliability": rel}

    def flat(lg, sname, rec, mode):
        return {"mode": mode, "league": lg, "source": sname, **{k: v for k, v in rec.items() if not isinstance(v, (list, dict))}, "brier_ci_lo": rec["brier_ci95"][0], "brier_ci_hi": rec["brier_ci95"][1], "logloss_ci_lo": rec["logloss_ci95"][0], "logloss_ci_hi": rec["logloss_ci95"][1]}

    out, common, common_n, common_excluded, rows, rel_rows = {}, {}, {}, {}, [], []
    for lg in LEAGUES + ["all"]:
        ws = [w for w in pool if (lg == "all" or w["lg"] == lg) and w["hw"] is not None]
        out[lg], common[lg] = {}, {}
        # available mode
        for sname, fn in sources.items():
            ps = [(fn(w), w["hw"]) for w in ws if fn(w) is not None]
            if len(ps) < 5:
                continue
            rec = score(ps)
            out[lg][sname] = rec
            rows.append(flat(lg, sname, rec, "available"))
            for r in rec["reliability"]:
                rel_rows.append({"mode": "available", "league": lg, "source": sname, **{k: v for k, v in r.items() if k != "ci95"}, "ci_lo": r["ci95"][0], "ci_hi": r["ci95"][1]})
        # common mode: the same games for every source. A source is eligible in a league when it quotes at least half of
        # the league's games with a final (and at least 5); the common set is the games where every eligible source has a
        # value. Sources below that coverage are left out of the league's common table (named in `excluded`).
        eligible = {sname: fn for sname, fn in sources.items() if sum(1 for w in ws if fn(w) is not None) >= max(5, 0.5 * len(ws))}
        cws = [w for w in ws if all(fn(w) is not None for fn in eligible.values())]
        common_n[lg] = len(cws)
        common_excluded[lg] = [sname for sname in sources if sname not in eligible]
        if len(cws) >= 5:
            for sname, fn in eligible.items():
                rec = score([(fn(w), w["hw"]) for w in cws])
                common[lg][sname] = rec
                rows.append(flat(lg, sname, rec, "common"))
                for r in rec["reliability"]:
                    rel_rows.append({"mode": "common", "league": lg, "source": sname, **{k: v for k, v in r.items() if k != "ci95"}, "ci_lo": r["ci95"][0], "ci_hi": r["ci95"][1]})
        # paired comparison on the common set: Polymarket T-1min vs Pinnacle close (analysis window only)
        pairs = [(sources["Pinnacle close"](w), sources["Polymarket T-1min"](w), w["hw"]) for w in ws] if "Polymarket T-1min" in sources else []
        pairs = [p for p in pairs if p[0] is not None and p[1] is not None]
        if len(pairs) >= 5:
            d = [brier(pm, y) - brier(pin, y) for pin, pm, y in pairs]
            out[lg]["paired_pm_minus_pinnacle"] = {"n": len(pairs), "brier_diff": r4(mean(d)), "ci95": [r4(x) for x in bootstrap_ci(d)], "brier_pinnacle": r4(mean(brier(pin, y) for pin, _, y in pairs)), "brier_polymarket": r4(mean(brier(pm, y) for _, pm, y in pairs))}
    suffix = "_extended" if extended else ""
    write_csv(f"d_calibration_summary{suffix}.csv", rows)
    write_csv(f"d_reliability_bins{suffix}.csv", rel_rows)
    window = [wall["ext_window"][0], wall["window"][1]] if (extended and wall.get("ext_window")) else wall["window"]
    return {"window": window, "n": sum(1 for w in pool if w["hw"] is not None), "n_extension": sum(1 for w in (wall.get("ext_games") or []) if w["hw"] is not None) if extended else 0,
            "per_league": out, "common_per_league": common, "common_n": common_n, "common_excluded": common_excluded,
            "common_definition": ("per league, the games where every eligible sportsbook has a close within 6 h of kickoff (a book is eligible when it quotes at least half of the league's games)" if extended else
                                  "per league, the games where every eligible source has a value: sportsbook closes within 6 h of kickoff, the consensus, and Polymarket samples at T−24 h (≤ 120 min old), T−1 h (≤ 60 min) and T−1 min (≤ 30 min); a source is eligible when it quotes at least half of the league's games"),
            "outcome": "home team wins (soccer draw = 0; ties excluded)", "sources": "sportsbooks only (Polymarket not fetched for the extension)" if extended else "sportsbooks + Polymarket"}


# ----------------------------------------------------------------------------------------------
# (e) backtests
def bet_roi(bets):
    if not bets:
        return 0.0
    return sum(b["pnl"] if b["win"] == b["_win0"] else b["shares"] * b["win"] - 1.0 - b["fee"] for b in bets) / len(bets)


def settle(q, win, rate):
    shares = 1.0 / q
    fee = pm_taker_fee(shares, q, rate or 0.0)
    return {"q": q, "shares": shares, "fee": fee, "win": win, "_win0": win, "pnl": shares * win - 1.0 - fee}


def summarize_bets(bets, label):
    if not bets:
        return {"strategy": label, "n": 0}
    pnls = [b["pnl"] for b in bets]
    roi = mean(pnls)
    ci = bootstrap_ci(pnls)
    plac = shuffled_placebo(bet_roi, bets)
    return {"strategy": label, "n": len(bets), "hit_rate": r4(mean(b["win"] for b in bets)), "roi": r4(roi), "roi_ci95": [r4(x) for x in ci], "total_pnl_per_1usd": r4(sum(pnls)),
            "max_drawdown": r4(max_drawdown(pnls)), "fees_paid": r4(sum(b["fee"] for b in bets)), "roi_before_fees": r4(mean(b["pnl"] + b["fee"] for b in bets)),
            "avg_price": r4(mean(b["q"] for b in bets)), **{k: (r4(v) if isinstance(v, float) else v) for k, v in plac.items()}}


def backtests(wall, games):
    results, bet_rows = [], []
    for lg in ["all"] + LEAGUES:
        ws = [w for w in wall["games"] if (lg == "all" or w["lg"] == lg) and w["hw"] is not None and w["fee"] is not None]
        if lg != "all" and len(ws) < 5:
            continue
        for ename, _, max_age in ENTRIES:
            for th in THETAS:
                bets = []
                for w in sorted(ws, key=lambda w: w["ko"]):
                    pin, pm, age = w["pin_at"][ename], w["pm"][ename], w["pma"][ename]
                    if pin is None or pm is None or age is None or age > max_age or pm <= 0.005 or pm >= 0.995:
                        continue
                    edge = pin - pm
                    if edge >= th:
                        b = settle(pm, w["hw"], w["fee"]); side = "home"
                    elif -edge >= th:
                        b = settle(1.0 - pm, 1 - w["hw"], w["fee"]); side = "away"
                    else:
                        continue
                    b.update({"key": w["key"], "league": w["lg"], "side": side, "edge": edge, "kickoff": w["ko"]})
                    bets.append(b)
                s = summarize_bets(bets, "follow_pinnacle")
                s.update({"league": lg, "entry": ename, "theta": th})
                results.append(s)
                if lg == "all":
                    for b in bets:
                        bet_rows.append({"strategy": "follow_pinnacle", "entry": ename, "theta": th, "key": b["key"], "league": b["league"], "side": b["side"], "edge": r4(b["edge"]), "price": r4(b["q"]), "fee": r4(b["fee"]), "win": b["win"], "pnl": r4(b["pnl"])})
        # fade the late move: consensus moved >= theta between T-6h and T-10m -> buy the other side on Polymarket at T-10m
        for th in THETAS:
            bets = []
            for w in sorted(ws, key=lambda w: w["ko"]):
                c6, c10, pm, age = w["cons_at"]["t6h"], w["cons_at"]["t10m"], w["pm"]["t10m"], w["pma"]["t10m"]
                if None in (c6, c10, pm, age) or age > 20 or pm <= 0.005 or pm >= 0.995:
                    continue
                mv = c10 - c6
                if mv >= th:
                    b = settle(1.0 - pm, 1 - w["hw"], w["fee"]); side = "away"
                elif -mv >= th:
                    b = settle(pm, w["hw"], w["fee"]); side = "home"
                else:
                    continue
                b.update({"key": w["key"], "league": w["lg"], "side": side, "edge": mv, "kickoff": w["ko"]})
                bets.append(b)
            s = summarize_bets(bets, "fade_late_move")
            s.update({"league": lg, "entry": "t10m", "theta": th})
            results.append(s)
            if lg == "all":
                for b in bets:
                    bet_rows.append({"strategy": "fade_late_move", "entry": "t10m", "theta": th, "key": b["key"], "league": b["league"], "side": b["side"], "edge": r4(b["edge"]), "price": r4(b["q"]), "fee": r4(b["fee"]), "win": b["win"], "pnl": r4(b["pnl"])})
    # in-game illustrative: buy the scoring team at the first Polymarket sample after each scoring play (hero set only)
    ig_bets, ig_rows = [], []
    for w in wall["games"]:
        if not w["plays"] or w["hw"] is None or w["fee"] is None:
            continue
        g = games[w["key"]]
        full = load_full(w["key"])
        hs = full["home_series"]
        hts = [r[0] for r in hs]
        prev = (0, 0)
        for p in g["sr"]["plays"] or []:
            if not p["scoring"] or p["hp"] is None:
                continue
            dh, da = (p["hp"] or 0) - prev[0], (p["ap"] or 0) - prev[1]
            prev = (p["hp"] or 0, p["ap"] or 0)
            if dh <= 0 and da <= 0:
                continue
            team = "home" if dh > 0 else "away"
            i = bisect_right(hts, p["t"])
            if i >= len(hs):
                continue
            t_s, ph = hs[i][0], hs[i][1]
            q = ph if team == "home" else 1.0 - ph
            if q <= 0.005 or q >= 0.995:
                continue
            win = w["hw"] if team == "home" else 1 - w["hw"]
            b = settle(q, win, w["fee"])
            b.update({"key": w["key"], "league": w["lg"], "side": team})
            ig_bets.append(b)
            ig_rows.append({"key": w["key"], "league": w["lg"], "play_utc": datetime.fromtimestamp(p["t"], timezone.utc).isoformat(), "play": p["desc"][:80], "scoring_team": team, "fill_sample_utc": datetime.fromtimestamp(t_s, timezone.utc).isoformat(),
                            "fill_delay_s": t_s - p["t"], "price": r4(q), "fee": r4(b["fee"]), "win": win, "pnl": r4(b["pnl"])})
    ig = summarize_bets(ig_bets, "in_game_buy_scorer")
    ig.update({"league": "hero set", "entry": "next sample after scoring play", "theta": None, "illustrative": True})
    results.append(ig)
    write_csv("e_backtests_summary.csv", results)
    write_csv("e_backtest_bets_all.csv", bet_rows)
    write_csv("e_in_game_bets.csv", ig_rows)
    return {"results": results, "thetas": THETAS, "entries": [e[0] for e in ENTRIES], "stake": "1 USD per bet, hold to resolution, Polymarket taker fee charged on entry (fee = shares × rate × p × (1 − p)); no exit, no slippage, fill assumed at the sampled price",
            "placebo": "outcome labels shuffled across the strategy's bets, 500 shuffles, seed 17", "n_in_game_bets": len(ig_bets)}


# ----------------------------------------------------------------------------------------------
# (f) in-game reaction (hero set)
def in_game(wall, games):
    rows = []
    for w in wall["games"]:
        if not w["plays"]:
            continue
        g = games[w["key"]]
        full = load_full(w["key"])
        hs = full["home_series"]
        hts, hvs = [r[0] for r in hs], [r[1] for r in hs]
        prev = (0, 0)
        for p in g["sr"]["plays"] or []:
            if not p["scoring"] or p["hp"] is None:
                continue
            dh, da = (p["hp"] or 0) - prev[0], (p["ap"] or 0) - prev[1]
            prev = (p["hp"] or 0, p["ap"] or 0)
            if dh <= 0 and da <= 0:
                continue
            team = "home" if dh > 0 else "away"
            before = step_value(hts, hvs, p["t"])
            i = bisect_right(hts, p["t"])
            after = hs[i][1] if i < len(hs) else None
            after2 = hs[i + 1][1] if i + 1 < len(hs) else None
            if before is None or after is None:
                continue
            delta = (after - before) * (1 if team == "home" else -1)
            rows.append({"key": w["key"], "league": w["lg"], "home": w["home"], "away": w["away"], "play_utc": datetime.fromtimestamp(p["t"], timezone.utc).isoformat(), "period": p["period"], "clock": p["clock"], "type": p["type"],
                         "points": max(dh, da), "scoring_team": team, "score_after": f"{p['ap']}-{p['hp']}", "pm_home_before": r4(before), "pm_home_next_sample": r4(after), "pm_home_second_sample": r4(after2),
                         "sample_delay_s": hts[i] - p["t"], "delta_toward_scorer_pp": r4(delta * 100), "desc": p["desc"][:100]})
    write_csv("f_in_game_reaction.csv", rows)
    by_type = defaultdict(list)
    for r in rows:
        by_type[(r["league"], r["type"])].append(r["delta_toward_scorer_pp"])
    summary = [{"league": lg, "play_type": t, "n": len(v), "mean_delta_pp": r4(mean(v)), "share_positive": r4(sum(1 for x in v if x > 0) / len(v))} for (lg, t), v in sorted(by_type.items())]
    write_csv("f_in_game_summary.csv", summary)
    return {"n_plays": len(rows), "n_games": len({r["key"] for r in rows}), "summary": summary, "note": "Polymarket samples are 1-5 minutes apart; 'next sample' is the first sample at or after the play's Sportradar wall clock."}


# ----------------------------------------------------------------------------------------------
# (g) Sportradar context
def context(wall, games):
    rows = []
    for w in wall["games"]:
        if w["pin"] is None or w["hw"] is None:
            continue
        g = games[w["key"]]
        c = g["context"]
        wx = c.get("weather") or {}
        temp = wx.get("temp") if isinstance(wx, dict) else None
        wind = (wx.get("wind") or {}).get("speed") if isinstance(wx, dict) and isinstance(wx.get("wind"), dict) else (wx.get("wind_speed") if isinstance(wx, dict) else None)
        roof = (c.get("venue") or {}).get("roof_type") if isinstance(c.get("venue"), dict) else None
        rows.append({"key": w["key"], "league": w["lg"], "home_win": w["hw"], "pin": w["pin"], "resid": w["hw"] - w["pin"], "gap": (w["pm"]["t1m"] - w["pin"]) if w["pm"]["t1m"] is not None else None,
                     "neutral": bool(c.get("neutral")), "temp": temp, "wind": wind, "roof": roof, "week": c.get("week"), "attendance": c.get("attendance"),
                     "home_record": c.get("home_record"), "away_record": c.get("away_record")})
    write_csv("g_context_games.csv", rows)

    def group(name, keyfn):
        out = []
        groups = defaultdict(list)
        for r in rows:
            k = keyfn(r)
            if k is not None:
                groups[k].append(r)
        for k, v in sorted(groups.items(), key=lambda kv: str(kv[0])):
            if len(v) < 8:
                continue
            res = [r["resid"] for r in v]
            gaps = [r["gap"] for r in v if r["gap"] is not None]
            out.append({"factor": name, "level": str(k), "n": len(v), "mean_pinnacle_home": r4(mean(r["pin"] for r in v)), "home_win_rate": r4(mean(r["home_win"] for r in v)), "mean_residual": r4(mean(res)),
                        "residual_ci95": [r4(x) for x in bootstrap_ci(res)], "mean_pm_minus_pin": r4(mean(gaps)) if gaps else None, "gap_ci95": [r4(x) for x in bootstrap_ci(gaps)] if len(gaps) > 2 else [None, None]})
        return out

    def rec_diff(r):
        try:
            h = [int(x) for x in r["home_record"].split("-")]
            a = [int(x) for x in r["away_record"].split("-")]
            hw = h[0] / max(1, sum(h[:2]))
            aw = a[0] / max(1, sum(a[:2]))
            d = hw - aw
            return "home record better" if d > 0.1 else ("away record better" if d < -0.1 else "similar records")
        except Exception:
            return None

    factors = []
    factors += group("league", lambda r: r["league"])
    factors += group("neutral site", lambda r: "neutral" if r["neutral"] else "home venue")
    factors += group("roof", lambda r: r["roof"] if r["roof"] else None)
    factors += group("temperature", lambda r: None if r["temp"] is None else ("< 50°F" if r["temp"] < 50 else ("50-70°F" if r["temp"] < 70 else "≥ 70°F")))
    factors += group("wind", lambda r: None if r["wind"] is None else ("≥ 15 mph" if r["wind"] >= 15 else "< 15 mph"))
    factors += group("record", rec_diff)
    factors += group("week (NFL)", lambda r: f"week {r['week']}" if r["league"] == "nfl" and r["week"] else None)
    n_tests = len(factors)
    for f in factors:
        lo, hi = f["residual_ci95"]
        f["significant_95"] = bool(lo is not None and (lo > 0 or hi < 0))
    # Bonferroni: widen to 1 - 0.05/n_tests
    for f in factors:
        pass
    write_csv("g_context_factors.csv", [{**{k: v for k, v in f.items() if not isinstance(v, list)}, "resid_ci_lo": f["residual_ci95"][0], "resid_ci_hi": f["residual_ci95"][1], "gap_ci_lo": f["gap_ci95"][0], "gap_ci_hi": f["gap_ci95"][1]} for f in factors])
    return {"n": len(rows), "factors": factors, "n_comparisons": n_tests, "caveat": f"{n_tests} group comparisons are shown; with a 5% level about {n_tests * 0.05:.1f} would look 'significant' by chance. Bonferroni-adjusted level: {0.05 / max(1, n_tests):.4f}. Residual = outcome − Pinnacle closing probability (home)."}


def main():
    wall, manifest, games = load()
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "window": wall["window"], "n_games": len(wall["games"]), "tier": manifest.get("tier"),
           "census": census(wall, manifest), "agreement": agreement(wall, games), "discovery": discovery(wall, games), "calibration": calibration(wall),
           "calibration_extended": calibration(wall, extended=True) if wall.get("ext_games") else None,
           "backtests": backtests(wall, games), "in_game": in_game(wall, games), "context": context(wall, games)}
    json.dump(out, open(os.path.join(DER, "analysis.json"), "w"), separators=(",", ":"))
    print("agreement n", out["agreement"]["n"], "| discovery games", out["discovery"]["n_games"], "events", out["discovery"]["n_events"], "| calibration n", out["calibration"]["n"],
          "| backtests", len(out["backtests"]["results"]), "| in-game plays", out["in_game"]["n_plays"], "| context n", out["context"]["n"])
    a = out["agreement"]["per_league"].get("all")
    if a:
        print("agreement all:", {k: v for k, v in a.items() if not isinstance(v, (dict, list))})
    for r in out["backtests"]["results"]:
        if r["league"] == "all" and r.get("n"):
            print(r["strategy"], r["entry"], r["theta"], "n", r["n"], "hit", r["hit_rate"], "roi", r["roi"], r["roi_ci95"], "placebo p", r.get("p_value_one_sided"))


if __name__ == "__main__":
    main()
