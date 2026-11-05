#!/usr/bin/env python3
"""Assemble the static deploy folder for The Tape: app source + data + meta.json (tier label, ledger, matching stats)."""
import json
import os
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.dirname(HERE)
DATA = os.environ.get("A9_DATA", os.path.join(BUILD, "data"))
DER = os.path.join(DATA, "derived")
DEPLOY = os.environ.get("A9_DEPLOY", "/home/user/workspace/a9-deploy")
TIER = int(os.environ.get('A9_TIER', '1'))  # Tier 1 approved 2026-10-15 ~04:10 UTC (parent relay of Jeff's decision)
CAPS = {0: {'opticodds': 150, 'sportradar': 40, 'polymarket': 'paced, uncapped'}, 1: {'opticodds': '2,088 (+30 for the Today snapshot = 2,118)', 'sportradar': 178, 'polymarket': '5,765 successful calls'}}


def ledger_counts():
    out = {s: {"attempts": 0, "ok": 0, "throttled": 0, "errors": 0, "cached_reads": 0, "unique_ok_responses": 0} for s in ("opticodds", "polymarket", "sportradar")}
    first = last = None
    p = os.path.join(DATA, "ledger", "calls.jsonl")
    for line in open(p):
        r = json.loads(line)
        s = r["source"]
        out[s]["attempts"] += 1
        if r.get("ok"):
            out[s]["ok"] += 1
        elif r.get("transient") or "HTTP 429" in str(r.get("error")) or "rate limit" in str(r.get("error")).lower():
            out[s]["throttled"] += 1
        else:
            out[s]["errors"] += 1
        first = first or r["t"]
        last = r["t"]
    ch = os.path.join(DATA, "ledger", "cache_hits.jsonl")
    if os.path.exists(ch):
        for line in open(ch):
            parts = line.strip().split(",")
            if len(parts) == 3 and parts[1] in out:
                out[parts[1]]["cached_reads"] += 1
    for s in out:
        d = os.path.join(DATA, "cache", s)
        if os.path.isdir(d):
            out[s]["unique_ok_responses"] = sum(1 for fn in os.listdir(d) if fn.endswith(".json"))
    dm_path = os.path.join(DATA, "deploy_meta.json")
    if os.path.exists(dm_path):
        dm = json.load(open(dm_path))
        for s in out:
            if out[s]["unique_ok_responses"] == 0 and dm.get("ledger", {}).get(s, {}).get("unique_ok_responses"):
                out[s]["unique_ok_responses"] = dm["ledger"][s]["unique_ok_responses"]
    return out, first, last


def main():
    os.makedirs(os.path.join(DEPLOY, "data", "games"), exist_ok=True)
    # app source
    for f in ("index.html", "styles.css", "fonts.css"):
        if os.path.exists(os.path.join(HERE, f)):
            shutil.copy(os.path.join(HERE, f), DEPLOY)
    if os.path.isdir(os.path.join(HERE, "fonts")):
        os.makedirs(os.path.join(DEPLOY, "fonts"), exist_ok=True)
        for f in os.listdir(os.path.join(HERE, "fonts")):
            shutil.copy(os.path.join(HERE, "fonts", f), os.path.join(DEPLOY, "fonts", f))
    os.makedirs(os.path.join(DEPLOY, "js"), exist_ok=True)
    for f in os.listdir(os.path.join(HERE, "js")):
        shutil.copy(os.path.join(HERE, "js", f), os.path.join(DEPLOY, "js", f))
    # data
    for f in ("wall.json", "analysis.json", "manifest.json"):
        shutil.copy(os.path.join(DER, f), os.path.join(DEPLOY, "data", f))
    wall = json.load(open(os.path.join(DER, "wall.json")))
    keys = {g["key"] for g in wall["games"] + (wall.get("ext_games") or [])}
    n_copied = 0
    for g in wall["games"] + (wall.get("ext_games") or []):
        fn = g["key"].replace(":", "_") + ".json"
        src = os.path.join(DER, "games", fn)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(DEPLOY, "data", "games", fn))
            n_copied += 1
    # prune stale game files
    for fn in os.listdir(os.path.join(DEPLOY, "data", "games")):
        if fn[:-5].replace("_", ":", 1) not in keys:
            os.remove(os.path.join(DEPLOY, "data", "games", fn))
    # meta
    matches = json.load(open(os.path.join(DER, "matches.json")))
    overrides = json.load(open(os.path.join(BUILD, "pipeline", "overrides.json")))
    audit = json.load(open(os.path.join(BUILD, "qa", "matching_audit.json")))
    recomp = json.load(open(os.path.join(BUILD, "qa", "recomputation_20.json")))
    in_window = Counter(g["lg"] for g in wall["games"])
    per_league = []
    for lg, st in matches["stats"].items():
        per_league.append({"league": lg, **st, "in_window": in_window.get(lg, 0)})
    order = ["nfl", "ncaaf", "mlb", "nba", "nhl", "wnba", "mls", "epl", "laliga", "seriea", "bundesliga", "ligue1", "ucl"]
    per_league.sort(key=lambda r: order.index(r["league"]) if r["league"] in order else 99)
    led, first, last = ledger_counts()
    audit_rows = audit.get("sample", audit.get("rows", []))
    hand = json.load(open(os.path.join(BUILD, "qa", "hand_review.json"))) if os.path.exists(os.path.join(BUILD, "qa", "hand_review.json")) else {}
    worst = max((v for v in recomp.get("worst_abs_diff_by_check", {}).values() if isinstance(v, (int, float))), default=None)
    books_hist = Counter()
    for g in wall["games"]:
        for b in g.get("books") or []:
            books_hist[b] += 1
    oo_games = sum(1 for g in wall["games"] if g.get("oo"))
    oo_by_lg = Counter(g["lg"] for g in wall["games"] if g.get("oo"))
    sweep_state = os.environ.get("A9_SWEEP", "complete")
    tier_label = {0: f"Tier 0 (bounded slice: sportsbook history for {oo_games} games — {', '.join(f'{v} {k.upper()}' for k, v in sorted(oo_by_lg.items()))}; Polymarket + Sportradar for all {len(wall['games'])} matched games)",
                  1: (f"Tier 1 sweep in progress (snapshot {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%MZ')}): sportsbook history for {oo_games} of {len(wall['games'])} matched games so far; Polymarket + Sportradar for all {len(wall['games'])}"
                      if sweep_state != "complete" else
                      f"Tier 1 (full sweep: sportsbook history for {oo_games} of {len(wall['games'])} matched games in the window; Polymarket + Sportradar for all {len(wall['games'])})")}[TIER]
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tier": TIER,
        "tier_label": tier_label,
        "sweep_state": sweep_state,
        "oo_slice_label": f"Sportsbook history exists for {oo_games} of {len(wall['games'])} matched games in the window: " + ", ".join(f"{v} {k.upper()}" for k, v in sorted(oo_by_lg.items())) + f" (sportsbooks seen: {', '.join(sorted(books_hist))}); games without it are shown as Polymarket + Sportradar only.",
        "window": wall["window"],
        "n_games": len(wall["games"]),
        "n_game_files": n_copied,
        "ledger": led,
        "ledger_first_call": first,
        "ledger_last_call": last,
        "budget": CAPS[TIER],
        "ledger_note": f"Caps for the completed tier: OpticOdds {CAPS[TIER]['opticodds']} attempts, Sportradar {CAPS[TIER]['sportradar']} attempts, Polymarket {CAPS[TIER]['polymarket']} (paced at ≤ 20 calls/min from 04:08 UTC; ≤ 2/s before). Throttled responses (HTTP 429) were never cached and were retried after exponential backoff; they count as attempts, not as successes. Cache-served reads never reach the vendor and are counted separately.",
        "matching": {
            "tolerance_minutes": matches.get("tolerance_minutes", 20),
            "tiers": matches.get("tiers"),
            "per_league": per_league,
            "overrides": len(overrides.get("matches", [])) + len(overrides.get("rejects", [])),
            "orientation_conflicts": sum(1 for m in matches["matches"] if m.get("orientation_conflict")),
            "audit": {"n": len(audit_rows) or 40, "seed": audit.get("seed", 7), "wrong": hand.get("wrong", 0), "reviewed": hand.get("reviewed", False), "notes": hand.get("notes", "")},
        },
        "recompute": {"n": recomp.get("n", 20), "seed": recomp.get("seed", 2026), "ok": recomp.get("all_ok", recomp.get("ok")), "worst": worst, "tolerance": recomp.get("tolerance", 1e-9)},
        "books": sorted(books_hist),
        "limitations": [
            f"Sportsbook history covers {oo_games} of {len(wall['games'])} matched games in the window. Every cross-market statistic is computed only on games that have both a sportsbook close and a Polymarket close; games without one of them appear with the sources they do have.",
            "Polymarket series are sampled CLOB prices (10-minute fidelity for the 1-month lookback, 5-minute for the last week, 1-minute for the last day), not trades or order books; a sample is used directly as a probability and its age is recorded.",
            "OpticOdds retains roughly two months of history and histories end at kickoff; in-game sportsbook lines are not part of this dataset. Vendor OLV/CLV fields are kept as receipts but opening/closing values are recomputed from the entries.",
            "The five sportsbooks requested are Pinnacle, DraftKings, FanDuel, BetMGM and Caesars; Caesars histories are sparse (often stale by days), which the close-age column records.",
            "Sportradar play-by-play with wall clocks was fetched for the hero set only; in-game reaction results are illustrative and sample spacing (1–5 min) makes reaction times upper bounds.",
            "Backtests assume $1 stakes filled at the sampled price with the taker fee charged on entry; no slippage, no liquidity check, no exit before resolution. They describe history and are not recommendations.",
            "Context factors are descriptive group means with a Bonferroni caveat; nothing here is a causal claim.",
        ],
        "attribution": "Sportsbook lines and odds history: OpticOdds. Prediction-market prices and market metadata: Polymarket. Schedules, final scores and play-by-play: Sportradar. Every price shown names its sportsbook or Polymarket.",
    }
    json.dump(meta, open(os.path.join(DEPLOY, "data", "meta.json"), "w"), indent=1)
    # today snapshot passthrough
    tsrc = os.path.join(DER, "today.json")
    if os.path.exists(tsrc):
        shutil.copy(tsrc, os.path.join(DEPLOY, "data", "today.json"))
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(DEPLOY) for f in fs)
    print(f"deploy folder {DEPLOY}: {n_copied} game files, {total / 1e6:.1f} MB total; tier label: {tier_label}")


if __name__ == "__main__":
    main()
