from __future__ import annotations

import numpy as np

from moshari.data import validate
from moshari.features import FEATURE_COLS, FEATURE_SPECS, build_features, target_col


def test_rain_lags_are_computed_within_each_ward(tiny):
    f = build_features(validate(tiny)).set_index(["ward_id", "date"]).sort_index()
    a = f.loc["AAA_Ward_01"]
    b = f.loc["BBB_Ward_01"]
    # rainfall == week index (+1000 for ward B), so lag k at week i must equal i - k (+1000)
    for k in (1, 3, 8):
        assert np.allclose(a[f"rain_lag_{k}w"].iloc[k:].to_numpy(), np.arange(20 - k))
        assert np.allclose(b[f"rain_lag_{k}w"].iloc[k:].to_numpy(), np.arange(20 - k) + 1000)
        # the first k weeks of ward B must NOT borrow ward A's history
        assert a[f"rain_lag_{k}w"].iloc[:k].isna().all()
        assert b[f"rain_lag_{k}w"].iloc[:k].isna().all()


def test_breeding_window_is_sum_of_lags_two_to_four(tiny):
    f = build_features(validate(tiny))
    row = f[(f.ward_id == "AAA_Ward_01")].iloc[10]
    assert row["rain_breeding_window"] == (10 - 2) + (10 - 3) + (10 - 4)


def test_features_never_use_future_values(tiny):
    """Changing week 12 must not change any feature of weeks 0..11."""
    base = build_features(validate(tiny))
    changed = tiny.copy()
    changed.loc[(changed.ward_id == "AAA_Ward_01") & (changed.index % 20 == 12), ["rainfall_mm", "dengue_cases"]] = 999
    alt = build_features(validate(changed))
    early = (base.ward_id == "AAA_Ward_01") & (base.date < tiny.date.iloc[12])
    assert base.loc[early, FEATURE_COLS].equals(alt.loc[early, FEATURE_COLS])


def test_targets_look_forward_by_horizon(tiny):
    f = build_features(validate(tiny))
    a = f[f.ward_id == "AAA_Ward_01"].reset_index(drop=True)
    assert a.loc[5, target_col(3)] == 8  # cases == week index


def test_every_feature_has_a_driver_group():
    assert set(FEATURE_COLS) == set(FEATURE_SPECS)
