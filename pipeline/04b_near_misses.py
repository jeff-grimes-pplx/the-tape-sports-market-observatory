#!/usr/bin/env python3
"""List near-miss Polymarket candidates for OpticOdds fixtures that the ±20-minute rule left unmatched.

A near miss must have: both teams matching at ≥ 0.85 (exact/alias/nickname/abbr), |Δt| ≤ 12 h, a unique
candidate, and (when both have final scores) agreeing unordered final scores. The output is a proposal list
for overrides.json; nothing is applied automatically.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
m = importlib.import_module("04_match")

DER = m.DER


def main():
    matches = json.load(open(os.path.join(DER, "matches.json")))
    used_pm = {x["pm_event_id"] for x in matches["matches"]}
    unmatched = json.load(open(os.path.join(DER, "unmatched.json")))
    proposals = []
    for lg, rows in unmatched.items():
        oo, pm, sr = m.load_sources(lg)
        m.build_mascots(lg, pm)
        oo_by_id = {f["id"]: f for f in oo}
        pm_free = [e for e in pm if e["id"] not in used_pm]
        for u in rows:
            if u["has_pm"]:
                continue
            f = oo_by_id[u["oo_fixture_id"]]
            ta = m.iso(f["start_date"])
            cands = []
            for e in pm_free:
                dt = (m.iso(e["startTime"]) - ta).total_seconds() / 60.0
                if abs(dt) > 30 * 60:
                    continue
                s, how, swapped, (sh, sa) = m.pair_score(m.oo_team(f, "home"), m.oo_team(f, "away"), m.pm_team(e, "home"), m.pm_team(e, "away"))
                if min(sh, sa) < 0.85:
                    continue
                p_oo = m.score_pair((f["result"]["away"], f["result"]["home"]))
                p_pm = m.score_pair((e.get("score") or "").split("-")) if e.get("score") and "-" in e["score"] else None
                rel = None if not (p_oo and p_pm) else ("agree" if p_oo == p_pm else "disagree")
                cands.append({"pm_event_id": e["id"], "pm_slug": e["slug"], "pm_start": e["startTime"], "dt_min": round(dt, 1), "how": how, "swapped": swapped, "score_rel": rel, "pm_score": e.get("score")})
            if len(cands) == 1 and cands[0]["score_rel"] != "disagree":
                proposals.append({"league": lg, "oo_fixture_id": f["id"], "oo_start": f["start_date"], "away_oo": f["away_display"], "home_oo": f["home_display"], "oo_score": [f["result"]["away"], f["result"]["home"]], **cands[0]})
            elif cands:
                print("AMBIGUOUS/CONFLICT", lg, f["start_date"], f["away_display"], "@", f["home_display"], cands)
    for p in proposals:
        print(f"{p['league']:6s} OO {p['oo_start']} {p['away_oo']} @ {p['home_oo']} {p['oo_score']} | PM {p['pm_slug']} start={p['pm_start']} dt={p['dt_min']}min how={p['how']} swapped={p['swapped']} score={p['pm_score']} ({p['score_rel']})")
    json.dump(proposals, open(os.path.join(DER, "near_miss_proposals.json"), "w"), indent=1)
    print(len(proposals), "proposals")


if __name__ == "__main__":
    main()
