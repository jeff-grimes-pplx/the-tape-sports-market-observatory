#!/usr/bin/env python3
"""Independent recomputation of the headline per-game quantities for 20 random games.

Deliberately does NOT import lib/norm.py or lib/stats.py: it re-reads the raw vendor cache files and
re-implements the stated method from scratch (American odds -> implied -> multiplicative no-vig, step
functions, closing = last entry at or before kickoff, Polymarket last sample at or before T, finest
fidelity wins on identical timestamps). Compares against derived/games/<key>.json to 1e-9.
"""
import glob
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone
from fractions import Fraction

DATA = os.environ.get("A9_DATA", "/home/user/workspace/a9-data")
DER = os.path.join(DATA, "derived")
BUILD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOL = 1e-9
SEED = 2026
N = 20


def implied(odds):
    o = Fraction(str(odds))
    return Fraction(100) / (o + 100) if o > 0 else (-o) / ((-o) + 100)


def last_at_or_before(entries, t):
    """entries sorted by time; returns the entry with the largest time <= t (linear scan on purpose)."""
    best = None
    for e in entries:
        if e[0] <= t:
            best = e
        else:
            break
    return best


def load_raw_oo(fixture_id):
    hits = []
    for f in glob.glob(os.path.join(DATA, "cache", "opticodds", "*.json")):
        r = json.load(open(f))
        if r["args"]["path"] == "/fixtures/odds/historical" and r["args"]["params"].get("fixture_id") == fixture_id and r.get("ok") and not r["args"]["params"].get("purpose"):
            hits.append(r)
    # same selection rule as the builder: the response with the most odds lines
    hits.sort(key=lambda r: -len(r["data"]["data"]["data"][0]["odds"]))
    return hits[0]["data"]["data"]["data"][0] if hits else None


_PM_INDEX = None


def load_raw_pm(token):
    global _PM_INDEX
    if _PM_INDEX is None:
        _PM_INDEX = {}
        for f in glob.glob(os.path.join(DATA, "cache", "polymarket", "*.json")):
            r = json.load(open(f))
            p = r["args"]["params"]
            if r["args"]["path"] == "/prices-history" and r.get("ok"):
                hist = r["data"].get("data", r["data"]).get("history", [])
                _PM_INDEX.setdefault(p.get("market"), []).append((p["fidelity"], hist))
    return _PM_INDEX.get(token, [])


def pm_series(token):
    samples = {}
    for fid, hist in load_raw_pm(token):
        for h in hist:
            t = int(h["t"])
            if t not in samples or fid < samples[t][1]:
                samples[t] = (float(h["p"]), fid)
    return sorted((t, v[0]) for t, v in samples.items())


def normalize(s):
    import unicodedata, re
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("&", " and ").replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def main():
    wall = json.load(open(os.path.join(DER, "wall.json")))["games"]
    eligible = [w for w in wall if w["pin"] is not None and w["pm"]["t1m"] is not None]
    rng = random.Random(SEED)
    sample = rng.sample(eligible, min(N, len(eligible)))
    report, worst = [], {}
    all_ok = True
    for w in sample:
        g = json.load(open(os.path.join(DER, "games", w["key"].replace(":", "_") + ".json")))
        ko = g["kickoff"]
        home_names = {normalize(x) for x in (g["home"]["name"], g["home"]["abbr"], g["home"]["sr_alias"]) if x}
        away_names = {normalize(x) for x in (g["away"]["name"], g["away"]["abbr"], g["away"]["sr_alias"]) if x}
        fx = load_raw_oo(g["match"]["oo_fixture_id"])
        # OpticOdds names its own competitors in the raw response (home_competitors / away_competitors + team_id on each
        # odds line); use them in the vendor's orientation, swapped when the audited score cross-check found the vendor's
        # home/away label flipped relative to Sportradar (g.context.oo_flipped). Team identity, not label, decides the side.
        oo_home_ids = {c["id"] for c in fx.get("home_competitors") or []} | {normalize(c["name"]) for c in fx.get("home_competitors") or []} | {normalize(fx.get("home_team_display") or "")}
        oo_away_ids = {c["id"] for c in fx.get("away_competitors") or []} | {normalize(c["name"]) for c in fx.get("away_competitors") or []} | {normalize(fx.get("away_team_display") or "")}
        if g["context"].get("oo_flipped"):
            oo_home_ids, oo_away_ids = oo_away_ids, oo_home_ids
        def side_of(o):
            sel = normalize(o.get("selection") or o["name"])
            if sel in home_names or o.get("team_id") in oo_home_ids or sel in oo_home_ids:
                return "home"
            if sel in away_names or o.get("team_id") in oo_away_ids or sel in oo_away_ids:
                return "away"
            if (o.get("normalized_selection") or "").lower() in ("draw", "tie"):
                return "draw"
            return None
        checks = {}
        # --- sportsbook closes ---
        closes = {}
        for book in {o["sportsbook"] for o in fx["odds"]}:
            sides = {}
            for o in fx["odds"]:
                if o["sportsbook"] != book or o["market"].lower() != "moneyline":
                    continue
                side = side_of(o)
                if side is None:
                    continue
                ents = sorted((int(e["timestamp"]), e["price"]) for e in o["entries"] if e.get("price") is not None)
                sides[side] = ents
            if "home" not in sides or "away" not in sides:
                continue
            # closing state: each side's last entry at or before kickoff
            cur = {s: last_at_or_before(ents, ko) for s, ents in sides.items()}
            if any(v is None for v in cur.values()):
                continue
            t_close = max(v[0] for v in cur.values())
            imp = {s: implied(v[1]) for s, v in cur.items()}
            tot = sum(imp.values())
            closes[book] = (t_close, float(imp["home"] / tot))
        pin_t, pin_p = closes.get("Pinnacle", (None, None))
        checks["pinnacle_close"] = (pin_p if pin_t is not None and ko - pin_t <= 6 * 3600 else None, g["derived"]["pinnacle_close"])
        within = [p for (t, p) in closes.values() if ko - t <= 6 * 3600]
        checks["consensus_close"] = (sum(within) / len(within) if within else None, g["derived"]["consensus_close"])
        # Pinnacle at T-6h / T-1h / T-10m: state of the step function (each side held) at that instant
        pin_sides = {}
        for o in fx["odds"]:
            if o["sportsbook"] == "Pinnacle" and o["market"].lower() == "moneyline":
                side = side_of(o)
                if side in ("home", "away", "draw"):  # soccer moneylines are three-way: the draw is part of the no-vig sum
                    pin_sides[side] = sorted((int(e["timestamp"]), e["price"]) for e in o["entries"] if e.get("price") is not None)
        for name, dt in (("t6h", 21600), ("t1h", 3600), ("t10m", 600)):
            cur = {s: last_at_or_before(ents, ko - dt) for s, ents in pin_sides.items()}
            if all(cur.values()) and "home" in cur and "away" in cur:
                imp = {s: implied(v[1]) for s, v in cur.items()}
                val = float(imp["home"] / sum(imp.values()))
            else:
                val = None
            checks[f"pinnacle_at_{name}"] = (val, g["derived"]["pin_at"][name])
        # --- Polymarket ---
        mk = g["pm"]["markets"].get("ml_home") or g["pm"]["markets"].get("ml_away")
        series = pm_series(mk["token0"])
        if mk["side"] == "away":
            series = [(t, round(1.0 - p, 6)) for t, p in series]  # builder stores 1 - p rounded to 6 dp for the away-token case
        for name, dt, max_age in (("t24h", 86400, 7200), ("t6h", 21600, 7200), ("t1h", 3600, 7200), ("t10m", 600, 7200), ("t1m", 60, 7200)):
            s = last_at_or_before(series, ko - dt)
            val = s[1] if s and (ko - dt - s[0]) <= max_age else None
            checks[f"pm_{name}"] = (val, g["derived"]["pm_pre"][name])
        # Brier scores
        y = g["final"]["home_win"]
        checks["brier_pinnacle_close"] = ((pin_p - y) ** 2 if pin_p is not None and y is not None else None, (g["derived"]["pinnacle_close"] - y) ** 2 if g["derived"]["pinnacle_close"] is not None and y is not None else None)
        pm1 = checks["pm_t1m"][0]
        checks["brier_pm_t1m"] = ((pm1 - y) ** 2 if pm1 is not None and y is not None else None, (g["derived"]["pm_pre"]["t1m"] - y) ** 2 if g["derived"]["pm_pre"]["t1m"] is not None and y is not None else None)
        checks["final_score"] = (f"{g['final']['away']}-{g['final']['home']}", f"{w['as']}-{w['hs']}")
        row = {"key": w["key"], "league": w["lg"], "ok": True, "max_abs_diff": 0.0, "checks": {}}
        for k, (a, b) in checks.items():
            if isinstance(a, str) or isinstance(b, str):
                ok = a == b
                d = 0.0 if ok else 1.0
            elif a is None or b is None:
                ok = a is None and b is None
                d = 0.0 if ok else 1.0
            else:
                d = abs(a - b)
                ok = d <= TOL
            row["checks"][k] = {"recomputed": a, "stored": b, "abs_diff": d, "ok": ok}
            row["max_abs_diff"] = max(row["max_abs_diff"], d)
            row["ok"] = row["ok"] and ok
            worst[k] = max(worst.get(k, 0.0), d)
        all_ok = all_ok and row["ok"]
        report.append(row)
    os.makedirs(os.path.join(BUILD, "qa"), exist_ok=True)
    json.dump({"seed": SEED, "tolerance": TOL, "n": len(report), "all_ok": all_ok, "worst_abs_diff_by_check": worst, "games": report}, open(os.path.join(BUILD, "qa", "recomputation_20.json"), "w"), indent=1)
    lines = [f"# Independent recomputation ({len(report)} games, seed {SEED}, tolerance {TOL:g})", "",
             f"Result: {'ALL PASS' if all_ok else 'FAILURES PRESENT'}. Worst absolute difference by quantity:", ""]
    lines += [f"- {k}: {v:.3g}" for k, v in sorted(worst.items())]
    lines += ["", "| game | league | Pinnacle close (recomputed) | stored | PM T−1min (recomputed) | stored | max |abs diff| | ok |", "|---|---|---|---|---|---|---|---|"]
    for r in report:
        c = r["checks"]
        f6 = lambda x: "—" if x is None else f"{x:.9f}"
        lines.append(f"| {r['key']} | {r['league']} | {f6(c['pinnacle_close']['recomputed'])} | {f6(c['pinnacle_close']['stored'])} | {f6(c['pm_t1m']['recomputed'])} | {f6(c['pm_t1m']['stored'])} | {r['max_abs_diff']:.2e} | {'yes' if r['ok'] else 'NO'} |")
    lines += ["", "Method re-implemented from scratch in `pipeline/10_recompute.py` (reads raw vendor cache files; uses exact rational arithmetic for the odds conversion)."]
    open(os.path.join(BUILD, "qa", "recomputation_20.md"), "w").write("\n".join(lines) + "\n")
    print("ALL OK" if all_ok else "FAILURES", json.dumps(worst, indent=0))
    for r in report:
        if not r["ok"]:
            print(r["key"], {k: v for k, v in r["checks"].items() if not v["ok"]})


if __name__ == "__main__":
    main()
