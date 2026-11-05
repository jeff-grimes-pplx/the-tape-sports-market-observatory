#!/usr/bin/env python3
"""Derive compact per-league Sportradar game lists from the cached connector responses.

Reads every cached Sportradar response (schedules, soccer season summaries) and writes
derived/sr_<league>.json with one compact record per game inside the window.
"""
import glob
import json
import os
from datetime import datetime, timezone

DATA = os.environ.get("A9_DATA", "/home/user/workspace/a9-data")
WINDOW_START = os.environ.get("A9_SR_START", "2026-09-13T00:00:00+00:00")
WINDOW_END = os.environ.get("A9_SR_END", "2026-10-15T00:00:00+00:00")
OUT_PREFIX = os.environ.get("A9_SR_PREFIX", "sr_")

LEAGUE_FOR_PRODUCT = {
    "nfl": "nfl", "ncaafb": "ncaaf", "mlb": "mlb", "nba": "nba", "nhl": "nhl", "wnba": "wnba",
}
SOCCER_SEASONS = {
    "sr:season:140786": "ucl", "sr:season:142176": "laliga", "sr:season:140756": "epl",
    "sr:season:140782": "seriea", "sr:season:140780": "ligue1", "sr:season:140768": "bundesliga",
    "sr:season:137218": "mls",
}


def iso(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc)


def in_window(t):
    return iso(WINDOW_START) <= iso(t) <= iso(WINDOW_END)


def team_us(t):
    if not t:
        return None
    full = t.get("name") or ""
    if t.get("market") and t["market"] not in full:
        full = f"{t['market']} {t['name']}"
    return {"id": t.get("id"), "name": full, "alias": t.get("alias") or t.get("abbr"), "market": t.get("market"), "sr_name": t.get("name")}


def main():
    out = {}
    for f in glob.glob(os.path.join(DATA, "cache", "sportradar", "*.json")):
        r = json.load(open(f))
        if not r.get("ok"):
            continue
        a = r["args"]
        d = r["data"].get("data", r["data"]) if isinstance(r["data"], dict) else r["data"]
        product, path = a.get("product"), a["path"]
        if product in LEAGUE_FOR_PRODUCT and path.endswith("/schedule"):
            lg = LEAGUE_FOR_PRODUCT[product]
            season_type = path.split("/")[3]
            games = []
            if "weeks" in d:
                for w in d["weeks"]:
                    for g in w.get("games", []):
                        g = dict(g)
                        g["_week"] = w.get("sequence")
                        games.append(g)
            else:
                games = d.get("games", [])
            for g in games:
                if not g.get("scheduled") or not in_window(g["scheduled"]):
                    continue
                rec = {
                    "id": g["id"], "league": lg, "scheduled": iso(g["scheduled"]).isoformat(), "status": g.get("status"),
                    "season_type": season_type, "week": g.get("_week"), "neutral_site": g.get("neutral_site"),
                    "home": team_us(g.get("home")), "away": team_us(g.get("away")),
                    "home_points": (g.get("scoring") or {}).get("home_points", g.get("home_points")),
                    "away_points": (g.get("scoring") or {}).get("away_points", g.get("away_points")),
                    "periods": (g.get("scoring") or {}).get("periods"),
                    "venue": {k: (g.get("venue") or {}).get(k) for k in ("name", "city", "state", "country", "roof_type", "surface", "capacity")} if g.get("venue") else None,
                    "weather": g.get("weather"), "attendance": g.get("attendance"), "duration": g.get("duration"),
                    "title": g.get("title"), "broadcast": g.get("broadcast"), "sr_generated_at": d.get("generated_at") if isinstance(d, dict) else None,
                    "retrieved_at": r.get("retrieved_at"), "cache_key": r.get("key"),
                }
                out.setdefault(lg, {})[rec["id"]] = rec
        elif product == "soccer" and "/summaries" in path:
            sid = path.split("/")[2]
            lg = SOCCER_SEASONS.get(sid)
            if not lg:
                continue
            for s in d.get("summaries", []):
                se, st = s.get("sport_event", {}), s.get("sport_event_status", {})
                if not se.get("start_time") or not in_window(se["start_time"]):
                    continue
                comps = se.get("competitors", [])
                home = next((c for c in comps if c.get("qualifier") == "home"), None)
                away = next((c for c in comps if c.get("qualifier") == "away"), None)
                tt = lambda c: {"id": c.get("id"), "name": c.get("name"), "alias": c.get("abbreviation"), "market": None, "sr_name": c.get("name")} if c else None
                rec = {
                    "id": se["id"], "league": lg, "scheduled": iso(se["start_time"]).isoformat(), "status": st.get("status"),
                    "match_status": st.get("match_status"), "season_type": "REG", "week": (se.get("sport_event_context") or {}).get("round", {}).get("number"),
                    "neutral_site": None, "home": tt(home), "away": tt(away),
                    "home_points": st.get("home_score"), "away_points": st.get("away_score"), "periods": st.get("period_scores"),
                    "venue": {k: (se.get("venue") or {}).get(k) for k in ("name", "city_name", "country_name", "capacity")} if se.get("venue") else None,
                    "weather": None, "attendance": None, "duration": None, "title": None, "broadcast": None,
                    "sr_generated_at": d.get("generated_at"), "retrieved_at": r.get("retrieved_at"), "cache_key": r.get("key"),
                }
                out.setdefault(lg, {})[rec["id"]] = rec
    os.makedirs(os.path.join(DATA, "derived"), exist_ok=True)
    summary = {}
    for lg, games in out.items():
        recs = sorted(games.values(), key=lambda g: g["scheduled"])
        json.dump({"league": lg, "games": recs}, open(os.path.join(DATA, "derived", f"{OUT_PREFIX}{lg}.json"), "w"))
        statuses = {}
        for g in recs:
            statuses[g["status"]] = statuses.get(g["status"], 0) + 1
        summary[lg] = {"games": len(recs), "statuses": statuses}
        print(lg, len(recs), statuses)
    json.dump(summary, open(os.path.join(DATA, "derived", f"{OUT_PREFIX}summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
