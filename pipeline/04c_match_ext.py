#!/usr/bin/env python3
"""Two-way matcher for the sportsbook-only extension (2026-08-14 → 2026-09-14): OpticOdds fixtures ↔ Sportradar finals.

Same rules as 04_match.py (league, normalized names + aliases, start within ±20 min, mutual best, final-score
check), but without Polymarket. Writes derived/matches_ext.json with the same record shape (pm fields = None).
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("match4", os.path.join(HERE, "04_match.py"))
m4 = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]]
spec.loader.exec_module(m4)

DER = m4.DER
LEAGUES = ["nfl", "ncaaf", "mlb", "wnba", "mls", "epl", "laliga", "seriea", "bundesliga", "ligue1", "ucl"]


def main():
    all_matches, stats, unmatched, rejected = [], {}, {}, []
    for lg in LEAGUES:
        oo_path, sr_path = os.path.join(DER, f"ooext_{lg}.json"), os.path.join(DER, f"srext_{lg}.json")
        if not (os.path.exists(oo_path) and os.path.exists(sr_path)):
            continue
        oo = json.load(open(oo_path))["fixtures"]
        sr = json.load(open(sr_path))["games"]
        pm_path = os.path.join(DER, f"pm_{lg}.json")
        if os.path.exists(pm_path):
            m4.build_mascots(lg, json.load(open(pm_path))["events"])
        oo = [f for f in oo if f.get("result") and f["result"].get("home") is not None]
        sr_ok = [g for g in sr if g.get("status") in ("closed", "complete")]
        m_sr, amb_sr = m4.match_sources(oo, sr_ok, lambda f: f["start_date"], lambda g: g["scheduled"],
                                        lambda f: m4.oo_team(f, "home"), lambda f: m4.oo_team(f, "away"),
                                        lambda g: m4.sr_team(g, "home"), lambda g: m4.sr_team(g, "away"),
                                        lambda f: f["id"], lambda g: g["id"],
                                        a_score=lambda f: (f["result"]["away"], f["result"]["home"]), b_score=lambda g: (g.get("away_points"), g.get("home_points")))
        sr_by_id = {g["id"]: g for g in sr_ok}
        n2 = n_none = 0
        used_sr = set()
        for f in sorted(oo, key=lambda f: f["start_date"]):
            b = m_sr.get(f["id"])
            if not b:
                n_none += 1
                unmatched.setdefault(lg, []).append({"oo_fixture_id": f["id"], "start": f["start_date"], "away": f["away_display"], "home": f["home_display"], "amb_sr": amb_sr.get(f["id"])})
                continue
            used_sr.add(b["b"])
            g = sr_by_id[b["b"]]
            t = m4.tier(None, b)
            p_oo = m4.score_pair((f["result"]["away"], f["result"]["home"]))
            p_sr = m4.score_pair((g.get("away_points"), g.get("home_points")))
            score_consistent = (p_oo is None or p_sr is None or p_oo == p_sr)
            rec = {
                "game_key": f"{lg}:{f['id']}", "league": lg, "oo_fixture_id": f["id"], "oo_game_id": f.get("game_id"),
                "pm_event_id": None, "pm_slug": None, "sr_game_id": g["id"],
                "start_oo": f["start_date"], "start_pm": None, "start_sr": g["scheduled"],
                "home_oo": f["home_display"], "away_oo": f["away_display"], "home_pm": None, "away_pm": None,
                "home_sr": g["home"]["name"] if g.get("home") else None, "away_sr": g["away"]["name"] if g.get("away") else None,
                "score_oo": [f["result"]["away"], f["result"]["home"]], "score_pm": None, "score_sr": [g.get("away_points"), g.get("home_points")],
                "tier": t, "pm_match": None, "sr_match": {k: v for k, v in b.items() if k != "b"},
                "pm_swapped": False, "sr_swapped": b["swapped"], "score_consistent": score_consistent, "orientation_conflict": bool(b["swapped"]),
                "extension": True, "season_type": f.get("season_type"), "season_week": f.get("season_week"),
            }
            if not score_consistent:
                rejected.append(rec)
                n_none += 1
                continue
            n2 += 1
            all_matches.append(rec)
        stats[lg] = {"oo_fixtures_completed": len(oo), "sr_games_closed": len(sr_ok), "sr_games_all": len(sr), "matched_2way": n2,
                     "oo_unmatched": n_none, "sr_unmatched": len(sr_ok) - len(used_sr), "ambiguous_sr": len(amb_sr), "rejected_score": sum(1 for r in rejected if r["league"] == lg)}
        print(lg, stats[lg])
    tiers = {}
    for r in all_matches:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1
    json.dump({"window_utc": ["2026-08-14T00:00:00Z", "2026-09-15T00:00:00Z"], "tolerance_minutes": m4.TOL_MIN, "matches": all_matches, "stats": stats, "tiers": tiers,
               "unmatched": unmatched, "rejected": rejected}, open(os.path.join(DER, "matches_ext.json"), "w"), indent=0)
    print("extension matches:", len(all_matches), tiers, "rejected:", len(rejected))


if __name__ == "__main__":
    main()
