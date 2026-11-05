"""Shared normalization used by the dataset builder and the independent recomputation check.

Conventions (stated once, applied everywhere):
  * American odds -> implied probability: p = 100/(o+100) if o > 0 else -o/(-o+100).
  * No-vig: multiplicative normalization across the market's selections at the same instant,
    p_i / sum_j p_j (2-way for moneyline/spread/total in US sports, 3-way for soccer moneyline).
  * A sportsbook price is a step function: it holds until the sportsbook's next entry.
  * The no-vig series changes only when any selection changes; it is evaluated on the union of
    the selections' entry timestamps (seconds, UTC).
  * "Closing" = state of the step function at the kickoff instant (last entry with t <= kickoff).
  * "Opening" = vendor OLV price pair (OpticOdds `olv`), no-vigged the same way.
  * Polymarket `p` is a sampled CLOB price taken directly as a probability (labelled as such).
"""
import unicodedata
import re
from bisect import bisect_right


def american_to_prob(o):
    o = float(o)
    return 100.0 / (o + 100.0) if o > 0 else (-o) / ((-o) + 100.0)


def prob_to_american(p):
    if p <= 0 or p >= 1:
        return None
    return round(-100.0 * p / (1.0 - p)) if p >= 0.5 else round(100.0 * (1.0 - p) / p)


def prob_to_decimal(p):
    return None if p <= 0 else 1.0 / p


def norm_name(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("&", " and ").replace("'", "").replace("\u2019", "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def step_value(ts, vals, t):
    """Value of a step function (sorted timestamps `ts`, values `vals`) at time t; None before the first entry."""
    i = bisect_right(ts, t)
    return vals[i - 1] if i > 0 else None


def novig_from_prices(prices):
    """prices: list of American odds (one per selection) -> list of no-vig probabilities."""
    ps = [american_to_prob(o) for o in prices]
    s = sum(ps)
    return [p / s for p in ps]


def novig_series(selections, t_max=None, require_points_match=False):
    """selections: dict name -> list of (t, price, points) sorted by t.
    Returns list of (t, {name: novig_prob}, {name: points}) evaluated on the union of timestamps.
    If require_points_match (spreads): only emit when the two lines are mirror images (|a + b| < 1e-9).
    """
    names = list(selections)
    ts_all = sorted({t for n in names for (t, _, _) in selections[n] if t_max is None or t <= t_max})
    idx = {n: ([e[0] for e in selections[n]], selections[n]) for n in names}
    out = []
    for t in ts_all:
        cur = {}
        ok = True
        for n in names:
            ts, ents = idx[n]
            i = bisect_right(ts, t)
            if i == 0:
                ok = False
                break
            cur[n] = ents[i - 1]
        if not ok:
            continue
        if require_points_match and len(names) == 2:
            a, b = [cur[n][2] for n in names]
            if a is None or b is None or abs(float(a) + float(b)) > 1e-9:
                continue
        nv = novig_from_prices([cur[n][1] for n in names])
        out.append((t, dict(zip(names, nv)), {n: cur[n][2] for n in names}))
    return out


def dedup_entries(entries):
    """Drop consecutive entries whose (price, points) do not change."""
    out = []
    for e in entries:
        if out and out[-1][1] == e[1] and out[-1][2] == e[2]:
            continue
        out.append(e)
    return out


def brier(p, y):
    return (p - y) ** 2


def logloss(p, y, eps=1e-6):
    import math
    p = min(max(p, eps), 1 - eps)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def pm_taker_fee(shares, price, rate, exponent=1):
    """Polymarket taker fee: shares × rate × (p × (1 − p))^exponent (docs.polymarket.com/trading/fees)."""
    return shares * rate * (price * (1.0 - price)) ** exponent
