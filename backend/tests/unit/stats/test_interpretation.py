"""Landis-Koch bands include every documented boundary."""

import math

import pytest

from app.stats import landis_koch


@pytest.mark.parametrize(
    ("kappa", "expected"),
    [
        (-1.0, "poor"),
        (-0.001, "poor"),
        (0.0, "slight"),
        (0.20, "slight"),
        (0.200001, "fair"),
        (0.40, "fair"),
        (0.400001, "moderate"),
        (0.60, "moderate"),
        (0.600001, "substantial"),
        (0.80, "substantial"),
        (0.800001, "almost perfect"),
        (1.0, "almost perfect"),
    ],
)
def test_landis_koch_bands(kappa: float, expected: str) -> None:
    assert landis_koch(kappa) == expected


@pytest.mark.parametrize("kappa", [-1.001, 1.001, math.inf, -math.inf, math.nan])
def test_landis_koch_rejects_values_outside_kappa_range(kappa: float) -> None:
    with pytest.raises(ValueError, match="finite and between"):
        landis_koch(kappa)
