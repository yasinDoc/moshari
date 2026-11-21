"""Model bundle: training, serialisation, inference and explanations.

One LightGBM model per horizon (2, 3, 4 weeks) predicts expected cases with a
Poisson objective, plus two quantile models per horizon (10th / 90th
percentile) that form an 80% forecast interval.

The bundle is stored with joblib. Boosters are stored as LightGBM's native
text format inside the bundle, so a model trained with one LightGBM version
still loads with another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from . import config as C
from .features import CATEGORICAL_FEATURES, FEATURE_COLS, FEATURE_SPECS, DRIVER_GROUPS
from .risk import assign_tier

BASE_PARAMS: dict[str, Any] = {
    "learning_rate": 0.04,
    "num_leaves": 31,
    "min_data_in_leaf": 40,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": C.RANDOM_SEED,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 0,  # all cores
    "verbosity": -1,
}

KINDS = ("mean", "q10", "q90")


def _params(kind: str) -> dict[str, Any]:
    p = dict(BASE_PARAMS)
    if kind == "mean":
        p.update(objective="poisson", metric="poisson")
    else:
        alpha = C.QUANTILES[0] if kind == "q10" else C.QUANTILES[1]
        p.update(objective="quantile", alpha=alpha, metric="quantile")
    return p


def fit_booster(
    kind: str,
    X_tr: pd.DataFrame,
    y_tr: pd.Series,
    X_va: pd.DataFrame | None = None,
    y_va: pd.Series | None = None,
    num_rounds: int | None = None,
) -> lgb.Booster:
    """Fit one booster. With a validation set: early stopping. Without: fixed rounds."""
    dtr = lgb.Dataset(X_tr, y_tr, categorical_feature=CATEGORICAL_FEATURES, free_raw_data=False)
    if X_va is not None:
        dva = lgb.Dataset(X_va, y_va, reference=dtr, categorical_feature=CATEGORICAL_FEATURES)
        return lgb.train(
            _params(kind),
            dtr,
            num_boost_round=3000,
            valid_sets=[dva],
            callbacks=[lgb.early_stopping(150, verbose=False)],
        )
    return lgb.train(_params(kind), dtr, num_boost_round=int(num_rounds or 500))


def interval(q_lo, q_hi, mean, offset: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """80% interval from the two quantile models, widened by the conformal offset.

    Quantile models are fit independently, so we also enforce lo <= mean <= hi.
    """
    lo = np.clip(np.asarray(q_lo) - offset, 0, None)
    hi = np.clip(np.asarray(q_hi) + offset, 0, None)
    return np.minimum(lo, mean), np.maximum(hi, mean)


def conformal_offset(y, q_lo, q_hi, coverage: float = 0.80) -> float:
    """Conformalized quantile regression (Romano et al., 2019).

    Score each calibration point by how far it falls outside [q_lo, q_hi]; the
    finite-sample-corrected ``coverage`` quantile of those scores is how much the
    interval must be widened (or may be narrowed, if negative) to hit the target.
    """
    y = np.asarray(y, dtype=float)
    scores = np.maximum(np.asarray(q_lo) - y, y - np.asarray(q_hi))
    n = len(scores)
    level = min(np.ceil((n + 1) * coverage) / n, 1.0)
    return float(np.quantile(scores, level, method="higher"))


@dataclass
class ForecastBundle:
    boosters: dict[tuple[int, str], lgb.Booster]
    city_categories: list[str]
    tier_thresholds: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    feature_cols: list[str] = field(default_factory=lambda: list(FEATURE_COLS))
    # Conformal (CQR) widening per horizon, calibrated on the validation year.
    interval_offsets: dict[int, float] = field(default_factory=dict)

    # ------------------------------------------------------------------ io
    def save(self, path: Path = C.MODEL_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": "moshari-bundle/1",
            "boosters": {f"{h}|{k}": b.model_to_string() for (h, k), b in self.boosters.items()},
            "city_categories": self.city_categories,
            "tier_thresholds": self.tier_thresholds,
            "metadata": self.metadata,
            "feature_cols": self.feature_cols,
            "interval_offsets": {str(h): v for h, v in self.interval_offsets.items()},
        }
        joblib.dump(payload, path, compress=3)
        return path

    @classmethod
    def load(cls, path: Path = C.MODEL_PATH) -> "ForecastBundle":
        if not Path(path).exists():
            raise FileNotFoundError(
                f"No trained model at {path}. Run `python scripts/train.py` first."
            )
        payload = joblib.load(path)
        boosters = {}
        for key, text in payload["boosters"].items():
            h, kind = key.split("|")
            boosters[(int(h), kind)] = lgb.Booster(model_str=text)
        return cls(
            boosters=boosters,
            city_categories=payload["city_categories"],
            tier_thresholds=payload["tier_thresholds"],
            metadata=payload["metadata"],
            feature_cols=payload["feature_cols"],
            interval_offsets={int(h): float(v) for h, v in payload.get("interval_offsets", {}).items()},
        )

    # ----------------------------------------------------------- inference
    @property
    def horizons(self) -> list[int]:
        return sorted({h for h, _ in self.boosters})

    def _X(self, features: pd.DataFrame) -> pd.DataFrame:
        return features[self.feature_cols]

    def predict(self, features: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Expected cases, 80% interval and risk tier for each feature row."""
        X = self._X(features)
        mean = np.clip(self.boosters[(horizon, "mean")].predict(X), 0, None)
        lo, hi = interval(
            self.boosters[(horizon, "q10")].predict(X),
            self.boosters[(horizon, "q90")].predict(X),
            mean,
            self.interval_offsets.get(horizon, 0.0),
        )
        tier_idx = assign_tier(mean, self.tier_thresholds)
        upside_idx = assign_tier(hi, self.tier_thresholds)
        return pd.DataFrame(
            {
                "expected_cases": mean,
                "lower_80": lo,
                "upper_80": hi,
                "tier_idx": tier_idx,
                "tier": [C.TIER_NAMES[i] for i in tier_idx],
                "upside_tier": [C.TIER_NAMES[i] for i in upside_idx],
            },
            index=features.index,
        )

    def explain(self, features: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Per-feature contributions (TreeSHAP, computed natively by LightGBM).

        The Poisson model works in log space, so contributions are additive in
        log(expected cases). ``exp(contribution)`` is a multiplicative effect:
        1.8 means "this driver multiplies expected cases by 1.8x versus a
        typical ward-week".
        """
        X = self._X(features)
        contrib = self.boosters[(horizon, "mean")].predict(X, pred_contrib=True)
        cols = [*self.feature_cols, "__baseline__"]
        return pd.DataFrame(contrib, columns=cols, index=features.index)

    def explain_grouped(self, features_row: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, pd.DataFrame, float]:
        """Contributions for one row, by driver group and by feature.

        Returns (groups, features, baseline_cases).
        """
        contrib = self.explain(features_row.iloc[[0]], horizon).iloc[0]
        baseline = float(np.exp(contrib.pop("__baseline__")))
        feat = pd.DataFrame(
            {
                "feature": contrib.index,
                "log_effect": contrib.to_numpy(),
                "group": [FEATURE_SPECS[f][0] for f in contrib.index],
                "label": [FEATURE_SPECS[f][1] for f in contrib.index],
                "value": features_row.iloc[0][contrib.index].to_numpy(),
            }
        )
        feat["multiplier"] = np.exp(feat["log_effect"])
        groups = (
            feat.groupby("group", sort=False)["log_effect"].sum().reindex(DRIVER_GROUPS).fillna(0.0)
        ).to_frame("log_effect")
        groups["multiplier"] = np.exp(groups["log_effect"])
        groups = groups.reset_index().rename(columns={"index": "group"})
        return groups, feat.sort_values("log_effect", key=np.abs, ascending=False), baseline
