"""Metrics and baselines for chronological validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, mean_absolute_error, mean_squared_error

from . import config as C
from .risk import assign_tier


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
    }


def tier_metrics(y_true, y_pred, thresholds: list[float]) -> dict[str, float]:
    """How well forecast tiers match the tiers the actual case counts fell into."""
    t_true = assign_tier(y_true, thresholds)
    t_pred = assign_tier(y_pred, thresholds)
    alert_true = t_true >= 2  # High or Critical
    alert_pred = t_pred >= 2
    tp = int((alert_true & alert_pred).sum())
    return {
        "tier_accuracy": float((t_true == t_pred).mean()),
        "tier_within_one": float((np.abs(t_true - t_pred) <= 1).mean()),
        "tier_macro_f1": float(f1_score(t_true, t_pred, average="macro", labels=[0, 1, 2, 3], zero_division=0)),
        "alert_recall": float(tp / max(int(alert_true.sum()), 1)),
        "alert_precision": float(tp / max(int(alert_pred.sum()), 1)),
    }


def alert_policy_metrics(y_true, expected, upper, thresholds: list[float]) -> dict[str, dict[str, float]]:
    """Recall / precision of "High or above" alerts under each alert policy."""
    from .risk import ALERT_POLICIES, alert_score

    actual = np.asarray(y_true, dtype=float) >= thresholds[1]
    out = {}
    for name in ALERT_POLICIES:
        flagged = alert_score(expected, upper, name) >= thresholds[1]
        tp = int((flagged & actual).sum())
        out[name] = {
            "recall": float(tp / max(int(actual.sum()), 1)),
            "precision": float(tp / max(int(flagged.sum()), 1)),
            "flag_rate": float(flagged.mean()),
            "missed": int((actual & ~flagged).sum()),
            "false_alarms": int((flagged & ~actual).sum()),
        }
    return out


def alert_onset_metrics(df: pd.DataFrame, thresholds: list[float]) -> dict[str, float]:
    """Share of ward-seasons where an alert was out by the first week cases actually reached High.

    ``df`` needs ward_id, target_date, actual, expected, upper_80 for one horizon.
    """
    from .risk import ALERT_POLICIES, alert_score

    d = df.assign(year=pd.to_datetime(df["target_date"]).dt.year)
    out = {}
    for name in ALERT_POLICIES:
        d["score"] = alert_score(d["expected"], d["upper_80"], name)
        on_time, n = 0, 0
        for _, g in d.groupby(["ward_id", "year"]):
            first_high = g.loc[g["actual"] >= thresholds[1], "target_date"].min()
            if pd.isna(first_high):
                continue
            n += 1
            first_alert = g.loc[g["score"] >= thresholds[1], "target_date"].min()
            on_time += int(pd.notna(first_alert) and first_alert <= first_high)
        out[name] = float(on_time / max(n, 1))
    return out


def interval_coverage(y_true, lo, hi) -> float:
    y = np.asarray(y_true, dtype=float)
    return float(((y >= np.asarray(lo)) & (y <= np.asarray(hi))).mean())


def tier_confusion(y_true, y_pred, thresholds: list[float]) -> pd.DataFrame:
    t_true = assign_tier(y_true, thresholds)
    t_pred = assign_tier(y_pred, thresholds)
    m = pd.crosstab(
        pd.Categorical([C.TIER_NAMES[i] for i in t_true], categories=C.TIER_NAMES),
        pd.Categorical([C.TIER_NAMES[i] for i in t_pred], categories=C.TIER_NAMES),
        dropna=False,
    )
    m.index.name, m.columns.name = "Actual", "Forecast"
    return m


def seasonal_naive(raw: pd.DataFrame, feats: pd.DataFrame, horizon: int) -> pd.Series:
    """Baseline: cases in the same ward, same week one year (52 weeks) before the target week."""
    lookup = raw.set_index([C.WARD_COL, C.DATE_COL])[C.TARGET_COL]
    keys = pd.MultiIndex.from_arrays(
        [feats[C.WARD_COL], feats[C.DATE_COL] + pd.Timedelta(weeks=horizon - 52)]
    )
    return pd.Series(lookup.reindex(keys).to_numpy(), index=feats.index)


def climatology(train_raw: pd.DataFrame, feats: pd.DataFrame, horizon: int) -> pd.Series:
    """Baseline: average cases for this ward and week-of-year over the training years."""
    tr = train_raw.assign(woy=train_raw[C.DATE_COL].dt.isocalendar().week.astype(int))
    clim = tr.groupby([C.WARD_COL, "woy"])[C.TARGET_COL].mean()
    woy = (feats[C.DATE_COL] + pd.Timedelta(weeks=horizon)).dt.isocalendar().week.astype(int)
    keys = pd.MultiIndex.from_arrays([feats[C.WARD_COL], woy])
    return pd.Series(clim.reindex(keys).to_numpy(), index=feats.index)
