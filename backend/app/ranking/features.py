"""What a record is ranked by: TF-IDF over its words (guide 9.2).

The title counts twice, then the abstract and the keywords, as word unigrams and bigrams
with sublinear term frequency. A corpus is built once per review and reused until
records are added or removed (the service keeps it; see `app/services/ranking.py`).
"""

from collections.abc import Hashable, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

MAX_FEATURES = 100_000
# A word or pair seen in one record only cannot help rank any other.
MIN_DF = 2


def text_of(title: str | None, abstract: str | None, keywords: Sequence[str] = ()) -> str:
    """The text a record is ranked by. The title says the most in the fewest words, so
    it is given twice the weight by appearing twice."""
    title = title or ""
    return " ".join((title, title, abstract or "", " ".join(keywords)))


@dataclass(frozen=True)
class Corpus[K: Hashable]:
    """Every record of a review as a row of TF-IDF weights, and which row is which."""

    keys: tuple[K, ...]
    rows: dict[K, int]
    matrix: csr_matrix

    def __len__(self) -> int:
        return len(self.keys)

    def select(self, keys: Sequence[K]) -> csr_matrix:
        return self.matrix[[self.rows[key] for key in keys]]


def build[K: Hashable](keys: Sequence[K], texts: Sequence[str]) -> Corpus[K]:
    """Fit the vocabulary and weights on the whole review, labelled or not: which words
    are rare in this review is known before anyone screens (transductive TF-IDF)."""
    if len(keys) != len(texts):
        raise ValueError("One text per record.")
    try:
        matrix = _vectorizer(MIN_DF).fit_transform(texts)
    except ValueError:
        # Too few records for any word to appear twice (a tiny or empty review).
        matrix = _vectorizer(1).fit_transform([*texts, "empty"])[: len(texts)]
    return Corpus(keys=tuple(keys), rows={key: row for row, key in enumerate(keys)}, matrix=matrix)


def _vectorizer(min_df: int) -> TfidfVectorizer:
    return TfidfVectorizer(
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=min_df,
        max_features=MAX_FEATURES,
        strip_accents="unicode",
        dtype=np.float32,
    )
