"""Vector-control impact simulator: what do spraying crews buy over the next 2–4 weeks?

How a crew enters the model
---------------------------
Larviciding and fogging remove breeding sites and adult mosquitoes. In model
terms that is *less effective breeding water*: each crew removes ``per_crew`` of
the remaining breeding pressure in its ward, with diminishing returns:

    effect(c) = min(cap, 1 - (1 - per_crew) ** c)

and the ward's recent breeding signals (rain lags 0–4 weeks, the 2–4-week
breeding window, rolling sums and heavy-rain weeks) are scaled by
``1 - effect(c)``. Older rain (5–8 weeks back) has already produced its
mosquitoes and is left alone.

Why it's model-driven and safe
------------------------------
The counterfactual is scored by a dedicated *simulation model* per horizon:
LightGBM with monotone constraints so forecast cases can only fall when breeding
rain falls (adding a crew can never raise a forecast). Its hold-out accuracy is
close to the main model's. The *proportional* reduction it predicts is applied
to the main, validated forecast, so baseline numbers match the rest of the app.

Everything is local and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C
from .allocation import demand_ratios
from .model import SIM_KIND

DEFAULT_PER_CREW = 0.20   # share of remaining breeding pressure one crew removes
DEFAULT_CAP = 0.75        # no amount of spraying removes all breeding
MAX_CREWS_PER_WARD = 6
MIN_GAIN = 0.1            # cases prevented; below this a crew is held in reserve
SCALED_LAGS = range(0, 5)  # rain 0–4 weeks back: still producing mosquitoes


def crew_effect(crews, per_crew: float = DEFAULT_PER_CREW, cap: float = DEFAULT_CAP) -> np.ndarray:
    """Share of breeding pressure removed by ``crews`` crews (diminishing returns)."""
    c = np.asarray(crews, dtype=float)
    return np.minimum(cap, 1 - (1 - per_crew) ** c)


def apply_crews(rows: pd.DataFrame, effect) -> pd.DataFrame:
    """Scale each row's recent breeding signals by ``1 - effect`` and recompute the sums."""
    out = rows.copy()
    keep = 1 - np.asarray(effect, dtype=float)
    for k in SCALED_LAGS:
        out[f"rain_lag_{k}w"] = out[f"rain_lag_{k}w"] * keep
    lag = lambda ks: out[[f"rain_lag_{k}w" for k in ks]]  # noqa: E731
    out["rain_sum_2w"] = lag(range(2)).sum(axis=1)
    out["rain_sum_4w"] = lag(range(4)).sum(axis=1)
    out["rain_sum_8w"] = lag(range(8)).sum(axis=1)
    out["rain_breeding_window"] = lag((2, 3, 4)).sum(axis=1)
    out["heavy_rain_weeks_4w"] = (lag(range(4)) > 50).sum(axis=1).astype(float)
    return out


@dataclass
class EffectTable:
    """Main-model forecasts and simulated forecasts for every ward × crew count × horizon."""
    wards: pd.DataFrame           # ward_id, city, density, tier, baseline per horizon
    cases: np.ndarray             # [ward, crews 0..max, horizon] simulated main-scale cases
    horizons: list[int]
    per_crew: float
    cap: float

    @property
    def max_crews(self) -> int:
        return self.cases.shape[1] - 1

    def prevented(self) -> np.ndarray:
        """[ward, crews] cases prevented, summed over the 2–4-week window."""
        return (self.cases[:, :1, :] - self.cases).sum(axis=2)


def build_effect_table(svc, issue_date, per_crew: float = DEFAULT_PER_CREW, cap: float = DEFAULT_CAP,
                       max_crews: int = MAX_CREWS_PER_WARD, cities: list[str] | None = None) -> EffectTable:
    """Score every ward at 0..max_crews crews for each horizon (one vectorised pass per horizon)."""
    bundle = svc.bundle
    rows = svc.features.xs(pd.Timestamp(issue_date), level=C.DATE_COL, drop_level=False)
    if cities:
        rows = rows[rows[C.CITY_COL].isin(cities)]
    rows = rows.reset_index(drop=True)
    n, levels = len(rows), np.arange(max_crews + 1)
    horizons = [h for h in bundle.horizons if (h, SIM_KIND) in bundle.boosters]
    stacked = pd.concat([apply_crews(rows, crew_effect(c, per_crew, cap)) for c in levels], ignore_index=True)

    cases = np.zeros((n, len(levels), len(horizons)))
    base_info = {}
    for j, h in enumerate(horizons):
        main = bundle.predict(rows, h)
        base_info[f"baseline_h{h}"] = main["expected_cases"].to_numpy()
        if h == (3 if 3 in horizons else horizons[0]):
            base_info["tier"] = main["tier"].to_numpy()
            base_info["tier_idx"] = main["tier_idx"].to_numpy()
        sim = np.clip(bundle.boosters[(h, SIM_KIND)].predict(stacked[bundle.feature_cols]), 0, None)
        sim = sim.reshape(len(levels), n).T                       # [ward, crews]
        frac = np.where(sim[:, :1] > 1e-6, sim / np.maximum(sim[:, :1], 1e-6), 1.0)
        frac = np.minimum.accumulate(np.clip(frac, 0, 1), axis=1)   # guard: never rises with crews
        cases[:, :, j] = main["expected_cases"].to_numpy()[:, None] * frac

    wards = pd.DataFrame({
        C.WARD_COL: rows[C.WARD_COL].to_numpy(),
        C.CITY_COL: rows[C.CITY_COL].to_numpy(),
        "population_density_sqkm": rows["population_density_sqkm"].to_numpy(),
        **base_info,
    })
    return EffectTable(wards, cases, horizons, per_crew, cap)


def recommend(table: EffectTable, total_crews: int, max_per_ward: int | None = None,
              min_gain: float = MIN_GAIN) -> dict[str, int]:
    """Greedy crew placement: each crew goes where it prevents the most extra cases.

    Crews that would prevent fewer than ``min_gain`` cases (e.g. in the dry
    season) are held in reserve rather than wasted.
    """
    max_per_ward = min(max_per_ward or table.max_crews, table.max_crews)
    prev = table.prevented()
    alloc = np.zeros(len(table.wards), dtype=int)
    for _ in range(int(total_crews)):
        gains = np.full(len(alloc), -1.0)
        ok = alloc < max_per_ward
        gains[ok] = prev[np.arange(len(alloc))[ok], alloc[ok] + 1] - prev[np.arange(len(alloc))[ok], alloc[ok]]
        best = int(np.argmax(gains))
        if gains[best] < min_gain:
            break
        alloc[best] += 1
    return {w: int(c) for w, c in zip(table.wards[C.WARD_COL], alloc) if c > 0}


def simulate(table: EffectTable, plan: dict[str, int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply a crew plan.

    Returns ``(by_ward, by_horizon)``:
    * by_ward: crews, cases prevented over the window, ROI (cases per crew), marginal
      value of one more crew, and per-horizon baseline vs simulated cases;
    * by_horizon: totals for cases, beds and saline, baseline vs with crews.
    """
    ratios = demand_ratios().ratios
    w = table.wards.copy()
    idx = np.arange(len(w))
    crews = np.array([min(int(plan.get(wid, 0)), table.max_crews) for wid in w[C.WARD_COL]])
    prev = table.prevented()
    w["crews"] = crews
    w["cases_prevented"] = prev[idx, crews]
    w["roi"] = np.where(crews > 0, w["cases_prevented"] / np.maximum(crews, 1), 0.0)
    nxt = np.minimum(crews + 1, table.max_crews)
    w["next_crew_gain"] = np.where(crews < table.max_crews, prev[idx, nxt] - prev[idx, crews], 0.0)
    w["first_crew_roi"] = prev[:, 1]
    for j, h in enumerate(table.horizons):
        w[f"with_crews_h{h}"] = table.cases[idx, crews, j]

    rows = []
    for j, h in enumerate(table.horizons):
        base = float(table.cases[:, 0, j].sum())
        sim = float(table.cases[idx, crews, j].sum())
        rows.append({
            "horizon": h, "cases_baseline": base, "cases_with_crews": sim, "cases_prevented": base - sim,
            "beds_baseline": base * ratios["hospital_beds_required"],
            "beds_with_crews": sim * ratios["hospital_beds_required"],
            "saline_baseline": base * ratios["saline_bags_needed"],
            "saline_with_crews": sim * ratios["saline_bags_needed"],
        })
    by_h = pd.DataFrame(rows)
    by_h["beds_freed"] = by_h["beds_baseline"] - by_h["beds_with_crews"]
    by_h["saline_saved"] = by_h["saline_baseline"] - by_h["saline_with_crews"]
    return w, by_h
