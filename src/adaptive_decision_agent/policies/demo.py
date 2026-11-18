"""Reproduce one fixed seed-42-file comparison; no tuning or statistical study."""

import argparse
from pathlib import Path

import pandas as pd

from adaptive_decision_agent.simulation import simulate
from .replenishment import DECISION_DAYS, OrderUpToPolicy


def summarize(result) -> dict:
    daily = result.daily
    last = daily[daily.day == daily.day.max()]
    demand, sales = int(daily.demand.sum()), int(daily.sales.sum())
    return {"customer_demand": demand, "sales": sales,
            "unmet_demand": int(daily.unmet_demand.sum()),
            "unit_fill_rate": sales / demand if demand else float("nan"),
            "purchasing_expenditure": float(daily.purchasing_expenditure.sum()),
            "holding_cost": float(daily.holding_cost.sum()),
            "ending_inventory": int(last.closing_stock.sum()),
            "ending_outstanding_units": int(last.outstanding_orders.sum())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/replenishment_baseline"))
    args = parser.parse_args()
    catalog = pd.read_csv(args.data_dir / "product_catalog.csv")
    history = pd.read_csv(args.data_dir / "historical_daily_demand.csv")
    evaluation = pd.read_csv(args.data_dir / "daily_demand.csv")
    traces = []
    policy = OrderUpToPolicy()

    def recorded_policy(observation):
        plan = policy.plan(observation)
        plan["decision_day"] = observation.day
        traces.append(plan)
        return dict(zip(plan.product_id, map(int, plan.allocated_quantity)))

    baseline = simulate(catalog, evaluation, policy=recorded_policy, historical_demand=history)
    schedule = {day: {p: 10 for p in catalog.product_id} for day in DECISION_DAYS}
    fixed = simulate(catalog, evaluation, schedule, historical_demand=history)
    plans = pd.concat(traces, ignore_index=True)
    decisions = plans.groupby("decision_day", as_index=False).agg(
        desired_units=("desired_quantity", "sum"), ordered_units=("allocated_quantity", "sum"),
        desired_cost=("desired_cost", "sum"), purchasing_expenditure=("allocated_cost", "sum"))
    decisions["unused_budget"] = 20000 - decisions.purchasing_expenditure
    results = {"order_up_to": baseline, "fixed_10": fixed}
    summary = pd.DataFrame([{"policy": name, **summarize(result)} for name, result in results.items()])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plans.to_csv(args.output_dir / "baseline_decision_details.csv", index=False)
    decisions.to_csv(args.output_dir / "baseline_decision_summary.csv", index=False)
    summary.to_csv(args.output_dir / "comparison_summary.csv", index=False)
    for name, result in results.items():
        for ledger in ("daily", "orders", "periods"):
            getattr(result, ledger).to_csv(args.output_dir / f"{name}_{ledger}.csv", index=False)
    print(summary.to_string(index=False))
    print("\nOrder-up-to decisions:\n", decisions.to_string(index=False))


if __name__ == "__main__":
    main()
