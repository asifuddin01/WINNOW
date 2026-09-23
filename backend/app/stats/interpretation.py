"""Conventional interpretation labels for agreement statistics."""

import math


def landis_koch(kappa: float) -> str:
    """Return the conventional Landis-Koch interpretation band for kappa.

    Input must be a finite kappa in [-1, 1]. The output is a lower-case band label.
    Complexity is O(1) time and space. These bands are a reporting convention rather than
    a statistical inference, as the build guide requires the application to disclose.
    """

    if not math.isfinite(kappa) or not -1 <= kappa <= 1:
        msg = "kappa must be finite and between -1 and 1"
        raise ValueError(msg)
    if kappa < 0:
        return "poor"
    if kappa <= 0.20:
        return "slight"
    if kappa <= 0.40:
        return "fair"
    if kappa <= 0.60:
        return "moderate"
    if kappa <= 0.80:
        return "substantial"
    return "almost perfect"
