"""Cheap candidate blocking for duplicate detection."""

import uuid
from collections import defaultdict
from collections.abc import Sequence

from app.dedup.normalisation import normalise_title
from app.dedup.types import RecordForDedup


def blocks(records: Sequence[RecordForDedup]) -> dict[str, list[uuid.UUID]]:
    """Group record IDs under the two in-process block keys from guide 9.1.

    The input is a sequence of deduplication records. The output maps namespaced keys to
    sorted, unique IDs: ``title3:`` for the first three title words and
    ``year-title10:`` for year plus the first ten non-whitespace title characters. Records
    without a usable title have no key, and records without a year omit the second key.
    Runtime is O(n*l + k log k), where l is title length and k is emitted memberships.
    The pg_trgm block in the guide is deliberately omitted because the database adapter
    owns that indexed query.
    """

    grouped: defaultdict[str, set[uuid.UUID]] = defaultdict(set)
    for record in records:
        title_norm = normalise_title(record.title_norm or record.title)
        words = title_norm.split()
        if not words:
            continue

        grouped[f"title3:{' '.join(words[:3])}"].add(record.id)
        compact_title = "".join(words)[:10]
        if record.year is not None and compact_title:
            grouped[f"year-title10:{record.year}:{compact_title}"].add(record.id)

    return {
        key: sorted(member_ids, key=lambda member_id: member_id.int)
        for key, member_ids in sorted(grouped.items())
    }
