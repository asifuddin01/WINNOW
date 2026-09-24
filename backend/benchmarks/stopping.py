"""How well the stopping-rule helper's range holds the truth, on the benchmark's runs.

`benchmarks/ranking.py` keeps, for every run, where each relevant record was found and when
the stopping rule (200 excludes in a row) first spoke up. This replays the helper at that
moment and compares its range with the number of relevant records really left.

    python -m benchmarks.stopping [results.json]
"""

import json
import statistics
import sys
from pathlib import Path

from app.ranking.stopping import estimate_remaining

RESULTS = Path(__file__).parent / "data" / "results.json"


def _first_model(history: list[bool]) -> int:
    """How many decisions it took to have one relevant and one irrelevant record."""
    seen: set[bool] = set()
    for count, found in enumerate(history, start=1):
        seen.add(found)
        if len(seen) == 2:
            return count
    return 0


def main(path: Path) -> None:
    runs = [
        (result["dataset"], result["records"], run)
        for result in json.loads(path.read_text())
        if result["variant"] == "winnow"
        for run in result["runs"]
    ]
    fired = [(name, records, run) for name, records, run in runs if run["stop_fired_at"]]
    inside = short = 0
    widths = []
    errors = []
    recalls = []
    for _, records, run in fired:
        screened = run["stop_fired_at"]
        found = set(run["curve"])
        history = [position in found for position in range(1, screened + 1)]
        # Ranking began once there was one include and one exclude.
        ranked_from = _first_model(history)
        estimate = estimate_remaining(history, records - screened, ranked_from=ranked_from)
        truth = run["remaining_at_stop"]
        inside += estimate.low <= truth <= estimate.high
        short += truth > estimate.high
        widths.append(estimate.high - estimate.low)
        errors.append(abs(estimate.expected - truth))
        recalls.append(run["recall_at_stop"])
    print(f"stopping rule spoke up in {len(fired)} of {len(runs)} runs")
    print(
        f"recall when it did: median {statistics.median(recalls):.1%}, "
        f"lowest {min(recalls):.1%}; at least 95% in {sum(r >= 0.95 for r in recalls)}"
    )
    print(
        f"true number left inside the range: {inside} ({inside / len(fired):.0%}); "
        f"above it: {short} ({short / len(fired):.0%}); median width {statistics.median(widths)}"
    )
    print(f"headline number off by {statistics.median(errors):.1f} at the median")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS)
