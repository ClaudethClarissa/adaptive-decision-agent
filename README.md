# Adaptive Decision Agent: Agentic AI for Inventory Optimization

An incremental research and portfolio project exploring how a tool-using AI agent
can support inventory purchasing decisions under uncertainty and budget constraints.

**Current status:** Phase 1 synthetic data generation is implemented. See
[synthetic data documentation](docs/synthetic_data.md) for ranges, assumptions,
validation, and the seed-42 generation command. Optimization,
forecasting, decision agents, evaluation runners, and the dashboard remain future work.
Phase 2A adds a deterministic lost-sales inventory engine with external order
schedules or policy callbacks receiving only decision-time information; see
[simulation timing and accounting](docs/inventory_simulation.md).

## Scientific motivation

Inventory management combines uncertain future demand, delayed replenishment,
limited purchasing capital, and competing costs. Buying too much ties up budget
and increases holding costs; buying too little creates stockouts and penalties.
This makes inventory planning a useful setting for studying sequential decisions
and evaluating whether agentic AI adds measurable value.

The research question is whether an LLM-based agent, using explicit forecasting
and optimization tools, can make feasible purchasing decisions that perform
competitively with traditional baselines. Agent performance will be measured
experimentally rather than assumed. Quantitative outcomes, reproducibility, tool
use, and decision traceability will be central to the project.

## Objectives

- Generate reproducible synthetic inventory, supplier, and demand data.
- Model inventory evolution, replenishment delays, and operational costs.
- Establish traditional purchasing and optimization baselines.
- Forecast demand using statistical methods and quantify forecast error.
- Build a decision agent that calls tools and produces auditable recommendations.
- Compare strategies through controlled, repeatable experiments.
- Present results and decision traces in a Streamlit dashboard.

## Initial experimental scope

| Parameter | Planned initial setting |
| --- | --- |
| Products | 50 |
| Suppliers | 3 |
| Purchasing budget | $20,000 per decision period |
| Demand | Independent Poisson demand; product rates uniform 1-3.8 units/day |
| Unit purchase costs | Uniform $10-$30 |
| Replenishment | Supplier lead times of 2-5 days |
| Initial inventory | ceil(demand rate * (lead time + 2 safety-coverage days)) |
| Costs | Purchasing costs, inventory holding costs, and stockout penalties |
| Simulation horizon | 30 days |
| Purchasing frequency | Weekly |

The generator calibrates population-average weekly replacement purchasing to
approximately $16,800 (84% of the $20,000 budget), without rescaling samples or
clipping demand. Individual seeds and realized weeks can differ. Initial stock
covers expected lead-time demand plus two days; this is an illustrative starting
rule, not an optimized reorder policy or a guaranteed service level. It does not
cover a full weekly review period plus lead time. Budget headroom alone does not
establish profitability or stockout-free operation.

Before simulation implementation, the environment specification will define
purchase quantities and the treatment of unmet demand. It will also
define event ordering, decision days, budget reset rules, and how outstanding
orders and remaining stock are treated at the horizon. These choices will be
documented so strategy comparisons share the same operational assumptions.

## Proposed methodology

1. **Reproducible data:** use explicit random seeds and recorded configuration
   to generate product attributes, supplier characteristics, and demand paths.
2. **Simulation:** track daily inventory, incoming orders, fulfilled demand,
   unmet demand, and costs. Expose only information available at decision time.
3. **Baselines:** establish a simple purchasing policy and a traditional
   budget-constrained optimization baseline before introducing an agent.
4. **Forecasting:** fit statistical demand models using historical observations
   only. Use time-ordered validation to avoid future-data leakage.
5. **Agent:** provide bounded tools for inspecting inventory, obtaining forecasts,
   and evaluating purchases. Validate proposed orders against operational
   constraints before execution, and record tool calls and decision rationale.
6. **Evaluation:** compare strategies on shared demand scenarios and random seeds,
   repeat experiments across seeds, and report uncertainty in performance
   differences. Keep tuning scenarios separate from final evaluation scenarios.
7. **Systematic improvement:** examine failure cases and run ablations to test
   the contribution of forecasts, optimization tools, and agent decisions.

Planned metrics include total cost with its purchasing, holding, and stockout
components; demand fill rate; stockout frequency; budget utilization; and
constraint violations. Agent evaluation will additionally track tool failures,
latency, and model usage cost. Metric definitions and terminal inventory
accounting will be fixed before comparing strategies.
The synthetic stockout penalty represents an additional service cost and excludes
lost margin. A future profit objective must not also charge lost margin already
reflected in unrealized sales revenue.

## Project structure

```text
adaptive-decision-agent/
|-- pyproject.toml
|-- README.md
|-- .gitignore
|-- src/
|   `-- adaptive_decision_agent/
|       |-- __init__.py
|       |-- data/          # Synthetic dataset generation
|       |-- simulation/    # Inventory state and environment
|       |-- optimization/  # Traditional purchasing baselines
|       |-- forecasting/   # Statistical demand forecasts
|       |-- agents/        # Tool-using decision agent
|       `-- evaluation/    # Strategy comparisons and metrics
|-- tests/
|-- data/
|   |-- README.md
|   |-- raw/
|   `-- processed/
`-- docs/
    `-- README.md
```

The data package contains the synthetic generator, with tests in `tests/`.
The simulation package provides deterministic daily accounting with external
orders. Other source subpackages contain only package markers. The dashboard
will be added in a later phase.

## Local setup

Requires Python 3.11 or newer. From the project root:

```bash
python -m venv .venv
```

Activate the environment on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Or on macOS/Linux:

```bash
source .venv/bin/activate
```

Install the package and optional development tools:

```bash
python -m pip install -e ".[dev]"
```

NumPy and pandas support synthetic data generation and CSV export. Setuptools
provides packaging, and pytest is the sole optional development dependency.
Other dependencies will be added when their components are implemented.

Run tests with `python -m pytest`. Generate example data with
`python -m adaptive_decision_agent.data.synthetic --seed 42`.
Setup does not require an API key. When using Conda, use the dedicated
`adaptive-agent` environment instead of creating an additional virtual environment.

## Development roadmap

- [x] Create modular packaging, directory structure, and initial documentation.
- [ ] Specify environment assumptions, data schemas, and evaluation metrics.
- [x] Implement and validate a seeded synthetic dataset generator.
- [x] Implement deterministic inventory simulation and test state and cost accounting.
- [ ] Establish simple purchasing and traditional optimization baselines.
- [ ] Implement statistical demand forecasts and time-ordered validation.
- [ ] Add an LLM decision agent with tool calling and order validation.
- [ ] Automate repeated strategy comparisons, uncertainty estimates, and ablations.
- [ ] Build a Streamlit dashboard for scenarios, results, and decision traces.
- [ ] Publish reproducible findings, limitations, and portfolio documentation.

Future experiments should record configuration, seeds, package versions,
strategy settings, and model identifiers where applicable. Synthetic results
will support controlled comparisons, with limitations documented before drawing
conclusions about real inventory operations.
