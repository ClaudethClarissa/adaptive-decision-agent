"""Deterministic daily lost-sales inventory accounting with external orders."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from numbers import Integral, Real

import numpy as np
import pandas as pd

DECISION_DAYS = (1, 8, 15, 22, 29)
ORDER_COLUMNS = ("order_day", "product_id", "quantity", "arrival_day", "purchase_cost")
POLICY_PRODUCT_COLUMNS = (
    "product_id", "supplier_id", "unit_cost", "selling_price",
    "holding_cost_per_unit_day", "stockout_penalty_per_unit", "lead_time_days",
)


@dataclass(frozen=True)
class PolicyObservation:
    """Detached snapshots after today's receipts, before orders and demand.

    Products use an explicit known-information allowlist: latent demand rates
    and arbitrary catalog extras are never passed to the policy.
    """

    day: int
    current_inventory: dict[str, int]
    outstanding_orders: pd.DataFrame
    products: pd.DataFrame
    remaining_budget: Decimal
    demand_history: pd.DataFrame


@dataclass(frozen=True)
class SimulationResult:
    """Daily product ledger, accepted orders, and expiring period budgets."""

    daily: pd.DataFrame
    orders: pd.DataFrame
    periods: pd.DataFrame


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be an integer >= {minimum}")
    if not np.isfinite(value) or value != int(value) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _money(value: object, name: str, *, cents: bool = False) -> Decimal:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be finite and nonnegative")
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    if cents and number != number.quantize(Decimal("0.01")):
        raise ValueError(f"{name} must use whole cents")
    return number


def simulate(
    catalog: pd.DataFrame,
    demand: pd.DataFrame,
    order_schedule: Mapping[int, Mapping[str, int]] | None = None,
    *,
    horizon: int = 30,
    weekly_budget: float = 20_000,
    policy: Callable[[PolicyObservation], Mapping[str, int]] | None = None,
) -> SimulationResult:
    """Run a precommitted schedule or one policy call per decision day.

    Schedule format: {1: {"P001": 10}, 8: {"P001": 5}}. Receipts precede
    orders and demand; purchases are charged on placement, holding on closing
    stock. Policy observations contain only known information and past demand.
    """
    horizon = _integer(horizon, "horizon", 1)
    if horizon > 30:
        raise ValueError("horizon must not exceed 30 days")
    budget = _money(weekly_budget, "weekly_budget", cents=True)
    if policy is not None and (not callable(policy) or order_schedule is not None):
        raise ValueError("Supply either an order_schedule or a callable policy, not both")
    required = {"product_id", "initial_stock", "unit_cost", "lead_time_days", "holding_cost_per_unit_day"}
    if not catalog.columns.is_unique or not required.issubset(catalog.columns) or catalog.empty:
        raise ValueError("Catalog must contain unique required columns and at least one product")
    ids = catalog["product_id"].tolist()
    if any(not isinstance(p, str) or not p for p in ids) or len(set(ids)) != len(ids):
        raise ValueError("Product IDs must be unique nonempty strings")
    stock, costs, holding, leads = {}, {}, {}, {}
    for row in catalog.to_dict("records"):
        p = row["product_id"]
        stock[p] = _integer(row["initial_stock"], "initial_stock")
        leads[p] = _integer(row["lead_time_days"], "lead_time_days", 1)
        costs[p] = _money(row["unit_cost"], "unit_cost", cents=True)
        if costs[p] == 0:
            raise ValueError("unit_cost must be positive")
        holding[p] = _money(row["holding_cost_per_unit_day"], "holding cost")
    if not demand.columns.is_unique or not {"day", "product_id", "demand"}.issubset(demand.columns):
        raise ValueError("Demand requires day, product_id, and demand columns")
    observed = {}
    for row in demand.to_dict("records"):
        day = _integer(row["day"], "demand day", 1)
        p = row["product_id"]
        if not isinstance(p, str) or p not in stock or day > horizon or (day, p) in observed:
            raise ValueError("Invalid or duplicate demand day/product")
        observed[day, p] = _integer(row["demand"], "demand")
    if len(observed) != horizon * len(ids):
        raise ValueError("Demand must cover every product on every simulation day exactly once")

    schedule = {} if order_schedule is None else order_schedule
    if not isinstance(schedule, Mapping):
        raise ValueError("order_schedule must be a day-to-product-quantity mapping")
    decisions = [day for day in DECISION_DAYS if day <= horizon]
    orders = []
    spending = {day: Decimal(0) for day in decisions}

    def validate_order(day, quantities):
        """Validate the entire batch before accepting any of its lines."""
        if not isinstance(quantities, Mapping):
            raise ValueError("Each decision must map product IDs to quantities")
        batch = []
        total = Decimal(0)
        for p, quantity in quantities.items():
            if p not in stock:
                raise ValueError(f"Unknown order product: {p}")
            q = _integer(quantity, "order quantity")
            cost = q * costs[p]
            total += cost
            if q:
                batch.append({"order_day": int(day), "product_id": p, "quantity": q,
                               "arrival_day": int(day) + leads[p], "purchase_cost": float(cost)})
        if total > budget - spending[day]:
            raise ValueError(f"Orders on day {day} exceed the period budget")
        return batch, total

    for day, quantities in schedule.items():
        if isinstance(day, bool) or not isinstance(day, Integral) or day not in decisions:
            raise ValueError("Orders are allowed only on decision days within the horizon")
        batch, total = validate_order(day, quantities)
        orders.extend(batch)
        spending[day] += total
    rank = {p: i for i, p in enumerate(ids)}
    orders.sort(key=lambda order: (order["order_day"], rank[order["product_id"]]))
    receipts, placements, purchases = {}, {}, {}
    for order in orders:
        p, day = order["product_id"], order["order_day"]
        receipts[order["arrival_day"], p] = receipts.get((order["arrival_day"], p), 0) + order["quantity"]
        placements[day, p] = order["quantity"]
        purchases[day, p] = order["purchase_cost"]
    outstanding = dict.fromkeys(ids, 0)
    rows = []
    history = []
    known_products = catalog[[column for column in POLICY_PRODUCT_COLUMNS if column in catalog]].copy(deep=True)
    for day in range(1, horizon + 1):
        if policy is not None and day in decisions:
            observation = PolicyObservation(
                day=day,
                current_inventory={p: stock[p] + receipts.get((day, p), 0) for p in ids},
                outstanding_orders=pd.DataFrame(
                    [order.copy() for order in orders if order["order_day"] < day < order["arrival_day"]],
                    columns=ORDER_COLUMNS,
                ),
                products=known_products.copy(deep=True),
                remaining_budget=budget - spending[day],
                demand_history=pd.DataFrame(history, columns=("day", "product_id", "demand")),
            )
            batch, total = validate_order(day, policy(observation))
            spending[day] += total
            orders.extend(sorted(batch, key=lambda order: rank[order["product_id"]]))
            for order in batch:
                p = order["product_id"]
                key = (order["arrival_day"], p)
                receipts[key] = receipts.get(key, 0) + order["quantity"]
                placements[day, p] = order["quantity"]
                purchases[day, p] = order["purchase_cost"]
        for p in ids:
            opening = stock[p]
            arriving = receipts.get((day, p), 0)
            outstanding[p] -= arriving
            ordered = placements.get((day, p), 0)
            outstanding[p] += ordered
            available = opening + arriving
            requested = observed[day, p]
            history.append((day, p, requested))
            sales = min(available, requested)
            stock[p] = available - sales
            rows.append({"day": day, "product_id": p, "opening_stock": opening,
                         "arriving_units": arriving, "ordered_units": ordered,
                         "demand": requested, "sales": sales, "unmet_demand": requested - sales,
                         "closing_stock": stock[p], "outstanding_orders": outstanding[p],
                         "purchasing_expenditure": purchases.get((day, p), 0.0),
                         "holding_cost": float(stock[p] * holding[p])})
    periods = [{"decision_day": day, "period_end_day": min(day + 6, horizon),
                "allocation": float(budget), "purchasing_expenditure": float(spending[day]),
                "expired_unused_budget": float(budget - spending[day])} for day in decisions]
    return SimulationResult(pd.DataFrame(rows), pd.DataFrame(orders, columns=ORDER_COLUMNS), pd.DataFrame(periods))
