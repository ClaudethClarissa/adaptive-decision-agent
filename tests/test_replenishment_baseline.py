"""Order-up-to equations, proportional rationing, and causal integration."""

from decimal import Decimal
from fractions import Fraction
from math import ceil

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from adaptive_decision_agent.data.synthetic import generate_data
from adaptive_decision_agent.policies import OrderUpToPolicy, allocate_budget
from adaptive_decision_agent.simulation import PolicyObservation, simulate


def observation(total=150, inventory=5, pending=7, lead=3, budget="20000"):
    values = np.full(60, total // 60, dtype=int)
    values[:total % 60] += 1
    history = pd.DataFrame({"day": range(-59, 1), "product_id": "P", "demand": values})
    products = pd.DataFrame([{"product_id": "P", "unit_cost": 10., "lead_time_days": lead,
                              "estimated_demand_rate": 999.}])
    orders = pd.DataFrame([{"product_id": "P", "quantity": pending, "arrival_day": 4}])
    return PolicyObservation(1, {"P": inventory}, orders, products, Decimal(budget), history)


def test_target_preliminary_quantity_and_outstanding_orders():
    plan = OrderUpToPolicy().plan(observation()).iloc[0]
    assert plan.estimated_daily_demand == 2.5
    assert plan.target_inventory_position == 30
    assert plan.outstanding_units == 7
    assert plan.desired_quantity == plan.allocated_quantity == 18
    assert plan.allocated_cost == 180
    assert OrderUpToPolicy()(observation()) == {"P": 18}


@pytest.mark.parametrize("total,lead", [(0, 3), (60, 2), (168, 6), (150, 3), (173, 5)])
def test_target_uses_exact_expanding_mean(total, lead):
    o = observation(total=total, inventory=0, pending=0, lead=lead)
    p = OrderUpToPolicy().plan(o).iloc[0]
    assert p.target_inventory_position == ceil(Fraction(total, 60) * (lead + 7 + 2))
    assert p.estimated_daily_demand == total / 60


def test_expanding_forecast_not_stale_catalog_or_short_window():
    o = observation(inventory=0, pending=0)
    o.demand_history["demand"] = [1] * 30 + [3] * 30
    p = OrderUpToPolicy().plan(o).iloc[0]
    assert p.estimated_daily_demand == 2
    assert p.target_inventory_position == 24
    assert p.desired_quantity == 24


def test_no_purchases_for_excess_stock_and_pipeline():
    assert OrderUpToPolicy()(observation(inventory=100)) == {"P": 0}
    assert OrderUpToPolicy()(observation(inventory=0, pending=100)) == {"P": 0}


@pytest.mark.parametrize("desired,costs,budget,expected", [
    ({"A": 3, "B": 3}, {"A": 10., "B": 20.}, "50", {"A": 3, "B": 1}),
    ({"A": 3, "B": 1}, {"A": 6., "B": 4.}, "10", {"A": 1, "B": 1}),
    ({"A": 1, "B": 1}, {"A": 100., "B": 1.}, "50", {"A": 0, "B": 1}),
    ({"A": 3}, {"A": .1}, ".30", {"A": 3}),
    ({"A": 3}, {"A": .1}, ".29", {"A": 2}),
    ({"A": 0}, {"A": 10.}, "20000", {"A": 0}),
    ({"A": 3}, {"A": 10.}, "0", {"A": 0}),
    ({}, {}, "20", {}),
])
def test_allocation_hand_calculations(desired, costs, budget, expected):
    actual = allocate_budget(desired, costs, Decimal(budget))
    assert actual == expected
    assert actual == allocate_budget(dict(reversed(list(desired.items()))), costs, Decimal(budget))
    assert all(isinstance(q, int) for q in actual.values())


def test_allocation_constraints_for_different_prices():
    rng = np.random.default_rng(12)
    for _ in range(40):
        ids = [f"P{i}" for i in range(8)]
        desired = dict(zip(ids, map(int, rng.integers(0, 50, len(ids)))))
        cents = dict(zip(ids, map(int, rng.integers(1, 3001, len(ids)))))
        budget_cents = int(rng.integers(0, 100001))
        prices = {p: Decimal(c) / 100 for p, c in cents.items()}
        result = allocate_budget(desired, prices, Decimal(budget_cents) / 100)
        remaining = budget_cents - sum(result[p] * cents[p] for p in ids)
        assert remaining >= 0
        assert all(0 <= result[p] <= desired[p] for p in ids)
        assert all(cents[p] > remaining for p in ids if result[p] < desired[p])


@pytest.mark.parametrize("desired,cost,budget", [
    (-1, 10, 20), (1.5, 10, 20), (True, 10, 20),
    (1, 0, 20), (1, -1, 20), (1, .001, 20), (1, float("nan"), 20),
    (1, 10, -1), (1, 10, float("inf")),
])
def test_invalid_allocation_inputs(desired, cost, budget):
    with pytest.raises(ValueError):
        allocate_budget({"P": desired}, {"P": cost}, budget)


def test_full_simulator_integration_and_reproducibility():
    c, h, d = generate_data()
    original_c, original_h = c.copy(deep=True), h.copy(deep=True)
    first = simulate(c, d, policy=OrderUpToPolicy(), historical_demand=h)
    second = simulate(c, d, policy=OrderUpToPolicy(), historical_demand=h)
    for field in ("daily", "orders", "periods"):
        assert_frame_equal(getattr(first, field), getattr(second, field))
    assert first.daily.shape == (1500, 12)
    assert (first.periods.purchasing_expenditure <= 20000).all()
    assert set(first.orders.order_day).issubset({1, 8, 15, 22, 29})
    assert (first.orders.quantity % 1 == 0).all()
    assert (first.daily.closing_stock >= 0).all()
    assert_frame_equal(c, original_c)
    assert_frame_equal(h, original_h)


@pytest.mark.parametrize("divergence_day", [1, 8])
def test_no_current_or_future_demand_leakage(divergence_day):
    c, h, d = generate_data()
    changed = d.copy()
    changed.loc[changed.day >= divergence_day, "demand"] += 100
    snapshots = []
    for demand in (d, changed):
        decisions = {}

        def callback(o):
            decisions[o.day] = OrderUpToPolicy().plan(o)
            return dict(zip(decisions[o.day].product_id, decisions[o.day].allocated_quantity))

        simulate(c, demand, policy=callback, historical_demand=h)
        snapshots.append(decisions)
    assert_frame_equal(snapshots[0][divergence_day], snapshots[1][divergence_day])


def test_policy_rejects_current_day_history():
    o = observation()
    o.demand_history.loc[59, "day"] = 1
    with pytest.raises(ValueError):
        OrderUpToPolicy()(o)


def test_simulator_binding_budget_uses_observation_balance():
    c, h, d = generate_data()
    plans = []

    def callback(o):
        assert o.remaining_budget == Decimal("5000")
        plan = OrderUpToPolicy().plan(o)
        plans.append(plan)
        return dict(zip(plan.product_id, plan.allocated_quantity))

    result = simulate(c, d, policy=callback, historical_demand=h, weekly_budget=5000)
    assert (result.periods.purchasing_expenditure <= 5000).all()
    assert (plans[0].allocated_quantity < plans[0].desired_quantity).any()
    assert all((p.allocated_quantity <= p.desired_quantity).all() for p in plans)
