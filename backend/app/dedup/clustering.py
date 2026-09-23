"""Deterministic union-find clustering for duplicate candidates."""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import combinations, pairwise
from math import isclose

from app.dedup.blocking import blocks
from app.dedup.scoring import _clean_identifier, _conflicting_dois, score_pair
from app.dedup.types import Cluster, RecordForDedup

AUTO_RESOLVE_SCORE = 0.98
MAX_PAIR_SCORE = 1.05


@dataclass(frozen=True, slots=True)
class _Evidence:
    left: uuid.UUID
    right: uuid.UUID
    score: float
    exact: bool


class _UnionFind:
    def __init__(self, records: Sequence[RecordForDedup]) -> None:
        self._parent = {record.id: record.id for record in records}
        self._size = {record.id: 1 for record in records}
        self._dois = {
            record.id: frozenset([doi])
            if (doi := _clean_identifier(record.doi_norm))
            else frozenset()
            for record in records
        }

    def find(self, record_id: uuid.UUID) -> uuid.UUID:
        parent = self._parent[record_id]
        if parent != record_id:
            self._parent[record_id] = self.find(parent)
        return self._parent[record_id]

    def union(self, left: uuid.UUID, right: uuid.UUID) -> bool:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return False

        left_dois = self._dois[left_root]
        right_dois = self._dois[right_root]
        if left_dois and right_dois and left_dois != right_dois:
            return False

        if (self._size[left_root], -left_root.int) < (self._size[right_root], -right_root.int):
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root
        self._size[left_root] += self._size[right_root]
        self._dois[left_root] = left_dois | right_dois
        return True

    def has_doi_conflict(self, left: uuid.UUID, right: uuid.UUID) -> bool:
        left_dois = self._dois[self.find(left)]
        right_dois = self._dois[self.find(right)]
        return bool(left_dois and right_dois and left_dois != right_dois)


def _ordered_pair(left: uuid.UUID, right: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (left, right) if left.int < right.int else (right, left)


def _exact_pairs(
    records: Sequence[RecordForDedup],
) -> tuple[set[tuple[uuid.UUID, uuid.UUID]], set[uuid.UUID]]:
    doi_groups: defaultdict[str, list[uuid.UUID]] = defaultdict(list)
    pmid_groups: defaultdict[str, list[uuid.UUID]] = defaultdict(list)
    by_id = {record.id: record for record in records}

    for record in records:
        if doi := _clean_identifier(record.doi_norm):
            doi_groups[doi].append(record.id)
        if pmid := _clean_identifier(record.pmid):
            pmid_groups[pmid].append(record.id)

    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    ambiguous_ids: set[uuid.UUID] = set()
    for group in doi_groups.values():
        member_ids = sorted(set(group), key=lambda member_id: member_id.int)
        pairs.update((member_ids[0], member_id) for member_id in member_ids[1:])

    # Adjacent PMID edges form a linear chain. DOI stars above retain same-DOI groups if
    # a conflicting DOI splits that chain, while the component guard prevents bridging.
    for group in pmid_groups.values():
        member_ids = sorted(set(group), key=lambda member_id: member_id.int)
        group_dois = {
            doi
            for member_id in member_ids
            if (doi := _clean_identifier(by_id[member_id].doi_norm)) is not None
        }
        if len(group_dois) > 1:
            ambiguous_ids.update(member_ids)
        pairs.update(
            (left_id, right_id)
            for left_id, right_id in pairwise(member_ids)
            if not _conflicting_dois(by_id[left_id], by_id[right_id])
        )
    return pairs, ambiguous_ids


def _candidate_pairs(
    records: Sequence[RecordForDedup],
    extra_pairs: Iterable[tuple[uuid.UUID, uuid.UUID]] = (),
) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    known = {record.id for record in records}
    grouped = blocks(records)
    title_block_by_id: dict[uuid.UUID, str] = {}
    for key, member_ids in grouped.items():
        if not key.startswith("title3:"):
            continue
        title_block_by_id.update(dict.fromkeys(member_ids, key))
        for left_id, right_id in combinations(member_ids, 2):
            yield _ordered_pair(left_id, right_id)

    for key, member_ids in grouped.items():
        if not key.startswith("year-title10:"):
            continue
        for left_id, right_id in combinations(member_ids, 2):
            if title_block_by_id[left_id] != title_block_by_id[right_id]:
                yield _ordered_pair(left_id, right_id)

    # Block C (guide 9.1): pairs the database found by trigram similarity, which catches
    # titles whose first words differ. Scoring and the DOI guards below treat them exactly
    # like a block A or B candidate; ids the caller does not also pass in are ignored.
    for left_id, right_id in extra_pairs:
        if left_id != right_id and left_id in known and right_id in known:
            yield _ordered_pair(left_id, right_id)


def _shares_exact_key(left: RecordForDedup, right: RecordForDedup) -> bool:
    left_doi = _clean_identifier(left.doi_norm)
    right_doi = _clean_identifier(right.doi_norm)
    left_pmid = _clean_identifier(left.pmid)
    right_pmid = _clean_identifier(right.pmid)
    return bool(
        (left_doi is not None and left_doi == right_doi)
        or (left_pmid is not None and left_pmid == right_pmid)
    )


def _meets_threshold(score: float, threshold: float) -> bool:
    return score >= threshold or isclose(score, threshold, rel_tol=0.0, abs_tol=1e-12)


def _field_count(record: RecordForDedup) -> int:
    return sum(
        (
            bool(record.title.strip()),
            any(author.strip() for author in record.authors),
            record.year is not None,
            bool(record.journal and record.journal.strip()),
            bool(record.volume and record.volume.strip()),
            bool(record.issue and record.issue.strip()),
            bool(record.pages and record.pages.strip()),
            _clean_identifier(record.doi_norm) is not None,
            _clean_identifier(record.pmid) is not None,
        )
    )


def _choose_primary(records: Sequence[RecordForDedup]) -> RecordForDedup:
    return min(
        records,
        key=lambda record: (
            -int(_clean_identifier(record.doi_norm) is not None),
            -int(record.abstract_present),
            -_field_count(record),
            record.imported_at,
            record.id.int,
        ),
    )


def cluster(
    records: Sequence[RecordForDedup],
    threshold: float = 0.90,
    *,
    extra_pairs: Iterable[tuple[uuid.UUID, uuid.UUID]] = (),
) -> list[Cluster]:
    """Return non-singleton duplicate clusters for a sequence of records.

    Exact nonblank DOI/PMID keys create confidence-1 edges; remaining candidates come
    from :func:`blocks`, plus any ``extra_pairs`` the caller found another way — the
    database's trigram block C — and must meet ``threshold`` under :func:`score_pair`. The output
    contains deterministically ordered member IDs, the weakest union edge as cluster
    confidence, the most complete primary, and auto-resolution eligibility. Runtime is
    O(n + sum(b^2) + e log e), where b are block sizes and e are qualifying edges; memory
    is O(n + e). Exact-key groups use linear spanning edges, and candidate block pairs are
    streamed before qualifying evidence is sorted. Unlike a naive guide implementation,
    component-level DOI sets prevent a missing-DOI record from transitively joining two
    conflicting DOIs; any cluster touched by such ambiguity requires manual review.
    """

    if not 0.0 <= threshold <= MAX_PAIR_SCORE:
        raise ValueError(f"threshold must be between 0 and {MAX_PAIR_SCORE}")

    by_id = {record.id: record for record in records}
    if len(by_id) != len(records):
        raise ValueError("record IDs must be unique")
    if len(records) < 2:
        return []

    exact_pairs, ambiguous_ids = _exact_pairs(records)
    evidence = [
        _Evidence(left=left, right=right, score=1.0, exact=True) for left, right in exact_pairs
    ]
    for left_id, right_id in _candidate_pairs(records, extra_pairs):
        left = by_id[left_id]
        right = by_id[right_id]
        if _conflicting_dois(left, right) or _shares_exact_key(left, right):
            continue
        pair_score = score_pair(left, right)
        # Decimal weights such as 0.70 + 0.12 + 0.08 can land one ULP below 0.90.
        if _meets_threshold(pair_score, threshold):
            evidence.append(_Evidence(left=left_id, right=right_id, score=pair_score, exact=False))

    evidence.sort(
        key=lambda item: (
            not item.exact,
            -item.score,
            item.left.int,
            item.right.int,
        )
    )
    union_find = _UnionFind(records)
    selected: list[_Evidence] = []
    for item in evidence:
        if union_find.has_doi_conflict(item.left, item.right):
            ambiguous_ids.update((item.left, item.right))
        elif union_find.union(item.left, item.right):
            selected.append(item)

    members_by_root: defaultdict[uuid.UUID, list[RecordForDedup]] = defaultdict(list)
    for record in records:
        members_by_root[union_find.find(record.id)].append(record)

    edges_by_root: defaultdict[uuid.UUID, list[_Evidence]] = defaultdict(list)
    for item in selected:
        edges_by_root[union_find.find(item.left)].append(item)

    result: list[Cluster] = []
    for root, members in members_by_root.items():
        if len(members) < 2:
            continue
        member_ids = tuple(sorted((member.id for member in members), key=lambda item: item.int))
        supporting_edges = edges_by_root[root]
        cluster_score = min(item.score for item in supporting_edges)
        exact_only = all(item.exact for item in supporting_edges)
        doi_ambiguous = any(member.id in ambiguous_ids for member in members)
        result.append(
            Cluster(
                members=member_ids,
                score=cluster_score,
                primary_id=_choose_primary(members).id,
                auto_resolvable=not doi_ambiguous
                and (exact_only or _meets_threshold(cluster_score, AUTO_RESOLVE_SCORE)),
            )
        )

    return sorted(result, key=lambda item: tuple(member.int for member in item.members))
