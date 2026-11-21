"""End-to-end training with a strict chronological split.

    2016 ─────────── 2022 │ 2023  │ 2024 ── 2025
          TRAIN           │ VALID │   TEST (hold-out)

1. Fit on TRAIN, early-stop on VALID  -> number of boosting rounds per model.
2. Refit on TRAIN+VALID with those rounds -> the shipped model.
3. Score that model on TEST, which it has never seen, against three baselines.

With ``production=True`` step 2 also includes TEST (use after evaluation, for a
live deployment that should learn from the most recent seasons).
"""

from __future__ import annotations

import json
import time
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import config as C
from .data import file_fingerprint, load_dataset
from .evaluation import (
    climatology,
    interval_coverage,
    regression_metrics,
    seasonal_naive,
    tier_confusion,
    tier_metrics,
)
from .features import FEATURE_COLS, FEATURE_SPECS, build_features, lag_correlations, target_col
from .model import KINDS, ForecastBundle, conformal_offset, fit_booster, interval
from .risk import assign_tier, tier_thresholds


def _split(feats: pd.DataFrame, horizon: int) -> dict[str, pd.DataFrame]:
    tcol = target_col(horizon)
    usable = feats.dropna(subset=[*FEATURE_COLS, tcol])
    target_date = usable[C.DATE_COL] + pd.Timedelta(weeks=horizon)
    return {
        "train": usable[target_date <= C.TRAIN_END],
        "valid": usable[(target_date > C.TRAIN_END) & (target_date <= C.VALID_END)],
        "test": usable[target_date > C.VALID_END],
    }


def run_training(production: bool = False, log=print) -> dict[str, Any]:
    t0 = time.perf_counter()
    raw = load_dataset()
    city_categories = sorted(raw[C.CITY_COL].unique())
    feats = build_features(raw, city_categories)
    log(f"Loaded {len(raw):,} rows · {raw[C.WARD_COL].nunique()} wards · "
        f"{raw[C.DATE_COL].min():%Y-%m-%d} → {raw[C.DATE_COL].max():%Y-%m-%d}")

    train_raw = raw[raw[C.DATE_COL] <= C.TRAIN_END]
    thresholds = tier_thresholds(train_raw[C.TARGET_COL])
    log(f"Tier thresholds (weekly ward cases): Medium ≥ {thresholds[0]}, "
        f"High ≥ {thresholds[1]}, Critical ≥ {thresholds[2]}")

    boosters: dict[tuple[int, str], lgb.Booster] = {}
    metrics: dict[str, Any] = {"horizons": {}}
    backtests = []
    importance = {}
    offsets: dict[int, float] = {}

    for h in C.HORIZONS:
        tcol = target_col(h)
        parts = _split(feats, h)
        tr, va, te = parts["train"], parts["valid"], parts["test"]
        log(f"\n[h={h}w] train {len(tr):,} · valid {len(va):,} · test {len(te):,}")

        rounds, stage_a = {}, {}
        for kind in KINDS:
            b = fit_booster(kind, tr[FEATURE_COLS], tr[tcol], va[FEATURE_COLS], va[tcol])
            rounds[kind] = max(int(b.best_iteration * 1.1), 50)
            stage_a[kind] = b
        # Calibrate the 80% interval on the validation year (unseen by stage-A models).
        offsets[h] = conformal_offset(
            va[tcol],
            stage_a["q10"].predict(va[FEATURE_COLS]),
            stage_a["q90"].predict(va[FEATURE_COLS]),
        )

        final_fit = pd.concat([tr, va, te] if production else [tr, va])
        bundle_h = {}
        for kind in KINDS:
            bundle_h[kind] = fit_booster(
                kind, final_fit[FEATURE_COLS], final_fit[tcol], num_rounds=rounds[kind]
            )
            boosters[(h, kind)] = bundle_h[kind]

        # ---- hold-out evaluation ------------------------------------------
        X_te = te[FEATURE_COLS]
        y_te = te[tcol].to_numpy()
        pred = np.clip(bundle_h["mean"].predict(X_te), 0, None)
        lo, hi = interval(bundle_h["q10"].predict(X_te), bundle_h["q90"].predict(X_te), pred, offsets[h])

        baselines = {
            "persistence": te["cases_lag_0w"].to_numpy(),
            "seasonal_naive": seasonal_naive(raw, te, h).fillna(0).to_numpy(),
            "climatology": climatology(train_raw, te, h).fillna(0).to_numpy(),
        }
        hm = {
            "rounds": rounds,
            "n_train": int(len(final_fit)),
            "n_test": int(len(te)),
            "model": {**regression_metrics(y_te, pred), **tier_metrics(y_te, pred, thresholds)},
            "baselines": {k: regression_metrics(y_te, v) for k, v in baselines.items()},
            "interval_coverage_80": interval_coverage(y_te, lo, hi),
            "interval_offset": offsets[h],
            "interval_mean_width": float(np.mean(hi - lo)),
            "confusion": tier_confusion(y_te, pred, thresholds).to_dict(),
        }
        best_base = min(v["mae"] for v in hm["baselines"].values())
        hm["mae_improvement_vs_best_baseline"] = float(1 - hm["model"]["mae"] / best_base)
        metrics["horizons"][str(h)] = hm
        log(f"  MAE {hm['model']['mae']:.2f} · RMSE {hm['model']['rmse']:.2f} · "
            f"tier acc {hm['model']['tier_accuracy']:.1%} · alert recall {hm['model']['alert_recall']:.1%} · "
            f"80% PI coverage {hm['interval_coverage_80']:.1%} · "
            f"{hm['mae_improvement_vs_best_baseline']:.0%} lower MAE than best baseline")

        gain = bundle_h["mean"].feature_importance("gain")
        importance[str(h)] = {
            f: float(v) for f, v in sorted(zip(FEATURE_COLS, gain / gain.sum()), key=lambda x: -x[1])
        }
        backtests.append(
            pd.DataFrame(
                {
                    "issue_date": te[C.DATE_COL].to_numpy(),
                    "target_date": (te[C.DATE_COL] + pd.Timedelta(weeks=h)).to_numpy(),
                    "city": te[C.CITY_COL].to_numpy(),
                    "ward_id": te[C.WARD_COL].to_numpy(),
                    "horizon": h,
                    "actual": y_te,
                    "expected": pred,
                    "lower_80": lo,
                    "upper_80": hi,
                    "tier_idx": assign_tier(pred, thresholds),
                    "actual_tier_idx": assign_tier(y_te, thresholds),
                    **{f"base_{k}": v for k, v in baselines.items()},
                }
            )
        )

    trained_through = str(raw[C.DATE_COL].max().date()) if production else C.VALID_END
    metadata = {
        "trained_through": trained_through,
        "production": production,
        "split": {"train_end": C.TRAIN_END, "valid_end": C.VALID_END},
        "data_fingerprint": file_fingerprint(C.RAW_DATA_PATH),
        "data_rows": int(len(raw)),
        "wards": int(raw[C.WARD_COL].nunique()),
        "lightgbm_version": lgb.__version__,
        "trained_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "feature_count": len(FEATURE_COLS),
    }
    bundle = ForecastBundle(boosters, city_categories, thresholds, metadata, interval_offsets=offsets)
    path = bundle.save()

    C.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    pd.concat(backtests, ignore_index=True).to_parquet(C.BACKTEST_PATH, index=False)
    metrics.update(
        {
            "metadata": metadata,
            "tier_thresholds": thresholds,
            "lag_correlations": lag_correlations(raw).to_dict(orient="records"),
            "feature_importance": importance,
            "feature_labels": {f: FEATURE_SPECS[f][1] for f in FEATURE_COLS},
            "train_seconds": round(time.perf_counter() - t0, 1),
        }
    )
    C.METRICS_PATH.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    log(f"\nSaved model → {path.relative_to(C.PROJECT_ROOT)} "
        f"({path.stat().st_size / 1024:.0f} KB) in {metrics['train_seconds']}s")
    return metrics
