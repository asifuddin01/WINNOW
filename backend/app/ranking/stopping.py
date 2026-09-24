"""The stopping-rule helper (guide 8.5): advice, never a decision.

When a reviewer has excluded many records in a row, Winnow says so and estimates how many
relevant records are still unscreened. The estimate assumes that relevant records keep
turning up more and more rarely, as they do while screening in relevance order: the rate
at which the reviewer's decisions found them is fitted as an exponential decay (a Poisson
process, which suits events as rare as relevant records late in screening) and carried on
over the records left.

Only the decisions made in relevance order count: before the first model the queue is in
random order, where finds come at a steady rate, and fitting those made a reviewer who had
found everything read "about 25 left". The decay is fitted to the ranked part and to its
recent half; each has a 90% parametric-bootstrap range, the answer spans both, and the top
is widened by two Poisson standard deviations. On 21 labelled SYNERGY reviews that range
held the true number left 96% of the time (4% above it), and the headline number was off
by 0.8 records at the median (`benchmarks/stopping.py`). See docs/methods.md.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

# The part of the reviewer's history the decay is fitted to: the more recent half, and
# never fewer than this many decisions.
MIN_WINDOW = 200
RESAMPLES = 200
# Fastest thinning considered: finds halve every ~7 records.
MAX_DECAY = 0.1
# Poisson standard deviations added to the top of the range.
MARGIN = 2


@dataclass(frozen=True)
class Estimate:
    expected: float
    low: int
    high: int


def excluded_in_a_row(relevant: Sequence[bool]) -> int:
    """How many of the latest decisions in a row found nothing relevant."""
    count = 0
    for found in reversed(relevant):
        if found:
            break
        count += 1
    return count


def estimate_remaining(
    relevant: Sequence[bool], remaining: int, *, ranked_from: int = 0, seed: int = 0
) -> Estimate:
    """Relevant records expected among the `remaining` unscreened ones, with a range.

    `relevant` is the reviewer's decisions in the order they were made, True for an
    include or a maybe; `ranked_from` is how many of them came before the first model,
    in random order.
    """
    ranked = relevant[ranked_from:] or relevant
    if remaining <= 0 or not ranked:
        return Estimate(expected=0.0, low=0, high=0)
    recent = _estimate(ranked[-max(MIN_WINDOW, len(ranked) // 2) :], remaining, seed)
    whole = _estimate(ranked, remaining, seed)
    low, high = min(recent.low, whole.low), max(recent.high, whole.high)
    high += math.ceil(MARGIN * math.sqrt(high + 1))
    # The number shown always lies inside the range shown beside it.
    expected = min(max(max(recent.expected, whole.expected), low), high)
    return Estimate(expected=expected, low=low, high=high)


def _estimate(history: Sequence[bool], remaining: int, seed: int) -> Estimate:
    """One fit, with its 90% parametric-bootstrap range."""
    window = np.asarray(history, dtype=np.float64)
    rate, decay = _fit(window)
    expected = _carry_on(rate, decay, start=len(window), count=remaining)

    generator = np.random.default_rng(seed)
    positions = np.arange(len(window))
    fitted = np.clip(rate * np.exp(-decay * positions), 0.0, 1.0)
    totals = []
    for _ in range(RESAMPLES):
        resample = (generator.random(len(window)) < fitted).astype(np.float64)
        again = _fit(resample)
        mean = _carry_on(*again, start=len(window), count=remaining)
        totals.append(generator.poisson(mean))
    low, high = np.percentile(totals, [5, 95])
    return Estimate(expected=expected, low=math.floor(low), high=math.ceil(high))


def _fit(window: np.ndarray) -> tuple[float, float]:
    """Maximum-likelihood rate and decay for finds arriving as a Poisson process with
    intensity rate * exp(-decay * x) over positions x of the window.

    For a given decay the best rate is closed-form (finds / sum of exp(-decay * x)), and
    the best decay is where the intensity-weighted mean position equals the mean position
    of the finds — one equation in one unknown, solved by bisection.
    """
    found = float(window.sum())
    if found == 0:
        return 0.0, 0.0
    positions = np.arange(len(window), dtype=np.float64)
    target = float((window * positions).sum()) / found

    def weighted_mean(decay: float) -> float:
        weights = np.exp(-decay * positions)
        return float((positions * weights).sum() / weights.sum())

    if weighted_mean(0.0) <= target:
        # Finds are not thinning out (or are coming faster): no decay.
        decay = 0.0
    else:
        low, high = 0.0, MAX_DECAY
        if weighted_mean(high) > target:
            decay = high
        else:
            for _ in range(60):
                middle = (low + high) / 2
                if weighted_mean(middle) > target:
                    low = middle
                else:
                    high = middle
            decay = (low + high) / 2
    rate = found / float(np.exp(-decay * positions).sum())
    return rate, decay


def _carry_on(rate: float, decay: float, *, start: int, count: int) -> float:
    """The sum of rate * exp(-decay * x) for x from `start` over the next `count`."""
    if rate == 0.0:
        return 0.0
    if decay < 1e-12:
        return rate * count
    first = rate * math.exp(-decay * start)
    return first * (1 - math.exp(-decay * count)) / (1 - math.exp(-decay))
