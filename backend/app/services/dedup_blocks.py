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

from app.dedup import Cluster, RecordForDedup
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


def _same_copy_key(record: RecordForDedup) -> tuple[str, int | None, str, str] | None:
    """What makes two records the same export of the same entry: title, year, first
    author's surname and source, all normalised. None when the title is missing."""
    title = normalise_title(record.title_norm or record.title)
    if not title:
        return None
    first = record.authors[0] if record.authors else ""
    surname = normalise_title(first.split(",")[0])
    journal = normalise_title(record.journal or "")
    return (title, record.year, surname, journal)


def split_certain(found: Sequence[Cluster], records: Sequence[RecordForDedup]) -> list[Cluster]:
    """Take the identical copies out of the clusters that need a person.

    Overlapping searches of one database return the same entry again and again: a group
    of an arXiv preprint and a journal chapter can arrive as five identical preprints and
    the chapter. The five are certain; only the preprint-against-chapter question needs a
    reviewer. So each uncertain cluster becomes a certain cluster per set of identical
    copies (merged like any certain cluster) plus a smaller one of what is left to ask.
    """
    by_id = {record.id: record for record in records}
    result: list[Cluster] = []
    for group in found:
        if group.auto_resolvable:
            result.append(group)
            continue
        copies: dict[object, list[uuid.UUID]] = {}
        for member_id in group.members:
            key = _same_copy_key(by_id[member_id]) or member_id
            copies.setdefault(key, []).append(member_id)
        representatives: list[uuid.UUID] = []
        for ids in copies.values():
            keep = (
                group.primary_id
                if group.primary_id in ids
                else min(ids, key=lambda item: (by_id[item].imported_at, item.int))
            )
            representatives.append(keep)
            if len(ids) > 1:
                result.append(
                    Cluster(
                        members=tuple(sorted(ids, key=lambda item: item.int)),
                        score=1.0,
                        primary_id=keep,
                        auto_resolvable=True,
                    )
                )
        if len(representatives) > 1:
            result.append(
                Cluster(
                    members=tuple(sorted(representatives, key=lambda item: item.int)),
                    score=group.score,
                    primary_id=group.primary_id,
                    auto_resolvable=False,
                )
            )
    return result
