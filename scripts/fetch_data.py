"""Download the challenge dataset (public Google Sheet) to data/raw/dengue.csv.

The CSV is already committed, so this is only needed to refresh it. One HTTP
request, no API key; the file is validated before it replaces the local copy.
"""

from __future__ import annotations

import sys
import urllib.request
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from moshari import config as C  # noqa: E402
from moshari.data import load_dataset  # noqa: E402

if __name__ == "__main__":
    with urllib.request.urlopen(C.DATASET_CSV_URL, timeout=60) as resp:
        payload = resp.read()
    df = load_dataset(BytesIO(payload))  # raises if the sheet changed shape
    C.RAW_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    C.RAW_DATA_PATH.write_bytes(payload)
    print(f"Saved {len(df):,} validated rows to {C.RAW_DATA_PATH}")
