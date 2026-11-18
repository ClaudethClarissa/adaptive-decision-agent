"""Point forecasts using observed history only; no distribution is implied."""

from dataclasses import dataclass
from numbers import Integral

import numpy as np
import pandas as pd


def validate_history(history: pd.DataFrame) -> pd.DataFrame:
    """Return a sorted, complete daily product panel, rejecting ambiguous data."""
    if not history.columns.is_unique or set(history.columns) != {"day", "product_id", "demand"}:
        raise ValueError("History must contain only day, product_id, demand")
    if history.empty or history.isna().any().any():
        raise ValueError("History must be nonempty without missing values")
    for name in ("day", "demand"):
        x = history[name]
        if not pd.api.types.is_numeric_dtype(x) or pd.api.types.is_bool_dtype(x):
            raise ValueError(f"{name} must contain finite integers")
        if not (np.isfinite(x) & (x % 1 == 0)).all():
            raise ValueError(f"{name} must contain finite integers")
    if (history.demand < 0).any():
        raise ValueError("Demand must be nonnegative")
    if not history.product_id.map(lambda x: isinstance(x, str) and bool(x)).all():
        raise ValueError("Product IDs must be nonempty strings")
    if history.duplicated(["day", "product_id"]).any():
        raise ValueError("Duplicate day/product observations")
    first, last = int(history.day.min()), int(history.day.max())
    products = sorted(history.product_id.unique())
    expected = pd.MultiIndex.from_product([range(first, last + 1), products], names=["day", "product_id"])
    actual = pd.MultiIndex.from_frame(history[["day", "product_id"]])
    if not actual.sort_values().equals(expected):
        raise ValueError("History must cover consecutive days for every product")
    return history.sort_values(["day", "product_id"]).reset_index(drop=True).copy()


def _positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


@dataclass(frozen=True)
class ForecastResult:
    """Expected daily units and horizon totals; no intervals or count distribution."""

    daily: pd.DataFrame
    cumulative: pd.DataFrame


@dataclass(frozen=True)
class MeanForecaster:
    """Use all observed days, or exactly the most recent window_days."""

    window_days: int | None = None

    def __post_init__(self):
        if self.window_days is not None:
            _positive_integer(self.window_days, "window_days")

    def predict(self, history: pd.DataFrame, *, decision_day: int, horizon: int = 7) -> ForecastResult:
        horizon = _positive_integer(horizon, "horizon")
        if isinstance(decision_day, bool) or not isinstance(decision_day, Integral):
            raise ValueError("decision_day must be an integer")
        history = validate_history(history)
        if history.day.max() >= decision_day:
            raise ValueError("History must exclude current and future realized demand")
        if history.day.max() != decision_day - 1:
            raise ValueError("History must end the day before the decision")
        available_days = history.day.nunique()
        if self.window_days is not None:
            if available_days < self.window_days:
                raise ValueError(f"At least {self.window_days} historical days are required")
            history = history[history.day >= decision_day - self.window_days]
        means = history.groupby("product_id", sort=True).demand.mean()
        daily = pd.DataFrame({
            "day": np.repeat(np.arange(decision_day, decision_day + horizon), len(means)),
            "product_id": np.tile(means.index.to_numpy(), horizon),
            "expected_demand": np.tile(means.to_numpy(dtype=float), horizon),
        })
        cumulative = pd.DataFrame({"product_id": means.index.to_numpy(), "horizon": horizon,
                                   "expected_cumulative_demand": means.to_numpy() * horizon})
        return ForecastResult(daily, cumulative)


MODELS = {
    "expanding_mean": MeanForecaster(),
    "moving_average_14": MeanForecaster(14),
    "moving_average_30": MeanForecaster(30),
}
