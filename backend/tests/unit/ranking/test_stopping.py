"""The stopping-rule helper (guide 8.5): a run of excludes, and what may be left."""

from app.ranking.stopping import estimate_remaining, excluded_in_a_row


def test_the_run_of_excludes_is_counted_from_the_latest_decision() -> None:
    assert excluded_in_a_row([]) == 0
    assert excluded_in_a_row([True, False, False]) == 2
    assert excluded_in_a_row([False, False, True]) == 0


def test_nothing_left_means_nothing_to_find() -> None:
    assert estimate_remaining([True, False], 0).expected == 0
    assert estimate_remaining([], 100).high == 0


def test_when_finds_have_stopped_the_estimate_is_small() -> None:
    """Relevant records thinning out and then 300 excludes in a row: little is left."""
    history = [index % 3 == 0 for index in range(60)]
    history += [index % 20 == 0 for index in range(200)]
    history += [False] * 300
    estimate = estimate_remaining(history, 4_000)
    assert estimate.low <= estimate.expected <= estimate.high
    assert estimate.expected < 5


def test_a_steady_rate_carries_on_over_what_is_left() -> None:
    """With no sign of slowing, the rate so far applies to every remaining record."""
    history = [index % 10 == 0 for index in range(1_000)]
    estimate = estimate_remaining(history, 500)
    assert 30 <= estimate.expected <= 70
    assert estimate.low < 50 < estimate.high


def test_the_same_history_gives_the_same_answer() -> None:
    history = [index % 7 == 0 for index in range(400)] + [False] * 200
    assert estimate_remaining(history, 1_000) == estimate_remaining(history, 1_000)


def test_the_random_warm_up_before_the_first_model_is_left_out() -> None:
    """Finds at a steady rate in random order, then ranking finds the rest and dries up:
    counting the warm-up would read as many still to find."""
    warm_up = [index % 25 == 0 for index in range(250)]
    ranked = [index % 3 == 0 for index in range(60)] + [False] * 200
    everything = estimate_remaining(warm_up + ranked, 400)
    after = estimate_remaining(warm_up + ranked, 400, ranked_from=250)
    assert after.expected < 2 < everything.expected
    assert after.low <= after.expected <= after.high
