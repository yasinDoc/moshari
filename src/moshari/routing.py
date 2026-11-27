"""Hospital overflow routing (Phase 2, module 2).

When a ward needs more hospital beds than it normally has, its overflow
patients are sent to wards in the **same city corporation** that still have
spare beds. Patients never cross city boundaries.

Bed capacity
------------
The onsite dataset has no bed-capacity column, so each ward's capacity is
estimated as its **90th-percentile weekly ``hospital_beds_required`` over
2016-2023** (the training and validation years), rounded up to whole beds and
never below 1. That is the level the ward is used to handling in a bad but
normal week (1 to 5 beds per ward), while peak outbreak weeks need 4 to 12.

Routing rule
------------
For each city separately:

1. Wards whose required beds exceed capacity are *senders*; wards with spare
   beds are *receivers*.
2. Senders are handled largest overflow first.
3. Each sender fills the **least loaded** receiver first (lowest share of its
   beds in use). Ties go to the **nearest** ward by ward number, then to the
   lowest ward id, so results are deterministic.
4. A sender stops when its overflow is placed; the city stops when it runs
   out of spare beds. Anything left is reported as ``net_deficit``.

Everything here is plain pandas: no internet and no model calls, so it works
offline.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Union

import numpy as np
import pandas as pd

from . import config as C

ONSITE_DATA_PATH = C.DATA_DIR / "raw" / "dengue_onsite.csv"
BEDS_COL = "hospital_beds_required"

# Capacity assumption (documented in the module docstring and ARCHITECTURE.md).
CAPACITY_QUANTILE = 0.90
CAPACITY_END = "2023-12-31"
MIN_CAPACITY = 1

TRANSFER_COLS = ["from_ward", "to_ward", "city", "patients"]
WARD_SUMMARY_COLS = ["ward_id", "city", "beds_required", "bed_capacity", "net_deficit", "received", "sent"]
CITY_SUMMARY_COLS = ["city", "total_capacity", "total_required", "utilization", "headroom"]

CapacityLike = Union[pd.Series, Mapping[str, float], pd.DataFrame]


@dataclass
class RoutingResult:
    """The three tables from the shared interface in TASKS.md."""

    transfers: pd.DataFrame
    ward_summary: pd.DataFrame
    city_summary: pd.DataFrame

    def __iter__(self):  # lets callers write `transfers, wards, cities = route_overflow(...)`
        return iter((self.transfers, self.ward_summary, self.city_summary))


# --------------------------------------------------------------------------- capacity
def estimate_bed_capacity(df: pd.DataFrame, end: str = CAPACITY_END,
                          quantile: float = CAPACITY_QUANTILE) -> pd.Series:
    """Each ward's bed capacity: its ``quantile`` weekly ``hospital_beds_required`` up to ``end``.

    Rounded up to whole beds, minimum :data:`MIN_CAPACITY`. Returns a Series indexed by ward id.
    """
    missing = [c for c in (C.DATE_COL, C.WARD_COL, BEDS_COL) if c not in df.columns]
    if missing:
        raise ValueError(f"Bed capacity needs column(s): {', '.join(missing)}")
    hist = df[pd.to_datetime(df[C.DATE_COL]) <= pd.Timestamp(end)]
    if hist.empty:
        raise ValueError(f"No rows on or before {end} to estimate bed capacity from.")
    q = hist.groupby(C.WARD_COL)[BEDS_COL].quantile(quantile)
    cap = np.maximum(np.ceil(q.to_numpy(dtype=float) - 1e-9), MIN_CAPACITY).astype(int)
    return pd.Series(cap, index=q.index, name="bed_capacity").sort_index()


def load_bed_capacity(path: Path | str = ONSITE_DATA_PATH) -> pd.Series:
    """Bed capacity estimated from the onsite dataset on disk."""
    df = pd.read_csv(path, usecols=[C.DATE_COL, C.WARD_COL, BEDS_COL])
    return estimate_bed_capacity(df)


# --------------------------------------------------------------------------- routing
def ward_number(ward_id: str) -> int | None:
    """'DNCC_Ward_07' -> 7 (None if the id has no trailing number)."""
    m = re.search(r"(\d+)\s*$", str(ward_id))
    return int(m.group(1)) if m else None


def _distance(a: str, b: str) -> float:
    na, nb = ward_number(a), ward_number(b)
    return math.inf if na is None or nb is None else abs(na - nb)


def _as_capacity(bed_capacity: CapacityLike) -> pd.Series:
    if isinstance(bed_capacity, pd.DataFrame):
        cap = bed_capacity.set_index(C.WARD_COL)["bed_capacity"]
    else:
        cap = pd.Series(bed_capacity, dtype=float)
    return cap


def route_overflow(alloc_df: pd.DataFrame, bed_capacity: CapacityLike,
                   beds_col: str = BEDS_COL) -> RoutingResult:
    """Move overflow patients to wards with spare beds, strictly within each city.

    ``alloc_df`` needs ``ward_id``, ``city`` and ``beds_col`` (the allocation table's
    ``hospital_beds_required`` by default). ``bed_capacity`` maps ward id to beds, as a
    Series, a dict, or a frame with ``ward_id`` and ``bed_capacity`` columns.
    Required beds are rounded up to whole patients.
    """
    missing = [c for c in (C.WARD_COL, C.CITY_COL, beds_col) if c not in alloc_df.columns]
    if missing:
        raise ValueError(f"Allocation table is missing column(s): {', '.join(missing)}")

    cap = _as_capacity(bed_capacity)
    wards = alloc_df[[C.WARD_COL, C.CITY_COL, beds_col]].copy()
    wards[C.WARD_COL] = wards[C.WARD_COL].astype(str)
    if wards[C.WARD_COL].duplicated().any():
        raise ValueError("Allocation table has more than one row for some wards.")
    unknown = sorted(set(wards[C.WARD_COL]) - set(cap.index))
    if unknown:
        raise ValueError(f"No bed capacity for ward(s): {', '.join(unknown[:5])}"
                         + (" …" if len(unknown) > 5 else ""))

    required = np.ceil(pd.to_numeric(wards[beds_col], errors="coerce").fillna(0).clip(lower=0) - 1e-9)
    wards["beds_required"] = required.astype(int)
    wards["bed_capacity"] = cap.reindex(wards[C.WARD_COL]).fillna(0).clip(lower=0).astype(int).to_numpy()
    wards = wards.sort_values([C.CITY_COL, C.WARD_COL]).reset_index(drop=True)

    transfers: list[dict] = []
    received = dict.fromkeys(wards[C.WARD_COL], 0)
    sent = dict.fromkeys(wards[C.WARD_COL], 0)

    for city, grp in wards.groupby(C.CITY_COL, sort=True):
        load = dict(zip(grp[C.WARD_COL], grp["beds_required"]))
        capacity = dict(zip(grp[C.WARD_COL], grp["bed_capacity"]))
        overflow = {w: load[w] - capacity[w] for w in load if load[w] > capacity[w]}
        # Largest overflow first; ward id breaks ties.
        for sender in sorted(overflow, key=lambda w: (-overflow[w], w)):
            need = overflow[sender]
            # Rank receivers once per sender. Every receiver except the last one used is
            # filled completely and drops out, so the ranking never needs refreshing:
            # O(R log R) per sender instead of re-scanning the city for every move.
            spare = sorted((w for w in load if w != sender and capacity[w] > load[w]),
                           key=lambda w: (load[w] / capacity[w], _distance(sender, w), w))
            for target in spare:
                if need <= 0:
                    break
                moved = min(need, capacity[target] - load[target])
                load[target] += moved
                received[target] += moved
                sent[sender] += moved
                need -= moved
                transfers.append({"from_ward": sender, "to_ward": target, "city": city, "patients": int(moved)})

    wards["received"] = wards[C.WARD_COL].map(received).astype(int)
    wards["sent"] = wards[C.WARD_COL].map(sent).astype(int)
    wards["beds_in_use"] = wards["beds_required"] + wards["received"] - wards["sent"]
    wards["net_deficit"] = (wards["beds_in_use"] - wards["bed_capacity"]).clip(lower=0).astype(int)
    wards["beds_in_use"] = wards["beds_in_use"].clip(upper=wards["bed_capacity"])
    ward_summary = wards[[*WARD_SUMMARY_COLS, "beds_in_use"]]

    city = wards.groupby(C.CITY_COL, sort=True).agg(
        total_capacity=("bed_capacity", "sum"),
        total_required=("beds_required", "sum"),
        patients_moved=("sent", "sum"),
        unplaced=("net_deficit", "sum"),
    ).reset_index()
    city["utilization"] = np.where(city["total_capacity"] > 0,
                                   city["total_required"] / city["total_capacity"].where(city["total_capacity"] > 0),
                                   np.inf)
    city["headroom"] = city["total_capacity"] - city["total_required"]
    city_summary = city[[*CITY_SUMMARY_COLS, "patients_moved", "unplaced"]]

    transfer_df = pd.DataFrame(transfers, columns=TRANSFER_COLS).astype({"patients": int})
    return RoutingResult(transfer_df, ward_summary, city_summary)


# --------------------------------------------------------------------------- what-if and summaries
def with_surge(bed_capacity: pd.Series, surge_pct: float) -> pd.Series:
    """Capacity after adding ``surge_pct`` % surge beds per ward (e.g. corridor or field beds).

    Rounded down so the plan never counts beds that aren't there.
    """
    if surge_pct < 0:
        raise ValueError("Surge percentage cannot be negative.")
    cap = _as_capacity(bed_capacity)
    return np.floor(cap * (1 + surge_pct / 100) + 1e-9).astype(int).rename("bed_capacity")


def beds_to_clear(city_summary: pd.DataFrame) -> int:
    """Extra beds needed, summed over cities, so that no patient is left without one."""
    return int((-city_summary["headroom"]).clip(lower=0).sum())


def plain_summary(city_summary: pd.DataFrame) -> list[str]:
    """One plain-language sentence per city, worst first, for officers who won't read tables."""
    lines = []
    for r in city_summary.sort_values("utilization", ascending=False).itertuples():
        moved = f", after moving {r.patients_moved} patient{'s' if r.patients_moved != 1 else ''}" \
            if r.patients_moved else ""
        if r.unplaced:
            lines.append(f"{r.city} is {-r.headroom} bed{'s' if -r.headroom != 1 else ''} short{moved}: "
                         f"{r.unplaced} patient{'s still need' if r.unplaced != 1 else ' still needs'} a bed.")
        elif r.patients_moved:
            lines.append(f"{r.city} can absorb its overflow{moved}, with {r.headroom} spare "
                         f"bed{'s' if r.headroom != 1 else ''} left.")
        else:
            lines.append(f"{r.city} needs no transfers ({r.headroom} spare bed{'s' if r.headroom != 1 else ''}).")
    return lines


# --------------------------------------------------------------------------- stand-in input
# Until Yasin's `allocate()` lands, the Hospital page and tests build the
# allocation table's bed column straight from the forecast with this ratio
# (fitted from the onsite data: hospital_beds_required ≈ 0.3 × dengue_cases).
FALLBACK_BEDS_PER_CASE = 0.3


def beds_from_forecast(fc: pd.DataFrame, beds_per_case: float = FALLBACK_BEDS_PER_CASE) -> pd.DataFrame:
    """A minimal allocation-shaped table (ward_id, city, hospital_beds_required) from a forecast."""
    out = fc[[C.WARD_COL, C.CITY_COL, "expected_cases"]].copy()
    out[BEDS_COL] = np.ceil(out["expected_cases"].clip(lower=0) * beds_per_case - 1e-9).astype(int)
    return out
