#!/usr/bin/env python3
"""Deterministic three-way matcher: OpticOdds fixture ↔ Polymarket event ↔ Sportradar game.

Rules (per league):
  * start times within ±20 minutes (OpticOdds start_date vs Polymarket startTime vs Sportradar scheduled)
  * both teams match, home with home and away with away (a swapped pair is accepted only as tier C and flagged)
  * team similarity: exact normalized name (1.0) > alias-table hit (0.95) > abbreviation equality (0.9)
    > token Jaccard ≥ 0.5 (fuzzy) ; a candidate needs min(team scores) ≥ 0.5 and must be the unique best
    for the fixture AND the unique best for the counterpart (mutual best), otherwise unmatched.
  * confidence tier: A = both teams ≥ 0.9 and |Δt| ≤ 5 min; B = both ≥ 0.9 and |Δt| ≤ 20 min, or one fuzzy;
    C = fuzzy on both sides or swapped home/away. Tier C rows are listed for manual review.
  * manual overrides (pipeline/overrides.json) win over everything; they are recorded with tier "M".
Never fabricates a match: anything that fails the rules stays unmatched and is counted.
"""
import json
import os
import random
import re
import sys
import unicodedata
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("A9_DATA", "/home/user/workspace/a9-data")
DER = os.path.join(DATA, "derived")
LEAGUES = ["nfl", "ncaaf", "mlb", "nba", "nhl", "wnba", "mls", "epl", "laliga", "seriea", "bundesliga", "ligue1", "ucl"]
TOL_MIN = 20

GENERIC = {"1901", "1907", "09", "07", "fc", "cf", "sc", "afc", "ac", "as", "ss", "us", "ssc", "club", "de", "calcio", "the", "fk", "sv", "tsg", "vfb", "vfl", "fsv", "bsc", "cd", "rc", "rcd", "ud", "sd", "osc", "ogc", "aj", "fco", "rb", "1", "04", "05", "1899", "1909", "1913", "1846"}

ALIASES = json.load(open(os.path.join(HERE, "aliases.json"))) if os.path.exists(os.path.join(HERE, "aliases.json")) else {}
OVERRIDES = json.load(open(os.path.join(HERE, "overrides.json"))) if os.path.exists(os.path.join(HERE, "overrides.json")) else {"matches": [], "blocks": []}


def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("&", " and ").replace("'", "").replace("’", "").replace("ø", "o").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def canon(s):
    """Normalized name with alias-table substitution and generic tokens removed."""
    n = norm(s)
    n = ALIASES.get(n, n)
    toks = [t for t in n.split() if t not in GENERIC]
    return " ".join(toks) if toks else n


def tokens(s):
    return set(canon(s).split())


def iso(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(timezone.utc)


def team_score(a, b):
    """a, b: dicts with keys names(list of str), abbr(str|None). Returns (score, how)."""
    ca = {canon(x) for x in a["names"] if x}
    cb = {canon(x) for x in b["names"] if x}
    if ca & cb:
        return 1.0, "exact"
    na = {norm(x) for x in a["names"] if x}
    nb = {norm(x) for x in b["names"] if x}
    for x in na:
        for y in nb:
            if ALIASES.get(x) == y or ALIASES.get(y) == x or (ALIASES.get(x) and ALIASES.get(x) == ALIASES.get(y)):
                return 0.95, "alias"
    if a.get("abbr") and b.get("abbr") and len(a["abbr"]) >= 2 and a["abbr"].lower() == b["abbr"].lower():
        return 0.9, "abbr"
    best = 0.0
    nick = False
    for x in a["names"]:
        for y in b["names"]:
            lx, ly = canon(x).split(), canon(y).split()
            tx, ty = set(lx), set(ly)
            if not tx or not ty:
                continue
            # nickname rule: the shorter name equals the trailing tokens of the longer one ("Sharks" ⊂ "San Jose Sharks")
            short, long_ = (lx, ly) if len(lx) < len(ly) else (ly, lx)
            if short and len(short) < len(long_) and long_[-len(short):] == short:
                nick = True
            j = len(tx & ty) / len(tx | ty)
            best = max(best, j)
    if nick:
        return 0.85, "nickname"
    return (best, "fuzzy") if best >= 0.5 else (best, "none")


def load_sources(lg):
    oo = json.load(open(os.path.join(DER, f"oo_{lg}.json")))["fixtures"]
    pm = json.load(open(os.path.join(DER, f"pm_{lg}.json")))["events"]
    sr = json.load(open(os.path.join(DER, f"sr_{lg}.json")))["games"]
    # Polymarket soccer has a sibling "-more-markets" event per match; keep the main event (has moneyline).
    pm = [e for e in pm if any(m["type"] == "moneyline" for m in e["markets"])]
    return oo, pm, sr


def oo_team(f, side):
    t = (f.get(side) or [{}])[0]
    return {"names": [t.get("name"), f.get(f"{side}_display")], "abbr": t.get("abbreviation")}


def pm_team(e, side):
    t = next((x for x in e["teams"] if x.get("ordering") == side), None)
    if not t:
        return {"names": [], "abbr": None}
    names = [t.get("name")]
    if t.get("alias") and t.get("name") and t["alias"].lower() != t["name"].lower():
        names.append(f"{t['alias']} {t['name']}")
        names.append(t["alias"])
    return {"names": names, "abbr": t.get("abbreviation")}


MASCOTS = {}  # league -> {norm(school + " " + mascot): school}


def build_mascots(lg, pm):
    d = {}
    for e in pm:
        for t in e["teams"]:
            if t.get("alias") and t.get("name") and t["alias"].lower() != t["name"].lower():
                d[norm(f"{t['alias']} {t['name']}")] = t["alias"]
    MASCOTS[lg] = d


def sr_team(g, side):
    t = g.get(side) or {}
    names = [t.get("name"), t.get("sr_name")]
    school = MASCOTS.get(g.get("league"), {}).get(norm(t.get("name") or ""))
    if school:
        names.append(school)
    return {"names": [n for n in names if n], "abbr": t.get("alias")}


def pair_score(a_home, a_away, b_home, b_away):
    """Score both orientations. Returns dict with straight/swapped team scores; the caller picks the orientation
    (better raw team similarity; final scores break ties and can overrule a lenient name rule)."""
    sh, hh = team_score(a_home, b_home)
    sa, ha = team_score(a_away, b_away)
    sh2, hh2 = team_score(a_home, b_away)
    sa2, ha2 = team_score(a_away, b_home)
    return {"straight": (min(sh, sa), (hh, ha), (sh, sa)), "swapped": (min(sh2, sa2), (hh2, ha2), (sh2, sa2))}


def score_pair(x):
    """Return the final score as an unordered pair {a, b} or None."""
    if not x or any(v is None for v in x):
        return None
    try:
        return tuple(sorted(int(v) for v in x))
    except (TypeError, ValueError):
        return None


def ordered_score(x):
    """Final score as an ordered (home, away) pair of ints or None."""
    if not x or any(v is None for v in x):
        return None
    try:
        return tuple(int(v) for v in x)
    except (TypeError, ValueError):
        return None


def match_sources(A, B, a_time, b_time, a_home, a_away, b_home, b_away, a_id, b_id, a_score=None, b_score=None):
    """Mutual-best matching between lists A and B. Returns dict a_id -> match record, and unmatched info.
    Orientation: both home/away orientations are scored; the better team similarity wins, except that an
    asymmetric final score that agrees in exactly one orientation decides it (this catches lenient name rules such
    as "Virginia" vs "West Virginia"). Final-score agreement adds 0.05; disagreement halves the score. A swapped
    orientation means the two vendors label home/away differently (neutral sites); it is flagged, not fabricated."""
    cands = {}
    for a in A:
        ta = iso(a_time(a))
        for b in B:
            dt = abs((iso(b_time(b)) - ta).total_seconds()) / 60.0
            if dt > TOL_MIN:
                continue
            ps = pair_score(a_home(a), a_away(a), b_home(b), b_away(b))
            m_str, m_sw = ps["straight"][0], ps["swapped"][0]
            if max(m_str, m_sw) < 0.5:
                continue
            # final-score evidence (ordered home, away) for both orientations
            sa_, sb_ = (ordered_score(a_score(a)) if a_score else None), (ordered_score(b_score(b)) if b_score else None)
            agree_str = agree_sw = None
            if sa_ and sb_:
                agree_str = sa_ == sb_
                agree_sw = sa_ == (sb_[1], sb_[0])
                if sa_[0] == sa_[1]:  # a drawn game cannot tell orientations apart
                    agree_sw = agree_str
            if agree_str is not None and agree_str != agree_sw:
                swapped = agree_sw and m_sw >= 0.5
                if not swapped and not agree_str and m_sw >= 0.5 and m_sw > m_str:
                    swapped = True
            else:
                swapped = m_sw > m_str
            m, how, (sh, sa) = ps["swapped"] if swapped else ps["straight"]
            if m < 0.5:
                continue
            score_rel = None
            s = m * (0.8 if swapped else 1.0)
            if agree_str is not None:
                agree = agree_sw if swapped else agree_str
                score_rel = "agree" if agree else "disagree"
                s = s + 0.05 if agree else s * 0.5
            if s < 0.5:
                continue
            cands.setdefault(a_id(a), []).append({"b": b_id(b), "score": s, "how": how, "swapped": swapped, "dt_min": dt, "sh": sh, "sa": sa, "score_rel": score_rel})
    best_for_b = {}
    for aid, lst in cands.items():
        lst.sort(key=lambda c: (-c["score"], c["dt_min"]))
        for c in lst:
            cur = best_for_b.get(c["b"])
            if cur is None or (c["score"], -c["dt_min"]) > (cur[1], -cur[2]):
                best_for_b[c["b"]] = (aid, c["score"], c["dt_min"])
    matches, ambiguous = {}, {}
    for aid, lst in cands.items():
        top = lst[0]
        if len(lst) > 1 and lst[1]["score"] == top["score"] and abs(lst[1]["dt_min"] - top["dt_min"]) < 1e-9:
            ambiguous[aid] = lst[:3]
            continue
        if best_for_b.get(top["b"], (None,))[0] != aid:
            ambiguous[aid] = lst[:3]
            continue
        matches[aid] = top
    return matches, ambiguous


def tier(m_pm, m_sr):
    def one(m):
        if m is None:
            return None
        fuzzy = "fuzzy" in m["how"]
        if m["swapped"]:
            # vendors label home/away differently (neutral site); certain when both names are strong and scores agree
            return "B" if (m["sh"] >= 0.9 and m["sa"] >= 0.9 and m.get("score_rel") == "agree") else "C"
        if fuzzy:
            return "C" if m["how"] == ("fuzzy", "fuzzy") else "B"
        if "nickname" in m["how"] or "abbr" in m["how"]:
            return "B"
        return "A" if m["dt_min"] <= 5 else "B"
    tiers = [t for t in (one(m_pm), one(m_sr)) if t]
    if not tiers:
        return None
    return max(tiers)  # worst of the two (A < B < C lexicographically)


def main():
    random.seed(20261015)
    all_matches, stats, unmatched, review, rejected = [], {}, {}, [], []
    for lg in LEAGUES:
        oo, pm, sr = load_sources(lg)
        build_mascots(lg, pm)
        oo = [f for f in oo if f.get("result") and f["result"].get("home") is not None]
        sr_ok = [g for g in sr if g.get("status") in ("closed", "complete")]
        pm_score = lambda e: (e.get("score") or "").split("-") if e.get("score") and "-" in e["score"] else None
        m_pm, amb_pm = match_sources(oo, pm, lambda f: f["start_date"], lambda e: e["startTime"],
                                     lambda f: oo_team(f, "home"), lambda f: oo_team(f, "away"),
                                     lambda e: pm_team(e, "home"), lambda e: pm_team(e, "away"),
                                     lambda f: f["id"], lambda e: e["id"],
                                     a_score=lambda f: (f["result"]["away"], f["result"]["home"]), b_score=pm_score)
        m_sr, amb_sr = match_sources(oo, sr_ok, lambda f: f["start_date"], lambda g: g["scheduled"],
                                     lambda f: oo_team(f, "home"), lambda f: oo_team(f, "away"),
                                     lambda g: sr_team(g, "home"), lambda g: sr_team(g, "away"),
                                     lambda f: f["id"], lambda g: g["id"],
                                     a_score=lambda f: (f["result"]["away"], f["result"]["home"]), b_score=lambda g: (g.get("away_points"), g.get("home_points")))
        # manual overrides
        for ov in OVERRIDES.get("matches", []):
            if ov.get("league") != lg:
                continue
            if ov.get("pm_event_id"):
                m_pm[ov["oo_fixture_id"]] = {"b": ov["pm_event_id"], "score": 1.0, "how": ("manual", "manual"), "swapped": False, "dt_min": 0.0, "sh": 1, "sa": 1, "manual": True}
            if ov.get("sr_game_id"):
                m_sr[ov["oo_fixture_id"]] = {"b": ov["sr_game_id"], "score": 1.0, "how": ("manual", "manual"), "swapped": False, "dt_min": 0.0, "sh": 1, "sa": 1, "manual": True}
        blocked = {(b["league"], b["oo_fixture_id"]) for b in OVERRIDES.get("blocks", [])}
        pm_by_id = {e["id"]: e for e in pm}
        sr_by_id = {g["id"]: g for g in sr_ok}
        n3 = n_pm_only = n_sr_only = n_none = 0
        used_pm, used_sr = set(), set()
        for f in sorted(oo, key=lambda f: f["start_date"]):
            if (lg, f["id"]) in blocked:
                continue
            a, b = m_pm.get(f["id"]), m_sr.get(f["id"])
            if a:
                used_pm.add(a["b"])
            if b:
                used_sr.add(b["b"])
            if a and b:
                n3 += 1
            elif a:
                n_pm_only += 1
            elif b:
                n_sr_only += 1
            else:
                n_none += 1
            if not (a and b):
                unmatched.setdefault(lg, []).append({
                    "oo_fixture_id": f["id"], "start": f["start_date"], "away": f["away_display"], "home": f["home_display"],
                    "has_pm": bool(a), "has_sr": bool(b), "amb_pm": amb_pm.get(f["id"]), "amb_sr": amb_sr.get(f["id"]),
                })
                continue
            t = "M" if (a.get("manual") or b.get("manual")) else tier(a, b)
            e, g = pm_by_id[a["b"]], sr_by_id[b["b"]]
            p_oo = score_pair((f["result"]["away"], f["result"]["home"]))
            p_sr = score_pair((g.get("away_points"), g.get("home_points")))
            p_pm = score_pair(pm_score(e))
            pairs = [p for p in (p_oo, p_sr, p_pm) if p]
            score_consistent = len(set(pairs)) <= 1
            orientation_conflict = bool(a["swapped"] or b["swapped"])
            rec = {
                "game_key": f"{lg}:{f['id']}", "league": lg, "oo_fixture_id": f["id"], "oo_game_id": f.get("game_id"),
                "pm_event_id": e["id"], "pm_slug": e["slug"], "sr_game_id": g["id"],
                "start_oo": f["start_date"], "start_pm": e["startTime"], "start_sr": g["scheduled"],
                "home_oo": f["home_display"], "away_oo": f["away_display"],
                "home_pm": next((x["name"] for x in e["teams"] if x["ordering"] == "home"), None),
                "away_pm": next((x["name"] for x in e["teams"] if x["ordering"] == "away"), None),
                "home_sr": g["home"]["name"] if g.get("home") else None, "away_sr": g["away"]["name"] if g.get("away") else None,
                "score_oo": [f["result"]["away"], f["result"]["home"]], "score_pm": e.get("score"), "score_sr": [g.get("away_points"), g.get("home_points")],
                "tier": t, "pm_match": {k: v for k, v in a.items() if k != "b"}, "sr_match": {k: v for k, v in b.items() if k != "b"},
                "pm_swapped": a["swapped"], "sr_swapped": b["swapped"],
                "score_consistent": score_consistent, "orientation_conflict": orientation_conflict,
            }
            if not score_consistent and t != "M":
                rejected.append(rec)
                n3 -= 1
                n_none += 1
                continue
            all_matches.append(rec)
            if t in ("B", "C") or orientation_conflict:
                review.append(rec)
        stats[lg] = {
            "oo_fixtures_completed": len(oo), "pm_game_events": len(pm), "sr_games_closed": len(sr_ok), "sr_games_all": len(sr),
            "matched_3way": n3, "oo_pm_only": n_pm_only, "oo_sr_only": n_sr_only, "oo_unmatched_both": n_none,
            "pm_unmatched": len(pm) - len(used_pm), "sr_unmatched": len(sr_ok) - len(used_sr),
            "ambiguous_pm": len(amb_pm), "ambiguous_sr": len(amb_sr),
        }
        print(f"{lg:11s} oo={len(oo):4d} pm={len(pm):4d} sr={len(sr_ok):4d} | 3-way={n3:4d} pm-only={n_pm_only:3d} sr-only={n_sr_only:3d} none={n_none:3d} | pm_unm={stats[lg]['pm_unmatched']:3d} sr_unm={stats[lg]['sr_unmatched']:3d} amb={len(amb_pm)}/{len(amb_sr)}")
    tiers = {}
    for m in all_matches:
        tiers[m["tier"]] = tiers.get(m["tier"], 0) + 1
    # score consistency check across sources (final scores should agree)
    disagree = []
    for m in all_matches:
        so, ss = m["score_oo"], m["score_sr"]
        if None not in so and None not in ss and (so[0] != ss[0] or so[1] != ss[1]):
            disagree.append({"game_key": m["game_key"], "oo": so, "sr": ss, "pm": m["score_pm"]})
    sample = random.sample(all_matches, min(40, len(all_matches)))
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "tolerance_minutes": TOL_MIN, "matches": all_matches, "stats": stats, "tiers": tiers,
           "score_disagreements": disagree, "review_rows": review, "rejected_score_conflicts": rejected, "audit_sample_40": [m["game_key"] for m in sample]}
    json.dump(out, open(os.path.join(DER, "matches.json"), "w"))
    json.dump(unmatched, open(os.path.join(DER, "unmatched.json"), "w"), indent=1)
    print("total 3-way matches:", len(all_matches), "tiers:", tiers, "score disagreements:", len(disagree), "rejected (score conflict):", len(rejected))


if __name__ == "__main__":
    main()
