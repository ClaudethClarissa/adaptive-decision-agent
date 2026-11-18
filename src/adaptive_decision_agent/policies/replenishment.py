"""Periodic order-up-to heuristic with exact-cent proportional budget rationing."""

from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction
from math import ceil
from numbers import Integral, Real

import pandas as pd

from adaptive_decision_agent.forecasting import MeanForecaster
from adaptive_decision_agent.simulation import PolicyObservation

REVIEW_INTERVAL = 7
SAFETY_COVERAGE = 2
DECISION_DAYS = (1, 8, 15, 22, 29)


def _quantity(value, name):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)


def _cents(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        raise ValueError(f"{name} must be a finite monetary amount")
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0 or (positive and amount == 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"{name} must use whole cents")
    return int(cents)


def allocate_budget(desired: Mapping[str, int], unit_costs: Mapping[str, float], budget: Decimal) -> dict[str, int]:
    """Scale, floor, then repeatedly award affordable remainder-ranked units.

    Descending exact fractional remainder, then ascending product ID. Revisit
    the same ranking until no desired unit is affordable. Costs differ: this is
    a heuristic, not an optimal knapsack or service allocation.
    """
    if not isinstance(desired, Mapping) or not isinstance(unit_costs, Mapping) or set(desired) != set(unit_costs):
        raise ValueError("Desired quantities and costs must map the same product IDs")
    if any(not isinstance(p, str) or not p for p in desired):
        raise ValueError("Product IDs must be nonempty strings")
    ids = sorted(desired)
    quantities = {p: _quantity(desired[p], "desired quantity") for p in ids}
    costs = {p: _cents(unit_costs[p], "unit_cost", positive=True) for p in ids}
    available = _cents(budget, "budget")
    total = sum(quantities[p] * costs[p] for p in ids)
    if total <= available:
        return quantities
    allocated = {p: quantities[p] * available // total for p in ids}
    remainder = {p: quantities[p] * available % total for p in ids}
    ranked = sorted(ids, key=lambda p: (-remainder[p], p))
    remaining = available - sum(allocated[p] * costs[p] for p in ids)
    while True:
        progress = False
        for p in ranked:
            if allocated[p] < quantities[p] and costs[p] <= remaining:
                allocated[p] += 1
                remaining -= costs[p]
                progress = True
        if not progress:
            return allocated


class OrderUpToPolicy:
    """Stateless callback: expanding mean, lead + seven review + two safety days."""

    def plan(self, observation: PolicyObservation) -> pd.DataFrame:
        """Return a detached, auditable desired/allocated order table."""
        if observation.day not in DECISION_DAYS:
            raise ValueError("Purchasing is allowed only on decision days")
        products = observation.products
        if not {"product_id", "unit_cost", "lead_time_days"}.issubset(products.columns):
            raise ValueError("Products require ID, unit cost, and lead time")
        if products.product_id.duplicated().any():
            raise ValueError("Duplicate product IDs")
        predicted = MeanForecaster().predict(
            observation.demand_history, decision_day=observation.day, horizon=1
        ).daily.set_index("product_id").expected_demand
        ids = set(products.product_id)
        if ids != set(predicted.index) or ids != set(observation.current_inventory):
            raise ValueError("Inventory, product, and observed-history IDs must match")
        pending = dict.fromkeys(ids, 0)
        for order in observation.outstanding_orders.to_dict("records"):
            p = order["product_id"]
            if p not in ids or order["arrival_day"] <= observation.day:
                raise ValueError("Outstanding orders must be known products due after today")
            pending[p] += _quantity(order["quantity"], "outstanding quantity")
        n_days = observation.demand_history.day.nunique()
        rows = []
        for product in products.sort_values("product_id").itertuples():
            p = product.product_id
            lead = _quantity(product.lead_time_days, "lead time")
            if lead == 0:
                raise ValueError("Lead time must be positive")
            inventory = _quantity(observation.current_inventory[p], "current inventory")
            rate = float(predicted[p])
            # Reconstruct the rational sample mean (denominator <= n_days) only
            # for an exact ceiling at integer boundaries; never use latent rates.
            exact_rate = Fraction(rate).limit_denominator(n_days)
            target = ceil(exact_rate * (lead + REVIEW_INTERVAL + SAFETY_COVERAGE))
            desired = max(0, target - inventory - pending[p])
            rows.append({"product_id": p, "estimated_daily_demand": rate,
                         "lead_time_days": lead, "target_inventory_position": target,
                         "current_inventory": inventory, "outstanding_units": pending[p],
                         "desired_quantity": desired, "unit_cost": product.unit_cost})
        plan = pd.DataFrame(rows)
        desired = dict(zip(plan.product_id, plan.desired_quantity))
        costs = dict(zip(plan.product_id, plan.unit_cost))
        allocated = allocate_budget(desired, costs, observation.remaining_budget)
        plan["allocated_quantity"] = plan.product_id.map(allocated).astype(int)
        for quantity, name in [("desired_quantity", "desired_cost"), ("allocated_quantity", "allocated_cost")]:
            plan[name] = [int(q) * _cents(c, "unit_cost", positive=True) / 100
                          for q, c in zip(plan[quantity], plan.unit_cost)]
        return plan

    def __call__(self, observation: PolicyObservation) -> dict[str, int]:
        plan = self.plan(observation)
        return dict(zip(plan.product_id, map(int, plan.allocated_quantity)))
