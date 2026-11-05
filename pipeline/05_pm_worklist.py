#!/usr/bin/env python3
"""Build the Polymarket price-history work list for matched games.

Per matched game: moneyline market(s) (one for US sports; home-win / draw / away-win for soccer),
the highest-volume spread market and the highest-volume total market. For each market the first
outcome token is fetched at `1m`/10-minute fidelity (full lookback), plus `1w`/5-minute fidelity when
the game ended within the last 7 days of now, plus `1d`/1-minute when it ended within the last 24 h.
Work items are ordered so the most perishable series are fetched first.
"""
import json
import os
from datetime import datetime, timedelta, timezone

DATA = os.environ.get("A9_DATA", "/home/user/workspace/a9-data")
DER = os.path.join(DATA, "derived")
SOCCER = {"mls", "epl", "laliga", "seriea", "bundesliga", "ligue1", "ucl"}


def iso(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc)


def main():
    now = datetime.now(timezone.utc)
    matches = json.load(open(os.path.join(DER, "matches.json")))["matches"]
    pm_events = {}
    for lg in {m["league"] for m in matches}:
        for e in json.load(open(os.path.join(DER, f"pm_{lg}.json")))["events"]:
            pm_events[e["id"]] = e
    items, plan = [], {}
    for m in matches:
        e = pm_events[m["pm_event_id"]]
        kickoff = iso(m["start_oo"])
        end_est = kickoff + timedelta(hours=5)
        age = now - end_est
        intervals = [("1m", 10)]
        if age <= timedelta(days=7):
            intervals.append(("1w", 5))
        if age <= timedelta(hours=24):
            intervals.append(("1d", 1))
        mkts = []
        mls = [x for x in e["markets"] if x["type"] == "moneyline" and x.get("tokens")]
        if m["league"] in SOCCER:
            for x in mls:
                q = (x.get("question") or "").lower()
                role = "draw" if "draw" in q else "ml"
                mkts.append((role, x))
        else:
            mls.sort(key=lambda x: -(x.get("volume") or 0))
            if mls:
                mkts.append(("ml", mls[0]))
        for typ, role in (("spreads", "spread"), ("totals", "total")):
            cands = [x for x in e["markets"] if x["type"] == typ and x.get("tokens")]
            if cands:
                cands.sort(key=lambda x: -(x.get("volume") or 0))
                mkts.append((role, cands[0]))
        plan[m["game_key"]] = {"pm_event_id": e["id"], "markets": [{"role": r, "market_id": x["id"], "question": x["question"], "line": x.get("line"), "outcomes": x.get("outcomes"), "token0": x["tokens"][0], "volume": x.get("volume"), "fee": x.get("feeSchedule"), "intervals": intervals} for r, x in mkts]}
        for r, x in mkts:
            for interval, fid in intervals:
                items.append({"game_key": m["game_key"], "league": m["league"], "kickoff": m["start_oo"], "role": r, "market_id": x["id"], "token": x["tokens"][0], "interval": interval, "fidelity": fid, "question": x["question"]})
    # perishability ordering: 1d first, then 1w (oldest first), then 1m (oldest first); moneylines before spreads/totals
    rank = {"1d": 0, "1w": 1, "1m": 2}
    role_rank = {"ml": 0, "draw": 1, "spread": 2, "total": 3}
    items.sort(key=lambda i: (rank[i["interval"]], role_rank[i["role"]] if i["interval"] != "1m" else 0, i["kickoff"], role_rank[i["role"]]))
    json.dump({"generated_at": now.isoformat(), "items": items}, open(os.path.join(DER, "pm_work.json"), "w"))
    json.dump(plan, open(os.path.join(DER, "pm_plan.json"), "w"))
    from collections import Counter
    print(len(items), "work items", Counter(i["interval"] for i in items), Counter(i["role"] for i in items))


if __name__ == "__main__":
    main()
