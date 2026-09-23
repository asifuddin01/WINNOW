"""Which records the model learns from, and as what (guide 9.2).

A record's final status at the stage decides its label: included or maybe is relevant,
excluded is not. A record that is not final yet takes the majority of the individual
decisions on it, a tie teaching nothing.
"""

from collections.abc import Iterable

RELEVANT = frozenset({"included", "maybe"})
DECISIONS_RELEVANT = frozenset({"include", "maybe"})


def training_label(final: str, decisions: Iterable[str]) -> int | None:
    """1 relevant, 0 not, None when there is nothing to learn from yet."""
    if final in RELEVANT:
        return 1
    if final == "excluded":
        return 0
    yes = no = 0
    for decision in decisions:
        if decision in DECISIONS_RELEVANT:
            yes += 1
        elif decision == "exclude":
            no += 1
    if yes == no:
        return None
    return 1 if yes > no else 0
