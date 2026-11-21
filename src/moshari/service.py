"""Forecast service: the single entry point the dashboard (or a future API) talks to.

It owns the validated data, its feature table and the trained bundle, and
answers questions like "what is every ward's risk 3 weeks after this week?".
Features are computed once per dataset; each forecast is a sub-millisecond
LightGBM call on already-built rows, so there is nothing to call remotely.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C
from .features import FEATURE_COLS, build_features
from .model import ForecastBundle
from .risk import DEFAULT_ALERT_POLICY, apply_alert_policy


@dataclass
class Scenario:
    """What-if adjustments applied to the two most recent weeks of a ward's weather."""

    rain_factor: float = 1.0      # multiply rainfall
    temp_offset: float = 0.0      # add °C to avg/max/min temperature
    humidity_offset: float = 0.0  # add percentage points of relative humidity

    @property
    def is_baseline(self) -> bool:
        return self.rain_factor == 1.0 and self.temp_offset == 0.0 and self.humidity_offset == 0.0


class ForecastService:
    def __init__(self, raw: pd.DataFrame, bundle: ForecastBundle, use_forecast: bool = False):
        """``use_forecast``: rows carry weather for the weeks after the issue week (live mode),
        so the forecast-assisted models are used where available."""
        self.raw = raw.sort_values([C.WARD_COL, C.DATE_COL]).reset_index(drop=True)
        self.bundle = bundle
        self.use_forecast = use_forecast
        self.features = build_features(self.raw, bundle.city_categories)
        complete = self.features.dropna(subset=FEATURE_COLS)
        self.features = complete.set_index([C.WARD_COL, C.DATE_COL], drop=False).sort_index()
        self.wards = (
            self.raw.drop_duplicates(C.WARD_COL)
            .set_index(C.WARD_COL)[[C.CITY_COL, *C.STATIC_COLS]]
            .sort_index()
        )

    # ------------------------------------------------------------------ dates
    @property
    def issue_dates(self) -> list[pd.Timestamp]:
        return sorted(self.features[C.DATE_COL].unique())

    def default_issue_date(self) -> pd.Timestamp:
        """A week ahead of the most recent season's peak — the moment an early warning matters."""
        last_year = self.raw[C.DATE_COL].dt.year.max()
        season = self.raw[self.raw[C.DATE_COL].dt.year == last_year]
        weekly = season.groupby(C.DATE_COL)[C.TARGET_COL].sum()
        target = weekly.idxmax() - pd.Timedelta(weeks=4)
        dates = pd.DatetimeIndex(self.issue_dates)
        return dates[dates.get_indexer([target], method="nearest")[0]]

    # -------------------------------------------------------------- forecasts
    def forecast_all(self, issue_date, horizon: int, cities: list[str] | None = None,
                     policy: str = DEFAULT_ALERT_POLICY) -> pd.DataFrame:
        """Risk for every ward, issued at ``issue_date`` for ``horizon`` weeks later.

        Sorted by alert priority (``alert_score`` under ``policy``), most urgent first.
        """
        rows = self.features.xs(pd.Timestamp(issue_date), level=C.DATE_COL, drop_level=False)
        if cities:
            rows = rows[rows[C.CITY_COL].isin(cities)]
        pred = self.bundle.predict(rows, horizon, self.use_forecast)
        out = pd.concat(
            [rows[[C.WARD_COL, C.CITY_COL, C.DATE_COL, "cases_lag_0w", "rain_breeding_window",
                   "vulnerability_index"]].reset_index(drop=True),
             pred.reset_index(drop=True)],
            axis=1,
        )
        out["target_date"] = out[C.DATE_COL] + pd.Timedelta(weeks=horizon)
        out["actual"] = [self._actual(w, d) for w, d in zip(out[C.WARD_COL], out["target_date"])]
        out = apply_alert_policy(out, self.bundle.tier_thresholds, policy)
        return out.sort_values(["alert_score", "expected_cases"], ascending=False).reset_index(drop=True)

    def forecast_timeline(self, issue_dates, horizon: int, cities: list[str] | None = None) -> pd.DataFrame:
        """Forecasts for every ward across a range of issue weeks (for the season heatmap)."""
        idx = pd.IndexSlice
        rows = self.features.loc[idx[:, list(pd.DatetimeIndex(issue_dates))], :]
        if cities:
            rows = rows[rows[C.CITY_COL].isin(cities)]
        pred = self.bundle.predict(rows, horizon, self.use_forecast)
        return pd.DataFrame(
            {
                C.WARD_COL: rows[C.WARD_COL].to_numpy(),
                C.CITY_COL: rows[C.CITY_COL].to_numpy(),
                "target_date": (rows[C.DATE_COL] + pd.Timedelta(weeks=horizon)).to_numpy(),
                "expected_cases": pred["expected_cases"].to_numpy(),
                "tier_idx": pred["tier_idx"].to_numpy(),
            }
        )

    def ward_outlook(self, ward_id: str, issue_date, scenario: Scenario | None = None) -> pd.DataFrame:
        """Forecasts for one ward at every horizon (the 2-to-4-week outlook)."""
        row = self.ward_row(ward_id, issue_date, scenario)
        frames = []
        for h in self.bundle.horizons:
            p = self.bundle.predict(row, h, self.use_forecast).iloc[0].to_dict()
            target = pd.Timestamp(issue_date) + pd.Timedelta(weeks=h)
            frames.append({"horizon": h, "target_date": target, "actual": self._actual(ward_id, target), **p})
        return pd.DataFrame(frames)

    def ward_row(self, ward_id: str, issue_date, scenario: Scenario | None = None) -> pd.DataFrame:
        """The single feature row for a ward/week, optionally with a what-if scenario applied."""
        issue_date = pd.Timestamp(issue_date)
        if scenario is None or scenario.is_baseline:
            return self.features.loc[[(ward_id, issue_date)]]
        ward = self.raw[self.raw[C.WARD_COL] == ward_id].copy()
        recent = ward[C.DATE_COL].between(issue_date - pd.Timedelta(weeks=1), issue_date)
        ward.loc[recent, "rainfall_mm"] *= scenario.rain_factor
        for col in ("avg_temp_c", "max_temp_c", "min_temp_c"):
            ward.loc[recent, col] += scenario.temp_offset
        ward.loc[recent, "relative_humidity_pct"] = (
            ward.loc[recent, "relative_humidity_pct"] + scenario.humidity_offset
        ).clip(0, 100)
        feats = build_features(ward, self.bundle.city_categories)
        return feats[feats[C.DATE_COL] == issue_date]

    def explain(self, ward_id: str, issue_date, horizon: int, scenario: Scenario | None = None):
        return self.bundle.explain_grouped(self.ward_row(ward_id, issue_date, scenario), horizon)

    # ---------------------------------------------------------------- history
    def ward_history(self, ward_id: str, end, weeks: int = 16) -> pd.DataFrame:
        end = pd.Timestamp(end)
        w = self.raw[self.raw[C.WARD_COL] == ward_id]
        return w[w[C.DATE_COL].between(end - pd.Timedelta(weeks=weeks - 1), end)].copy()

    def _actual(self, ward_id: str, date) -> float:
        try:
            return float(self.features.loc[(ward_id, pd.Timestamp(date)), C.TARGET_COL])
        except KeyError:
            return np.nan
