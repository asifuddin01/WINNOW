"""Fetch labelled reviews from the SYNERGY collection for the ranking benchmark.

SYNERGY (https://github.com/asreview/synergy-dataset, CC0) publishes, for each systematic
review, the OpenAlex id of every record the search found and whether the review included
it. The titles, abstracts and keywords come from the OpenAlex API, as SYNERGY's own tool
fetches them. Nothing here is committed: the data lands in `benchmarks/data/`.

    python benchmarks/synergy.py Appenzeller-Herzog_2019 van_de_Schoot_2018 ...

Standard library only, so it runs on the host or in the api container. It resumes (a
dataset already written is skipped), backs off on 429 and 5xx, and stops before OpenAlex's
daily allowance for callers without a key runs out.
"""

import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

IDS_URL = "https://raw.githubusercontent.com/asreview/synergy-dataset/master/datasets/{name}/{name}_ids.csv"
WORKS_URL = "https://api.openalex.org/works"
DATA = Path(__file__).parent / "data" / "synergy"
PER_REQUEST = 100
# Leave some of the day's allowance for anyone else on this machine.
KEEP_IN_RESERVE = 25


def main(names: list[str]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for name in names:
        target = DATA / f"{name}.csv"
        if target.exists():
            print(f"{name}: already fetched")
            continue
        labels = _labels(name)
        if not labels:
            print(f"{name}: no OpenAlex ids, skipped")
            continue
        works = _works(list(labels))
        _write(target, works, labels)
        missing = len(labels) - len(works)
        includes = sum(labels[w] for w in works)
        print(f"{name}: {len(works):,} records, {includes} includes, {missing} not in OpenAlex")


def _labels(name: str) -> dict[str, int]:
    """OpenAlex id → 1 if the review included the record. A record listed twice counts
    as included if either row says so."""
    with urllib.request.urlopen(IDS_URL.format(name=name), timeout=60) as response:
        rows = csv.DictReader(response.read().decode("utf-8").splitlines())
        labels: dict[str, int] = {}
        for row in rows:
            work = (row.get("openalex_id") or "").rsplit("/", 1)[-1]
            if work:
                labels[work] = max(labels.get(work, 0), int(row["label_included"]))
    return labels


def _works(ids: list[str]) -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for start in range(0, len(ids), PER_REQUEST):
        chunk = ids[start : start + PER_REQUEST]
        query = urllib.parse.urlencode(
            {
                "filter": "openalex:" + "|".join(chunk),
                "select": "id,title,abstract_inverted_index,keywords,publication_year",
                "per-page": str(PER_REQUEST),
            }
        )
        for work in _get(f"{WORKS_URL}?{query}")["results"]:
            found[str(work["id"]).rsplit("/", 1)[-1]] = work
    return found


def _get(url: str) -> dict[str, list[dict[str, object]]]:
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                remaining = int(response.headers.get("x-ratelimit-remaining", "1000"))
                if remaining < KEEP_IN_RESERVE:
                    sys.exit(f"Stopping: {remaining} OpenAlex requests left today.")
                body: dict[str, list[dict[str, object]]] = json.load(response)
                return body
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500:
                raise
            time.sleep(2**attempt)
    sys.exit("OpenAlex kept refusing; try again later.")


def _abstract(inverted: object) -> str:
    """OpenAlex stores abstracts as {word: [positions]}; put the words back in order."""
    if not isinstance(inverted, dict):
        return ""
    positions = [(at, word) for word, places in inverted.items() for at in places]
    return " ".join(word for _, word in sorted(positions))


def _write(target: Path, works: dict[str, dict[str, object]], labels: dict[str, int]) -> None:
    partial = target.with_suffix(".part")
    with partial.open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["openalex_id", "title", "abstract", "keywords", "year", "label"])
        for work_id, work in works.items():
            keywords = work.get("keywords")
            if not isinstance(keywords, list):
                keywords = []
            writer.writerow(
                [
                    work_id,
                    work.get("title") or "",
                    _abstract(work.get("abstract_inverted_index")),
                    "; ".join(str(k.get("display_name", "")) for k in keywords),
                    work.get("publication_year") or "",
                    labels[work_id],
                ]
            )
    partial.rename(target)


if __name__ == "__main__":
    main(sys.argv[1:])
