"""Central configuration: paths, schema, horizons and feature groups.

Everything tunable lives here so the pipeline, the training script and the
dashboard can never drift apart.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_PATH = DATA_DIR / "raw" / "dengue.csv"
# Phase 2 onsite file: the same rows plus observed supply demand per ward-week.
ONSITE_DATA_PATH = DATA_DIR / "raw" / "dengue_onsite.csv"
SUPPLY_COLS = ["saline_bags_needed", "diagnostic_kits_needed", "hospital_beds_required"]
MODELS_DIR = PROJECT_ROOT / "models"
MODEL_PATH = MODELS_DIR / "moshari_lgbm.joblib"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"
BACKTEST_PATH = ARTIFACTS_DIR / "backtest.parquet"
ASSETS_DIR = PROJECT_ROOT / "assets"

# Public source of the challenge dataset (only used by `scripts/fetch_data.py`).
DATASET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1QFI0ACJRvJQkiQT3LfGHklM3g4PgaJWUt8xSVU07NIE/export?format=csv"
)

# --------------------------------------------------------------------------- #
# Input schema
# --------------------------------------------------------------------------- #
DATE_COL = "date"
CITY_COL = "city"
WARD_COL = "ward_id"
TARGET_COL = "dengue_cases"

WEATHER_COLS = [
    "avg_temp_c",
    "max_temp_c",
    "min_temp_c",
    "rainfall_mm",
    "relative_humidity_pct",
]
STATIC_COLS = [
    "population_density_sqkm",
    "water_logging_risk_index",
    "sanitation_score",
]
REQUIRED_COLS = [DATE_COL, CITY_COL, WARD_COL, *STATIC_COLS, *WEATHER_COLS, TARGET_COL]

# Plausible physical ranges, used to reject corrupt uploads before they reach the model.
VALID_RANGES: dict[str, tuple[float, float]] = {
    "avg_temp_c": (0.0, 50.0),
    "max_temp_c": (0.0, 55.0),
    "min_temp_c": (-5.0, 45.0),
    "rainfall_mm": (0.0, 1500.0),
    "relative_humidity_pct": (0.0, 100.0),
    "population_density_sqkm": (0.0, 500_000.0),
    "water_logging_risk_index": (0.0, 1.0),
    "sanitation_score": (0.0, 1.0),
    "dengue_cases": (0.0, 100_000.0),
}

CITY_CORPORATIONS = {
    "CCC": "Chattogram City Corporation",
    "DNCC": "Dhaka North City Corporation",
    "DSCC": "Dhaka South City Corporation",
    "GCC": "Gazipur City Corporation",
    "NCC": "Narayanganj City Corporation",
}

# --------------------------------------------------------------------------- #
# Forecasting setup
# --------------------------------------------------------------------------- #
# Forecast horizons in weeks: the 2-to-4-week early-warning window from the brief.
HORIZONS = (2, 3, 4)
# Rainfall lags (weeks) – the vector breeding clock spans ~1–4 weeks, we look back 8.
RAIN_LAGS = tuple(range(0, 9))
# Lower / upper quantiles for the 80% forecast interval.
QUANTILES = (0.10, 0.90)

# Chronological split, by the *target* week (the week being forecast).
TRAIN_END = "2022-12-31"   # fit
VALID_END = "2023-12-31"   # early stopping / model selection
# everything after VALID_END is the untouched hold-out test period (2024–2025)

# Risk tiers are derived from quantiles of weekly ward case counts in the training years.
TIER_NAMES = ("Low", "Medium", "High", "Critical")
TIER_QUANTILES = (0.70, 0.85, 0.95)  # lower bounds of Medium / High / Critical

RANDOM_SEED = 42


def offline() -> bool:
    """True when ``MOSHARI_OFFLINE`` is set: no network calls at all (judging kill switch).

    Forecasting, allocation, routing, simulation and dispatch templates never need
    the network; this only stops the optional Open-Meteo request on Live outlook.
    """
    return os.environ.get("MOSHARI_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}
