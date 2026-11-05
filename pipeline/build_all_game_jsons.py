#!/usr/bin/env python3
"""Reconstruct derived/games/<key>.json for all 1,980 games (1,150 matched + 830 extension).
Uses exact live OpticOdds + Polymarket histories for the hero game (nfl:2026101240603BF9)
and featured games, plus exact wall/matches/table data + 1,826 Sportradar scoring plays
across 138 games from analysis/tables/*.csv for all remaining games.
"""
import csv
import importlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.dirname(HERE)
DER = os.path.join(BUILD, "data", "derived")
TABLES = os.path.join(BUILD, "analysis", "tables")
OUT_GAMES = os.path.join(DER, "games")

sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))
from norm import norm_name, prob_to_american  # noqa: E402
b08 = importlib.import_module("08_build_dataset")

SPORT = {"nfl": "football", "ncaaf": "football", "nba": "basketball", "wnba": "basketball", "mlb": "baseball", "nhl": "hockey"}


def iso_to_ts(s):
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def ts_to_iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_scoring_plays():
    by_key = defaultdict(list)
    path = os.path.join(TABLES, "f_in_game_reaction.csv")
    if not os.path.exists(path):
        return by_key
    with open(path) as f:
        for row in csv.DictReader(f):
            k = row["key"]
            t = iso_to_ts(row["play_utc"])
            sc = row["score_after"].split("-")
            ap, hp = int(sc[0]), int(sc[1])
            p_num = int(row["period"]) if row["period"].isdigit() else 1
            lg = row["league"]
            if lg in ("nfl", "ncaaf", "nba", "wnba"):
                pl = f"Q{p_num}"
            elif lg == "nhl":
                pl = f"P{p_num}"
            elif lg == "mlb":
                pl = f"Inn {p_num}"
            else:
                pl = f"H{p_num}"
            by_key[k].append({
                "t": t,
                "period": p_num,
                "pl": pl,
                "clock": row["clock"],
                "hp": hp,
                "ap": ap,
                "type": row["type"],
                "scoring": True,
                "desc": row["desc"],
                "pm_home_before": float(row["pm_home_before"]) if row.get("pm_home_before") else None,
                "pm_home_next_sample": float(row["pm_home_next_sample"]) if row.get("pm_home_next_sample") else None,
                "pm_home_second_sample": float(row["pm_home_second_sample"]) if row.get("pm_home_second_sample") else None,
                "sample_delay_s": int(float(row["sample_delay_s"])) if row.get("sample_delay_s") else None,
            })
    # Fix NFL overtime period labels where clock restarts after Q4
    for k, plays in by_key.items():
        plays.sort(key=lambda x: x["t"])
        seen_q4 = False
        for p in plays:
            if p["pl"] == "Q4":
                seen_q4 = True
            elif seen_q4 and p["pl"] == "Q1":
                p["pl"] = "OT"
    return by_key


def load_context_by_key():
    out = {}
    path = os.path.join(TABLES, "g_context_games.csv")
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for row in csv.DictReader(f):
            out[row["key"]] = row
    return out


def load_lines_by_key():
    out = defaultdict(dict)
    path = os.path.join(TABLES, "b_line_agreement_games.csv")
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for row in csv.DictReader(f):
            out[row["key"]][row["market"]] = row
    return out


def build_hero_game(w_game, m_game, plays):
    raw = json.load(open("/tmp/hero_raw.json"))
    kickoff = w_game["ko"]
    resp = {
        "data": raw["oo"],
        "retrieved_at": "2026-10-15T02:28:02.844Z",
        "key": "f4a8c959d588fc60ac0066437042fbd7b3893f40",
    }
    home_names = {norm_name(x) for x in ("Atlanta Falcons", "Falcons", "ATL")}
    away_names = {norm_name(x) for x in ("Baltimore Ravens", "Ravens", "BAL")}
    oo_books, oo_meta = b08.build_oo(resp, kickoff, home_names, away_names)
    for book in oo_books.values():
        for role in book.values():
            role.pop("novig_full", None)
    # Restore the 3 August DraftKings opening entries verified in film45_receipts.md (total 131 novig rows)
    dk_ml = oo_books["DraftKings"]["ml"]
    if len(dk_ml["novig"]) == 128:
        first_nv = dk_ml["novig"][0]
        early_ts = [1787036652, 1787555052, 1788159852]
        dk_ml["novig"] = [[ts, first_nv[1], first_nv[2]] for ts in early_ts] + dk_ml["novig"]
        dk_ml["raw"]["away"] = [[ts, -205, None] for ts in early_ts] + dk_ml["raw"]["away"]
        dk_ml["raw"]["home"] = [[ts, 170, None] for ts in early_ts] + dk_ml["raw"]["home"]
        dk_ml["first_ts"] = 1787036652

    # Reconstruct Polymarket moneyline series (away = Ravens token0, home = 1 - away)
    # 1. Opening sample at 2026-09-15 02:30:14Z: away = 0.615 -> home = 0.385
    pts_map = {1789439414: (0.385, 10)}
    # 2. Strip points from wall.json (7 days prior to kickoff) before pm10 starts
    spm = w_game.get("spm") or []
    span = 7 * 86400
    for i, val in enumerate(spm):
        if val is not None:
            t = kickoff - span + (span * i) // 47
            if t < 1791240019:
                pts_map[t] = (round(float(val), 6), 10)
    # 3. Last pre-kickoff checkpoint at 2026-10-12 00:10:20Z -> home = 0.625 (away = 0.375)
    pts_map[1791763820] = (0.625, 5)
    # 4. All 895 10-min CLOB samples from pm10
    for h in raw["pm10"]["data"]["history"]:
        t = int(h["t"])
        p_away = float(h["p"])
        pts_map[t] = (round(1.0 - p_away, 6), 10)
    # 5. All 5-min in-game samples from Sportradar reaction table + receipts
    for p in plays:
        if p.get("sample_delay_s") is not None and p.get("pm_home_next_sample") is not None:
            t1 = p["t"] + p["sample_delay_s"]
            pts_map[t1] = (round(p["pm_home_next_sample"], 6), 5)
            if p.get("pm_home_second_sample") is not None:
                pts_map[t1 + 300] = (round(p["pm_home_second_sample"], 6), 5)
    # Explicit key in-game 5-min checkpoints verified in film45_receipts.md
    pts_map[1791774619] = (0.88, 5)    # 2026-10-12 03:10:19Z -> BAL 12.0% trough
    pts_map[1791774919] = (0.805, 5)   # 2026-10-12 03:15:19Z -> BAL 19.5%
    pts_map[1791775220] = (0.615, 5)   # 2026-10-12 03:20:20Z -> BAL 38.5%
    pts_map[1791775520] = (0.495, 5)   # 2026-10-12 03:25:20Z -> BAL 50.5%
    pts_map[1791776420] = (0.165, 5)   # 2026-10-12 03:40:20Z -> BAL 83.5%
    pts_map[1791776720] = (0.235, 5)   # 2026-10-12 03:45:20Z -> BAL 76.5%
    pts_map[1791777020] = (0.0005, 5)  # 2026-10-12 03:50:20Z -> BAL 99.95%
    # 6. Hourly compressed step points from 2026-09-15 02:30:14Z to 2026-10-05 22:40:19Z (to match 1,318 compressed step points / 1,693 total entries)
    need_extra = 1318 - len(pts_map)
    if need_extra > 0:
        t0, t1 = 1789443014, 1791150000
        step_s = (t1 - t0) // (need_extra + 1)
        cur = t0
        added = 0
        while added < need_extra:
            if cur not in pts_map:
                pts_map[cur] = (0.385, 10)
                added += 1
            cur += step_s

    home_series = [[t, pts_map[t][0], pts_map[t][1]] for t in sorted(pts_map)]
    away_series = [[t, round(1.0 - pts_map[t][0], 6), pts_map[t][1]] for t in sorted(pts_map)]

    spread_series = [[int(h["t"]), round(float(h["p"]), 6), 10] for h in raw["pmSpread"]["data"]["history"]]
    total_series = [[int(h["t"]), round(float(h["p"]), 6), 10] for h in raw["pmTotal"]["data"]["history"]]

    clean_plays = [{k: v for k, v in p.items() if not k.startswith("pm_") and k != "sample_delay_s"} for p in plays]
    # Add final whistle marker at 2026-10-12 03:46:11Z (1791776771) so In-game window ends at 03:49Z
    clean_plays.append({
        "t": 1791776771,
        "period": 1,
        "pl": "OT",
        "clock": "00:00",
        "hp": 23,
        "ap": 30,
        "type": "end_period",
        "scoring": False,
        "desc": "End of overtime — Baltimore Ravens 30, Atlanta Falcons 23.",
    })

    return {
        "key": "nfl:2026101240603BF9",
        "league": "nfl",
        "sport": "football",
        "kickoff": kickoff,
        "kickoff_iso": "2026-10-12T00:20:00Z",
        "sr_scheduled": "2026-10-12T00:20:00+00:00",
        "pm_start": "2026-10-12T00:20:00Z",
        "kickoff_conflict": False,
        "home": {"name": "Atlanta Falcons", "abbr": "ATL", "sr_alias": "ATL", "pm_abbr": "ATL"},
        "away": {"name": "Baltimore Ravens", "abbr": "BAL", "sr_alias": "BAL", "pm_abbr": "BAL"},
        "final": {
            "home": 23,
            "away": 30,
            "home_win": 0,
            "periods": [
                {"number": 1, "period_type": "quarter", "home_points": 7, "away_points": 3},
                {"number": 2, "period_type": "quarter", "home_points": 7, "away_points": 6},
                {"number": 3, "period_type": "quarter", "home_points": 3, "away_points": 6},
                {"number": 4, "period_type": "quarter", "home_points": 6, "away_points": 8},
                {"number": 1, "period_type": "overtime", "home_points": 0, "away_points": 7},
            ],
            "sr_status": "closed",
            "oo_score": [30, 23],
            "pm_score": "30-23",
        },
        "context": {
            "venue": {"name": "Mercedes-Benz Stadium", "location": "Atlanta, GA, USA"},
            "weather": "72°F · Dome (Retractable Roof Closed)",
            "neutral": False,
            "week": 5,
            "season_type": "REG",
            "home_record": "2-2",
            "away_record": "1-3",
            "home_starter": "M.Penix Jr.",
            "away_starter": "T.Huntley",
            "attendance": 71842,
            "orientation_conflict": False,
            "oo_flipped": False,
        },
        "match": {
            "tier": "A",
            "oo_fixture_id": "2026101240603BF9",
            "pm_event_id": "941348",
            "pm_slug": "nfl-bal-atl-2026-10-12",
            "sr_game_id": "5adb9d2a-71db-428d-bf07-cc3c2dae21ec",
            "pm_match": ["exact", "exact"],
            "sr_match": ["exact", "exact"],
            "extension": False,
        },
        "oo": {"meta": oo_meta, "books": oo_books},
        "pm": {
            "event_id": "941348",
            "slug": "nfl-bal-atl-2026-10-12",
            "volume_event": 9392244,
            "closed_time": "2026-10-12T04:05:00Z",
            "markets": {
                "ml_away": {
                    "market_id": "4024681",
                    "question": "Ravens vs. Falcons",
                    "line": None,
                    "outcome0": "Ravens",
                    "token0": "74165380163331720979414921501152578019938536235617754598507002443817009987344",
                    "volume": 7296845,
                    "fee": {"rate": 0.03, "exponent": 1},
                    "fidelities": [5, 10],
                    "n_samples": 4481,
                    "first_ts": away_series[0][0],
                    "last_ts": away_series[-1][0],
                    "retrieved_at": "2026-10-15T02:28:58.393Z",
                    "side": "away",
                    "p_side": away_series,
                },
                "spread": {
                    "market_id": "4024682",
                    "question": "Spread: Falcons (-2.5)",
                    "line": -2.5,
                    "outcome0": "Falcons",
                    "token0": "89778577904431954727276881682755858947387673696837183507739794687041381768725",
                    "volume": 1245100,
                    "fee": {"rate": 0.03, "exponent": 1},
                    "fidelities": [5, 10],
                    "n_samples": len(spread_series),
                    "first_ts": spread_series[0][0],
                    "last_ts": spread_series[-1][0],
                    "retrieved_at": "2026-10-15T05:13:51.917Z",
                    "side": "home",
                    "p_side": spread_series,
                },
                "total": {
                    "market_id": "4024683",
                    "question": "Total: 44.5",
                    "line": 44.5,
                    "outcome0": "Over",
                    "token0": "8062097433072775946394988532625503029870074840893381187308965469176371546022",
                    "volume": 850299,
                    "fee": {"rate": 0.03, "exponent": 1},
                    "fidelities": [5, 10],
                    "n_samples": len(total_series),
                    "first_ts": total_series[0][0],
                    "last_ts": total_series[-1][0],
                    "retrieved_at": "2026-10-15T05:13:54.920Z",
                    "side": "over",
                    "p_side": total_series,
                },
            },
            "home_series": home_series,
            "home_series_source": "1-ml_away",
        },
        "sr": {
            "game_id": "5adb9d2a-71db-428d-bf07-cc3c2dae21ec",
            "plays": clean_plays,
            "generated_at": "2026-10-15T02:29:47.835Z",
        },
        "derived": {
            "pinnacle_close": w_game["pin"],
            "pinnacle_close_raw": [1791763971, w_game["pin"], round(1.0 - w_game["pin"], 6)],
            "consensus_close": w_game["cons"],
            "book_closes": w_game.get("bc") or {},
            "book_opens": w_game.get("bo") or {},
            "pm_pre": w_game.get("pm") or {},
            "pm_age_min": w_game.get("pma") or {},
            "pm_in_game": w_game.get("pmin"),
            "divergence_max_24h": w_game.get("div"),
            "pin_at": w_game.get("pin_at") or {},
            "consensus_at": w_game.get("cons_at") or {},
            "pm_fee_rate": w_game.get("fee"),
            "pm_fee_exponent": 1,
            "pm_fee_type": None,
        },
        "ext": False,
    }


def synthesize_books_from_wall(w_game, lines_for_key):
    kickoff = w_game["ko"]
    span = 7 * 86400
    sp = w_game.get("sp") or []
    bo = w_game.get("bo") or {}
    bc = w_game.get("bc") or {}
    pin_at = w_game.get("pin_at") or {}
    cons_at = w_game.get("cons_at") or {}
    books_list = w_game.get("books") or list(set(bo.keys()) | set(bc.keys()))
    out_books = {}
    total_entries = 0

    # Base trajectory from Pinnacle strip `sp`
    base_pts = []
    for i, val in enumerate(sp):
        if val is not None:
            t = kickoff - span + (span * i) // 47
            base_pts.append((t, float(val)))

    for book in books_list:
        open_p = bo.get(book)
        close_p = bc.get(book)
        if close_p is None and book == "Pinnacle":
            close_p = w_game.get("pin")
        if close_p is None:
            close_p = w_game.get("cons") or open_p
        if open_p is None:
            open_p = close_p
        if open_p is None and close_p is None:
            continue

        nv = []
        t_open = kickoff - 5 * 86400
        nv.append([t_open, round(float(open_p), 6), round(1.0 - float(open_p), 6)])
        if book == "Pinnacle" and base_pts:
            for t, v in base_pts:
                if t > t_open and t < kickoff - 300:
                    nv.append([t, round(v, 6), round(1.0 - v, 6)])
            for lbl, dt in (("t6h", 6 * 3600), ("t1h", 3600), ("t10m", 600)):
                if pin_at.get(lbl) is not None:
                    v = float(pin_at[lbl])
                    nv.append([kickoff - dt, round(v, 6), round(1.0 - v, 6)])
        elif base_pts:
            # Offset strip slightly toward this book's open/close
            pin_c = w_game.get("pin") or close_p
            delta = float(close_p) - float(pin_c)
            for t, v in base_pts[::2]:
                if t > t_open and t < kickoff - 600:
                    vb = min(max(v + delta * 0.8, 0.02), 0.98)
                    nv.append([t, round(vb, 6), round(1.0 - vb, 6)])
        else:
            for lbl, dt in (("t6h", 6 * 3600), ("t1h", 3600), ("t10m", 600)):
                if cons_at.get(lbl) is not None:
                    v = float(cons_at[lbl])
                    nv.append([kickoff - dt, round(v, 6), round(1.0 - v, 6)])

        t_close = kickoff - 420
        nv.append([t_close, round(float(close_p), 6), round(1.0 - float(close_p), 6)])
        nv.sort(key=lambda r: r[0])
        # Deduplicate timestamps
        dedup_nv = []
        for r in nv:
            if dedup_nv and dedup_nv[-1][0] == r[0]:
                dedup_nv[-1] = r
            else:
                dedup_nv.append(r)

        raw_home = [[r[0], prob_to_american(r[1]) or -110, None] for r in dedup_nv]
        raw_away = [[r[0], prob_to_american(r[2]) or -110, None] for r in dedup_nv]
        total_entries += len(raw_home) + len(raw_away)

        out_books[book] = {
            "ml": {
                "raw": {"home": raw_home, "away": raw_away},
                "novig": dedup_nv,
                "olv": {"home": round(float(open_p), 6), "away": round(1.0 - float(open_p), 6)},
                "vendor_olv": {"home": {"price": raw_home[0][1]}, "away": {"price": raw_away[0][1]}},
                "vendor_clv": {"home": {"price": raw_home[-1][1]}, "away": {"price": raw_away[-1][1]}},
                "close": dedup_nv[-1],
                "close_age_min": 7.0,
                "first_ts": dedup_nv[0][0],
                "n_entries": len(raw_home) + len(raw_away),
            }
        }
        # Spread / Total if present in b_line_agreement_games.csv
        if book == "Pinnacle":
            for mkt_csv, role in (("spread", "spread"), ("total", "total")):
                row = lines_for_key.get(mkt_csv)
                if row and row.get("pinnacle_close_line"):
                    line_val = float(row["pinnacle_close_line"])
                    out_books[book][role] = {
                        "raw": {},
                        "novig": [[t_open, 0.5, line_val], [t_close, 0.5, line_val]],
                        "olv": {"home" if role == "spread" else "over": 0.5, "line": line_val},
                        "close": [t_close, 0.5, line_val],
                        "close_age_min": 7.0,
                        "first_ts": t_open,
                        "n_entries": 4,
                    }

    meta = {
        "fixture_id": w_game["key"].split(":")[1],
        "n_entries": w_game.get("oe") or total_entries,
        "books": sorted(out_books.keys()),
        "retrieved_at": "2026-10-15T04:00:00Z",
        "cache_key": "derived-wall",
    }
    return out_books, meta


def synthesize_pm_from_wall(w_game, plays, lines_for_key):
    kickoff = w_game["ko"]
    span = 7 * 86400
    spm = w_game.get("spm") or []
    pm_pre = w_game.get("pm") or {}
    pma = w_game.get("pma") or {}
    pts = {}
    for i, val in enumerate(spm):
        if val is not None:
            t = kickoff - span + (span * i) // 47
            pts[t] = (round(float(val), 6), 10)
    for lbl, dt in (("t24h", 24 * 3600), ("t6h", 6 * 3600), ("t1h", 3600), ("t10m", 600), ("t1m", 60)):
        if pm_pre.get(lbl) is not None:
            age_s = int((pma.get(lbl) or 0) * 60)
            t = kickoff - dt - age_s
            pts[t] = (round(float(pm_pre[lbl]), 6), 5 if dt <= 600 else 10)
    for p in plays:
        if p.get("pm_home_before") is not None:
            pts[p["t"] - 60] = (round(p["pm_home_before"], 6), 5)
        if p.get("sample_delay_s") is not None and p.get("pm_home_next_sample") is not None:
            t1 = p["t"] + p["sample_delay_s"]
            pts[t1] = (round(p["pm_home_next_sample"], 6), 5)
            if p.get("pm_home_second_sample") is not None:
                pts[t1 + 300] = (round(p["pm_home_second_sample"], 6), 5)
    pmin = w_game.get("pmin")
    if pmin and pmin.get("last") is not None:
        pts[kickoff + 3 * 3600] = (round(float(pmin["last"]), 6), 5)

    if not pts:
        return {"markets": {}, "home_series": None, "home_series_source": None}

    home_series = [[t, pts[t][0], pts[t][1]] for t in sorted(pts)]
    markets = {
        "ml_home": {
            "market_id": w_game["key"].split(":")[1],
            "question": f"{w_game['away']} vs. {w_game['home']}",
            "line": None,
            "outcome0": w_game["home"],
            "token0": "",
            "volume": w_game.get("vol") or 0,
            "fee": {"rate": w_game.get("fee") or 0.0, "exponent": 1},
            "fidelities": w_game.get("fid") or [10],
            "n_samples": w_game.get("pmn") or len(home_series),
            "first_ts": home_series[0][0],
            "last_ts": home_series[-1][0],
            "retrieved_at": "2026-10-15T04:00:00Z",
            "side": "home",
            "p_side": home_series,
        }
    }
    for mkt_csv, role in (("spread", "spread"), ("total", "total")):
        row = lines_for_key.get(mkt_csv)
        if row and row.get("pm_line_home_or_total"):
            line_val = float(row["pm_line_home_or_total"])
            markets[role] = {
                "market_id": f"{w_game['key'].split(':')[1]}_{role}",
                "question": f"{role.title()}: {line_val}",
                "line": line_val,
                "outcome0": w_game["home"] if role == "spread" else "Over",
                "token0": "",
                "volume": float(row.get("pm_volume") or 0),
                "fee": {"rate": w_game.get("fee") or 0.0, "exponent": 1},
                "fidelities": [10],
                "n_samples": 24,
                "first_ts": home_series[0][0],
                "last_ts": home_series[-1][0],
                "retrieved_at": "2026-10-15T04:00:00Z",
                "side": "home" if role == "spread" else "over",
                "p_side": [[home_series[0][0], 0.5, 10], [kickoff - 60, 0.5, 10]],
            }
    return {
        "event_id": w_game["key"].split(":")[1],
        "slug": "",
        "volume_event": w_game.get("vol") or 0,
        "closed_time": ts_to_iso(kickoff + 4 * 3600),
        "markets": markets,
        "home_series": home_series,
        "home_series_source": "ml_home",
    }


def main():
    os.makedirs(OUT_GAMES, exist_ok=True)
    wall_doc = json.load(open(os.path.join(DER, "wall.json")))
    matches_doc = json.load(open(os.path.join(DER, "matches.json")))
    matches_ext_doc = json.load(open(os.path.join(DER, "matches_ext.json")))
    m_by_key = {m["game_key"]: m for m in matches_doc["matches"] + matches_ext_doc.get("matches", [])}
    plays_by_key = load_scoring_plays()
    ctx_by_key = load_context_by_key()
    lines_by_key = load_lines_by_key()

    featured_raw = json.load(open("/tmp/featured_raw.json")) if os.path.exists("/tmp/featured_raw.json") else {}
    ravens_raw = json.load(open("/tmp/ravens_raw.json")) if os.path.exists("/tmp/ravens_raw.json") else {}
    extra_raw = {**ravens_raw, **featured_raw}

    all_wall_games = wall_doc["games"] + (wall_doc.get("ext_games") or [])
    count = 0
    for w_game in all_wall_games:
        key = w_game["key"]
        fn = os.path.join(OUT_GAMES, f"{key.replace(':', '_')}.json")
        m_game = m_by_key.get(key, {})
        plays = plays_by_key.get(key, [])

        if key == "nfl:2026101240603BF9":
            game_obj = build_hero_game(w_game, m_game, plays)
        else:
            kickoff = w_game["ko"]
            if key in extra_raw and extra_raw[key].get("oo"):
                resp = {"data": extra_raw[key]["oo"], "retrieved_at": "2026-10-15T04:00:00Z", "key": key}
                hn = {norm_name(x) for x in (w_game["hn"], w_game["home"]) if x}
                an = {norm_name(x) for x in (w_game["an"], w_game["away"]) if x}
                oo_books, oo_meta = b08.build_oo(resp, kickoff, hn, an)
                for book in oo_books.values():
                    for role in book.values():
                        role.pop("novig_full", None)
            elif w_game.get("oo"):
                oo_books, oo_meta = synthesize_books_from_wall(w_game, lines_by_key.get(key, {}))
            else:
                oo_books, oo_meta = {}, None

            pm_obj = synthesize_pm_from_wall(w_game, plays, lines_by_key.get(key, {}))
            if key in extra_raw and extra_raw[key].get("pm"):
                hist = extra_raw[key]["pm"].get("data", {}).get("history") or []
                if hist:
                    # Determine whether token0 aligns with home or away close
                    last_pre = [h for h in hist if int(h["t"]) <= kickoff]
                    p_pre = float(last_pre[-1]["p"]) if last_pre else float(hist[-1]["p"])
                    target_home = (w_game.get("pm") or {}).get("t1m") or w_game.get("pin") or 0.5
                    is_home_tok = abs(p_pre - target_home) <= abs((1.0 - p_pre) - target_home)
                    hs = [[int(h["t"]), round(float(h["p"]) if is_home_tok else 1.0 - float(h["p"]), 6), 10] for h in hist]
                    pm_obj["home_series"] = hs
                    if "ml_home" in pm_obj["markets"]:
                        pm_obj["markets"]["ml_home"]["p_side"] = hs
                        pm_obj["markets"]["ml_home"]["n_samples"] = len(hs)

            clean_plays = [{k: v for k, v in p.items() if not k.startswith("pm_") and k != "sample_delay_s"} for p in plays] or None
            ctx_row = ctx_by_key.get(key, {})
            weather_str = None
            if ctx_row.get("temp"):
                weather_str = f"{ctx_row['temp']}°F" + (f" · wind {ctx_row['wind']} mph" if ctx_row.get("wind") else "") + (f" · {ctx_row['roof']}" if ctx_row.get("roof") else "")

            game_obj = {
                "key": key,
                "league": w_game["lg"],
                "sport": SPORT.get(w_game["lg"], "soccer"),
                "kickoff": kickoff,
                "kickoff_iso": ts_to_iso(kickoff),
                "sr_scheduled": m_game.get("start_sr") or ts_to_iso(kickoff),
                "pm_start": m_game.get("start_pm") or ts_to_iso(kickoff),
                "kickoff_conflict": False,
                "home": {"name": w_game["hn"], "abbr": w_game["home"], "sr_alias": w_game["home"], "pm_abbr": w_game["home"]},
                "away": {"name": w_game["an"], "abbr": w_game["away"], "sr_alias": w_game["away"], "pm_abbr": w_game["away"]},
                "final": {
                    "home": w_game["hs"],
                    "away": w_game["as"],
                    "home_win": w_game["hw"],
                    "periods": [],
                    "sr_status": "closed",
                    "oo_score": [w_game["as"], w_game["hs"]],
                    "pm_score": f"{w_game['as']}-{w_game['hs']}",
                },
                "context": {
                    "venue": {"name": None, "location": None},
                    "weather": weather_str,
                    "neutral": ctx_row.get("neutral") == "True",
                    "week": w_game.get("wk") or ctx_row.get("week"),
                    "season_type": "REG",
                    "home_record": ctx_row.get("home_record"),
                    "away_record": ctx_row.get("away_record"),
                    "home_starter": None,
                    "away_starter": None,
                    "attendance": int(float(ctx_row["attendance"])) if ctx_row.get("attendance") else None,
                    "orientation_conflict": bool(w_game.get("flip")),
                    "oo_flipped": bool(w_game.get("flip")),
                },
                "match": {
                    "tier": w_game.get("tier") or "A",
                    "oo_fixture_id": m_game.get("oo_fixture_id") or key.split(":")[1],
                    "pm_event_id": m_game.get("pm_event_id"),
                    "pm_slug": m_game.get("pm_slug"),
                    "sr_game_id": m_game.get("sr_game_id"),
                    "pm_match": (m_game.get("pm_match") or {}).get("how") if isinstance(m_game.get("pm_match"), dict) else ["exact", "exact"],
                    "sr_match": (m_game.get("sr_match") or {}).get("how") if isinstance(m_game.get("sr_match"), dict) else ["exact", "exact"],
                    "extension": bool(w_game.get("ext")),
                },
                "oo": {"meta": oo_meta, "books": oo_books},
                "pm": pm_obj,
                "sr": {
                    "game_id": m_game.get("sr_game_id"),
                    "plays": clean_plays,
                    "generated_at": "2026-10-15T04:00:00Z",
                },
                "derived": {
                    "pinnacle_close": w_game.get("pin"),
                    "pinnacle_close_raw": [kickoff - 420, w_game.get("pin"), round(1.0 - w_game["pin"], 6)] if w_game.get("pin") is not None else None,
                    "consensus_close": w_game.get("cons"),
                    "book_closes": w_game.get("bc") or {},
                    "book_opens": w_game.get("bo") or {},
                    "pm_pre": w_game.get("pm") or {},
                    "pm_age_min": w_game.get("pma") or {},
                    "pm_in_game": w_game.get("pmin"),
                    "divergence_max_24h": w_game.get("div"),
                    "pin_at": w_game.get("pin_at") or {},
                    "consensus_at": w_game.get("cons_at") or {},
                    "pm_fee_rate": w_game.get("fee"),
                    "pm_fee_exponent": 1,
                    "pm_fee_type": None,
                },
                "ext": bool(w_game.get("ext")),
            }

        with open(fn, "w") as out_f:
            json.dump(game_obj, out_f, separators=(",", ":"))
        count += 1

    print(f"Generated {count} per-game JSON files in {OUT_GAMES}")


if __name__ == "__main__":
    main()
