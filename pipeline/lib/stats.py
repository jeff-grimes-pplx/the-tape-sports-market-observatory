"""Small, dependency-free statistics helpers (deterministic seeds everywhere)."""
import math
import random


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def sd(xs):
    xs = list(xs)
    n = len(xs)
    if n < 2:
        return None
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def quantile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    pos = (len(xs) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return xs[lo] if lo == hi else xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


def bootstrap_ci(values, stat=mean, n_boot=2000, seed=9, alpha=0.05):
    """Percentile bootstrap CI of `stat` over resamples of `values` (list of numbers or tuples)."""
    values = list(values)
    if len(values) < 2:
        return (None, None)
    rng = random.Random(seed)
    n = len(values)
    stats = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        s = stat(sample)
        if s is not None:
            stats.append(s)
    if not stats:
        return (None, None)
    return (quantile(stats, alpha / 2), quantile(stats, 1 - alpha / 2))


def wilson_ci(k, n, z=1.959964):
    if n == 0:
        return (None, None)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def max_drawdown(pnls):
    peak = 0.0
    cum = 0.0
    mdd = 0.0
    for x in pnls:
        cum += x
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    return mdd


def shuffled_placebo(outcomes_fn, bets, n_shuffle=500, seed=17):
    """bets: list of dicts with 'q' (price paid), 'fee', 'win' (0/1). Shuffle `win` labels across bets and
    recompute ROI each time; returns dict with placebo mean, 2.5/97.5 percentiles and one-sided p-value."""
    rng = random.Random(seed)
    wins = [b["win"] for b in bets]
    actual = outcomes_fn(bets)
    rois = []
    for _ in range(n_shuffle):
        rng.shuffle(wins)
        rois.append(outcomes_fn([dict(b, win=w) for b, w in zip(bets, wins)]))
    p = sum(1 for r in rois if r >= actual) / len(rois) if rois else None
    return {"placebo_mean_roi": mean(rois), "placebo_p2_5": quantile(rois, 0.025), "placebo_p97_5": quantile(rois, 0.975), "p_value_one_sided": p, "n_shuffles": n_shuffle}
