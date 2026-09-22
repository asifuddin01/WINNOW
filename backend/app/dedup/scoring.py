"""Pairwise bibliographic similarity scoring from guide 9.1."""

from difflib import SequenceMatcher

from app.dedup.normalisation import normalise_title
from app.dedup.types import RecordForDedup


def _clean_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().casefold()
    return cleaned or None


def _conflicting_dois(left: RecordForDedup, right: RecordForDedup) -> bool:
    left_doi = _clean_identifier(left.doi_norm)
    right_doi = _clean_identifier(right.doi_norm)
    return left_doi is not None and right_doi is not None and left_doi != right_doi


def _token_sort_ratio(left: str, right: str) -> float:
    left_tokens = " ".join(sorted(normalise_title(left).split()))
    right_tokens = " ".join(sorted(normalise_title(right).split()))
    if not left_tokens or not right_tokens:
        return 0.0
    if left_tokens == right_tokens:
        return 1.0
    first, second = sorted((left_tokens, right_tokens))
    # SequenceMatcher can be directional; canonical ordering preserves RapidFuzz symmetry.
    return SequenceMatcher(None, first, second, autojunk=False).ratio()


def _first_author_surname(record: RecordForDedup) -> str | None:
    if not record.authors:
        return None
    first_author = record.authors[0].strip()
    if not first_author:
        return None
    surname = (
        first_author.partition(",")[0]
        if "," in first_author
        else first_author.rsplit(maxsplit=1)[-1]
    )
    normalised = normalise_title(surname).replace(" ", "")
    return normalised or None


def _author_score(left: RecordForDedup, right: RecordForDedup) -> float:
    left_surname = _first_author_surname(left)
    right_surname = _first_author_surname(right)
    if left_surname is None or right_surname is None:
        return 0.5
    return 1.0 if left_surname == right_surname else 0.0


def _year_score(left: int | None, right: int | None) -> float:
    if left is None or right is None:
        return 0.0
    if left == right:
        return 1.0
    return 0.7 if abs(left - right) == 1 else 0.0


def _journal_score(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.5
    left_norm = normalise_title(left)
    right_norm = normalise_title(right)
    if not left_norm or not right_norm:
        return 0.5
    return _token_sort_ratio(left_norm, right_norm)


def _same_present(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    left_clean = left.strip().casefold()
    right_clean = right.strip().casefold()
    return bool(left_clean and right_clean and left_clean == right_clean)


def score_pair(left: RecordForDedup, right: RecordForDedup) -> float:
    """Return the guide 9.1 similarity score for two records.

    Inputs are two immutable bibliographic records; output is an unrounded float from 0
    through 1.05. Conflicting nonblank DOIs always return 0. Runtime is O(l^2) in the
    worst case because ``difflib.SequenceMatcher`` replaces the unavailable RapidFuzz
    token-sort ratio; other work is linear in field length. A missing author is the
    guide's neutral 0.5 case, and matching either pages or volume grants the single 0.05
    bonus.
    """

    if _conflicting_dois(left, right):
        return 0.0

    left_title = left.title_norm or left.title
    right_title = right.title_norm or right.title
    title_similarity = _token_sort_ratio(left_title, right_title)
    author_similarity = _author_score(left, right)
    year_similarity = _year_score(left.year, right.year)
    journal_similarity = _journal_score(left.journal, right.journal)
    pages_or_volume_bonus = (
        0.05
        if (_same_present(left.pages, right.pages) or _same_present(left.volume, right.volume))
        else 0.0
    )

    return (
        0.70 * title_similarity
        + 0.12 * author_similarity
        + 0.10 * year_similarity
        + 0.08 * journal_similarity
        + pages_or_volume_bonus
    )
