"""Pure percent-agreement and kappa calculations."""

import uuid
from collections import Counter
from collections.abc import Sequence
from fractions import Fraction
from typing import Final

from app.stats.types import Decision, DecisionValue, MaybeCountsAs

_VALID_MAYBE_MAPPINGS: Final = frozenset({"include", "maybe"})


def _mapped_entries(
    decisions: Sequence[Decision], maybe_counts_as: MaybeCountsAs
) -> list[tuple[uuid.UUID, uuid.UUID, DecisionValue]]:
    if maybe_counts_as not in _VALID_MAYBE_MAPPINGS:
        msg = "maybe_counts_as must be 'include' or 'maybe'"
        raise ValueError(msg)

    entries: list[tuple[uuid.UUID, uuid.UUID, DecisionValue]] = []
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for decision in decisions:
        key = (decision.record_id, decision.reviewer_id)
        if key in seen:
            msg = "each reviewer may have only one decision per record"
            raise ValueError(msg)
        seen.add(key)
        value = maybe_counts_as if decision.decision == "maybe" else decision.decision
        entries.append((decision.record_id, decision.reviewer_id, value))
    return entries


def _paired_values(
    decisions: Sequence[Decision],
    reviewer_a: uuid.UUID,
    reviewer_b: uuid.UUID,
    maybe_counts_as: MaybeCountsAs,
) -> list[tuple[DecisionValue, DecisionValue]]:
    if reviewer_a == reviewer_b:
        msg = "pairwise agreement requires two distinct reviewers"
        raise ValueError(msg)

    left: dict[uuid.UUID, DecisionValue] = {}
    right: dict[uuid.UUID, DecisionValue] = {}
    for record_id, reviewer_id, value in _mapped_entries(decisions, maybe_counts_as):
        if reviewer_id == reviewer_a:
            left[record_id] = value
        elif reviewer_id == reviewer_b:
            right[record_id] = value

    # Iterating one reviewer's mapping avoids sorting while counts remain order-independent.
    return [(value, right[record_id]) for record_id, value in left.items() if record_id in right]


def percent_agreement(
    decisions: Sequence[Decision],
    reviewer_a: uuid.UUID,
    reviewer_b: uuid.UUID,
    *,
    maybe_counts_as: MaybeCountsAs = "include",
) -> float | None:
    """Return observed agreement between two reviewers.

    Inputs are decisions from one project and stage, two distinct reviewer UUIDs, and the
    project's ``maybe_counts_as`` setting. The output is agreements divided by jointly
    reviewed records, or ``None`` when the reviewers have no overlap. Complexity is O(n)
    time and O(n) space for n decisions.
    """

    pairs = _paired_values(decisions, reviewer_a, reviewer_b, maybe_counts_as)
    if not pairs:
        return None
    agreements = sum(left == right for left, right in pairs)
    return agreements / len(pairs)


def cohens_kappa(
    decisions: Sequence[Decision],
    reviewer_a: uuid.UUID,
    reviewer_b: uuid.UUID,
    *,
    maybe_counts_as: MaybeCountsAs = "include",
) -> float | None:
    """Return Cohen's kappa between two reviewers.

    Inputs are decisions from one project and stage, two distinct reviewer UUIDs, and the
    project's ``maybe_counts_as`` setting. The output is kappa, or ``None`` for no overlap
    or expected agreement of one. Complexity is O(n) time and O(n) space. When configured
    to retain ``maybe``, this deliberately generalises the guide's binary wording to the
    standard nominal multi-category formula so it matches the project's setting semantics.
    """

    pairs = _paired_values(decisions, reviewer_a, reviewer_b, maybe_counts_as)
    if not pairs:
        return None

    sample_size = len(pairs)
    observed = Fraction(sum(left == right for left, right in pairs), sample_size)
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    categories = left_counts.keys() | right_counts.keys()
    expected = sum(
        (
            Fraction(left_counts[category], sample_size)
            * Fraction(right_counts[category], sample_size)
        )
        for category in categories
    )
    if expected == 1:
        return None
    return float((observed - expected) / (1 - expected))


def fleiss_kappa(
    decisions: Sequence[Decision], *, maybe_counts_as: MaybeCountsAs = "include"
) -> float | None:
    """Return Fleiss' kappa for a fixed-size panel of at least three ratings per record.

    Input decisions must belong to one project and stage; each record must have the same
    number of unique reviewers, although reviewer identities may vary. The output is kappa,
    or ``None`` for no records or expected agreement of one. Complexity is O(n) time and
    O(n) space. Retained ``maybe`` decisions form a third nominal category, consistent with
    project settings and the general Fleiss formula.
    """

    entries = _mapped_entries(decisions, maybe_counts_as)
    if not entries:
        return None

    by_record: dict[uuid.UUID, Counter[DecisionValue]] = {}
    for record_id, _, value in entries:
        by_record.setdefault(record_id, Counter())[value] += 1

    panel_sizes = {sum(counts.values()) for counts in by_record.values()}
    if len(panel_sizes) != 1:
        msg = "Fleiss' kappa requires the same number of ratings for every record"
        raise ValueError(msg)
    panel_size = panel_sizes.pop()
    if panel_size < 3:
        msg = "Fleiss' kappa requires at least three ratings per record"
        raise ValueError(msg)

    record_count = len(by_record)
    agreement_numerator = sum(
        count * (count - 1) for counts in by_record.values() for count in counts.values()
    )
    observed = Fraction(
        agreement_numerator,
        record_count * panel_size * (panel_size - 1),
    )

    category_totals: Counter[DecisionValue] = Counter()
    for counts in by_record.values():
        category_totals.update(counts)
    total_ratings = record_count * panel_size
    expected = sum(Fraction(count, total_ratings) ** 2 for count in category_totals.values())
    if expected == 1:
        return None
    return float((observed - expected) / (1 - expected))
