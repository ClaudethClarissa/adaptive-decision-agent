"""History-based initialization, separated streams, and business data contracts."""

import hashlib
from fractions import Fraction

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from adaptive_decision_agent.data import synthetic as module
from adaptive_decision_agent.data.synthetic import (
    estimate_demand_rates, expected_weekly_replenishment_cost,
    generate_data, researcher_diagnostics, validate_data, write_csv,
)


def test_reproducibility_and_seed_variation():
    for a, b in zip(generate_data(), generate_data(42)):
        assert_frame_equal(a, b)
    for a, b in zip(generate_data(42), generate_data(43)):
        assert not a.equals(b)


def test_seed42_evaluation_preserved_from_phase2a():
    _, _, evaluation = generate_data(42)
    digest = hashlib.sha256(evaluation.to_csv(index=False, lineterminator="\n").encode()).hexdigest()
    # Captured from the unchanged Phase 2A generator before Phase 3A edits.
    assert digest == "f3f851adf126b088ee4b005d0e688177f95ffb1d5eaf3e65c21cbad62f4162cb"


@pytest.mark.parametrize("seed", [0, 1, 42, 1234])
def test_dimensions_validity_and_exact_initialization(seed):
    c, h, d = generate_data(seed)
    validate_data(c, h, d)
    assert c.shape == (50, 9)
    assert h.shape == (3000, 3)
    assert d.shape == (1500, 3)
    assert set(h.day) == set(range(-59, 1))
    assert set(d.day) == set(range(1, 31))
    assert h.groupby("product_id").size().eq(60).all()
    assert d.groupby("product_id").size().eq(30).all()
    means = h.groupby("product_id").demand.mean().reindex(c.product_id)
    np.testing.assert_allclose(c.estimated_demand_rate, means, rtol=0, atol=0)
    totals = h.groupby("product_id").demand.sum()
    # Fraction is an independent exact-rational reference for ceil.
    expected = [int(np.ceil(Fraction(int(totals[r.product_id]) * (r.lead_time_days + 2), 60)))
                for r in c.itertuples()]
    np.testing.assert_array_equal(c.initial_stock, expected)
    assert c.unit_cost.between(10, 30).all()
    assert c.lead_time_days.between(2, 5).all()
    assert c.selling_price.gt(c.unit_cost).all()
    assert not any("true" in col or "latent" in col or col == "daily_demand_rate" for col in c.columns)


def test_independent_streams_share_latent_rates():
    seeds = np.random.SeedSequence(42).spawn(3)
    params, rates = module._generate_parameters(np.random.default_rng(seeds[0]))
    _, h, d = generate_data(42)
    expected_eval = module._sample_demand(params.product_id, rates, np.random.default_rng(seeds[1]), range(1, 31))
    expected_history = module._sample_demand(params.product_id, rates, np.random.default_rng(seeds[2]), range(-59, 1))
    assert_frame_equal(d, expected_eval)
    assert_frame_equal(h, expected_history)
    assert not np.array_equal(h.demand.to_numpy()[:1500], d.demand.to_numpy())


@pytest.mark.parametrize("historical_count", [0, 100])
def test_initialization_uses_history_without_true_rate_corrections(monkeypatch, historical_count):
    sampler = module._sample_demand
    _, _, original_eval = generate_data()

    def substitute_history(ids, rates, rng, days):
        result = sampler(ids, rates, rng, days)
        if result.day.min() < 1:
            result["demand"] = historical_count
        return result

    monkeypatch.setattr(module, "_sample_demand", substitute_history)
    c, h, d = generate_data()
    assert_frame_equal(original_eval, d)
    assert c.estimated_demand_rate.eq(historical_count).all()
    assert c.initial_stock.eq(historical_count * (c.lead_time_days + 2)).all()
    validate_data(c, h, d)


@pytest.mark.parametrize("column,value", [
    ("supplier_id", "S999"), ("unit_cost", -1), ("selling_price", 1),
    ("holding_cost_per_unit_day", -0.1), ("stockout_penalty_per_unit", -1),
    ("initial_stock", 10.5), ("lead_time_days", 20), ("estimated_demand_rate", np.nan),
])
def test_invalid_catalog_rejected(column, value):
    c, h, d = generate_data()
    c[column] = c[column].astype(object) if isinstance(value, str) else c[column].astype(float)
    c.loc[0, column] = value
    with pytest.raises(ValueError):
        validate_data(c, h, d)


@pytest.mark.parametrize("period", ["history", "evaluation"])
@pytest.mark.parametrize("problem", ["negative", "fractional", "infinite", "missing", "duplicate", "unknown", "wrong_day"])
def test_invalid_demand_rejected(period, problem):
    c, h, d = generate_data()
    frame = h.copy() if period == "history" else d.copy()
    if problem == "missing":
        frame = frame.iloc[:-1]
    elif problem == "duplicate":
        frame.iloc[0] = frame.iloc[1]
    elif problem == "unknown":
        frame.loc[0, "product_id"] = "P999"
    elif problem == "wrong_day":
        frame.loc[0, "day"] = 1 if period == "history" else 0
    else:
        frame["demand"] = frame.demand.astype(float)
        frame.loc[0, "demand"] = {"negative": -1, "fractional": 1.5, "infinite": np.inf}[problem]
    with pytest.raises(ValueError):
        validate_data(c, frame if period == "history" else h, frame if period == "evaluation" else d)


@pytest.mark.parametrize("problem", ["missing_row", "duplicate_id", "missing_column", "stock_formula", "estimate", "latent_column", "supplier_lead"])
def test_catalog_contract_rejected(problem):
    c, h, d = generate_data()
    if problem == "missing_row":
        c = c.iloc[:-1]
    elif problem == "duplicate_id":
        c.loc[0, "product_id"] = c.loc[1, "product_id"]
    elif problem == "missing_column":
        c = c.drop(columns="unit_cost")
    elif problem == "stock_formula":
        c.loc[0, "initial_stock"] += 1
    elif problem == "estimate":
        c.loc[0, "estimated_demand_rate"] += .1
    elif problem == "latent_column":
        c["daily_demand_rate"] = 2.
    else:
        c.loc[0, "lead_time_days"] = 2
        total = int(h[h.product_id == c.loc[0, "product_id"]].demand.sum())
        c.loc[0, "initial_stock"] = (total * 4 + 59) // 60
    with pytest.raises(ValueError):
        validate_data(c, h, d)


def test_csv_generation_and_no_latent_exports(tmp_path):
    data = generate_data()
    paths = write_csv(*data, tmp_path / "nested")
    assert [p.name for p in paths] == ["product_catalog.csv", "historical_daily_demand.csv", "daily_demand.csv"]
    for expected, path in zip(data, paths):
        assert_frame_equal(expected, pd.read_csv(path))
        assert "daily_demand_rate" not in path.read_text()
    validate_data(*(pd.read_csv(p) for p in paths))
    original = [p.read_bytes() for p in paths]
    write_csv(*generate_data(), tmp_path / "nested")
    assert original == [p.read_bytes() for p in paths]


def test_invalid_export_creates_no_directory(tmp_path):
    c, h, d = generate_data()
    with pytest.raises(ValueError):
        write_csv(c, h.iloc[:-1], d, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_estimated_weekly_expenditure_and_research_diagnostics():
    c, h, _ = generate_data()
    independent = sum(7 * r.unit_cost * h[h.product_id == r.product_id].demand.mean() for r in c.itertuples())
    assert expected_weekly_replenishment_cost(c) == pytest.approx(independent)
    assert .7 <= independent / 20000 <= .9
    diagnostic = researcher_diagnostics()
    assert diagnostic["mean_true_rate"] == pytest.approx(2.5146)
    assert diagnostic["true_expected_weekly_cost"] == pytest.approx(17390.72489)
    assert diagnostic["estimated_weekly_cost"] == pytest.approx(independent)
