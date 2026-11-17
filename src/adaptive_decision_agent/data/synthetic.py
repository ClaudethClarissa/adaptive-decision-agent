"""Seeded illustrative inventory data; no inventory dynamics or sales censoring."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

N_PRODUCTS = 50
N_SUPPLIERS = 3
N_DAYS = 30
N_HISTORY_DAYS = 60
WEEKLY_BUDGET = 20_000
SAFETY_COVERAGE_DAYS = 2
SUPPLIER_IDS = ("S001", "S002", "S003")
CATALOG_COLUMNS = (
    "product_id", "supplier_id", "unit_cost", "selling_price",
    "holding_cost_per_unit_day", "stockout_penalty_per_unit", "initial_stock",
    "lead_time_days", "estimated_demand_rate",
)
DEMAND_COLUMNS = ("day", "product_id", "demand")


def _generate_parameters(rng: np.random.Generator) -> tuple[pd.DataFrame, np.ndarray]:
    """Internal catalog parameters and latent rates; never export the rates."""
    supplier_index = rng.permutation(np.arange(N_PRODUCTS) % N_SUPPLIERS)
    supplier_lead_times = rng.integers(2, 6, size=N_SUPPLIERS)
    costs = np.round(rng.uniform(10, 30, N_PRODUCTS), 2)
    # Population-average weekly purchase cost: 50 * 7 * 2.4 * $20 = $16,800.
    rates = np.round(rng.uniform(1, 3.8, N_PRODUCTS), 3)
    lead_times = supplier_lead_times[supplier_index]
    catalog = pd.DataFrame({
        "product_id": [f"P{i:03d}" for i in range(1, N_PRODUCTS + 1)],
        "supplier_id": np.array(SUPPLIER_IDS)[supplier_index],
        "unit_cost": costs,
        "selling_price": np.round(costs * rng.uniform(1.2, 1.8, N_PRODUCTS), 2),
        "holding_cost_per_unit_day": np.round(costs * 0.001, 4),
        "stockout_penalty_per_unit": np.round(costs * rng.uniform(0.5, 1.5, N_PRODUCTS), 2),
        "lead_time_days": lead_times,
    })
    return catalog, rates


def _sample_demand(product_ids, rates, rng: np.random.Generator, days) -> pd.DataFrame:
    """Internal latent-rate sampler, independent of inventory availability."""
    days = list(days)
    demand = rng.poisson(rates, size=(len(days), len(product_ids)))
    return pd.DataFrame({
        "day": np.repeat(days, len(product_ids)),
        "product_id": np.tile(np.asarray(product_ids), len(days)),
        "demand": demand.ravel(),
    })


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_demand(demand: pd.DataFrame, product_ids, days) -> None:
    """Check complete integer customer demand for an explicit day range."""
    _require(tuple(demand.columns) == DEMAND_COLUMNS, "Invalid demand columns")
    _require(not demand.isna().any().any(), "Missing demand values")
    for column in ("day", "demand"):
        values = demand[column]
        _require(pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values), f"{column} must be numeric")
        _require(bool((np.isfinite(values) & (values % 1 == 0)).all()), f"{column} must contain finite integers")
    _require(bool((demand["demand"] >= 0).all()), "Demand must be nonnegative")
    expected = pd.MultiIndex.from_product([days, sorted(product_ids)], names=["day", "product_id"])
    actual = pd.MultiIndex.from_frame(demand[["day", "product_id"]])
    _require(actual.is_unique and actual.sort_values().equals(expected), "Invalid day/product coverage")


def estimate_demand_rates(history: pd.DataFrame) -> pd.Series:
    """Initialization estimates only: exact 60-day per-product sample means."""
    ids = [f"P{i:03d}" for i in range(1, N_PRODUCTS + 1)]
    _validate_demand(history, ids, range(1 - N_HISTORY_DAYS, 1))
    return history.groupby("product_id")["demand"].sum() / N_HISTORY_DAYS


def validate_data(catalog: pd.DataFrame, history: pd.DataFrame, demand: pd.DataFrame) -> None:
    """Reject missing, malformed, out-of-range, or incomplete generated data."""
    _require(tuple(catalog.columns) == CATALOG_COLUMNS, "Invalid catalog columns")
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
        "stockout_penalty_per_unit": (5, 45), "initial_stock": (0, np.inf),
        "lead_time_days": (2, 5), "estimated_demand_rate": (0, np.inf),
    }
    for column, (low, high) in ranges.items():
        values = catalog[column]
        _require(pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values), f"{column} must be numeric")
        _require(bool((np.isfinite(values) & values.between(low, high)).all()), f"{column} outside illustrative range")
    for column in ("initial_stock", "lead_time_days"):
        _require(bool((catalog[column] % 1 == 0).all()), f"{column} must contain integers")
    estimates = estimate_demand_rates(history).reindex(catalog["product_id"]).to_numpy()
    _require(bool(np.allclose(catalog["estimated_demand_rate"], estimates, rtol=0, atol=1e-12)), "Estimated rates must equal historical sample means")
    totals = history.groupby("product_id").demand.sum().reindex(catalog.product_id).to_numpy()
    expected_stock = (totals * (catalog.lead_time_days + SAFETY_COVERAGE_DAYS) + N_HISTORY_DAYS - 1) // N_HISTORY_DAYS
    _require(bool((catalog["initial_stock"] == expected_stock).all()), "Initial stock must follow the coverage formula")
    cost = catalog["unit_cost"]
    _require(bool(((catalog["selling_price"] >= cost * 1.2 - 0.005001)
                   & (catalog["selling_price"] <= cost * 1.8 + 0.005001)).all()), "Invalid selling margin")
    _require(bool(np.allclose(catalog["holding_cost_per_unit_day"], np.round(cost * 0.001, 4))), "Invalid holding costs")
    penalty = catalog["stockout_penalty_per_unit"]
    _require(bool(((penalty >= cost * 0.5 - 0.005001)
                   & (penalty <= cost * 1.5 + 0.005001)).all()), "Invalid stockout penalties")
    _require(bool((catalog.groupby("supplier_id")["lead_time_days"].nunique() == 1).all()), "Inconsistent supplier lead times")
    _validate_demand(demand, expected_ids, range(1, N_DAYS + 1))


def expected_weekly_replenishment_cost(catalog: pd.DataFrame) -> float:
    """History-based estimate of seven-day replacement cost, not oracle demand.

    This steady-state diagnostic does not impose a budget or adjust the draws.
    Initial inventory is not subtracted from recurring replenishment demand.
    """
    return float((7 * catalog["estimated_demand_rate"] * catalog["unit_cost"]).sum())


def _generate_data(seed: int):
    # Keep child 0 (catalog) and 1 (evaluation) unchanged from Phase 2A.
    catalog_seed, demand_seed, history_seed = np.random.SeedSequence(seed).spawn(3)
    catalog, rates = _generate_parameters(np.random.default_rng(catalog_seed))
    demand = _sample_demand(catalog.product_id, rates, np.random.default_rng(demand_seed), range(1, N_DAYS + 1))
    history = _sample_demand(catalog.product_id, rates, np.random.default_rng(history_seed), range(1 - N_HISTORY_DAYS, 1))
    estimates = estimate_demand_rates(history).reindex(catalog.product_id).to_numpy()
    catalog["estimated_demand_rate"] = estimates
    # Integer arithmetic is exactly ceil((historical total / 60) * coverage).
    # It avoids a binary floating-point ceil error when the result is integral.
    totals = history.groupby("product_id").demand.sum().reindex(catalog.product_id).to_numpy()
    numerator = totals * (catalog.lead_time_days.to_numpy() + SAFETY_COVERAGE_DAYS)
    catalog["initial_stock"] = (numerator + N_HISTORY_DAYS - 1) // N_HISTORY_DAYS
    catalog = catalog[list(CATALOG_COLUMNS)]
    validate_data(catalog, history, demand)
    return catalog, history, demand, rates


def generate_data(seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return business catalog, historical demand, evaluation demand; no latent rates."""
    catalog, history, demand, _ = _generate_data(seed)
    return catalog, history, demand


def researcher_diagnostics(seed: int = 42) -> dict[str, float | int]:
    """Aggregate research-only truth diagnostics; never pass these to a policy."""
    catalog, _, _, rates = _generate_data(seed)
    estimates = catalog.estimated_demand_rate.to_numpy()
    errors = estimates - rates
    coverage = catalog.initial_stock.to_numpy() / rates
    return {
        "mean_true_rate": float(rates.mean()), "mean_estimated_rate": float(estimates.mean()),
        "bias": float(errors.mean()), "mae": float(np.abs(errors).mean()),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "min_error": float(errors.min()), "max_error": float(errors.max()),
        "mean_true_coverage": float(coverage.mean()), "min_true_coverage": float(coverage.min()),
        "max_true_coverage": float(coverage.max()),
        "below_true_lead_time": int((coverage < catalog.lead_time_days).sum()),
        "true_expected_weekly_cost": float((7 * rates * catalog.unit_cost).sum()),
        "estimated_weekly_cost": expected_weekly_replenishment_cost(catalog),
    }


def write_csv(catalog: pd.DataFrame, history: pd.DataFrame, demand: pd.DataFrame, output_dir: str | Path) -> tuple[Path, Path, Path]:
    """Validate and export three business CSVs, replacing same-named files."""
    validate_data(catalog, history, demand)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    catalog_path = directory / "product_catalog.csv"
    demand_path = directory / "daily_demand.csv"
    history_path = directory / "historical_daily_demand.csv"
    catalog.to_csv(catalog_path, index=False)
    demand.to_csv(demand_path, index=False)
    history.to_csv(history_path, index=False)
    return catalog_path, history_path, demand_path


def main() -> None:
    """Generate CSV files from a configurable seed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    catalog, history, demand = generate_data(args.seed)
    for path in write_csv(catalog, history, demand, args.output_dir):
        print(path.resolve())


if __name__ == "__main__":
    main()
