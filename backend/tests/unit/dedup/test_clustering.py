"""Union-find clustering is deterministic, conservative and fixture-measured."""

import uuid
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime
from itertools import combinations

import pytest

from app.dedup import Cluster, RecordForDedup, cluster, score_pair
from tests.unit.dedup.conftest import KnownCorpus


def _pairs(groups: Iterable[Iterable[uuid.UUID]]) -> set[frozenset[uuid.UUID]]:
    return {frozenset(pair) for group in groups for pair in combinations(group, 2)}


def test_known_fixture_clusters_and_primary_selection(known_corpus: KnownCorpus) -> None:
    actual = cluster(known_corpus.records)
    by_members = {frozenset(item.members): item for item in actual}

    assert set(by_members) == {item.members for item in known_corpus.expected_clusters}
    for expected in known_corpus.expected_clusters:
        candidate = by_members[expected.members]
        assert candidate.primary_id == expected.primary_id, expected.name
        assert candidate.score == pytest.approx(expected.score), expected.name
        assert candidate.auto_resolvable is expected.auto_resolvable, expected.name


def test_known_fixture_reaches_target_precision_and_recall(known_corpus: KnownCorpus) -> None:
    predicted_pairs = _pairs(item.members for item in cluster(known_corpus.records))
    truth_pairs = _pairs(item.members for item in known_corpus.expected_clusters)
    true_positives = len(predicted_pairs & truth_pairs)
    false_positives = len(predicted_pairs - truth_pairs)
    false_negatives = len(truth_pairs - predicted_pairs)

    precision = true_positives / (true_positives + false_positives)
    recall = true_positives / (true_positives + false_negatives)

    assert (true_positives, false_positives, false_negatives) == (7, 0, 0)
    assert precision >= 0.97
    assert recall >= 0.95


def test_named_negative_pairs_never_share_a_cluster(known_corpus: KnownCorpus) -> None:
    actual_member_sets = [frozenset(item.members) for item in cluster(known_corpus.records)]
    for forbidden_pair in known_corpus.must_not_cluster:
        assert not any(forbidden_pair <= members for members in actual_member_sets)


def test_exact_keys_override_a_subthreshold_weighted_score(known_corpus: KnownCorpus) -> None:
    for left_key, right_key in (("doi-a", "doi-b"), ("pmid-a", "pmid-b")):
        left = known_corpus.by_key[left_key]
        right = known_corpus.by_key[right_key]
        assert score_pair(left, right) < 0.90
        assert cluster((left, right))[0].score == 1.0


def _record(
    record_id: int,
    *,
    doi: str | None = None,
    pmid: str | None = None,
    year: int | None = 2020,
    imported_day: int | None = None,
) -> RecordForDedup:
    return RecordForDedup(
        id=uuid.UUID(int=record_id),
        title="Shared title for a controlled trial",
        title_norm="shared title for a controlled trial",
        authors=("Smith, Alex",),
        year=year,
        journal="Trials",
        volume="1",
        issue="1",
        pages="1-5",
        doi_norm=doi,
        pmid=pmid,
        abstract_present=False,
        imported_at=datetime(2026, 1, imported_day or record_id, tzinfo=UTC),
    )


def test_missing_identifier_cannot_bridge_conflicting_dois() -> None:
    doi_one = _record(1, doi="10.1000/one")
    bridge = _record(2)
    doi_two = _record(3, doi="10.1000/two")

    result = cluster((doi_one, bridge, doi_two))

    assert len(result) == 1
    assert not {doi_one.id, doi_two.id} <= set(result[0].members)
    assert not result[0].auto_resolvable


def test_conflicting_dois_override_an_exact_pmid() -> None:
    left = _record(1, doi="10.1000/one", pmid="12345678")
    right = _record(2, doi="10.1000/two", pmid="12345678")
    assert cluster((left, right)) == []


@pytest.mark.parametrize(
    "dois",
    [
        ("10.1000/one", "10.1000/two", None),
        ("10.1000/one", None, "10.1000/two"),
        (None, "10.1000/one", "10.1000/two"),
    ],
)
def test_conflicting_doi_pmid_group_is_manual_in_every_id_order(
    dois: tuple[str | None, str | None, str | None],
) -> None:
    records = tuple(_record(index, doi=doi, pmid="12345678") for index, doi in enumerate(dois, 1))
    result = cluster(records)

    assert result
    assert all(not item.auto_resolvable for item in result)
    for item in result:
        cluster_dois = {
            record.doi_norm for record in records if record.id in item.members and record.doi_norm
        }
        assert len(cluster_dois) <= 1


def test_mixed_exact_and_fuzzy_cluster_is_not_automatically_resolvable() -> None:
    exact_left = _record(1, doi="10.1000/shared")
    exact_right = _record(2, doi="10.1000/shared")
    fuzzy = _record(3, year=None)

    result = cluster((exact_left, exact_right, fuzzy))

    assert len(result) == 1
    assert result[0].score == pytest.approx(0.95)
    assert not result[0].auto_resolvable


def test_primary_prefers_doi_then_abstract_then_fields_then_import_time() -> None:
    sparse_with_doi = replace(
        _record(1, doi="10.1000/shared", imported_day=3),
        journal=None,
        volume=None,
        issue=None,
        pages=None,
    )
    complete_without_doi = replace(_record(2, imported_day=1), abstract_present=True)
    result = cluster((complete_without_doi, sparse_with_doi))
    assert result[0].primary_id == sparse_with_doi.id

    abstract = replace(_record(3, imported_day=3), abstract_present=True)
    fields = _record(4, imported_day=1)
    result = cluster((fields, abstract))
    assert result[0].primary_id == abstract.id

    earlier = _record(5, imported_day=1)
    later = _record(6, imported_day=2)
    result = cluster((later, earlier))
    assert result[0].primary_id == earlier.id


@pytest.mark.parametrize("threshold", [-0.01, 1.06, float("nan")])
def test_invalid_threshold_is_rejected(threshold: float) -> None:
    with pytest.raises(ValueError, match="threshold"):
        cluster((), threshold)


def test_duplicate_record_ids_are_rejected() -> None:
    record = _record(1)
    with pytest.raises(ValueError, match="unique"):
        cluster((record, replace(record, title="Another title")))


def test_empty_and_singleton_inputs_have_no_duplicate_clusters() -> None:
    assert cluster(()) == []
    assert cluster((_record(1),)) == []


def test_custom_threshold_can_leave_a_manual_pair_unclustered() -> None:
    assert cluster((_record(1), _record(2, year=None)), threshold=0.96) == []


def test_score_on_threshold_is_not_lost_to_binary_float_rounding() -> None:
    left = replace(_record(1, year=None), volume=None, pages=None)
    right = replace(_record(2, year=None), volume=None, pages=None)
    assert score_pair(left, right) == pytest.approx(0.90)
    assert len(cluster((left, right))) == 1


def test_auto_resolve_score_on_boundary_is_not_lost_to_float_rounding() -> None:
    left = replace(
        _record(1),
        title="aa bb cc ddddddddddd",
        title_norm="aa bb cc ddddddddddd",
        journal="a" * 16,
    )
    right = replace(
        _record(2, year=2021),
        title="aa bb cc dddddddddde",
        title_norm="aa bb cc dddddddddde",
        journal="a" * 15 + "b",
    )
    assert score_pair(left, right) == pytest.approx(0.98)
    assert cluster((left, right))[0].auto_resolvable


def test_cluster_membership_does_not_depend_on_ids_or_input_order() -> None:
    tide = replace(
        _record(1),
        title="x y z tide",
        title_norm="x y z tide",
        volume=None,
        pages=None,
    )
    diet = replace(
        _record(2),
        title="x y z diet",
        title_norm="x y z diet",
        volume=None,
        pages=None,
    )
    original = bool(cluster((tide, diet)))
    reassigned = bool(
        cluster(
            (
                replace(diet, id=tide.id),
                replace(tide, id=diet.id),
            )
        )
    )
    assert reassigned is original


def test_cluster_values_are_frozen() -> None:
    value = Cluster(
        members=(uuid.UUID(int=1), uuid.UUID(int=2)),
        score=1.0,
        primary_id=uuid.UUID(int=1),
        auto_resolvable=True,
    )
    with pytest.raises(AttributeError):
        value.score = 0.0  # type: ignore[misc]
