"""Candidate pairs from the words a title is made of (guide 9.1, block C).

Blocks A and B key on the *start* of a title, so they miss a duplicate whose title was
reordered ("Night shifts and sleep: a cohort study" against "A cohort study of night
shifts and sleep") or given a subtitle. The guide reaches for pg_trgm there, and the
database does hold that index — but an all-pairs trigram join over 50,000 records takes
minutes, which is nowhere near the budget in 2.2.

This does the same job in memory: an inverted index over the distinctive words of each
title, pairing records that share enough of them. It is O(n·k + Σ bucket²) with the
buckets bounded, and it hands its pairs to the same scorer, which decides.
"""

import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence

from app.dedup import RecordForDedup
from app.dedup.normalisation import normalise_title

# Words this common carry no information about which record is which.
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "this",
        "to",
        "with",
        "without",
        "using",
        "via",
        "towards",
        "toward",
        "through",
        "study",
        "trial",
        "review",
        "analysis",
        "report",
        "results",
        "case",
        "cases",
        "new",
        "novel",
        "based",
        "approach",
        "method",
        "methods",
        "evaluation",
        "assessment",
    ]
)
# A word in more than this share of the corpus is treated as a stopword as well: in a
# review about kidneys, "kidney" tells you nothing.
COMMON_SHARE = 0.05
# How many records may share one word before the word is too vague to block on.
MAX_BUCKET = 300
# Words shorter than this are usually initials or units.
MIN_WORD = 4
# Two records must share this many distinctive words to be worth scoring.
MIN_SHARED = 2
# An upper bound on the work, so a pathological corpus degrades rather than hangs.
MAX_PAIRS = 400_000


def _words(record: RecordForDedup) -> list[str]:
    title = normalise_title(record.title_norm or record.title)
    seen: dict[str, None] = {}
    for word in title.split():
        if len(word) >= MIN_WORD and word not in STOPWORDS and not word.isdigit():
            seen.setdefault(word, None)
    return list(seen)


def token_pairs(records: Sequence[RecordForDedup]) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Pairs of records whose titles share at least two distinctive words."""
    if len(records) < 2:
        return []
    words_by_record = {record.id: _words(record) for record in records}
    frequency = Counter(word for words in words_by_record.values() for word in words)
    ceiling = max(MAX_BUCKET, int(len(records) * COMMON_SHARE))

    buckets: defaultdict[str, list[uuid.UUID]] = defaultdict(list)
    for record_id, words in words_by_record.items():
        for word in words:
            if frequency[word] <= ceiling:
                buckets[word].append(record_id)

    shared: Counter[tuple[uuid.UUID, uuid.UUID]] = Counter()
    for members in buckets.values():
        if len(members) < 2 or len(members) > MAX_BUCKET:
            continue
        ordered = sorted(members, key=lambda item: item.int)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                shared[(left, right)] += 1
        if len(shared) > MAX_PAIRS:
            break
    return [pair for pair, count in shared.items() if count >= MIN_SHARED][:MAX_PAIRS]


def merged(*sources: Iterable[tuple[uuid.UUID, uuid.UUID]]) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """One list of candidate pairs, each pair once, whichever block found it."""
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for source in sources:
        for left, right in source:
            seen.add((left, right) if left.int < right.int else (right, left))
    return list(seen)
