"""Training and scoring (guide 9.2): logistic regression over the review's TF-IDF.

No record's score comes from a model that saw that record's own label. Records that are
labelled but still waiting for someone (a second reviewer, say) are scored by
cross-fitting — each fold by a model trained on the other folds — so a high score never
repeats another reviewer's decision back to them. The same out-of-fold scores give the
cross-validated AUC.
"""

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

from app.ranking.features import Corpus

# The first model is trained once a stage has this many relevant and irrelevant records.
# Guide 8.10 says 5 of each; the owner chose 1 (2026-09-25) on the benchmark's evidence:
# on sparse reviews the random warm-up before five includes was most of the work, and
# starting from the first of each saved a median 63% of screening instead of 55%.
MIN_EACH = 1
FOLDS = 5
# Guide 9.2: the cross-validated AUC is reported from this many labelled records.
AUC_FROM = 50


@dataclass(frozen=True)
class Ranking[K: Hashable]:
    scores: dict[K, float]
    n_labeled: int
    n_included: int
    auc: float | None


def can_train[K: Hashable](labels: Mapping[K, int], *, min_each: int = MIN_EACH) -> bool:
    included = sum(labels.values())
    return included >= min_each and len(labels) - included >= min_each


def rank[K: Hashable](
    corpus: Corpus[K],
    labels: Mapping[K, int],
    targets: Sequence[K],
    *,
    with_auc: bool = True,
    min_each: int = MIN_EACH,
) -> Ranking[K]:
    """The probability that each target is relevant, from the labelled records.

    `labels` maps records to 1 (relevant) or 0; `targets` are the records to score.
    Keys the corpus does not know are ignored.
    """
    labeled = [key for key in labels if key in corpus.rows]
    y = np.fromiter((labels[key] for key in labeled), dtype=np.int8, count=len(labeled))
    if not can_train(dict(zip(labeled, y.tolist(), strict=True)), min_each=min_each):
        raise ValueError(f"Need at least {min_each} relevant and {min_each} irrelevant records.")
    x = corpus.select(labeled)
    position = {key: index for index, key in enumerate(labeled)}
    wanted = [key for key in targets if key in corpus.rows]
    also_labeled = [key for key in wanted if key in position]
    fresh = [key for key in wanted if key not in position]

    scores: dict[K, float] = {}
    out_of_fold: np.ndarray | None = None
    folds = min(FOLDS, int(y.sum()), int(len(y) - y.sum()))
    # Cross-fitting needs two of each. Until then a labelled record that is still waiting
    # is left unscored (it comes in random order) rather than scored by its own label.
    if folds >= 2 and (also_labeled or (with_auc and len(labeled) >= AUC_FROM)):
        out_of_fold = _cross_fit(x, y, folds)
        for key in also_labeled:
            scores[key] = float(out_of_fold[position[key]])
    if fresh:
        model = _fit(x, y)
        for key, score in zip(fresh, model.predict_proba(corpus.select(fresh))[:, 1], strict=True):
            scores[key] = float(score)

    auc = None
    if with_auc and out_of_fold is not None and len(labeled) >= AUC_FROM:
        auc = float(roc_auc_score(y, out_of_fold))
    return Ranking(scores=scores, n_labeled=len(labeled), n_included=int(y.sum()), auc=auc)


def _fit(x: csr_matrix, y: np.ndarray) -> LogisticRegression:
    model = LogisticRegression(class_weight="balanced", C=1.0, solver="liblinear")
    model.fit(x, y)
    return model


def _cross_fit(x: csr_matrix, y: np.ndarray, folds: int) -> np.ndarray:
    out = np.empty(len(y), dtype=np.float64)
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=0)
    for train, test in splitter.split(np.zeros(len(y)), y):
        out[test] = _fit(x[train], y[train]).predict_proba(x[test])[:, 1]
    return out
