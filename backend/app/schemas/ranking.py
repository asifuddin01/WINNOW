"""Relevance ranking: the model's state, the recall curve, the stopping-rule helper."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models import ScreeningStage


class ModelOut(BaseModel):
    trained_at: datetime
    # Team-wide counts: None for a reviewer screening blind (guide 8.6).
    n_labeled: int | None
    n_included: int | None
    # Cross-validated, from 50 labelled records (guide 9.2).
    auc: float | None
    scored: int


class RankingStatus(BaseModel):
    stage: ScreeningStage
    enabled: bool
    model: ModelOut | None
    # What the first model waits for (guide 8.10): this many of each.
    needs_each: int
    # How far the team has got towards it; None when screening blind.
    have_included: int | None
    have_excluded: int | None
    retrain_after: int
    # A run is queued or under way.
    training: bool
    # Guide 9.2: one record in this many is taken from random order in relevance sort.
    explore_every: int


class TrainStarted(BaseModel):
    queued: bool


class Curve(BaseModel):
    """Where each relevant record was found, in the order of screening: the recall curve
    is a step up at each of these positions (guide 8.10)."""

    screened: int
    found_at: list[int]


class RecallCurve(BaseModel):
    stage: ScreeningStage
    total: int
    mine: Curve
    # The whole team, records in the order they were first decided; None when blind.
    team: Curve | None


class Estimate(BaseModel):
    expected: float
    low: int
    high: int


class StoppingAdvice(BaseModel):
    """Guide 8.5: advice only. Winnow never stops anyone."""

    stage: ScreeningStage
    rule: Literal["consecutive_excludes"]
    threshold: int
    in_a_row: int
    remaining: int
    # Filled once the threshold is reached and a model exists.
    estimate: Estimate | None
