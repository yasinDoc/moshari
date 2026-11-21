"""Risk tiers and the response playbook attached to each tier."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C


@dataclass(frozen=True)
class Tier:
    name: str
    color: str
    soft: str
    action: str
    detail: str


TIERS: dict[str, Tier] = {
    "Low": Tier(
        "Low",
        "#3AA876",
        "rgba(58,168,118,0.16)",
        "Routine surveillance",
        "Keep weekly larval surveys and community clean-up messaging on schedule.",
    ),
    "Medium": Tier(
        "Medium",
        "#E8B10E",
        "rgba(232,177,14,0.18)",
        "Source reduction",
        "Clear drains and stagnant containers; schedule larviciding of known breeding sites.",
    ),
    "High": Tier(
        "High",
        "#EA6B2D",
        "rgba(234,107,45,0.16)",
        "Targeted vector control",
        "Deploy larvicide and fogging teams this week; brief ward health workers; notify nearby hospitals.",
    ),
    "Critical": Tier(
        "Critical",
        "#D63A47",
        "rgba(214,58,71,0.16)",
        "Outbreak response",
        "Vector control within 48h, door-to-door source reduction, pre-position saline, beds and NS1 test kits.",
    ),
}


def tier_thresholds(cases: pd.Series) -> list[float]:
    """Lower bounds (weekly ward cases) of Medium, High and Critical, from training data."""
    q = np.quantile(cases.to_numpy(dtype=float), C.TIER_QUANTILES)
    # Keep thresholds strictly increasing and at least 1 case apart.
    out: list[float] = []
    for v in q:
        v = max(float(np.round(v, 1)), 1.0)
        if out and v <= out[-1]:
            v = out[-1] + 1.0
        out.append(v)
    return out


def assign_tier(values, thresholds: list[float]) -> np.ndarray:
    """Map expected weekly cases to tier index 0..3."""
    return np.searchsorted(np.asarray(thresholds), np.asarray(values, dtype=float), side="right")


def tier_name(idx: int) -> str:
    return C.TIER_NAMES[int(idx)]
