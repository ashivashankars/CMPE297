"""Metrics shared by every lab (RSIGym-style RSI-Index and friends)."""
from __future__ import annotations

import numpy as np


def gap_closed(baseline: float, final: float, ceiling: float = 1.0) -> float:
    """Fraction of the remaining gap to the ceiling that an improver closed (can be negative)."""
    if ceiling - baseline <= 1e-12:
        return 0.0
    return (final - baseline) / (ceiling - baseline)


def rsi_index(pairs: list[tuple[float, float]], ceiling: float = 1.0) -> float:
    """RSIGym's RSI-Index: mean fraction of remaining gap closed across benchmarks/runs."""
    return float(np.mean([gap_closed(b, f, ceiling) for b, f in pairs]))


def mean_ci(xs) -> str:
    xs = np.asarray(xs, dtype=float)
    if len(xs) < 2:
        return f"{xs.mean():.3f}"
    half = 1.96 * xs.std(ddof=1) / np.sqrt(len(xs))
    return f"{xs.mean():.3f} ± {half:.3f}"


def paired_sign_test(a, b) -> str:
    """How often a beats b across paired seeds (ties ignored) and the two-sided sign-test p."""
    from math import comb
    wins = sum(x > y for x, y in zip(a, b))
    losses = sum(x < y for x, y in zip(a, b))
    n = wins + losses
    if n == 0:
        return "all ties"
    k = min(wins, losses)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
    return f"{wins} wins / {losses} losses / {len(a) - n} ties (sign-test p={p:.3f})"
