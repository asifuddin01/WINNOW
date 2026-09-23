"""Plain data types used by the pure agreement statistics package."""

import uuid
from dataclasses import dataclass
from typing import Final, Literal

type DecisionValue = Literal["include", "exclude", "maybe"]
type MaybeCountsAs = Literal["include", "maybe"]

_VALID_DECISIONS: Final = frozenset({"include", "exclude", "maybe"})


@dataclass(frozen=True, slots=True, kw_only=True)
class Decision:
    """A reviewer's nominal decision for one record.

    The adapter must supply decisions from one authorised project and one screening stage.
    Runtime validation protects the pure functions when values originate outside typed Python.
    """

    record_id: uuid.UUID
    reviewer_id: uuid.UUID
    decision: DecisionValue

    def __post_init__(self) -> None:
        if self.decision not in _VALID_DECISIONS:
            msg = "decision must be 'include', 'exclude', or 'maybe'"
            raise ValueError(msg)
