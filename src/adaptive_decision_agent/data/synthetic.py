"""Seeded illustrative inventory data; no inventory dynamics or sales censoring."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

N_PRODUCTS = 50
N_SUPPLIERS = 3
N_DAYS = 30
WEEKLY_BUDGET = 20_000
SAFETY_COVERAGE_DAYS = 2
SUPPLIER_IDS = ("S001", "S002", "S003")
CATALOG_COLUMNS = (
    "product_id", "supplier_id", "unit_cost", "selling_price",
    "holding_cost_per_unit_day", "stockout_penalty_per_unit", "initial_stock",
    "lead_time_days", "daily_demand_rate",
)
DEMAND_COLUMNS = ("day", "product_id", "demand")


def generate_catalog(rng: np.random.Generator) -> pd.DataFrame:
    """Generate 50 products with balanced, shuffled supplier assignments."""
    supplier_index = rng.permutation(np.arange(N_PRODUCTS) % N_SUPPLIERS)
    supplier_lead_times = rng.integers(2, 6, size=N_SUPPLIERS)
    costs = np.round(rng.uniform(10, 30, N_PRODUCTS), 2)
    # Population-average weekly purchase cost: 50 * 7 * 2.4 * $20 = $16,800.
    rates = np.round(rng.uniform(1, 3.8, N_PRODUCTS), 3)
    lead_times = supplier_lead_times[supplier_index]
    initial_stock = np.ceil(rates * (lead_times + SAFETY_COVERAGE_DAYS)).astype(int)
    return pd.DataFrame({
        "product_id": [f"P{i:03d}" for i in range(1, N_PRODUCTS + 1)],
        "supplier_id": np.array(SUPPLIER_IDS)[supplier_index],
        "unit_cost": costs,
        "selling_price": np.round(costs * rng.uniform(1.2, 1.8, N_PRODUCTS), 2),
        "holding_cost_per_unit_day": np.round(costs * 0.001, 4),
        "stockout_penalty_per_unit": np.round(costs * rng.uniform(0.5, 1.5, N_PRODUCTS), 2),
        "initial_stock": initial_stock,
        "lead_time_days": lead_times,
        "daily_demand_rate": rates,
    })


def generate_demand(catalog: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Sample latent customer demand using rates only, regardless of stock."""
    demand = rng.poisson(catalog["daily_demand_rate"].to_numpy(), size=(N_DAYS, len(catalog)))
    return pd.DataFrame({
        "day": np.repeat(np.arange(1, N_DAYS + 1), len(catalog)),
        "product_id": np.tile(catalog["product_id"].to_numpy(), N_DAYS),
        "demand": demand.ravel(),
    })


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_data(catalog: pd.DataFrame, demand: pd.DataFrame) -> None:
    """Reject missing, malformed, out-of-range, or incomplete generated data."""
    _require(tuple(catalog.columns) == CATALOG_COLUMNS, "Invalid catalog columns")
    _require(tuple(demand.columns) == DEMAND_COLUMNS, "Invalid demand columns")
    _require(catalog.shape == (N_PRODUCTS, len(CATALOG_COLUMNS)), "Expected 50 catalog rows")
    _require(demand.shape == (N_PRODUCTS * N_DAYS, len(DEMAND_COLUMNS)), "Expected 1500 demand rows")
    _require(not catalog.isna().any().any() and not demand.isna().any().any(), "Missing values")
    expected_ids = {f"P{i:03d}" for i in range(1, N_PRODUCTS + 1)}
    _require(set(catalog["product_id"]) == expected_ids, "Invalid or duplicate product IDs")
    _require(set(catalog["supplier_id"]) == set(SUPPLIER_IDS), "Invalid supplier IDs")
    counts = catalog["supplier_id"].value_counts()
    _require(counts.max() - counts.min() <= 1, "Supplier assignments must be balanced")
    ranges = {
        "unit_cost": (10, 30), "selling_price": (12, 54),
        "holding_cost_per_unit_day": (0.01, 0.03),
        "stockout_penalty_per_unit": (5, 45), "initial_stock": (4, 28),
        "lead_time_days": (2, 5), "daily_demand_rate": (1, 3.8),
    }
    for column, (low, high) in ranges.items():
        values = catalog[column]
        _require(pd.api.types.is_numeric_dtype(values), f"{column} must be numeric")
        _require(bool(values.between(low, high).all()), f"{column} outside illustrative range")
    for column in ("initial_stock", "lead_time_days"):
        _require(bool((catalog[column] % 1 == 0).all()), f"{column} must contain integers")
    expected_stock = np.ceil(catalog["daily_demand_rate"] * (
        catalog["lead_time_days"] + SAFETY_COVERAGE_DAYS
    ))
    _require(bool((catalog["initial_stock"] == expected_stock).all()), "Initial stock must follow the coverage formula")
    cost = catalog["unit_cost"]
    _require(bool(((catalog["selling_price"] >= cost * 1.2 - 0.005001)
                   & (catalog["selling_price"] <= cost * 1.8 + 0.005001)).all()), "Invalid selling margin")
    _require(bool(np.allclose(catalog["holding_cost_per_unit_day"], np.round(cost * 0.001, 4))), "Invalid holding costs")
    penalty = catalog["stockout_penalty_per_unit"]
    _require(bool(((penalty >= cost * 0.5 - 0.005001)
                   & (penalty <= cost * 1.5 + 0.005001)).all()), "Invalid stockout penalties")
    _require(bool((catalog.groupby("supplier_id")["lead_time_days"].nunique() == 1).all()), "Inconsistent supplier lead times")
    for column in ("day", "demand"):
        values = demand[column]
        _require(pd.api.types.is_numeric_dtype(values), f"{column} must be numeric")
        _require(bool((np.isfinite(values) & (values % 1 == 0)).all()), f"{column} must contain finite integers")
    _require(bool((demand["demand"] >= 0).all()), "Demand must be nonnegative")
    expected = pd.MultiIndex.from_product([range(1, N_DAYS + 1), sorted(expected_ids)], names=["day", "product_id"])
    actual = pd.MultiIndex.from_frame(demand[["day", "product_id"]])
    _require(actual.is_unique and actual.sort_values().equals(expected), "Invalid day/product coverage")


def expected_weekly_replenishment_cost(catalog: pd.DataFrame) -> float:
    """Cost to replace seven days of expected demand, without safety-stock builds.

    This steady-state diagnostic does not impose a budget or adjust the draws.
    Initial inventory is not subtracted from recurring replenishment demand.
    """
    return float((7 * catalog["daily_demand_rate"] * catalog["unit_cost"]).sum())


def generate_data(seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return validated catalog and demand with independent random streams."""
    catalog_seed, demand_seed = np.random.SeedSequence(seed).spawn(2)
    catalog = generate_catalog(np.random.default_rng(catalog_seed))
    demand = generate_demand(catalog, np.random.default_rng(demand_seed))
    validate_data(catalog, demand)
    return catalog, demand


def write_csv(catalog: pd.DataFrame, demand: pd.DataFrame, output_dir: str | Path) -> tuple[Path, Path]:
    """Validate and export two CSVs, replacing same-named files if present."""
    validate_data(catalog, demand)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    catalog_path = directory / "product_catalog.csv"
    demand_path = directory / "daily_demand.csv"
    catalog.to_csv(catalog_path, index=False)
    demand.to_csv(demand_path, index=False)
    return catalog_path, demand_path


def main() -> None:
    """Generate CSV files from a configurable seed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    catalog, demand = generate_data(args.seed)
    for path in write_csv(catalog, demand, args.output_dir):
        print(path.resolve())


if __name__ == "__main__":
    main()
