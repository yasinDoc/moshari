"""Constrained resource allocation: forecasts -> supplies and spraying crews.

1. **Demand.** Each ward's forecast cases become saline bags, diagnostic kits and
   hospital beds using per-case ratios *fitted from the onsite dataset* (observed
   demand vs. cases, least squares through the origin). Demand is rounded up so
   it is never understated.
2. **Priority.** Wards are ranked by risk (tier and chance of High/Critical)
   weighted by population density, so high-risk, crowded wards are served first.
3. **Scarcity.** Available regional stock is a share (30–100%) of total demand.
   Stock goes to wards in priority order until it runs out; any ward that gets
   less than it needs is flagged with the exact shortfall.
4. **Crews.** Spraying is the response for High and Critical wards (Medium wards
   get source reduction), so those wards need one crew per ``CASES_PER_CREW``
   expected cases. Every ward that needs a crew gets one in priority order, then
   remaining crews top up the highest-priority needs. Crew shortfalls are flagged
   separately from supply deficits.

Pure Python and pandas: no network, fully deterministic, so it runs offline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C

# Fallback ratios (per expected case) if the onsite file is missing; the fitted
# values from the onsite data are 2.39, 1.16 and 0.30.
DEFAULT_RATIOS = {"saline_bags_needed": 2.39, "diagnostic_kits_needed": 1.16, "hospital_beds_required": 0.30}

# (demand column, allocated column, label)
RESOURCES = [
    ("saline_bags_needed", "saline_bags_allocated", "saline bags"),
    ("diagnostic_kits_needed", "diagnostic_kits_allocated", "test kits"),
    ("hospital_beds_required", "hospital_beds_allocated", "beds"),
]
SINGULAR = {"saline bags": "saline bag", "test kits": "test kit", "beds": "bed", "crews": "crew"}
CASES_PER_CREW = 5.0      # one larvicide/fogging crew per ~5 expected cases
CREW_MIN_TIER = 2         # High and Critical wards get spraying crews
RISK_WEIGHTS = (0.6, 0.4)  # tier, P(High)


@dataclass(frozen=True)
class DemandRatios:
    ratios: dict[str, float]
    r2: dict[str, float]
    source: str  # "fitted from onsite data" or "default"


@lru_cache(maxsize=4)
def demand_ratios(path: Path = C.ONSITE_DATA_PATH) -> DemandRatios:
    """Per-case demand ratios, fitted through the origin on observed onsite demand."""
    try:
        df = pd.read_csv(path, usecols=[C.TARGET_COL, *C.SUPPLY_COLS])
    except (FileNotFoundError, ValueError):
        return DemandRatios(dict(DEFAULT_RATIOS), {}, "default")
    x = df[C.TARGET_COL].to_numpy(dtype=float)
    ratios, r2 = {}, {}
    for col in C.SUPPLY_COLS:
        y = df[col].to_numpy(dtype=float)
        k = float((x @ y) / max(x @ x, 1e-9))
        ratios[col] = round(k, 3)
        ss_res = float(((y - k * x) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum()) or 1.0
        r2[col] = round(1 - ss_res / ss_tot, 4)
    return DemandRatios(ratios, r2, "fitted from onsite data")


def priority_scores(fc: pd.DataFrame) -> pd.Series:
    """0–100: risk (tier and P(High)) scaled by relative population density.

    Risk decides most of the ordering; density moves a ward up or down within it
    (the densest ward keeps its full risk score, the sparsest keeps half).
    """
    tier = fc["tier_idx"].astype(float) / 3.0
    p_high = fc["p_high"] if "p_high" in fc else (fc["tier_idx"] >= 2).astype(float)
    risk = RISK_WEIGHTS[0] * tier + RISK_WEIGHTS[1] * p_high.astype(float)
    dens = fc["population_density_sqkm"].astype(float)
    dens_rel = dens / max(float(dens.max()), 1.0)
    return (100 * risk * (0.5 + 0.5 * dens_rel)).round(2)


def _greedy_fill(need: np.ndarray, order: np.ndarray, stock: int) -> np.ndarray:
    """Give each ward its full need in priority order until stock runs out."""
    out = np.zeros_like(need)
    left = int(stock)
    for i in order:
        give = min(int(need[i]), left)
        out[i] = give
        left -= give
        if left <= 0:
            break
    return out


def _assign_crews(crew_need: np.ndarray, order: np.ndarray, total: int) -> np.ndarray:
    """One crew to every ward that needs one (by priority), then top up the highest needs."""
    out = np.zeros_like(crew_need)
    left = int(total)
    for i in order:
        if left <= 0:
            break
        if crew_need[i] > 0:
            out[i] = 1
            left -= 1
    for i in order:
        if left <= 0:
            break
        extra = min(int(crew_need[i] - out[i]), left)
        if extra > 0:
            out[i] += extra
            left -= extra
    return out


def allocate(
    fc: pd.DataFrame,
    wards: pd.DataFrame,
    stock_pct: float = 1.0,
    total_crews: int = 40,
    plan_for: str = "expected",
    ratios: DemandRatios | None = None,
) -> pd.DataFrame:
    """One row per ward with demand, allocation under scarcity, crews and deficit flags.

    ``fc``: output of ``ForecastService.forecast_all`` (one horizon, one week).
    ``wards``: ward profiles indexed by ward_id (needs ``population_density_sqkm``).
    ``stock_pct``: available regional stock as a share of total demand (0.3–1.0).
    ``plan_for``: ``"expected"`` cases or ``"upper"`` (upper end of the 80% range).
    """
    if not 0.0 < stock_pct <= 1.0:
        raise ValueError("stock_pct must be between 0 and 1")
    ratios = ratios or demand_ratios()
    df = fc.copy()
    df["population_density_sqkm"] = df[C.WARD_COL].map(wards["population_density_sqkm"])
    cases = df["upper_80"] if plan_for == "upper" else df["expected_cases"]
    df["planned_cases"] = cases.astype(float)

    for need_col, _, _ in RESOURCES:
        df[need_col] = np.ceil(df["planned_cases"] * ratios.ratios[need_col] - 1e-9).astype(int)

    df["priority_score"] = priority_scores(df)
    order = np.lexsort((-df["planned_cases"].to_numpy(), -df["priority_score"].to_numpy()))

    for need_col, alloc_col, _ in RESOURCES:
        need = df[need_col].to_numpy()
        stock = math.floor(stock_pct * int(need.sum()) + 1e-9)
        df[alloc_col] = _greedy_fill(need, order, stock)

    needs_crew = df["tier_idx"] >= CREW_MIN_TIER
    df["crews_needed"] = np.where(needs_crew, np.ceil(df["planned_cases"] / CASES_PER_CREW), 0).astype(int)
    df.loc[needs_crew & (df["crews_needed"] == 0), "crews_needed"] = 1
    df["crews_assigned"] = _assign_crews(df["crews_needed"].to_numpy(), order, total_crews)

    def amount(n: int, label: str) -> str:
        return f"{n} {SINGULAR[label] if n == 1 else label}"

    notes, flags, fill = [], [], []
    for _, r in df.iterrows():
        short = [amount(int(r[n] - r[a]), label) for n, a, label in RESOURCES if r[a] < r[n]]
        flags.append(bool(short))
        crew_gap = int(r["crews_needed"] - r["crews_assigned"])
        parts = (["Short " + ", ".join(short)] if short else []) + (
            [f"needs {amount(crew_gap, 'crews')} more"] if crew_gap > 0 else [])
        notes.append("; ".join(parts) if parts else "Fully supplied")
        ratios_met = [r[a] / r[n] for n, a, _ in RESOURCES if r[n] > 0]
        fill.append(min(ratios_met) if ratios_met else 1.0)
    df["deficit_flag"] = flags                      # supplies short of demand
    df["crew_shortfall"] = (df["crews_needed"] - df["crews_assigned"]).clip(lower=0)
    df["deficit_note"] = notes
    df["fill_rate"] = np.round(fill, 3)
    df["priority_rank"] = 0
    df.iloc[order, df.columns.get_loc("priority_rank")] = np.arange(1, len(df) + 1)
    return df.sort_values("priority_rank").reset_index(drop=True)


def summarize(alloc: pd.DataFrame, total_crews: int) -> dict:
    """Totals for the dashboard: per-resource need/allocation/fill, deficits, crews."""
    res = {}
    for need_col, alloc_col, label in RESOURCES:
        need, got = int(alloc[need_col].sum()), int(alloc[alloc_col].sum())
        res[label] = {"needed": need, "allocated": got, "short": need - got,
                      "fill": (got / need) if need else 1.0,
                      "wards_short": int((alloc[alloc_col] < alloc[need_col]).sum())}
    crews_needed = int(alloc["crews_needed"].sum())
    crews_used = int(alloc["crews_assigned"].sum())
    return {
        "resources": res,
        "deficit_wards": int(alloc["deficit_flag"].sum()),
        "critical_deficits": int((alloc["deficit_flag"] & (alloc["tier_idx"] >= 2)).sum()),
        "crews": {"available": int(total_crews), "assigned": crews_used, "needed": crews_needed,
                  "unmet": max(crews_needed - crews_used, 0)},
    }
