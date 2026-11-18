# Adaptive Decision Agent: Agentic AI for Inventory Optimization

A research-oriented Python project for studying purchasing under uncertain
demand, delivery delays, and a limited budget. The long-term question is whether
a tool-using LLM can support feasible, effective inventory decisions compared
with simple rules and mathematical optimization.

**Current status:** reproducible synthetic data generation and a deterministic
inventory simulator are implemented, including a preliminary historical sample
mean for initialization. Phase 3B adds expanding/14-day/30-day mean forecasts,
historical EDA, and rolling-origin validation. **No purchasing optimization
algorithm or agentic AI system has been implemented yet.** The name describes
the intended direction, not a demonstrated AI capability.

## Implemented foundation

- 50 products, 3 suppliers, 60 historical days (-59 through 0), and 30 evaluation
  days (1 through 30) of Poisson customer demand on independent random streams.
- Seeded NumPy streams, data validation, and CSV export.
- Demand rates of 1-3.8 units/day, costs of USD 10-30, and lead times of 2-5 days.
- Initial inventory: `ceil(historical_mean_demand * (lead_time + 2))`.
- Business CSVs contain historical estimates, never true latent demand rates.
- Daily lost sales: unfulfilled customer requests disappear rather than becoming a backlog.
- Order pipelines and separate purchasing and inventory holding-cost ledgers.
- External schedules or callbacks with decision-time observations, checked by
  non-anticipativity tests that exclude current/future demand from policy inputs.
- Observed-history point forecasts at configurable horizons, including weekly
  totals, validated on three historical seven-day holdouts. Optional Poisson
  candidate scores are kept separate from point errors.

The budget is USD 20,000 on days 1, 8, 15, 22, and 29; unused funds expire each
period. Seed 42 has a historical weekly replacement estimate of **USD 17,601.28
(88.01%)**; the research-only true-rate expectation remains USD 17,390.72 (86.95%).
This calibration is not a profitability or service guarantee, and the
starting-stock rule is illustrative rather than optimized.

## Architecture

```text
Synthetic catalog + demand [implemented]
             |
             v
Daily simulator <--- external schedule / callback [implemented]
             |
             v
Inventory, order, and cost ledgers [implemented]

Historical demand -> point forecasts + temporal validation [implemented]
Future: forecasts -> purchasing rules / optimizer / LLM tools
        -> common simulator -> repeated policy evaluation -> dashboard
```

Source lives in `src/adaptive_decision_agent/`. The `data/` and `simulation/`
packages and `forecasting/` contain implementations; `optimization/`, `agents/`,
and `evaluation/` remain placeholders. Tests live in `tests/`. Generated CSVs in
`data/raw/` are Git-ignored.

## Installation and testing

Requires Python 3.11 or newer. From the project root in an isolated environment:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m adaptive_decision_agent.data.synthetic --seed 42 --output-dir data/raw
```

Runtime dependencies are NumPy and pandas; pytest is the optional development
dependency. No API key is required. For the established Windows Conda environment,
invoke its interpreter directly without changing `base` or creating another environment:

```powershell
& 'C:\Anaconda3\envs\adaptive-agent\python.exe' -m pytest -q
& 'C:\Anaconda3\envs\adaptive-agent\python.exe' -m adaptive_decision_agent.data.synthetic --seed 42 --output-dir data/raw
```

The Phase 3B verification run passes **127 tests** covering data validity,
accounting, timing, budgets, reproducibility, and policy information boundaries.
Forecasting tests also cover exact means, horizon aggregation, temporal splits,
fixed-origin non-anticipativity, and metric definitions. Matplotlib is available
through the optional `analysis` extra for reproducible plots; core forecasting
does not depend on it.
The expanding mean is the accepted provisional forecasting baseline based on
historical validation; statistical superiority is not claimed. Full-history
EDA is descriptive and does not tune individual validation-fold models.
The fixed-order demonstration is a correctness example, not an optimization benchmark.

## Documentation

| Guide | Purpose |
| --- | --- |
| [Project overview](docs/project_overview.md) | Motivation, architecture, completed and planned work |
| [Mathematical model](docs/mathematical_model.md) | Equations, units, numerical examples, and assumptions |
| [Synthetic data](docs/synthetic_data.md) | Generation, calibration, and reproducibility |
| [Inventory simulation](docs/inventory_simulation.md) | Timing, API, accounting, and verified demonstration |
| [Demand forecasting](docs/demand_forecasting.md) | Historical-only EDA, point forecasts, validation, and limitations |
| [Experimental design](docs/experimental_design.md) | Proposed fair comparisons and statistical evaluation |
| [Development log](docs/development_log.md) | Milestones and design decisions grounded in Git history |

## Roadmap

- [x] Modular packaging and isolated Python environment.
- [x] Reproducible generator, economic audit, and recalibration.
- [x] Deterministic simulator and policy information boundary.
- [x] Historical demand, sample-mean initialization, and validated prehistory inputs.
- [ ] Define final evaluation objectives, metrics, and terminal accounting.
- [x] Implement initial mean-based forecasts and historical rolling-origin validation.
- [ ] Implement simple purchasing rules and mathematical optimization.
- [ ] Implement an LLM-based tool-using decision-support system.
- [ ] Compare strategies across common scenarios with uncertainty estimates.
- [ ] Build a Streamlit dashboard and publish findings and limitations.

Synthetic experiments will not establish real-world performance or an advantage
for agentic AI without further evidence.
