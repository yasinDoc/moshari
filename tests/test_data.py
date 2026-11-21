from __future__ import annotations

from io import BytesIO

import pytest

from moshari.data import DataValidationError, load_dataset, validate


def test_bundled_dataset_is_valid(raw):
    assert len(raw) == 31_320
    assert raw["ward_id"].nunique() == 60


def test_missing_column_is_rejected(tiny):
    with pytest.raises(DataValidationError, match="rainfall_mm"):
        validate(tiny.drop(columns="rainfall_mm"))


def test_out_of_range_humidity_is_rejected(tiny):
    tiny.loc[3, "relative_humidity_pct"] = 140
    with pytest.raises(DataValidationError, match="relative_humidity_pct"):
        validate(tiny)


def test_gap_in_weeks_is_rejected(tiny):
    with pytest.raises(DataValidationError, match="consecutive"):
        validate(tiny.drop(index=5))


def test_duplicate_rows_are_rejected(tiny):
    import pandas as pd
    with pytest.raises(DataValidationError, match="duplicate"):
        validate(pd.concat([tiny, tiny.iloc[[0]]]))


def test_file_like_upload_round_trip(tiny):
    buf = BytesIO(tiny.to_csv(index=False).encode())
    assert len(load_dataset(buf)) == len(tiny)
