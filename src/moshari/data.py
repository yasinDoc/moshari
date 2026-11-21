"""Data ingestion and validation.

`load_dataset` accepts a path or a file-like object (e.g. a Streamlit upload),
validates it against the schema in :mod:`moshari.config` and returns a clean,
sorted frame. Bad data fails loudly with a readable message instead of
silently producing wrong forecasts.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import IO, Union

import pandas as pd

from . import config as C

Source = Union[str, Path, IO[bytes], BytesIO]


class DataValidationError(ValueError):
    """Raised when an input file does not match the expected schema."""


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Validate schema, types, ranges and weekly continuity. Returns a cleaned copy."""
    df = _normalise_columns(df)

    missing = [c for c in C.REQUIRED_COLS if c not in df.columns]
    if missing:
        raise DataValidationError(f"Missing required column(s): {', '.join(missing)}")

    df = df[C.REQUIRED_COLS].copy()
    df[C.DATE_COL] = pd.to_datetime(df[C.DATE_COL], errors="coerce")
    if df[C.DATE_COL].isna().any():
        raise DataValidationError("Some rows have an unreadable `date` (expected YYYY-MM-DD).")

    numeric = [*C.STATIC_COLS, *C.WEATHER_COLS, C.TARGET_COL]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    bad = df[numeric].isna().sum()
    bad = bad[bad > 0]
    if not bad.empty:
        detail = ", ".join(f"{k} ({v} rows)" for k, v in bad.items())
        raise DataValidationError(f"Non-numeric or empty values in: {detail}")

    for col, (lo, hi) in C.VALID_RANGES.items():
        out = ~df[col].between(lo, hi)
        if out.any():
            raise DataValidationError(
                f"`{col}` has {int(out.sum())} value(s) outside the plausible range [{lo}, {hi}]."
            )

    df[C.CITY_COL] = df[C.CITY_COL].astype(str).str.strip()
    df[C.WARD_COL] = df[C.WARD_COL].astype(str).str.strip()

    dupes = df.duplicated([C.WARD_COL, C.DATE_COL])
    if dupes.any():
        raise DataValidationError(f"{int(dupes.sum())} duplicate (ward_id, date) rows found.")

    df = df.sort_values([C.WARD_COL, C.DATE_COL]).reset_index(drop=True)

    # Lag features assume one row per ward per week with no gaps.
    gaps = df.groupby(C.WARD_COL)[C.DATE_COL].diff().dropna()
    if not (gaps == pd.Timedelta(days=7)).all():
        raise DataValidationError(
            "Each ward must have consecutive weekly rows (7-day spacing) for lag features to be valid."
        )
    return df


def load_dataset(source: Source | None = None) -> pd.DataFrame:
    """Load and validate the dataset from a CSV path or file-like object."""
    source = C.RAW_DATA_PATH if source is None else source
    if isinstance(source, (str, Path)) and not Path(source).exists():
        raise FileNotFoundError(
            f"Dataset not found at {source}. Run `python scripts/fetch_data.py` to download it."
        )
    return validate(pd.read_csv(source))


def file_fingerprint(path: Path) -> str:
    """Cheap content hash, used as a cache key so caches refresh only when data changes."""
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def corporation_of(ward_id: str) -> str:
    """'DNCC_Ward_07' -> 'DNCC'."""
    return ward_id.split("_", 1)[0]


def ward_label(ward_id: str) -> str:
    """'DNCC_Ward_07' -> 'DNCC · Ward 07'."""
    corp, _, rest = ward_id.partition("_")
    return f"{corp} · {rest.replace('_', ' ')}" if rest else ward_id
