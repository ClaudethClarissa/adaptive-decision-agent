"""Hand-calculated estimates, temporal boundaries, and independent scores."""

import math

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from adaptive_decision_agent.forecasting import MeanForecaster, point_metrics, rolling_splits, rolling_validate
from adaptive_decision_agent.forecasting.analysis import describe_history
from adaptive_decision_agent.forecasting.validation import poisson_metrics


def panel(days=60):
    return pd.DataFrame({"day": np.repeat(np.arange(1 - days, 1), 2),
                         "product_id": np.tile(["A", "B"], days),
                         "demand": np.column_stack([np.arange(1, days + 1), np.zeros(days, dtype=int)]).ravel()})


@pytest.mark.parametrize("window,expected", [(None, 30.5), (14, 53.5), (30, 45.5)])
@pytest.mark.parametrize("horizon", [1, 7, 12])
def test_exact_forecasts_and_aggregation(window, expected, horizon):
    h = panel()
    result = MeanForecaster(window).predict(h, decision_day=1, horizon=horizon)
    assert len(result.daily) == 2 * horizon
    assert result.daily.query("product_id == 'A'").expected_demand.eq(expected).all()
    assert result.daily.query("product_id == 'B'").expected_demand.eq(0).all()
    assert result.cumulative.query("product_id == 'A'").expected_cumulative_demand.item() == horizon * expected
    actual = result.daily.groupby("product_id").expected_demand.sum()
    np.testing.assert_allclose(actual, result.cumulative.expected_cumulative_demand)
    assert np.isfinite(result.daily.expected_demand).all()
    assert (result.daily.expected_demand >= 0).all()


def test_splits_exact_and_nonoverlapping():
    folds = rolling_splits(panel())
    assert [(t.day.min(), t.day.max(), v.day.min(), v.day.max(), t.day.nunique()) for t, v in folds] == [
        (-59, -21, -20, -14, 39), (-59, -14, -13, -7, 46), (-59, -7, -6, 0, 53)]
    all_days = []
    for train, valid in folds:
        assert train.day.max() < valid.day.min()
        all_days.extend(valid.day.unique())
    assert len(all_days) == len(set(all_days)) == 21


def test_current_and_future_rows_rejected():
    h = panel()
    for decision_day in (0, -10):
        with pytest.raises(ValueError, match="current and future"):
            MeanForecaster().predict(h, decision_day=decision_day)
    with pytest.raises(ValueError, match="before"):
        MeanForecaster().predict(h, decision_day=2)
    future = h.copy()
    future["day"] += 30
    with pytest.raises(ValueError, match="only days"):
        rolling_splits(future)


def test_rolling_forecasts_do_not_use_holdout_values():
    original = panel()
    changed = original.copy()
    changed.loc[changed.day >= -20, "demand"] += 1000
    first = rolling_validate(original)
    second = rolling_validate(changed)
    cols = ["day", "product_id", "predicted", "model", "window"]
    assert_frame_equal(first.daily_predictions.query("window == 1")[cols],
                       second.daily_predictions.query("window == 1")[cols])
    assert not first.daily_predictions.query("window == 2").predicted.equals(
        second.daily_predictions.query("window == 2").predicted)
    # Later folds may use earlier validation observations once they are in the past.
    assert_frame_equal(original, panel())


def test_hand_calculated_metrics_and_probabilistic_scores():
    assert point_metrics([0, 2, 4], [1, 1, 5]) == {"n": 3, "mae": 1., "rmse": 1., "bias": 1 / 3}
    perfect = poisson_metrics([0, 2], [0, 2])
    assert perfect["mean_poisson_deviance"] == 0
    assert perfect["mean_poisson_nll"] == pytest.approx((2 - 2 * math.log(2) + math.lgamma(3)) / 2)
    assert math.isinf(poisson_metrics([1], [0])["mean_poisson_nll"])
    assert poisson_metrics([0], [2])["mean_poisson_deviance"] == 4
    with pytest.raises(ValueError):
        poisson_metrics([1.5], [1])


def test_summary_metrics_are_pooled_errors_not_averaged_rmse():
    r = rolling_validate(panel(), evaluate_poisson=True)
    for _, row in r.overall.iterrows():
        source = r.daily_predictions if row.scale == "daily" else r.weekly_predictions
        source = source[source.model == row.model]
        expected = point_metrics(source.actual, source.predicted)
        for name, value in expected.items():
            assert row[name] == pytest.approx(value)
    assert len(r.by_window) == 18
    assert len(r.by_product) == 12
    assert len(r.poisson_overall) == 6


def test_deterministic_and_order_independent():
    h = panel()
    first = rolling_validate(h, evaluate_poisson=True)
    second = rolling_validate(h.sample(frac=1, random_state=9), evaluate_poisson=True)
    for field in first.__dataclass_fields__:
        assert_frame_equal(getattr(first, field), getattr(second, field))
    forecast = MeanForecaster().predict(h, decision_day=1)
    assert set(forecast.daily.columns) == {"day", "product_id", "expected_demand"}


@pytest.mark.parametrize("window,days", [(None, 0), (14, 13), (30, 29)])
def test_empty_and_insufficient_history(window, days):
    with pytest.raises(ValueError):
        MeanForecaster(window).predict(panel(days), decision_day=1)


@pytest.mark.parametrize("problem", ["negative", "fractional", "infinite", "missing", "duplicate", "bool", "privileged"])
def test_bad_history(problem):
    h = panel()
    if problem == "missing":
        h = h.iloc[:-1]
    elif problem == "duplicate":
        h = pd.concat([h, h.iloc[:1]])
    elif problem == "privileged":
        h["daily_demand_rate"] = 10
    elif problem == "bool":
        h["demand"] = True
    else:
        h["demand"] = h.demand.astype(float)
        h.loc[0, "demand"] = {"negative": -1, "fractional": .5, "infinite": np.inf}[problem]
    with pytest.raises(ValueError):
        MeanForecaster().predict(h, decision_day=1)


@pytest.mark.parametrize("horizon", [0, -1, 1.5, True])
def test_bad_horizon(horizon):
    with pytest.raises(ValueError):
        MeanForecaster().predict(panel(), decision_day=1, horizon=horizon)


def test_eda_and_zero_demand_handling():
    h = panel(4)
    stats = describe_history(h).set_index("product_id")
    assert stats.loc["A", "mean"] == 2.5
    assert stats.loc["A", "variance"] == pytest.approx(5 / 3)
    assert stats.loc["B", "zero_frequency"] == 1
    assert pd.isna(stats.loc["B", "variance_to_mean"])
    assert pd.isna(stats.loc["B", "lag1_autocorrelation"])
