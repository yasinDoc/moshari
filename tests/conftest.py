from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from moshari.data import load_dataset


@pytest.fixture(scope="session")
def raw() -> pd.DataFrame:
    return load_dataset()


@pytest.fixture()
def tiny() -> pd.DataFrame:
    """Two wards, 20 weeks, with rainfall = week index so lags are easy to check."""
    dates = pd.date_range("2024-01-01", periods=20, freq="7D")
    rows = []
    for w, offset in (("AAA_Ward_01", 0), ("BBB_Ward_01", 1000)):
        for i, d in enumerate(dates):
            rows.append({
                "date": d, "city": w[:3], "ward_id": w,
                "population_density_sqkm": 40000, "water_logging_risk_index": 0.5, "sanitation_score": 0.5,
                "avg_temp_c": 28.0, "max_temp_c": 32.0, "min_temp_c": 24.0,
                "rainfall_mm": float(i + offset), "relative_humidity_pct": 80.0,
                "dengue_cases": i,
            })
    return pd.DataFrame(rows)
