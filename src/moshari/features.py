"""Feature engineering: the vector breeding clock, encoded as ward-level lags.

Every time-dependent feature is computed **within each ward** (``groupby(ward_id)``)
and only looks backwards from the forecast issue week ``t``. Targets look
forwards (``t + h``). Nothing from the future can leak into a feature row,
and no ward's history leaks into another ward (both are covered by tests).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

# Human-readable driver groups used for the explanation panel in the dashboard.
GROUP_RAIN = "Rainfall (breeding clock)"
GROUP_TEMP = "Temperature"
GROUP_HUMID = "Humidity"
GROUP_WARD = "Ward vulnerability"
GROUP_CASES = "Recent transmission"
GROUP_SEASON = "Seasonality"
GROUP_FORECAST = "Weather forecast"

DRIVER_GROUPS = (GROUP_RAIN, GROUP_TEMP, GROUP_HUMID, GROUP_WARD, GROUP_CASES, GROUP_SEASON)

# Weather for the 1–2 weeks *after* the issue week. Only forecast-assisted models use
# these: in training they come from observed weather (with noise added to mimic
# forecast error); live, they come from Open-Meteo's forecast.
LEAD_SPECS: dict[str, tuple[str, str]] = {
    "rain_lead_1w": (GROUP_FORECAST, "Rain forecast, next week"),
    "rain_lead_2w": (GROUP_FORECAST, "Rain forecast, week after"),
    "temp_lead_1w": (GROUP_FORECAST, "Temperature forecast, next week"),
    "humid_lead_1w": (GROUP_FORECAST, "Humidity forecast, next week"),
}
LEAD_COLS = list(LEAD_SPECS)


def _feature_specs() -> dict[str, tuple[str, str]]:
    """feature name -> (driver group, human label)."""
    specs: dict[str, tuple[str, str]] = {}
    for k in C.RAIN_LAGS:
        label = "Rainfall this week" if k == 0 else f"Rainfall {k} wk ago"
        specs[f"rain_lag_{k}w"] = (GROUP_RAIN, label)
    specs.update(
        {
            "rain_sum_2w": (GROUP_RAIN, "Rainfall, last 2 wks"),
            "rain_sum_4w": (GROUP_RAIN, "Rainfall, last 4 wks"),
            "rain_sum_8w": (GROUP_RAIN, "Rainfall, last 8 wks"),
            "rain_breeding_window": (GROUP_RAIN, "Rainfall 2–4 wks ago (breeding window)"),
            "heavy_rain_weeks_4w": (GROUP_RAIN, "Heavy-rain weeks (>50 mm), last 4"),
            "temp_mean_2w": (GROUP_TEMP, "Avg temperature, last 2 wks"),
            "temp_mean_4w": (GROUP_TEMP, "Avg temperature, last 4 wks"),
            "temp_lag_3w": (GROUP_TEMP, "Avg temperature 3 wks ago"),
            "temp_range_4w": (GROUP_TEMP, "Day–night temperature range, 4 wks"),
            "humidity_mean_2w": (GROUP_HUMID, "Humidity, last 2 wks"),
            "humidity_mean_4w": (GROUP_HUMID, "Humidity, last 4 wks"),
            "humidity_lag_3w": (GROUP_HUMID, "Humidity 3 wks ago"),
            "population_density_sqkm": (GROUP_WARD, "Population density"),
            "water_logging_risk_index": (GROUP_WARD, "Water-logging risk"),
            "sanitation_score": (GROUP_WARD, "Sanitation score"),
            "vulnerability_index": (GROUP_WARD, "Composite vulnerability"),
            "city_code": (GROUP_WARD, "City corporation"),
            "cases_lag_0w": (GROUP_CASES, "Cases this week"),
            "cases_lag_1w": (GROUP_CASES, "Cases last week"),
            "cases_lag_2w": (GROUP_CASES, "Cases 2 wks ago"),
            "cases_mean_4w": (GROUP_CASES, "Avg weekly cases, last 4 wks"),
            "cases_trend_2w": (GROUP_CASES, "Case trend (2-wk change)"),
            "week_sin": (GROUP_SEASON, "Time of year (sin)"),
            "week_cos": (GROUP_SEASON, "Time of year (cos)"),
        }
    )
    return specs


FEATURE_SPECS = _feature_specs()
FEATURE_COLS = list(FEATURE_SPECS)
CATEGORICAL_FEATURES = ["city_code"]


def target_col(h: int) -> str:
    return f"target_cases_h{h}"


def vulnerability_index(df: pd.DataFrame) -> pd.Series:
    """Composite 0–1 ward vulnerability: drainage, crowding and (poor) sanitation.

    Density is min-max scaled against fixed bounds (not the data) so the index is
    stable for a single ward or an uploaded subset.
    """
    density = ((df["population_density_sqkm"] - 10_000) / (80_000 - 10_000)).clip(0, 1)
    return (
        0.45 * df["water_logging_risk_index"]
        + 0.30 * density
        + 0.25 * (1 - df["sanitation_score"])
    ).round(4)


def build_features(df: pd.DataFrame, city_categories: list[str] | None = None) -> pd.DataFrame:
    """Return one row per (ward, issue week) with lag features and forward targets.

    ``df`` must be the validated frame from :func:`moshari.data.load_dataset`.
    ``city_categories`` fixes the city -> integer mapping (taken from the trained
    model at inference time so codes always match training).
    """
    df = df.sort_values([C.WARD_COL, C.DATE_COL]).reset_index(drop=True)
    g = df.groupby(C.WARD_COL, sort=False)

    def roll(col: str, n: int, fn: str = "mean") -> pd.Series:
        return g[col].transform(lambda s: getattr(s.rolling(n, min_periods=n), fn)())

    out = df[[C.DATE_COL, C.CITY_COL, C.WARD_COL, *C.WEATHER_COLS, C.TARGET_COL]].copy()

    # --- Rainfall: the breeding clock ------------------------------------- #
    for k in C.RAIN_LAGS:
        out[f"rain_lag_{k}w"] = g["rainfall_mm"].shift(k)
    out["rain_sum_2w"] = roll("rainfall_mm", 2, "sum")
    out["rain_sum_4w"] = roll("rainfall_mm", 4, "sum")
    out["rain_sum_8w"] = roll("rainfall_mm", 8, "sum")
    out["rain_breeding_window"] = out["rain_lag_2w"] + out["rain_lag_3w"] + out["rain_lag_4w"]
    heavy = (df["rainfall_mm"] > 50).astype(float)
    out["heavy_rain_weeks_4w"] = heavy.groupby(df[C.WARD_COL], sort=False).transform(
        lambda s: s.rolling(4, min_periods=4).sum()
    )

    # --- Temperature & humidity (development speed / mosquito survival) --- #
    out["temp_mean_2w"] = roll("avg_temp_c", 2)
    out["temp_mean_4w"] = roll("avg_temp_c", 4)
    out["temp_lag_3w"] = g["avg_temp_c"].shift(3)
    trange = df["max_temp_c"] - df["min_temp_c"]
    out["temp_range_4w"] = trange.groupby(df[C.WARD_COL], sort=False).transform(
        lambda s: s.rolling(4, min_periods=4).mean()
    )
    out["humidity_mean_2w"] = roll("relative_humidity_pct", 2)
    out["humidity_mean_4w"] = roll("relative_humidity_pct", 4)
    out["humidity_lag_3w"] = g["relative_humidity_pct"].shift(3)

    # --- Ward vulnerability (static) --------------------------------------- #
    for col in C.STATIC_COLS:
        out[col] = df[col]
    out["vulnerability_index"] = vulnerability_index(df)
    cats = city_categories or sorted(df[C.CITY_COL].unique())
    out["city_code"] = pd.Categorical(df[C.CITY_COL], categories=cats).codes.astype("int16")

    # --- Recent transmission (cases reported up to the issue week) ---------- #
    out["cases_lag_0w"] = df[C.TARGET_COL].astype(float)
    out["cases_lag_1w"] = g[C.TARGET_COL].shift(1)
    out["cases_lag_2w"] = g[C.TARGET_COL].shift(2)
    out["cases_mean_4w"] = roll(C.TARGET_COL, 4)
    out["cases_trend_2w"] = out["cases_lag_0w"] - out["cases_lag_2w"]

    # --- Seasonality -------------------------------------------------------- #
    week = df[C.DATE_COL].dt.isocalendar().week.astype(float)
    out["week_sin"] = np.sin(2 * np.pi * week / 52.18)
    out["week_cos"] = np.cos(2 * np.pi * week / 52.18)

    # --- Weather leads (for forecast-assisted models only) ------------------ #
    out["rain_lead_1w"] = g["rainfall_mm"].shift(-1)
    out["rain_lead_2w"] = g["rainfall_mm"].shift(-2)
    out["temp_lead_1w"] = g["avg_temp_c"].shift(-1)
    out["humid_lead_1w"] = g["relative_humidity_pct"].shift(-1)

    # --- Forward targets: cases h weeks after the issue week --------------- #
    for h in C.HORIZONS:
        out[target_col(h)] = g[C.TARGET_COL].shift(-h)

    return out


def lag_correlations(df: pd.DataFrame, max_lag: int = 10) -> pd.DataFrame:
    """Pearson correlation between rainfall lagged k weeks and cases, within wards.

    This is the empirical evidence for the breeding clock shown in the dashboard.
    """
    df = df.sort_values([C.WARD_COL, C.DATE_COL])
    g = df.groupby(C.WARD_COL, sort=False)["rainfall_mm"]
    rows = []
    for k in range(max_lag + 1):
        lagged = g.shift(k)
        mask = lagged.notna()
        r = np.corrcoef(lagged[mask], df.loc[mask, C.TARGET_COL])[0, 1]
        rows.append({"lag_weeks": k, "correlation": float(r)})
    return pd.DataFrame(rows)
