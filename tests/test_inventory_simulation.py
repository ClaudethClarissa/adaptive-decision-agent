"""Inventory accounting, timing, validation, and budget contract tests."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from adaptive_decision_agent.data.synthetic import generate_data
from adaptive_decision_agent.simulation import simulate


def example(horizon=10, stock=3, cost=10., lead=2):
    catalog = pd.DataFrame([{"product_id": "P", "initial_stock": stock, "unit_cost": cost,
                             "lead_time_days": lead, "holding_cost_per_unit_day": .1}])
    demand = pd.DataFrame({"day": range(1, horizon + 1), "product_id": "P", "demand": 2})
    return catalog, demand


def test_hand_calculated_transitions_and_lost_sales():
    c, d = example(horizon=5)
    result = simulate(c, d, {1: {"P": 4}}, horizon=5)
    r = result.daily
    assert r.opening_stock.tolist() == [3, 1, 0, 2, 0]
    assert r.arriving_units.tolist() == [0, 0, 4, 0, 0]
    assert r.sales.tolist() == [2, 1, 2, 2, 0]
    assert r.unmet_demand.tolist() == [0, 1, 0, 0, 2]
    assert r.closing_stock.tolist() == [1, 0, 2, 0, 0]
    assert r.outstanding_orders.tolist() == [4, 4, 0, 0, 0]
    assert r.purchasing_expenditure.tolist() == [40., 0., 0., 0., 0.]
    assert r.holding_cost.tolist() == [.1, 0., .2, 0., 0.]
    assert result.periods.expired_unused_budget.tolist() == [19960.]


def test_full_dimensions_balances_and_reproducibility():
    c, _, d = generate_data()
    schedule = {1: {p: 2 for p in c.product_id}, 8: {"P001": 3}, 29: {"P002": 4}}
    first = simulate(c, d, schedule)
    second = simulate(c.copy(), d.sample(frac=1, random_state=5), schedule)
    for a, b in [(first.daily, second.daily), (first.orders, second.orders), (first.periods, second.periods)]:
        assert_frame_equal(a, b)
    r = first.daily
    assert r.shape == (1500, 12)
    assert not r.duplicated(["day", "product_id"]).any()
    assert (r.opening_stock + r.arriving_units == r.sales + r.closing_stock).all()
    assert (r.sales + r.unmet_demand == r.demand).all()
    assert (r[["opening_stock", "closing_stock", "outstanding_orders", "sales", "unmet_demand"]] >= 0).all().all()
    for p, group in r.groupby("product_id"):
        assert group.opening_stock.iloc[0] == c.set_index("product_id").loc[p, "initial_stock"]
        np.testing.assert_array_equal(group.opening_stock.iloc[1:], group.closing_stock.iloc[:-1])
        np.testing.assert_array_equal(group.outstanding_orders, (group.ordered_units - group.arriving_units).cumsum())
    assert first.periods.decision_day.tolist() == [1, 8, 15, 22, 29]


def test_late_pipeline_and_repeated_orders():
    c, d = example(horizon=30, stock=0, lead=5)
    r = simulate(c, d, {1: {"P": 4}, 8: {"P": 3}, 29: {"P": 9}})
    assert r.orders.arrival_day.tolist() == [6, 13, 34]
    assert r.daily.query("arriving_units > 0").day.tolist() == [6, 13]
    assert r.daily.iloc[-1].outstanding_orders == 9
    assert r.daily.purchasing_expenditure.sum() == 160


def test_overlapping_orders_remain_distinct_in_pipeline():
    c, d = example(horizon=30, stock=0, lead=10)
    r = simulate(c, d, {1: {"P": 4}, 8: {"P": 3}})
    assert r.daily.loc[r.daily.day == 8, "outstanding_orders"].item() == 7
    assert r.daily.loc[r.daily.day == 11, "outstanding_orders"].item() == 3
    assert r.daily.loc[r.daily.day == 18, "outstanding_orders"].item() == 0
    assert r.daily.query("arriving_units > 0").day.tolist() == [11, 18]


def test_all_five_decision_days():
    c, d = example(horizon=30)
    r = simulate(c, d, {day: {"P": 1} for day in [1, 8, 15, 22, 29]})
    assert r.orders.order_day.tolist() == [1, 8, 15, 22, 29]
    assert r.orders.arrival_day.tolist() == [3, 10, 17, 24, 31]
    assert r.daily.iloc[-1].outstanding_orders == 1


def test_exact_budget_and_no_rollover():
    c, d = example(cost=.1)
    r = simulate(c, d, {8: {"P": 200000}}, horizon=10)
    assert r.periods.purchasing_expenditure.tolist() == [0., 20000.]
    assert r.periods.expired_unused_budget.tolist() == [20000., 0.]
    with pytest.raises(ValueError, match="budget"):
        simulate(c, d, {8: {"P": 200001}}, horizon=10)
    r = simulate(c, d, {1: {"P": 200000}, 8: {"P": 200000}}, horizon=10)
    assert r.periods.purchasing_expenditure.sum() == 40000


def test_budget_aggregates_products():
    c, _, d = generate_data()
    with pytest.raises(ValueError, match="budget"):
        simulate(c, d, {1: {p: 500 for p in c.product_id}})


@pytest.mark.parametrize("schedule", [
    {1: {"P": -1}}, {1: {"P": 1.5}}, {1: {"P": True}}, {1: {"P": np.nan}},
    {1: {"P": np.inf}}, {1: {"P": "2"}}, {1: {"unknown": 1}},
    {2: {"P": 1}}, {0: {}}, {29: {}}, {True: {}}, {1: []}, [],
])
def test_invalid_orders_rejected(schedule):
    c, d = example()
    with pytest.raises(ValueError):
        simulate(c, d, schedule, horizon=10)


def test_empty_schedule_and_inputs_unchanged():
    c, d = example()
    before_c, before_d = c.copy(deep=True), d.copy(deep=True)
    schedule = {1: {"P": 0}}
    r = simulate(c, d, schedule, horizon=10)
    assert r.orders.empty
    assert r.daily.purchasing_expenditure.sum() == 0
    assert_frame_equal(c, before_c)
    assert_frame_equal(d, before_d)
    assert schedule == {1: {"P": 0}}


@pytest.mark.parametrize("problem", ["missing", "duplicate", "negative", "fractional", "unknown", "extra_day"])
def test_bad_demand(problem):
    c, d = example()
    if problem == "missing":
        d = d.iloc[:-1]
    elif problem == "duplicate":
        d = pd.concat([d, d.iloc[:1]])
    elif problem == "negative":
        d.loc[0, "demand"] = -1
    elif problem == "fractional":
        d["demand"] = d.demand.astype(float)
        d.loc[0, "demand"] = 1.5
    elif problem == "unknown":
        d.loc[0, "product_id"] = "unknown"
    else:
        d.loc[0, "day"] = 11
    with pytest.raises(ValueError):
        simulate(c, d, horizon=10)


@pytest.mark.parametrize("column,value", [("initial_stock", -1), ("lead_time_days", 0),
    ("unit_cost", -1), ("unit_cost", .001), ("holding_cost_per_unit_day", np.inf)])
def test_bad_catalog(column, value):
    c, d = example()
    c[column] = value
    with pytest.raises(ValueError):
        simulate(c, d, horizon=10)


@pytest.mark.parametrize("divergence_day", [1, 8])
def test_policy_observations_exclude_current_and_future_demand(divergence_day):
    c, d = example(horizon=30, stock=30, lead=10)
    c["supplier_id"] = "S001"
    c["daily_demand_rate"] = 123.456  # Hidden generating parameter.
    c["future_demand_hint"] = "must not reach policy"
    changed = d.copy()
    changed.loc[changed.day >= divergence_day, "demand"] = 100
    snapshots = []

    def run(data):
        seen = {}

        def mock(observation):
            seen[observation.day] = observation
            assert set(observation.demand_history.columns) == {"day", "product_id", "demand"}
            assert (observation.demand_history.day < observation.day).all()
            assert "daily_demand_rate" not in observation.products
            assert "future_demand_hint" not in observation.products
            return {"P": 4} if observation.day == 1 else {}

        simulate(c, data, policy=mock)
        snapshots.append(seen)

    run(d)
    run(changed)
    left, right = snapshots[0][divergence_day], snapshots[1][divergence_day]
    assert left.day == right.day == divergence_day
    assert left.current_inventory == right.current_inventory
    assert left.remaining_budget == right.remaining_budget == 20000
    for name in ("outstanding_orders", "products", "demand_history"):
        assert_frame_equal(getattr(left, name), getattr(right, name))
    assert left.products.supplier_id.tolist() == ["S001"]
    assert left.products.unit_cost.tolist() == [10.]
    assert left.products.lead_time_days.tolist() == [10]
    if divergence_day == 8:
        assert left.demand_history.day.max() == 7
        assert len(left.demand_history) == 7
        assert left.outstanding_orders.arrival_day.tolist() == [11]
        assert left.outstanding_orders.quantity.tolist() == [4]
        assert left.current_inventory == {"P": 16}
    else:
        assert left.demand_history.empty


def test_policy_receives_arrivals_before_ordering():
    c, d = example(horizon=10, stock=0, lead=7)

    def mock(observation):
        if observation.day == 1:
            return {"P": 10}
        assert observation.day == 8
        assert observation.current_inventory == {"P": 10}
        assert observation.outstanding_orders.empty
        return {}

    r = simulate(c, d, policy=mock, horizon=10)
    assert r.daily.loc[r.daily.day == 8, "sales"].item() == 2


def test_mock_policy_and_schedule_have_identical_results():
    c, _, d = generate_data()
    schedule = {day: {p: 10 for p in c.product_id} for day in [1, 8, 15, 22, 29]}
    first = simulate(c, d, schedule)
    second = simulate(c, d, policy=lambda observation: schedule[observation.day])
    repeated = simulate(c, d, policy=lambda observation: schedule[observation.day])
    for name in ("daily", "orders", "periods"):
        assert_frame_equal(getattr(first, name), getattr(second, name))
        assert_frame_equal(getattr(second, name), getattr(repeated, name))
    pending = second.orders.query("arrival_day > 30")
    assert len(pending) == 50
    assert pending.quantity.sum() == 500
    assert pending.order_day.eq(29).all()
    assert set(pending.arrival_day) == {32, 34}
    assert second.daily.query("day == 30").outstanding_orders.sum() == 500
    assert second.daily.purchasing_expenditure.sum() == pytest.approx(second.orders.purchase_cost.sum())
    assert second.daily.query("arriving_units > 0").purchasing_expenditure.sum() == 0


@pytest.mark.parametrize("response", [{"P": -1}, {"P": 1.5}, {"unknown": 1}, {"P": 2001}, None])
def test_policy_orders_use_same_validation(response):
    c, d = example()
    with pytest.raises(ValueError):
        simulate(c, d, horizon=10, policy=lambda observation: response)


def test_policy_cannot_mutate_engine_state_through_observations():
    c, d = example()
    baseline = simulate(c, d, horizon=10)

    def mock(observation):
        observation.current_inventory["P"] = 100000
        observation.products.loc[:, "unit_cost"] = 0
        observation.demand_history.loc[:, "demand"] = 100000
        observation.outstanding_orders["quantity"] = 100000
        return {}

    result = simulate(c, d, horizon=10, policy=mock)
    assert_frame_equal(baseline.daily, result.daily)
    assert c.unit_cost.item() == 10


def test_policy_and_schedule_are_mutually_exclusive():
    c, d = example()
    with pytest.raises(ValueError, match="either"):
        simulate(c, d, {}, horizon=10, policy=lambda observation: {})


@pytest.mark.parametrize("divergence_day", [1, 8])
def test_historical_information_and_nonanticipativity(divergence_day):
    c, h, d = generate_data()
    changed = d.copy()
    changed.loc[changed.day >= divergence_day, "demand"] += 100
    original_history = h.copy(deep=True)
    observations = []

    def run(evaluation, history):
        seen = {}

        def mock(observation):
            seen[observation.day] = observation
            assert len(observation.demand_history) == (60 + observation.day - 1) * 50
            assert observation.demand_history.day.min() == -59
            assert observation.demand_history.day.max() == observation.day - 1
            assert (observation.demand_history.day < observation.day).all()
            assert "daily_demand_rate" not in observation.products
            return {"P001": 1}

        result = simulate(c, evaluation, policy=mock, historical_demand=history)
        observations.append(seen)
        return result

    first = run(d, h)
    repeated = run(d, h.sample(frac=1, random_state=17))
    run(changed, h)
    assert_frame_equal(first.daily, repeated.daily)
    assert_frame_equal(h, original_history)
    for day in {1, divergence_day}:
        left, right = observations[0][day], observations[2][day]
        assert left.current_inventory == right.current_inventory
        assert left.remaining_budget == right.remaining_budget
        for field in ("demand_history", "products", "outstanding_orders"):
            assert_frame_equal(getattr(left, field), getattr(right, field))
    expected_history = h.sort_values(["day", "product_id"]).reset_index(drop=True)
    assert_frame_equal(observations[0][1].demand_history, expected_history)
    assert observations[0][1].products.estimated_demand_rate.tolist() == c.estimated_demand_rate.tolist()


def test_prehistory_does_not_change_inventory_accounting():
    c, h, d = generate_data()
    schedule = {1: {"P001": 4}}
    without = simulate(c, d, schedule)
    with_history = simulate(c, d, schedule, historical_demand=h)
    for field in ("daily", "orders", "periods"):
        assert_frame_equal(getattr(without, field), getattr(with_history, field))


@pytest.mark.parametrize("problem", ["missing", "duplicate", "future", "too_early", "unknown", "negative", "fractional", "nan", "bool", "columns"])
def test_invalid_prehistory_rejected_before_policy_called(problem):
    c, h, d = generate_data()
    if problem == "missing":
        h = h.iloc[:-1]
    elif problem == "duplicate":
        h = pd.concat([h, h.iloc[:1]])
    elif problem in ("future", "too_early"):
        h.loc[0, "day"] = 1 if problem == "future" else -60
    elif problem == "unknown":
        h.loc[0, "product_id"] = "unknown"
    elif problem == "columns":
        h = h.drop(columns="demand")
    elif problem == "bool":
        h["demand"] = True
    else:
        h["demand"] = h.demand.astype(float)
        h.loc[0, "demand"] = {"negative": -1, "fractional": .5, "nan": np.nan}[problem]

    def forbidden(observation):
        pytest.fail("Policy must not be called for invalid prehistory")

    with pytest.raises(ValueError):
        simulate(c, d, policy=forbidden, historical_demand=h)
