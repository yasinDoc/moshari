"""Train the Moshari forecast models.

    python scripts/train.py               # evaluation model (trained through 2023, tested on 2024–25)
    python scripts/train.py --production  # also learn from the hold-out years, for live deployment
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from moshari.training import run_training  # noqa: E402

if __name__ == "__main__":
    # Windows consoles default to cp1252; make arrows and dots print everywhere.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--production", action="store_true", help="refit on all years incl. the test period")
    args = parser.parse_args()
    run_training(production=args.production)
