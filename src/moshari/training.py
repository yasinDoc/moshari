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
from sklearn.metrics import roc_auc_score

from . import config as C
from .data import file_fingerprint, load_dataset
from .evaluation import (
    alert_onset_metrics,
    alert_policy_metrics,
    climatology,
    interval_coverage,
    regression_metrics,
    seasonal_naive,
    tier_confusion,
    tier_metrics,
)
from .features import FEATURE_COLS, FEATURE_SPECS, LEAD_COLS, build_features, lag_correlations, target_col
from .model import FORECAST_KIND, KINDS, PROB_KINDS, ForecastBundle, conformal_offset, fit_booster, interval
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


def _best_f1_threshold(y: np.ndarray, p: np.ndarray) -> float:
    """Probability cut-off that maximises F1 on the validation year."""
    def f1(t):
        f = p >= t
        tp = int((f & y).sum())
        return 2 * tp / max(int(f.sum() + y.sum()), 1)
    return float(max(np.linspace(0.05, 0.9, 86), key=f1))


def _with_forecast_noise(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Observed future weather plus noise, standing in for an imperfect weather forecast.

    Rain gets multiplicative log-normal error (sigma 0.5, roughly ±65%), temperature
    ±1 °C, humidity ±5 points. Training on this keeps the model from over-trusting
    forecast rain.
    """
    rng = np.random.default_rng(seed)
    out = df.copy()
    for c in ("rain_lead_1w", "rain_lead_2w"):
        out[c] = out[c] * np.exp(rng.normal(0, 0.5, len(out)))
    out["temp_lead_1w"] = out["temp_lead_1w"] + rng.normal(0, 1.0, len(out))
    out["humid_lead_1w"] = (out["humid_lead_1w"] + rng.normal(0, 5.0, len(out))).clip(0, 100)
    return out


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
    prob_thresholds: dict[int, dict[str, float]] = {}

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
            "alert_policies": alert_policy_metrics(y_te, pred, hi, thresholds),
            "alert_on_time": alert_onset_metrics(
                pd.DataFrame({"ward_id": te[C.WARD_COL].to_numpy(),
                              "target_date": (te[C.DATE_COL] + pd.Timedelta(weeks=h)).to_numpy(),
                              "actual": y_te, "expected": pred, "upper_80": hi}),
                thresholds,
            ),
        }
        best_base = min(v["mae"] for v in hm["baselines"].values())
        hm["mae_improvement_vs_best_baseline"] = float(1 - hm["model"]["mae"] / best_base)
        # ---- outbreak probabilities: P(High), P(Critical) -------------------
        prob_thresholds[h] = {}
        probs_te: dict[str, np.ndarray] = {}
        hm["probability"] = {}
        for kind, tier in PROB_KINDS.items():
            cut = thresholds[C.TIER_NAMES.index(tier) - 1]
            y_tr, y_va = (tr[tcol] >= cut).astype(int), (va[tcol] >= cut).astype(int)
            a = fit_booster(kind, tr[FEATURE_COLS], y_tr, va[FEATURE_COLS], y_va)
            prob_thresholds[h][kind] = _best_f1_threshold(y_va.to_numpy().astype(bool), a.predict(va[FEATURE_COLS]))
            y_fit = (final_fit[tcol] >= cut).astype(int)
            boosters[(h, kind)] = fit_booster(kind, final_fit[FEATURE_COLS], y_fit,
                                              num_rounds=max(int(a.best_iteration * 1.1), 50))
            pt = boosters[(h, kind)].predict(X_te)
            probs_te[kind] = pt
            actual = y_te >= cut
            flag, flag_exp = pt >= prob_thresholds[h][kind], pred >= cut
            tp, tp_exp = int((flag & actual).sum()), int((flag_exp & actual).sum())
            hm["probability"][tier] = {
                "threshold": prob_thresholds[h][kind],
                "auc": float(roc_auc_score(actual, pt)),
                "brier": float(np.mean((pt - actual) ** 2)),
                "recall": tp / max(int(actual.sum()), 1),
                "precision": tp / max(int(flag.sum()), 1),
                "recall_expected_rule": tp_exp / max(int(actual.sum()), 1),
                "precision_expected_rule": tp_exp / max(int(flag_exp.sum()), 1),
                "n_actual": int(actual.sum()),
            }
        probs_te["p_crit"] = np.minimum(probs_te["p_crit"], probs_te["p_high"])

        # ---- forecast-assisted model (uses next 1–2 weeks of weather) --------
        lead_ok = lambda d: d.dropna(subset=LEAD_COLS)  # noqa: E731
        cols_fc = [*FEATURE_COLS, *LEAD_COLS]
        tr_f, va_f = _with_forecast_noise(lead_ok(tr), 1), _with_forecast_noise(lead_ok(va), 2)
        a = fit_booster(FORECAST_KIND, tr_f[cols_fc], tr_f[tcol], va_f[cols_fc], va_f[tcol])
        fit_f = _with_forecast_noise(lead_ok(final_fit), 3)
        boosters[(h, FORECAST_KIND)] = fit_booster(FORECAST_KIND, fit_f[cols_fc], fit_f[tcol],
                                                    num_rounds=max(int(a.best_iteration * 1.1), 50))
        te_f = lead_ok(te)
        y_f = te_f[tcol].to_numpy()
        base_f = np.clip(bundle_h["mean"].predict(te_f[FEATURE_COLS]), 0, None)
        clim_f = climatology(train_raw, te_f, h).fillna(0).to_numpy()
        perfect = boosters[(h, FORECAST_KIND)].predict(te_f[cols_fc])
        realistic = boosters[(h, FORECAST_KIND)].predict(_with_forecast_noise(te_f, 4)[cols_fc])
        hm["forecast_assisted"] = {
            "mae_without_forecast": regression_metrics(y_f, base_f)["mae"],
            "mae_realistic_forecast": regression_metrics(y_f, realistic)["mae"],
            "mae_perfect_forecast": regression_metrics(y_f, perfect)["mae"],
            "mae_seasonal_average": regression_metrics(y_f, clim_f)["mae"],
            "n_test": int(len(te_f)),
        }
        metrics["horizons"][str(h)] = hm
        pc = hm["probability"]["Critical"]
        fa = hm["forecast_assisted"]
        log(f"  Critical caught: {pc['recall_expected_rule']:.0%} by expected cases -> {pc['recall']:.0%} by probability "
            f"(AUC {pc['auc']:.3f}) · with rain forecast MAE {fa['mae_without_forecast']:.2f} -> "
            f"{fa['mae_realistic_forecast']:.2f} (perfect {fa['mae_perfect_forecast']:.2f})")
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
                    "p_high": probs_te["p_high"],
                    "p_crit": probs_te["p_crit"],
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
    bundle = ForecastBundle(boosters, city_categories, thresholds, metadata, interval_offsets=offsets,
                            prob_thresholds=prob_thresholds)
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
