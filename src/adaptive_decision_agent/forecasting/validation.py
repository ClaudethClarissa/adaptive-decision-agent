"""Historical rolling-origin comparison with fixed seven-day forecast blocks."""

from dataclasses import dataclass
from math import lgamma, log

import numpy as np
import pandas as pd

from .models import MODELS, validate_history

ORIGINS = (-20, -13, -6)


def _vectors(actual, predicted):
    y, f = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if y.ndim != 1 or f.shape != y.shape or not len(y):
        raise ValueError("Metrics require equal nonempty one-dimensional vectors")
    if not np.isfinite(y).all() or not np.isfinite(f).all() or (y < 0).any() or (f < 0).any():
        raise ValueError("Actual and predicted values must be finite and nonnegative")
    return y, f


def point_metrics(actual, predicted) -> dict[str, float | int]:
    """Micro-averaged errors, bias = predicted minus actual; all in units."""
    y, f = _vectors(actual, predicted)
    error = f - y
    return {"n": len(y), "mae": float(np.abs(error).mean()),
            "rmse": float(np.sqrt(np.mean(error ** 2))), "bias": float(error.mean())}


def poisson_metrics(actual, predicted) -> dict[str, float]:
    """Separate plug-in Poisson candidate scores; smaller is better.

    This assumes integer counts and a Poisson predictive mean, not just a point
    forecast. Zero predicted mean with a positive observation has infinite loss.
    No smoothing or confidence interval is silently introduced.
    """
    y, f = _vectors(actual, predicted)
    if not (y % 1 == 0).all():
        raise ValueError("Poisson scores require integer observed counts")
    deviances, losses = [], []
    for value, mean in zip(y, f):
        if mean == 0:
            deviance = loss = 0. if value == 0 else float("inf")
        else:
            deviance = 2 * (mean - value + (value * log(value / mean) if value else 0))
            loss = mean - value * log(mean) + lgamma(value + 1)
        deviances.append(max(0., deviance))
        losses.append(loss)
    return {"mean_poisson_deviance": float(np.mean(deviances)),
            "mean_poisson_nll": float(np.mean(losses))}


def rolling_splits(history: pd.DataFrame):
    """Exactly the three specified historical-only train/validation folds."""
    history = validate_history(history)
    if set(history.day) != set(range(-59, 1)):
        raise ValueError("Development input must cover only days -59 through 0")
    return [(history[history.day < origin].copy(),
             history[history.day.between(origin, origin + 6)].copy()) for origin in ORIGINS]


def _summarize(frame, keys, evaluate_poisson=False):
    rows = []
    for values, group in frame.groupby(keys, sort=True):
        if not isinstance(values, tuple):
            values = (values,)
        row = dict(zip(keys, values))
        row.update(poisson_metrics(group.actual, group.predicted) if evaluate_poisson
                   else point_metrics(group.actual, group.predicted))
        rows.append(row)
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class ValidationResult:
    daily_predictions: pd.DataFrame
    weekly_predictions: pd.DataFrame
    by_window: pd.DataFrame
    overall: pd.DataFrame
    by_product: pd.DataFrame
    poisson_by_window: pd.DataFrame
    poisson_overall: pd.DataFrame


def rolling_validate(history: pd.DataFrame, *, evaluate_poisson: bool = False) -> ValidationResult:
    """Forecast seven days at each origin without updating inside the holdout."""
    daily, weekly = [], []
    for window, (train, valid) in enumerate(rolling_splits(history), start=1):
        origin = int(valid.day.min())
        for name, model in MODELS.items():
            forecast = model.predict(train, decision_day=origin, horizon=7)
            joined = valid.rename(columns={"demand": "actual"}).merge(
                forecast.daily.rename(columns={"expected_demand": "predicted"}),
                on=["day", "product_id"], validate="one_to_one")
            joined["model"], joined["window"], joined["scale"] = name, window, "daily"
            daily.append(joined)
            totals = joined.groupby("product_id", as_index=False)[["actual", "predicted"]].sum()
            totals["model"], totals["window"], totals["scale"] = name, window, "7_day_total"
            weekly.append(totals)
    daily, weekly = pd.concat(daily, ignore_index=True), pd.concat(weekly, ignore_index=True)
    combined = pd.concat([daily, weekly], ignore_index=True)
    return ValidationResult(
        daily, weekly, _summarize(combined, ["model", "window", "scale"]),
        _summarize(combined, ["model", "scale"]),
        _summarize(combined, ["model", "product_id", "scale"]),
        _summarize(combined, ["model", "window", "scale"], True) if evaluate_poisson else pd.DataFrame(),
        _summarize(combined, ["model", "scale"], True) if evaluate_poisson else pd.DataFrame(),
    )
