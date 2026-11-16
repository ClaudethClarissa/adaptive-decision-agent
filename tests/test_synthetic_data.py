"""Behavioral checks for reproducible synthetic inventory data."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from adaptive_decision_agent.data.synthetic import (
    WEEKLY_BUDGET, expected_weekly_replenishment_cost,
    generate_data, generate_demand, validate_data, write_csv,
)


def test_reproducibility():
    first = generate_data()
    second = generate_data(42)
    for left, right in zip(first, second):
        assert_frame_equal(left, right)
    other = generate_data(43)
    assert not first[0].equals(other[0])
    assert not first[1].equals(other[1])


@pytest.mark.parametrize("seed", [0, 42, 1234])
def test_dimensions_and_validity(seed):
    catalog, demand = generate_data(seed)
    validate_data(catalog, demand)
    assert catalog.shape == (50, 9)
    assert demand.shape == (1500, 3)
    assert catalog.product_id.nunique() == 50
    assert set(catalog.supplier_id) == {"S001", "S002", "S003"}
    assert demand.groupby("product_id").size().eq(30).all()
    assert demand.demand.ge(0).all()
    assert demand.demand.mod(1).eq(0).all()
    assert catalog.selling_price.gt(catalog.unit_cost).all()


def test_demand_independent_of_available_stock():
    catalog, _ = generate_data()
    empty_stock = catalog.copy()
    empty_stock["initial_stock"] = 0
    original = generate_demand(catalog, np.random.default_rng(123))
    changed = generate_demand(empty_stock, np.random.default_rng(123))
    assert_frame_equal(original, changed)
    assert changed.demand.sum() > 0


@pytest.mark.parametrize("column,value", [
    ("supplier_id", "S999"), ("unit_cost", -1), ("selling_price", 1),
    ("holding_cost_per_unit_day", -0.1), ("stockout_penalty_per_unit", -1),
    ("initial_stock", 10.5), ("lead_time_days", 20), ("daily_demand_rate", np.nan),
])
def test_invalid_catalog_rejected(column, value):
    catalog, demand = generate_data()
    catalog[column] = catalog[column].astype(object) if isinstance(value, str) else catalog[column].astype(float)
    catalog.loc[0, column] = value
    with pytest.raises(ValueError):
        validate_data(catalog, demand)


@pytest.mark.parametrize("problem", ["negative", "fractional", "infinite", "missing_row", "duplicate", "unknown_product", "wrong_day"])
def test_invalid_demand_rejected(problem):
    catalog, demand = generate_data()
    if problem == "missing_row":
        demand = demand.iloc[:-1]
    elif problem == "duplicate":
        demand.iloc[0] = demand.iloc[1]
    elif problem == "unknown_product":
        demand.loc[0, "product_id"] = "P999"
    elif problem == "wrong_day":
        demand.loc[0, "day"] = 31
    else:
        demand["demand"] = demand["demand"].astype(float)
        demand.loc[0, "demand"] = {"negative": -1, "fractional": 1.5, "infinite": np.inf}[problem]
    with pytest.raises(ValueError):
        validate_data(catalog, demand)


def test_csv_generation(tmp_path):
    catalog, demand = generate_data()
    paths = write_csv(catalog, demand, tmp_path / "nested")
    assert [path.name for path in paths] == ["product_catalog.csv", "daily_demand.csv"]
    for expected, path in zip((catalog, demand), paths):
        assert_frame_equal(expected, pd.read_csv(path))
    validate_data(*(pd.read_csv(path) for path in paths))
    original_bytes = [path.read_bytes() for path in paths]
    write_csv(*generate_data(42), tmp_path / "nested")
    assert original_bytes == [path.read_bytes() for path in paths]


def test_invalid_export_creates_no_directory(tmp_path):
    catalog, demand = generate_data()
    with pytest.raises(ValueError):
        write_csv(catalog, demand.iloc[:-1], tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize("problem", ["missing_row", "duplicate_id", "missing_column", "inconsistent_lead_time"])
def test_catalog_structure_rejected(problem):
    catalog, demand = generate_data()
    if problem == "missing_row":
        catalog = catalog.iloc[:-1]
    elif problem == "duplicate_id":
        catalog.loc[0, "product_id"] = catalog.loc[1, "product_id"]
    elif problem == "missing_column":
        catalog = catalog.drop(columns="unit_cost")
    else:
        catalog.loc[0, "lead_time_days"] = 2 if catalog.loc[0, "lead_time_days"] != 2 else 3
        catalog.loc[0, "initial_stock"] = np.ceil(catalog.loc[0, "daily_demand_rate"] * (catalog.loc[0, "lead_time_days"] + 2))
    with pytest.raises(ValueError):
        validate_data(catalog, demand)


@pytest.mark.parametrize("seed", [0, 1, 42, 1234])
def test_initial_inventory_uses_exact_coverage_formula(seed):
    catalog, _ = generate_data(seed)
    expected = np.ceil(catalog.daily_demand_rate * (catalog.lead_time_days + 2)).astype(int)
    np.testing.assert_array_equal(catalog.initial_stock, expected)
    coverage = catalog.initial_stock / catalog.daily_demand_rate
    assert (coverage >= catalog.lead_time_days + 2).all()
    assert (coverage < catalog.lead_time_days + 2 + 1 / catalog.daily_demand_rate).all()


def test_incorrect_integer_initial_stock_rejected():
    catalog, demand = generate_data()
    catalog.loc[0, "initial_stock"] += 1
    with pytest.raises(ValueError, match="coverage formula"):
        validate_data(catalog, demand)


@pytest.mark.parametrize("seed", [0, 42, 1234])
def test_calibrated_economic_ranges_and_relationships(seed):
    c, _ = generate_data(seed)
    assert c.daily_demand_rate.between(1, 3.8).all()
    assert c.unit_cost.between(10, 30).all()
    assert c.lead_time_days.between(2, 5).all()
    markup = c.selling_price / c.unit_cost
    assert markup.between(1.1995, 1.8005).all()
    np.testing.assert_allclose(c.holding_cost_per_unit_day, (c.unit_cost * .001).round(4))
    assert (c.stockout_penalty_per_unit >= c.unit_cost * .5 - .005001).all()
    assert (c.stockout_penalty_per_unit <= c.unit_cost * 1.5 + .005001).all()


def test_seed42_weekly_budget_calibration():
    catalog, _ = generate_data(42)
    cost = expected_weekly_replenishment_cost(catalog)
    independent = sum(7 * row.daily_demand_rate * row.unit_cost for row in catalog.itertuples())
    assert cost == pytest.approx(independent)
    assert WEEKLY_BUDGET == 20_000
    # A reference-seed regression check, not a requirement imposed on every seed.
    assert .7 <= cost / WEEKLY_BUDGET <= .9


def test_weekly_cost_is_not_clipped_to_budget_target():
    catalog, _ = generate_data()
    catalog["daily_demand_rate"] = 4.
    catalog["unit_cost"] = 30.
    assert expected_weekly_replenishment_cost(catalog) == 42_000
