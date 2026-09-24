"""Phase 6 acceptance: how soon relevance order finds 95% of a review's includes.

Replays each labelled SYNERGY review (fetched by `benchmarks/synergy.py`) as one reviewer
screening it in Winnow, using the ranking code the product runs:

- random order until there are 5 includes and 5 excludes (guide 8.10), then
- relevance order, retrained after every 25 decisions, with one record in twenty taken
  from random order instead (the 5% exploration of guide 9.2).

It reports the records screened to find 95% of the includes against what random order
needs on average, and checks the stopping-rule helper where it would first speak up.

    python -m benchmarks.ranking                 # every fetched dataset, 5 runs each
    python -m benchmarks.ranking Sep_2021 --runs 1
"""

import argparse
import csv
import json
import math
import random
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.ranking.features import Corpus, build, text_of
from app.ranking.model import MIN_EACH, can_train, rank
from app.ranking.stopping import estimate_remaining, excluded_in_a_row

DATA = Path(__file__).parent / "data" / "synergy"
RETRAIN_EVERY = 25
EXPLORE_EVERY = 20
TARGET_RECALL = 0.95
STOP_AFTER = 200

csv.field_size_limit(sys.maxsize)


@dataclass
class Run:
    screened_for_target: int
    stop_fired_at: int | None = None
    recall_at_stop: float | None = None
    remaining_at_stop: int | None = None
    estimate_at_stop: tuple[float, int, int] | None = None
    curve: list[int] = field(default_factory=list)


@dataclass
class Result:
    dataset: str
    records: int
    includes: int
    vectorise_seconds: float
    random_expected: float
    runs: list[Run]
    variant: str

    @property
    def median(self) -> float:
        return statistics.median(run.screened_for_target for run in self.runs)


def load(path: Path) -> tuple[list[str], list[str], dict[str, int]]:
    keys: list[str] = []
    texts: list[str] = []
    labels: dict[str, int] = {}
    with path.open(encoding="utf-8") as source:
        for row in csv.DictReader(source):
            keys.append(row["openalex_id"])
            keywords = [word for word in row["keywords"].split("; ") if word]
            texts.append(text_of(row["title"], row["abstract"], keywords))
            labels[row["openalex_id"]] = int(row["label"])
    return keys, texts, labels


def expected_random(records: int, includes: int, target: int) -> float:
    """Records screened, on average, before the target-th include in a random order."""
    return target * (records + 1) / (includes + 1)


def simulate(
    corpus: Corpus[str],
    truth: dict[str, int],
    *,
    seed: int,
    explore: bool,
    min_each: int = MIN_EACH,
) -> Run:
    rng = random.Random(seed)
    shuffled = list(corpus.keys)
    rng.shuffle(shuffled)
    includes = sum(truth.values())
    target = math.ceil(TARGET_RECALL * includes)

    labels: dict[str, int] = {}
    order: list[bool] = []
    unseen = set(corpus.keys)
    ranked: list[str] = []
    ranked_cursor = 0
    since_training = RETRAIN_EVERY
    random_cursor = 0
    reached: int | None = None
    stop: tuple[int, float, int, tuple[float, int, int]] | None = None
    ranked_from: int | None = None
    found = 0

    def take_random() -> str:
        nonlocal random_cursor
        while shuffled[random_cursor] not in unseen:
            random_cursor += 1
        return shuffled[random_cursor]

    while unseen and (reached is None or stop is None):
        trained = can_train(labels, min_each=min_each)
        if trained and since_training >= RETRAIN_EVERY:
            pending = list(unseen)
            scores = rank(corpus, labels, pending, with_auc=False, min_each=min_each).scores
            ranked = sorted(pending, key=lambda key: (-scores[key], key))
            ranked_cursor = 0
            since_training = 0
        if not trained or (explore and (len(order) + 1) % EXPLORE_EVERY == 0):
            pick = take_random()
        else:
            while ranked_cursor < len(ranked) and ranked[ranked_cursor] not in unseen:
                ranked_cursor += 1
            pick = ranked[ranked_cursor] if ranked_cursor < len(ranked) else take_random()

        unseen.discard(pick)
        labels[pick] = truth[pick]
        order.append(truth[pick] == 1)
        found += truth[pick]
        since_training += 1
        if reached is None and found >= target:
            reached = len(order)
        if ranked_from is None and trained:
            ranked_from = len(order) - 1
        if stop is None and trained and excluded_in_a_row(order) >= STOP_AFTER:
            estimate = estimate_remaining(order, len(unseen), ranked_from=ranked_from or 0)
            stop = (
                len(order),
                found / includes,
                includes - found,
                (round(estimate.expected, 2), estimate.low, estimate.high),
            )
    run = Run(screened_for_target=reached or len(order))
    if stop is not None:
        run.stop_fired_at, run.recall_at_stop, run.remaining_at_stop, run.estimate_at_stop = stop
    run.curve = [index + 1 for index, hit in enumerate(order) if hit]
    return run


def benchmark(name: str, runs: int, variants: dict[str, Callable[..., Run]]) -> list[Result]:
    keys, texts, truth = load(DATA / f"{name}.csv")
    started = time.perf_counter()
    corpus = build(keys, texts)
    seconds = time.perf_counter() - started
    includes = sum(truth.values())
    random_needs = expected_random(len(keys), includes, math.ceil(TARGET_RECALL * includes))
    results = []
    for variant, simulate_one in variants.items():
        done = [simulate_one(corpus, truth, seed=seed) for seed in range(runs)]
        results.append(
            Result(name, len(keys), includes, round(seconds, 2), random_needs, done, variant)
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("datasets", nargs="*")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data" / "results.json")
    parser.add_argument("--compare", action="store_true", help="also run without exploration")
    args = parser.parse_args()
    names = args.datasets or sorted(path.stem for path in DATA.glob("*.csv"))

    variants: dict[str, Callable[..., Run]] = {
        "winnow": lambda corpus, truth, seed: simulate(corpus, truth, seed=seed, explore=True)
    }
    if args.compare:
        variants["no exploration"] = lambda corpus, truth, seed: simulate(
            corpus, truth, seed=seed, explore=False
        )
        variants["train from 1+1"] = lambda corpus, truth, seed: simulate(
            corpus, truth, seed=seed, explore=True, min_each=1
        )

    everything: list[Result] = []
    print(
        f"{'dataset':26} {'variant':15} {'records':>8} {'incl':>5} {'relevance':>10} "
        f"{'random':>8} {'saved':>6} {'WSS@95':>7}"
    )
    for name in names:
        for result in benchmark(name, args.runs, variants):
            everything.append(result)
            saved = 1 - result.median / result.random_expected
            wss = (result.records - result.median) / result.records - (1 - TARGET_RECALL)
            print(
                f"{name:26} {result.variant:15} {result.records:8,} {result.includes:5} "
                f"{result.median:10,.0f} {result.random_expected:8,.0f} {saved:6.0%} {wss:7.1%}",
                flush=True,
            )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            [asdict(r) | {"median": r.median} for r in everything],
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
