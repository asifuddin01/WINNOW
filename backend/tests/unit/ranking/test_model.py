"""The ranking engine (guide 9.2): features, training labels and scores."""

import pytest

from app.ranking.features import build, text_of
from app.ranking.labels import training_label
from app.ranking.model import AUC_FROM, MIN_EACH, can_train, rank

KIDNEY = "deep learning kidney tumour segmentation on contrast ct in adults"
HEART = "heart valve surgery outcomes in a randomised trial of older patients"


def corpus_of(kidney: int, heart: int, extra: tuple[str, ...] = ()) -> tuple[list[str], list[str]]:
    keys = [f"k{i}" for i in range(kidney)] + [f"h{i}" for i in range(heart)]
    texts = [f"{KIDNEY} study {i}" for i in range(kidney)]
    texts += [f"{HEART} study {i}" for i in range(heart)]
    keys += [f"x{i}" for i in range(len(extra))]
    texts += list(extra)
    return keys, texts


def test_the_title_counts_twice_and_nothing_missing_breaks_it() -> None:
    assert text_of("Kidney CT", "An abstract.", ["radiomics"]) == (
        "Kidney CT Kidney CT An abstract. radiomics"
    )
    assert text_of(None, None).strip() == ""


def test_a_tiny_review_still_gets_a_corpus() -> None:
    corpus = build(["a", "b"], ["kidney", "heart"])
    assert len(corpus) == 2
    assert corpus.select(["b"]).shape[0] == 1
    with pytest.raises(ValueError, match="One text per record"):
        build(["a"], [])


def test_a_model_needs_five_of_each() -> None:
    assert not can_train({"a": 1, "b": 0})
    assert can_train({f"i{n}": 1 for n in range(MIN_EACH)} | {f"e{n}": 0 for n in range(MIN_EACH)})
    keys, texts = corpus_of(10, 10)
    corpus = build(keys, texts)
    with pytest.raises(ValueError, match="at least 5"):
        rank(corpus, {"k0": 1, "h0": 0}, keys)


def test_records_like_the_included_ones_rank_first() -> None:
    keys, texts = corpus_of(30, 30)
    corpus = build(keys, texts)
    labels = {f"k{i}": 1 for i in range(5)} | {f"h{i}": 0 for i in range(5)}
    ranking = rank(corpus, labels, [key for key in keys if key not in labels])
    kidney = [ranking.scores[f"k{i}"] for i in range(5, 30)]
    heart = [ranking.scores[f"h{i}"] for i in range(5, 30)]
    assert min(kidney) > max(heart)
    assert (ranking.n_labeled, ranking.n_included) == (10, 5)
    assert ranking.auc is None  # fewer than 50 labels


def test_no_record_is_scored_by_a_model_that_saw_its_own_label() -> None:
    """A heart-surgery record that one reviewer included, still waiting for the second
    reviewer: its score must not tell the second reviewer "someone included this"."""
    keys, texts = corpus_of(20, 20, extra=(f"{HEART} study odd",))
    corpus = build(keys, texts)
    labels = {f"k{i}": 1 for i in range(20)} | {f"h{i}": 0 for i in range(20)} | {"x0": 1}
    labelled_score = rank(corpus, labels, ["x0"]).scores["x0"]
    unlabelled = {key: value for key, value in labels.items() if key != "x0"}
    fresh_score = rank(corpus, unlabelled, ["x0"]).scores["x0"]
    assert labelled_score < 0.5
    assert labelled_score == pytest.approx(fresh_score, abs=0.1)


def test_the_cross_validated_auc_comes_with_enough_labels() -> None:
    keys, texts = corpus_of(40, 40)
    corpus = build(keys, texts)
    labels = {f"k{i}": 1 for i in range(AUC_FROM // 2)} | {f"h{i}": 0 for i in range(AUC_FROM // 2)}
    ranking = rank(corpus, labels, keys)
    assert ranking.auc == pytest.approx(1.0)
    assert len(ranking.scores) == len(keys)
    assert rank(corpus, labels, keys, with_auc=False).auc is None


def test_keys_the_corpus_does_not_know_are_ignored() -> None:
    keys, texts = corpus_of(10, 10)
    corpus = build(keys, texts)
    labels = {f"k{i}": 1 for i in range(5)} | {f"h{i}": 0 for i in range(5)} | {"gone": 1}
    ranking = rank(corpus, labels, ["k9", "gone"])
    assert set(ranking.scores) == {"k9"}
    assert ranking.n_labeled == 10


@pytest.mark.parametrize(
    ("final", "decisions", "label"),
    [
        ("included", [], 1),
        ("maybe", ["exclude"], 1),
        ("excluded", ["include"], 0),
        ("pending", ["include"], 1),
        ("pending", ["maybe", "exclude", "exclude"], 0),
        ("conflict", ["include", "exclude"], None),
        ("pending", [], None),
    ],
)
def test_training_labels_follow_the_final_status_then_the_majority(
    final: str, decisions: list[str], label: int | None
) -> None:
    assert training_label(final, decisions) == label
