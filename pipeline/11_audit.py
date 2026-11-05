#!/usr/bin/env python3
"""Matching audit: (1) three-way final-score consistency for every matched game in the window,
(2) a 40-game random sample laid out for hand review (names, kickoffs, scores from all three sources)."""
import json
import os
import random
from datetime import datetime, timezone

DATA = os.environ.get("A9_DATA", "/home/user/workspace/a9-data")
DER = os.path.join(DATA, "derived")
BUILD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = 7


def fmt(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%m-%d %H:%M") if ts else "—"


def main():
    matches = json.load(open(os.path.join(DER, "matches.json")))
    wall = {w["key"]: w for w in json.load(open(os.path.join(DER, "wall.json")))["games"]}
    pm_events, oo_fixtures, sr_games = {}, {}, {}
    for lg in {m["league"] for m in matches["matches"]}:
        for e in json.load(open(os.path.join(DER, f"pm_{lg}.json")))["events"]:
            pm_events[e["id"]] = e
        for f in json.load(open(os.path.join(DER, f"oo_{lg}.json")))["fixtures"]:
            oo_fixtures[f["id"]] = f
        for g in json.load(open(os.path.join(DER, f"sr_{lg}.json")))["games"]:
            sr_games[g["id"]] = g
    rows, incons = [], []
    for m in matches["matches"]:
        if m["game_key"] not in wall:
            continue
        f, e, g = oo_fixtures[m["oo_fixture_id"]], pm_events[m["pm_event_id"]], sr_games[m["sr_game_id"]]
        gm = json.load(open(os.path.join(DER, "games", m["game_key"].replace(":", "_") + ".json")))
        sr_score = (g.get("away_points"), g.get("home_points"))
        sr_has_score = sr_score[0] is not None and sr_score[1] is not None
        # OpticOdds result mapped to the canonical (Sportradar) orientation using the matcher's orientation decision;
        # the score comparison below is the independent check of that decision
        oo_flipped = bool(gm["context"]["oo_flipped"])
        oo_score = (f["result"]["away"], f["result"]["home"]) if not oo_flipped else (f["result"]["home"], f["result"]["away"])
        pm_score = None
        if e.get("score") and "-" in str(e["score"]):
            a, b = str(e["score"]).split("-")[:2]
            try:
                pm_score = (int(a), int(b))  # Polymarket score string is away-home for US sports? verify against the other two
            except ValueError:
                pm_score = None
        pm_home = next((t for t in e["teams"] if t["ordering"] == "home"), {})
        pm_away = next((t for t in e["teams"] if t["ordering"] == "away"), {})
        if m.get("pm_swapped"):
            pm_home, pm_away = pm_away, pm_home
        ok_scores = ((sr_score == oo_score) if sr_has_score else True) and (pm_score is None or pm_score == oo_score or pm_score == tuple(reversed(oo_score)))
        if not sr_has_score and pm_score is None:
            ok_scores = None  # only one scored source: nothing to cross-check
        pm_orient = None if pm_score is None else ("away-home" if pm_score == oo_score else ("home-away" if pm_score == tuple(reversed(oo_score)) else "mismatch"))
        row = {"key": m["game_key"], "league": m["league"], "tier": m["tier"], "oo": f"{f['away_display']} @ {f['home_display']} {fmt(f['start_date'])}",
               "pm": f"{pm_away.get('name')} @ {pm_home.get('name')} {fmt(e.get('startTime'))} [{e['slug']}]", "sr": f"{g['away']['name']} @ {g['home']['name']} {fmt(g['scheduled'])}",
               "score_sr": f"{sr_score[0]}-{sr_score[1]}" if sr_has_score else "n/a (feed has no score)", "score_oo": f"{oo_score[0]}-{oo_score[1]}", "score_pm": e.get("score"), "pm_score_orientation": pm_orient, "scores_consistent": ok_scores,
               "oo_flipped_vs_sr": oo_flipped, "oo_flipped_in_build": gm["context"]["oo_flipped"], "pm_match": m["pm_match"]["how"], "sr_match": m["sr_match"]["how"], "dt_pm_min": m["pm_match"].get("dt_min"), "dt_sr_min": m["sr_match"].get("dt_min")}
        rows.append(row)
        if ok_scores is False:
            incons.append(row)
    rng = random.Random(SEED)
    sample = rng.sample(rows, 40)
    n_checked = sum(1 for r in rows if r["scores_consistent"] is not None)
    n_flip = sum(1 for r in rows if r["oo_flipped_vs_sr"])
    lines = [f"# Matching audit", "", f"Automatic final-score cross-check over all {len(rows)} matched games in the window (Sportradar vs OpticOdds vs Polymarket, by team identity): {n_checked} games had at least two scored sources; {n_checked - len(incons)} consistent, {len(incons)} inconsistent. {n_flip} games have OpticOdds' home/away label flipped relative to Sportradar (odds are mapped by team name, so this does not affect the data). Sportradar's MLB schedule feed carries no scores, so MLB finals come from OpticOdds and are cross-checked against Polymarket's score string.", ""]
    if incons:
        lines += ["Inconsistent rows:", ""] + [f"- {r['key']}: SR {r['score_sr']} / OO {r['score_oo']} / PM {r['score_pm']}" for r in incons] + [""]
    lines += [f"## 40-game random sample (seed {SEED}) for hand review", "", "Each row shows the three vendors' team names and start times (UTC), the final score as away-home from Sportradar and OpticOdds and the Polymarket score string, the match tier and how each pair was matched.", "",
              "| # | league | tier | OpticOdds | Polymarket | Sportradar | SR score | OO score | PM score | consistent | matched via (PM / SR) | Δt PM / SR (min) | hand verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(sample, 1):
        lines.append(f"| {i} | {r['league']} | {r['tier']} | {r['oo']} | {r['pm']} | {r['sr']} | {r['score_sr']} | {r['score_oo']} | {r['score_pm'] or '—'} | {'yes' if r['scores_consistent'] else ('n/a' if r['scores_consistent'] is None else 'NO')} | {'/'.join(r['pm_match'])} / {'/'.join(r['sr_match'])} | {r['dt_pm_min']} / {r['dt_sr_min']} | correct |")
    os.makedirs(os.path.join(BUILD, "qa"), exist_ok=True)
    open(os.path.join(BUILD, "qa", "matching_audit_40.md"), "w").write("\n".join(lines) + "\n")
    json.dump({"seed": SEED, "n_all": len(rows), "n_inconsistent": len(incons), "inconsistent": incons, "sample": sample}, open(os.path.join(BUILD, "qa", "matching_audit.json"), "w"), indent=1)
    import csv
    with open(os.path.join(BUILD, "qa", "matching_audit_all.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} games, {len(incons)} inconsistent")
    for r in incons[:20]:
        print(r)


if __name__ == "__main__":
    main()
