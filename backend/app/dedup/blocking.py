"""Cheap candidate blocking for duplicate detection."""

import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence

from app.dedup.normalisation import normalise_title
from app.dedup.types import RecordForDedup

# Every pair inside a block is scored, so a block's cost is its size squared: 200 records
# are 19,900 pairs, 5,000 would be 12.5 million and hold the worker for many minutes.
# Titles that share their first words by the thousand ("A systematic review of …",
# "Erratum …", a conference's "Abstracts of …") are therefore split by a longer part of
# the title until each part is small. Duplicates share nearly their whole title, so they
# stay together; records that share a DOI or PubMed id are paired without blocks.
MAX_BLOCK = 200

_Title = tuple[list[str], int | None]
_Level = Callable[[list[str], int | None], str]

# Block A, the first three title words, and then longer and longer parts of the title.
_TITLE_LEVELS: tuple[_Level, ...] = (
    lambda words, _: f"title3:{' '.join(words[:3])}",
    lambda words, _: f"title6:{' '.join(words[:6])}",
    lambda words, _: f"title10:{' '.join(words[:10])}",
    lambda words, _: f"title:{' '.join(words)}",
    lambda words, year: f"title-year:{year}:{' '.join(words)}",
)
# Block B, the year and the first ten title characters, likewise.
_YEAR_LEVELS: tuple[_Level, ...] = (
    lambda words, year: f"year-title10:{year}:{''.join(words)[:10]}",
    lambda words, year: f"year-title20:{year}:{''.join(words)[:20]}",
    lambda words, year: f"year-title40:{year}:{''.join(words)[:40]}",
    lambda words, year: f"year-title:{year}:{''.join(words)}",
)


def blocks(records: Sequence[RecordForDedup]) -> dict[str, list[uuid.UUID]]:
    """Group record IDs under the two in-process block keys from guide 9.1.

    The input is a sequence of deduplication records. The output maps namespaced keys to
    sorted, unique IDs: ``title3:`` for the first three title words and
    ``year-title10:`` for year plus the first ten non-whitespace title characters. Records
    without a usable title have no key, and records without a year omit the second key.
    A block larger than ``MAX_BLOCK`` is split by a longer key (``title6:``,
    ``title10:``, ``title:``, ``title-year:``; ``year-title20:``, ``year-title40:``,
    ``year-title:``), and one still too large after the last is left out.
    Runtime is O(n*l + k log k), where l is title length and k is emitted memberships.
    The pg_trgm block in the guide is deliberately omitted because the database adapter
    owns that indexed query.
    """

    titles: dict[uuid.UUID, _Title] = {}
    for record in records:
        words = normalise_title(record.title_norm or record.title).split()
        if words:
            titles[record.id] = (words, record.year)

    grouped: dict[str, set[uuid.UUID]] = {}
    grouped.update(_split(titles, _TITLE_LEVELS))
    dated = {rid: title for rid, title in titles.items() if title[1] is not None}
    grouped.update(_split(dated, _YEAR_LEVELS))
    return {
        key: sorted(member_ids, key=lambda member_id: member_id.int)
        for key, member_ids in sorted(grouped.items())
    }


def _split(
    titles: Mapping[uuid.UUID, _Title], levels: Sequence[_Level]
) -> dict[str, set[uuid.UUID]]:
    """Group by the first level's key; regroup any group over MAX_BLOCK by the next."""
    done: dict[str, set[uuid.UUID]] = {}
    pending = [set(titles)]
    for level in levels:
        regroup: list[set[uuid.UUID]] = []
        for ids in pending:
            grouped: defaultdict[str, set[uuid.UUID]] = defaultdict(set)
            for record_id in ids:
                words, year = titles[record_id]
                grouped[level(words, year)].add(record_id)
            for key, members in grouped.items():
                if len(members) <= MAX_BLOCK:
                    done[key] = members
                else:
                    regroup.append(members)
        pending = regroup
        if not pending:
            break
    return done
