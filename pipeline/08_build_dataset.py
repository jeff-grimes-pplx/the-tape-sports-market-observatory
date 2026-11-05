#!/usr/bin/env python3
"""Build the aligned dataset: one JSON per matched game (for the explorer) + wall index + analysis table.

Inputs: derived/matches.json, derived/pm_plan.json, the OpticOdds / Polymarket / Sportradar caches.
Outputs:
  derived/games/<key>.json   full per-game detail (raw entries, no-vig change points, Polymarket samples, plays)
  derived/wall.json          compact index for the wall + scoreboard + backtest lab
  derived/manifest.json      dataset manifest (windows, counts, fidelity, retention, books)
All times are UTC epoch seconds. See lib/norm.py for the normalization conventions.
"""
import glob
import json
import math
import os
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
from norm import american_to_prob, novig_series, novig_from_prices, step_value, dedup_entries, norm_name  # noqa: E402

DATA = os.environ.get("A9_DATA", "/home/user/workspace/a9-data")
DER = os.path.join(DATA, "derived")
OUT_GAMES = os.path.join(DER, "games")
OUT_FULL = os.path.join(DER, "full")
WINDOW_START = "2026-09-15T00:00:00Z"
WINDOW_END = "2026-10-15T00:00:00Z"
SOCCER = {"mls", "epl", "laliga", "seriea", "bundesliga", "ligue1", "ucl"}
SPORT = {"nfl": "football", "ncaaf": "football", "nba": "basketball", "wnba": "basketball", "mlb": "baseball", "nhl": "hockey"}
MARKET_ROLE = {"moneyline": "ml", "point spread": "spread", "run line": "spread", "puck line": "spread", "asian handicap": "spread",
               "total points": "total", "total runs": "total", "total goals": "total"}
STRIP_POINTS = 48
STRIP_SPAN = 7 * 86400


def iso_to_ts(s):
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def load_cache_index():
    """Map (source, path, key-params) -> cached response, for the three sources."""
    oo_hist, pm_hist, sr_pbp = {}, {}, {}
    for f in glob.glob(os.path.join(DATA, "cache", "opticodds", "*.json")):
        r = json.load(open(f))
        if r["args"]["path"] == "/fixtures/odds/historical" and r.get("ok"):
            p = r["args"]["params"]
            # keep the request whose sportsbook basket is the sweep basket if two exist; else any
            oo_hist.setdefault(p["fixture_id"], []).append(r)
    for f in glob.glob(os.path.join(DATA, "cache", "polymarket", "*.json")):
        r = json.load(open(f))
        if r["args"]["path"] == "/prices-history" and r.get("ok"):
            p = r["args"]["params"]
            pm_hist[(p["market"], p["interval"], p["fidelity"])] = r
    for f in glob.glob(os.path.join(DATA, "cache", "sportradar", "*.json")):
        r = json.load(open(f))
        if r.get("ok") and ("/pbp" in r["args"]["path"] or "/timeline" in r["args"]["path"] or "/summary" in r["args"]["path"]):
            gid = r["args"]["path"].split("/")[2] if r["args"]["path"].startswith("/games/") else r["args"]["path"].split("/")[2]
            sr_pbp.setdefault(gid, {})[r["args"]["path"].split("/")[-1]] = r
    return oo_hist, pm_hist, sr_pbp


def pick_oo_response(responses):
    """Prefer the response with the most lines (full basket); never merge baskets silently."""
    best = None
    for r in responses:
        if r["args"]["params"].get("purpose"):
            continue
        fx = (r.get("data") or {}).get("data", {}).get("data") or []
        if not fx:
            continue
        n = len(fx[0].get("odds") or [])
        if best is None or n > best[0]:
            best = (n, r)
    return best[1] if best else None


def side_of(name, home_names, away_names):
    n = norm_name(name)
    if n in home_names:
        return "home"
    if n in away_names:
        return "away"
    return None


def build_oo(resp, kickoff, home_names, away_names):
    """Return (books dict, meta). books[book][role] = {raw: {sel: entries}, novig: [[t, p_home_or_over, line]], olv, clv}."""
    fx = resp["data"]["data"]["data"][0]
    books = defaultdict(dict)
    n_entries = 0
    for o in fx.get("odds") or []:
        role = MARKET_ROLE.get((o.get("market") or "").lower())
        if not role:
            continue
        book = o["sportsbook"]
        sel = o.get("selection") or o.get("name")
        if role == "ml":
            side = side_of(sel, home_names, away_names)
            if side is None and (o.get("normalized_selection") or "").lower() in ("draw", "tie"):
                side = "draw"
        elif role == "spread":
            side = side_of(sel, home_names, away_names)
        else:
            side = (o.get("selection") or o.get("name") or "").lower().strip()
            side = "over" if side.startswith("over") else ("under" if side.startswith("under") else None)
        if side is None:
            continue
        entries = sorted(((int(e["timestamp"]), e["price"], e.get("points")) for e in (o.get("entries") or []) if e.get("price") is not None), key=lambda x: x[0])
        entries = dedup_entries(entries)
        n_entries += len(entries)
        slot = books[book].setdefault(role, {"raw": {}, "olv": {}, "clv": {}})
        slot["raw"][side] = entries
        slot["olv"][side] = o.get("olv")
        slot["clv"][side] = o.get("clv")
    out = {}
    for book, roles in books.items():
        out[book] = {}
        for role, slot in roles.items():
            raw = slot["raw"]
            if role == "ml":
                names = [n for n in ("home", "away", "draw") if n in raw]
                if "home" not in raw or "away" not in raw:
                    continue
                series = novig_series({n: raw[n] for n in names}, t_max=kickoff + 300)
                nv = [[t, d["home"], d["away"]] + ([d["draw"]] if "draw" in d else []) for t, d, _ in series]
                olv = None
                if all(slot["olv"].get(n) and slot["olv"][n].get("price") is not None for n in names):
                    olv = novig_from_prices([slot["olv"][n]["price"] for n in names])
                    olv = dict(zip(names, [round(x, 6) for x in olv]))
            elif role == "spread":
                if "home" not in raw or "away" not in raw:
                    continue
                series = novig_series({"home": raw["home"], "away": raw["away"]}, t_max=kickoff + 300, require_points_match=True)
                nv = [[t, d["home"], pts["home"]] for t, d, pts in series]
                olv = None
                oh, oa = slot["olv"].get("home"), slot["olv"].get("away")
                if oh and oa and oh.get("price") is not None and oa.get("price") is not None and oh.get("points") is not None:
                    nvp = novig_from_prices([oh["price"], oa["price"]])
                    olv = {"home": round(nvp[0], 6), "line": oh["points"]}
            else:
                if "over" not in raw or "under" not in raw:
                    continue
                series = novig_series({"over": raw["over"], "under": raw["under"]}, t_max=kickoff + 300, require_points_match=False)
                nv = [[t, d["over"], pts["over"]] for t, d, pts in series if pts["over"] is not None and pts["under"] is not None and abs(float(pts["over"]) - float(pts["under"])) < 1e-9]
                olv = None
                oo_, ou = slot["olv"].get("over"), slot["olv"].get("under")
                if oo_ and ou and oo_.get("price") is not None and ou.get("price") is not None:
                    nvp = novig_from_prices([oo_["price"], ou["price"]])
                    olv = {"over": round(nvp[0], 6), "line": oo_.get("points")}
            # closing = last no-vig state at or before kickoff
            pre = [x for x in nv if x[0] <= kickoff]
            close = pre[-1] if pre else None
            out[book][role] = {
                "raw": {s: [[t, p, pts] for (t, p, pts) in ents] for s, ents in raw.items()},
                "novig": [[row[0]] + [round(x, 6) if isinstance(x, float) else x for x in row[1:]] for row in nv], "novig_full": nv, "olv": olv, "vendor_olv": slot["olv"], "vendor_clv": slot["clv"],
                "close": close, "close_age_min": round((kickoff - close[0]) / 60, 1) if close else None,
                "first_ts": min((e[0] for ents in raw.values() for e in ents), default=None),
                "n_entries": sum(len(e) for e in raw.values()),
            }
    meta = {"fixture_id": fx["id"], "n_entries": n_entries, "books": sorted(out.keys()), "retrieved_at": resp.get("retrieved_at"), "cache_key": resp.get("key")}
    return out, meta


def merge_pm_series(responses):
    """Union of samples across fidelities. Returns sorted [[t, p, fidelity_min]]; finest fidelity wins on ties."""
    best = {}
    for fid, r in responses:
        hist = ((r.get("data") or {}).get("data") or {}).get("history") or (r.get("data") or {}).get("history") or []
        for h in hist:
            t, p = int(h["t"]), float(h["p"])
            if t not in best or fid < best[t][1]:
                best[t] = (p, fid)
    return [[t, best[t][0], best[t][1]] for t in sorted(best)]


def compress_steps(series, keep_gap=3600):
    """Keep change points plus one sample per `keep_gap` seconds so the chart knows the price was observed."""
    out = []
    for row in series:
        if not out:
            out.append(row)
            continue
        if row[1] != out[-1][1] or row[0] - out[-1][0] >= keep_gap:
            out.append(row)
    if series and out[-1] is not series[-1]:
        out.append(series[-1])
    return out


def sample_at(series, t):
    """Latest sample at or before t -> (t_sample, p) or None. series sorted [[t, p, ...]]."""
    ts = [r[0] for r in series]
    i = bisect_right(ts, t)
    return (series[i - 1][0], series[i - 1][1]) if i > 0 else None


def build_pm(plan, pm_hist, pm_event, home_team, away_team):
    """Return dict role -> {market, series (home-prob or over-prob), ...}. Soccer ML: home/draw/away markets."""
    home_names = {norm_name(x) for x in (home_team.get("name"), home_team.get("alias"), home_team.get("abbreviation")) if x}
    away_names = {norm_name(x) for x in (away_team.get("name"), away_team.get("alias"), away_team.get("abbreviation")) if x}
    out = {}
    for mk in plan["markets"]:
        responses = [(fid, pm_hist[(mk["token0"], iv, fid)]) for iv, fid in mk["intervals"] if (mk["token0"], iv, fid) in pm_hist]
        if not responses:
            continue
        raw = merge_pm_series(responses)
        if not raw:
            continue
        role, q = mk["role"], (mk.get("question") or "")
        outcomes = mk.get("outcomes") or []
        rec = {"market_id": mk["market_id"], "question": q, "line": mk.get("line"), "outcome0": outcomes[0] if outcomes else None,
               "token0": mk["token0"], "volume": mk.get("volume"), "fee": mk.get("fee"), "fidelities": sorted({r[2] for r in raw}),
               "n_samples": len(raw), "first_ts": raw[0][0], "last_ts": raw[-1][0], "retrieved_at": max(r.get("retrieved_at") or "" for _, r in responses)}
        raw_full = raw
        if role in ("ml", "draw"):
            if role == "draw":
                rec["side"] = "draw"
                rec["p_side"] = raw  # P(draw)
            else:
                # outcome0 side: US sports -> team name in outcomes[0]; soccer -> team named in the question
                side = side_of(outcomes[0], home_names, away_names) if outcomes and outcomes[0] not in ("Yes", "No") else None
                if side is None:
                    qn = norm_name(q)
                    hn = [n for n in home_names if n and n in qn]
                    an = [n for n in away_names if n and n in qn]
                    side = "home" if hn and not an else ("away" if an and not hn else ("home" if hn and len(max(hn, key=len)) > len(max(an, key=len)) else ("away" if an else None)))
                rec["side"] = side
                rec["p_side"] = raw
            key = role if role == "draw" else ("ml_home" if side == "home" else "ml_away" if side == "away" else "ml_unknown")
            out[key] = rec
        elif role == "spread":
            # question "Spread: Falcons (-3.5)" -> outcome0 is the named team covering `line`
            side = side_of(outcomes[0], home_names, away_names) if outcomes else None
            rec["side"] = side
            rec["p_side"] = raw
            out["spread"] = rec
        else:
            rec["side"] = "over"
            rec["p_side"] = raw
            out["total"] = rec
    # Derived: home-win probability series from ml markets
    if "ml_home" in out:
        out["home_series"] = out["ml_home"]["p_side"]
        out["home_series_source"] = "ml_home"
    elif "ml_away" in out:
        out["home_series"] = [[t, round(1.0 - p, 6), f] for t, p, f in out["ml_away"]["p_side"]]
        out["home_series_source"] = "1-ml_away"
    return out


def strip_samples(series_fn, kickoff, n=STRIP_POINTS, span=STRIP_SPAN):
    out = []
    for i in range(n):
        t = kickoff - span + (span * i) // (n - 1)
        v = series_fn(t)
        out.append(None if v is None else round(v, 4))
    return out


def main():
    os.makedirs(OUT_GAMES, exist_ok=True)
    os.makedirs(OUT_FULL, exist_ok=True)
    matches = json.load(open(os.path.join(DER, "matches.json")))["matches"]
    plan = json.load(open(os.path.join(DER, "pm_plan.json")))
    oo_hist, pm_hist, sr_pbp = load_cache_index()
    ws, we = iso_to_ts(WINDOW_START), iso_to_ts(WINDOW_END)
    pm_events, oo_fixtures, sr_games = {}, {}, {}
    for lg in {m["league"] for m in matches}:
        for e in json.load(open(os.path.join(DER, f"pm_{lg}.json")))["events"]:
            pm_events[e["id"]] = e
        for f in json.load(open(os.path.join(DER, f"oo_{lg}.json")))["fixtures"]:
            oo_fixtures[f["id"]] = f
        for g in json.load(open(os.path.join(DER, f"sr_{lg}.json")))["games"]:
            sr_games[g["id"]] = g
    # sportsbook-only extension (2026-08-14 → 2026-09-14): OpticOdds ↔ Sportradar two-way matches, no Polymarket
    ext_matches = []
    ext_path = os.path.join(DER, "matches_ext.json")
    if os.path.exists(ext_path):
        ext_doc = json.load(open(ext_path))
        ext_matches = ext_doc["matches"]
        ext_ws, ext_we = iso_to_ts(ext_doc["window_utc"][0]), iso_to_ts(ext_doc["window_utc"][1])
        for lg in {m["league"] for m in ext_matches}:
            for f in json.load(open(os.path.join(DER, f"ooext_{lg}.json")))["fixtures"]:
                oo_fixtures[f["id"]] = f
            for g in json.load(open(os.path.join(DER, f"srext_{lg}.json")))["games"]:
                sr_games[g["id"]] = g
    wall, ext_wall, census = [], [], defaultdict(lambda: Counter())
    fid_counter = Counter()
    for m in matches + ext_matches:
        kickoff = iso_to_ts(m["start_oo"])
        is_ext = bool(m.get("extension"))
        if is_ext:
            if not (ext_ws <= kickoff < ext_we):
                continue
            if m["oo_fixture_id"] not in oo_hist:
                census[m["league"]]["ext_matched_without_history"] += 1
                continue
        elif not (ws <= kickoff < we):
            census[m["league"]]["outside_window"] += 1
            continue
        f, e, g = oo_fixtures[m["oo_fixture_id"]], (pm_events.get(m["pm_event_id"]) if m.get("pm_event_id") else {"teams": []}), sr_games[m["sr_game_id"]]
        # canonical orientation = Sportradar home/away; OpticOdds may be flipped (orientation_conflict)
        sr_home, sr_away = g["home"], g["away"]
        oo_home, oo_away = f["home"][0], f["away"][0]
        flipped = bool(m.get("orientation_conflict")) and bool(m.get("sr_swapped"))
        if flipped:
            oo_home, oo_away = oo_away, oo_home
        home_names = {norm_name(x) for x in (sr_home["name"], sr_home.get("sr_name"), sr_home.get("alias"), oo_home["name"], oo_home.get("abbreviation"), f["home_display"] if not flipped else f["away_display"]) if x}
        away_names = {norm_name(x) for x in (sr_away["name"], sr_away.get("sr_name"), sr_away.get("alias"), oo_away["name"], oo_away.get("abbreviation"), f["away_display"] if not flipped else f["home_display"]) if x}
        pm_home = next((t for t in e["teams"] if t["ordering"] == "home"), {})
        pm_away = next((t for t in e["teams"] if t["ordering"] == "away"), {})
        if m.get("pm_swapped"):
            pm_home, pm_away = pm_away, pm_home
        for t in (pm_home,):
            home_names |= {norm_name(x) for x in (t.get("name"), t.get("alias"), f"{t.get('alias','')} {t.get('name','')}".strip()) if x}
        for t in (pm_away,):
            away_names |= {norm_name(x) for x in (t.get("name"), t.get("alias"), f"{t.get('alias','')} {t.get('name','')}".strip()) if x}
        # final score in canonical orientation
        hp, ap = g.get("home_points"), g.get("away_points")
        if hp is None or ap is None:
            hp, ap = (f["result"]["home"], f["result"]["away"]) if not flipped else (f["result"]["away"], f["result"]["home"])
        home_win = None if hp == ap else (1 if hp > ap else 0)
        # OpticOdds
        oo_books, oo_meta = ({}, None)
        resp = pick_oo_response(oo_hist.get(m["oo_fixture_id"], []))
        if resp:
            oo_books, oo_meta = build_oo(resp, kickoff, home_names, away_names)
        if is_ext and not oo_books:
            # the extension is sportsbook-only: a game whose history request failed (rate-limited at the cap) or came back
            # empty has nothing to show, so it is counted as matched-without-history rather than drawn as an empty strip
            census[m["league"]]["ext_matched_without_history"] += 1
            continue
        # Polymarket
        pm = build_pm(plan[m["game_key"]], pm_hist, e, pm_home, pm_away) if m["game_key"] in plan else {}
        for k, v in pm.items():
            if isinstance(v, dict) and v.get("fidelities"):
                for fd in v["fidelities"]:
                    fid_counter[fd] += 1
        # Sportradar plays (hero games only)
        plays = None
        if m["sr_game_id"] in sr_pbp:
            plays = extract_plays(sr_pbp[m["sr_game_id"]], m["league"])
        # reference book: Pinnacle if it has a close within 6 h of kickoff, else consensus
        def book_close(book, role="ml"):
            b = oo_books.get(book, {}).get(role)
            if not b or not b.get("close"):
                return None
            return b["close"]
        pin = book_close("Pinnacle")
        pin_close = pin[1] if pin and (kickoff - pin[0]) <= 6 * 3600 else None
        book_closes = {}
        for book in oo_books:
            c = book_close(book)
            if c and (kickoff - c[0]) <= 6 * 3600:
                book_closes[book] = c[1]
        consensus_close = sum(book_closes.values()) / len(book_closes) if book_closes else None
        book_opens = {}
        for book in oo_books:
            olv = oo_books[book].get("ml", {}).get("olv")
            if olv and "home" in olv:
                book_opens[book] = olv["home"]
        hs = pm.get("home_series") or []
        def pm_at(dt):
            s = sample_at(hs, kickoff - dt) if hs else None
            return None if not s or (kickoff - dt - s[0]) > 2 * 3600 else s[1]
        pm_pre = {"t24h": pm_at(24 * 3600), "t6h": pm_at(6 * 3600), "t1h": pm_at(3600), "t10m": pm_at(600), "t1m": pm_at(60)}
        def pm_age(dt):
            s = sample_at(hs, kickoff - dt) if hs else None
            return None if not s else round((kickoff - dt - s[0]) / 60, 1)
        pm_age_min = {"t24h": pm_age(24 * 3600), "t6h": pm_age(6 * 3600), "t1h": pm_age(3600), "t10m": pm_age(600), "t1m": pm_age(60)}
        in_game = [r for r in hs if kickoff <= r[0] <= kickoff + 6 * 3600]
        pm_in = {"min": round(min(r[1] for r in in_game), 4), "max": round(max(r[1] for r in in_game), 4), "n": len(in_game), "last": in_game[-1][1]} if in_game else None
        # strips (Pinnacle no-vig home prob and Polymarket home prob over the final 7 days)
        pin_nv = oo_books.get("Pinnacle", {}).get("ml", {}).get("novig_full") or []
        pin_ts, pin_vals = [r[0] for r in pin_nv], [r[1] for r in pin_nv]
        strip_pin = strip_samples(lambda t: step_value(pin_ts, pin_vals, t), kickoff) if pin_nv else None
        hs_ts, hs_vals = [r[0] for r in hs], [r[1] for r in hs]
        strip_pm = strip_samples(lambda t: step_value(hs_ts, hs_vals, t), kickoff) if hs else None
        # divergence over the final 24 h on a 1-minute grid
        div_max = None
        if pin_nv and hs:
            div_max = 0.0
            for t in range(kickoff - 24 * 3600, kickoff + 1, 60):
                a, b = step_value(pin_ts, pin_vals, t), step_value(hs_ts, hs_vals, t)
                if a is not None and b is not None and (t - sample_at(hs, t)[0]) <= 2 * 3600:
                    div_max = max(div_max, abs(a - b))
            div_max = round(div_max, 4)
        # Pinnacle entry-time snapshots for the backtest lab
        def pin_at(dt):
            v = step_value(pin_ts, pin_vals, kickoff - dt) if pin_nv else None
            return None if v is None else v
        cons_at = {}
        for dt_name, dt in (("t6h", 6 * 3600), ("t1h", 3600), ("t10m", 600)):
            vals = []
            for book in oo_books:
                nv = oo_books[book].get("ml", {}).get("novig_full") or []
                v = step_value([r[0] for r in nv], [r[1] for r in nv], kickoff - dt)
                if v is not None:
                    vals.append(v)
            cons_at[dt_name] = sum(vals) / len(vals) if vals else None
        fee_rate = (pm.get("ml_home") or pm.get("ml_away") or {}).get("fee") or {}
        game = {
            "key": m["game_key"], "league": m["league"], "sport": SPORT.get(m["league"], "soccer"), "kickoff": kickoff, "kickoff_iso": m["start_oo"],
            "sr_scheduled": g["scheduled"], "pm_start": e.get("startTime"), "kickoff_conflict": abs(kickoff - iso_to_ts(g["scheduled"])) > 1200,
            "home": {"name": sr_home["name"], "abbr": oo_home.get("abbreviation") or sr_home.get("alias"), "sr_alias": sr_home.get("alias"), "pm_abbr": pm_home.get("abbreviation")},
            "away": {"name": sr_away["name"], "abbr": oo_away.get("abbreviation") or sr_away.get("alias"), "sr_alias": sr_away.get("alias"), "pm_abbr": pm_away.get("abbreviation")},
            "final": {"home": hp, "away": ap, "home_win": home_win, "periods": [{k: v for k, v in p.items() if k != "id"} for p in (g.get("periods") or [])], "sr_status": g.get("status"), "oo_score": [f["result"]["away"], f["result"]["home"]], "pm_score": e.get("score")},
            "context": {"venue": g.get("venue") or {"name": f.get("venue_name"), "location": f.get("venue_location")}, "weather": g.get("weather") or f.get("weather"), "neutral": g.get("neutral_site") if g.get("neutral_site") is not None else f.get("venue_neutral"),
                        "week": g.get("week") or f.get("season_week"), "season_type": g.get("season_type") or f.get("season_type"), "home_record": f.get("home_record"), "away_record": f.get("away_record"),
                        "home_starter": f.get("home_starter"), "away_starter": f.get("away_starter"), "attendance": g.get("attendance"), "orientation_conflict": m.get("orientation_conflict"), "oo_flipped": flipped},
            "match": {"tier": m["tier"], "oo_fixture_id": m["oo_fixture_id"], "pm_event_id": m["pm_event_id"], "pm_slug": m["pm_slug"], "sr_game_id": m["sr_game_id"], "pm_match": (m["pm_match"] or {}).get("how"), "sr_match": m["sr_match"]["how"], "extension": is_ext},
            "oo": {"meta": oo_meta, "books": oo_books},
            "pm": {"event_id": e.get("id"), "slug": e.get("slug"), "volume_event": e.get("volume"), "closed_time": e.get("closedTime"), "markets": {k: ({kk: (compress_steps(vv, 1800) if kk == "p_side" else vv) for kk, vv in v.items()}) for k, v in pm.items() if isinstance(v, dict)}, "home_series": compress_steps(hs, 1800) if hs else None, "home_series_source": pm.get("home_series_source")},
            "sr": {"game_id": m["sr_game_id"], "plays": plays, "generated_at": g.get("sr_generated_at")},
            "derived": {"pinnacle_close": pin_close, "pinnacle_close_raw": pin, "consensus_close": consensus_close, "book_closes": dict(book_closes),
                        "book_opens": dict(book_opens), "pm_pre": pm_pre, "pm_age_min": pm_age_min, "pm_in_game": pm_in, "divergence_max_24h": div_max,
                        "pin_at": {"t6h": pin_at(6 * 3600), "t1h": pin_at(3600), "t10m": pin_at(600)}, "consensus_at": cons_at,
                        "pm_fee_rate": fee_rate.get("rate"), "pm_fee_exponent": fee_rate.get("exponent"), "pm_fee_type": None},
        }
        for book in game["oo"]["books"].values():
            for role in book.values():
                role.pop("novig_full", None)
        game["ext"] = is_ext
        json.dump(game, open(os.path.join(OUT_GAMES, f"{m['game_key'].replace(':', '_')}.json"), "w"), separators=(",", ":"))
        # full-density Polymarket samples for the analysis stage (the explorer copy above is step-compressed)
        json.dump({"key": m["game_key"], "kickoff": kickoff, "home_series": hs, "markets": {k: v["p_side"] for k, v in pm.items() if isinstance(v, dict) and "p_side" in v}},
                  open(os.path.join(OUT_FULL, f"{m['game_key'].replace(':', '_')}.json"), "w"), separators=(",", ":"))
        if is_ext:
            ext_wall.append({
                "key": m["game_key"], "lg": m["league"], "ko": kickoff, "home": game["home"]["abbr"], "away": game["away"]["abbr"], "hn": game["home"]["name"], "an": game["away"]["name"],
                "hs": hp, "as": ap, "hw": home_win, "tier": m["tier"], "oo": bool(oo_books), "books": sorted(oo_books.keys()),
                "pin": pin_close, "cons": game["derived"]["consensus_close"], "bc": game["derived"]["book_closes"], "bo": game["derived"]["book_opens"],
                "pm": pm_pre, "pma": pm_age_min, "pmin": None, "vol": 0, "div": None, "sp": strip_pin, "spm": None, "pin_at": game["derived"]["pin_at"], "cons_at": cons_at, "fee": None,
                "fid": [], "plays": False, "oe": oo_meta["n_entries"] if oo_meta else 0, "pmn": 0, "flip": flipped, "wk": game["context"]["week"], "ext": True,
            })
            census[m["league"]]["ext_games"] += 1
            census[m["league"]]["ext_with_oo_history"] += 1 if oo_books else 0
            census[m["league"]]["ext_with_pinnacle_close"] += 1 if pin_close is not None else 0
            census[m["league"]]["ext_oo_entries"] += oo_meta["n_entries"] if oo_meta else 0
            continue
        wall.append({
            "key": m["game_key"], "lg": m["league"], "ko": kickoff, "home": game["home"]["abbr"], "away": game["away"]["abbr"], "hn": game["home"]["name"], "an": game["away"]["name"],
            "hs": hp, "as": ap, "hw": home_win, "tier": m["tier"], "oo": bool(oo_books), "books": sorted(oo_books.keys()),
            "pin": pin_close, "cons": game["derived"]["consensus_close"], "bc": game["derived"]["book_closes"], "bo": game["derived"]["book_opens"],
            "pm": pm_pre, "pma": pm_age_min, "pmin": pm_in, "vol": round((pm.get("ml_home") or pm.get("ml_away") or {}).get("volume") or 0), "div": div_max,
            "sp": strip_pin, "spm": strip_pm, "pin_at": game["derived"]["pin_at"], "cons_at": cons_at, "fee": fee_rate.get("rate"),
            "fid": sorted({fd for v in pm.values() if isinstance(v, dict) for fd in (v.get("fidelities") or [])}), "plays": bool(plays),
            "oe": oo_meta["n_entries"] if oo_meta else 0, "pmn": len(hs),
            "flip": flipped, "wk": game["context"]["week"],
        })
        census[m["league"]]["games"] += 1
        census[m["league"]]["with_oo_history"] += 1 if oo_books else 0
        census[m["league"]]["with_pm_history"] += 1 if hs else 0
        census[m["league"]]["with_pinnacle_close"] += 1 if pin_close is not None else 0
        census[m["league"]]["with_plays"] += 1 if plays else 0
        census[m["league"]]["plays"] += len(plays) if plays else 0
        census[m["league"]]["oo_entries"] += oo_meta["n_entries"] if oo_meta else 0
        census[m["league"]]["pm_samples"] += len(hs)
        census[m["league"]]["pm_samples_all_markets"] += sum((v.get("n_samples") or 0) for v in pm.values() if isinstance(v, dict))
        census[m["league"]]["pm_markets"] += sum(1 for v in pm.values() if isinstance(v, dict) and v.get("n_samples"))
        census[m["league"]]["pm_volume_ml"] += round((pm.get("ml_home") or pm.get("ml_away") or {}).get("volume") or 0)
    wall.sort(key=lambda w: (w["lg"], w["ko"]))
    ext_wall.sort(key=lambda w: (w["lg"], w["ko"]))
    ext_window = [ext_doc["window_utc"][0], ext_doc["window_utc"][1]] if ext_matches else None
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "window": [WINDOW_START, WINDOW_END], "games": wall, "ext_window": ext_window, "ext_games": ext_wall}, open(os.path.join(DER, "wall.json"), "w"), separators=(",", ":"))
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "window_utc": [WINDOW_START, WINDOW_END], "n_games": len(wall),
        "extension": {"window_utc": ext_window, "n_games_with_history": len(ext_wall), "n_matched": len(ext_matches), "sources": ["OpticOdds", "Sportradar"], "note": "sportsbook-only; no Polymarket markets were fetched for this period"} if ext_matches else None,
        "census": {lg: dict(c) for lg, c in sorted(census.items())}, "pm_fidelity_minutes_games": dict(fid_counter),
        "books_requested": ["Pinnacle", "DraftKings", "FanDuel", "BetMGM", "Caesars"],
        "notes": ["Polymarket prices are sampled CLOB prices (1m lookback: 10-min fidelity; 1w lookback: 5-min; 1d: 1-min).",
                  "OpticOdds history retention is a rolling two months; entries end at kickoff (a few land seconds after).",
                  "Closing = last sportsbook entry at or before kickoff; opening = vendor OLV; no-vig = multiplicative."],
    }
    json.dump(manifest, open(os.path.join(DER, "manifest.json"), "w"), indent=1)
    print(json.dumps(manifest["census"], indent=1))
    print("games:", len(wall), "fidelities:", dict(fid_counter))


def period_label(p):
    """Human label for a Sportradar period object: Q1-Q4 / OT / P1-P3 / H1-H2, from period_type + number."""
    pt = (p.get("period_type") or p.get("type") or "").lower()
    n = p.get("number")
    if pt == "overtime":
        return "OT" if (n or 1) == 1 else f"OT{n}"
    if pt == "quarter":
        return f"Q{n}"
    if pt == "period":
        return f"P{n}"
    if pt == "half":
        return f"H{n}"
    if pt == "shootout":
        return "SO"
    return f"Q{n}" if n is not None else ""


def extract_plays(resp_by_kind, league):
    """Scoring-relevant plays with wall clocks from Sportradar pbp (NFL/NCAAF/NBA/WNBA/NHL/MLB) or soccer timeline."""
    plays = []
    r = resp_by_kind.get("pbp") or resp_by_kind.get("timeline") or resp_by_kind.get("summary")
    if not r:
        return None
    d = r["data"].get("data", r["data"])
    kind = "pbp" if "pbp" in resp_by_kind else ("timeline" if "timeline" in resp_by_kind else "summary")
    if league in ("nfl", "ncaaf") and kind == "pbp":
        for p in d.get("periods") or []:
            for pp in p.get("pbp") or []:
                evs = pp.get("events") if pp.get("type") == "drive" else [pp]
                for ev in evs or []:
                    if not ev.get("wall_clock"):
                        continue
                    plays.append({"t": iso_to_ts(ev["wall_clock"]), "period": p.get("number"), "pl": period_label(p), "clock": ev.get("clock"), "hp": ev.get("home_points"), "ap": ev.get("away_points"),
                                  "type": ev.get("play_type") or ev.get("event_type") or ev.get("type"), "scoring": bool(ev.get("scoring_play")), "desc": (ev.get("description") or "")[:140]})
    elif league in ("nba", "wnba") and kind == "pbp":
        for p in d.get("periods") or []:
            for ev in p.get("events") or []:
                if not ev.get("wall_clock"):
                    continue
                plays.append({"t": iso_to_ts(ev["wall_clock"]), "period": p.get("number"), "pl": period_label(p), "clock": ev.get("clock"), "hp": ev.get("home_points"), "ap": ev.get("away_points"),
                              "type": ev.get("event_type"), "scoring": ev.get("event_type") in ("twopointmade", "threepointmade", "freethrowmade"), "desc": (ev.get("description") or "")[:140]})
    elif league == "nhl" and kind == "pbp":
        for p in d.get("periods") or []:
            for ev in p.get("events") or []:
                if not ev.get("wall_clock"):
                    continue
                plays.append({"t": iso_to_ts(ev["wall_clock"]), "period": p.get("number"), "pl": period_label(p), "clock": ev.get("clock"), "hp": ev.get("home_points"), "ap": ev.get("away_points"),
                              "type": ev.get("event_type"), "scoring": ev.get("event_type") == "goal", "desc": (ev.get("description") or "")[:140]})
    elif league == "mlb" and kind == "pbp":
        # MLB pbp: game.innings[].halfs[].events[].at_bat.events[] (pitches/steals) with wall_clock {start_time, end_time}
        # and a running score {home_team_runs, away_team_runs}; a scoring play = the first event where the score changes.
        g = d.get("game", d)
        prev = None
        for inn in g.get("innings") or []:
            for half in inn.get("halfs") or []:
                for ev in half.get("events") or []:
                    at = ev.get("at_bat")
                    if not at:
                        continue
                    for e2 in at.get("events") or []:
                        wc = e2.get("wall_clock")
                        wc = wc.get("end_time") or wc.get("start_time") if isinstance(wc, dict) else wc
                        if not wc:
                            continue
                        sc = e2.get("score") or {}
                        hp, ap = sc.get("home_team_runs"), sc.get("away_team_runs")
                        cur = (hp, ap) if hp is not None else None
                        scoring = bool(cur and prev is not None and cur != prev)
                        if cur is not None and prev is None and (hp or ap):
                            scoring = True
                        if cur is not None:
                            prev = cur
                        # keep every at-bat-ending event and every scoring event (pitch-level detail is too dense to plot)
                        if not scoring and not (e2.get("flags") or {}).get("is_ab_over"):
                            continue
                        plays.append({"t": iso_to_ts(wc), "period": inn.get("number"), "pl": f"{'Top' if half.get('half') == 'T' else 'Bot'} {inn.get('number')}", "clock": "", "hp": hp, "ap": ap,
                                      "type": e2.get("type"), "scoring": scoring, "desc": (at.get("description") or "")[:140]})
    elif kind == "timeline":
        for ev in d.get("timeline") or []:
            if not ev.get("time"):
                continue
            plays.append({"t": iso_to_ts(ev["time"]), "period": ev.get("period"), "pl": ("ET" if (ev.get("period_type") or "") == "overtime" else "PEN" if (ev.get("period_type") or "") == "penalties" else f"H{ev.get('period')}" if ev.get("period") else ""), "clock": ev.get("match_clock") or "", "hp": ev.get("home_score"), "ap": ev.get("away_score"),
                          "type": ev.get("type"), "scoring": ev.get("type") in ("score_change",), "desc": (ev.get("type") or "")[:140]})
    plays.sort(key=lambda p: p["t"])
    return plays or None


if __name__ == "__main__":
    main()
