# Project overview

## Scientific motivation

Can a tool-using LLM support feasible inventory purchasing decisions that compare
favorably with simple rules and traditional optimization, given the same budget,
information, and operating conditions? This is the planned research question.
Historical initialization and three simple mean-based forecasters with temporal
validation and an order-up-to purchasing heuristic are implemented. No mathematical purchasing optimization algorithm or agentic AI
system has been implemented yet.

Inventory is a sequential decision problem: purchases consume money now,
deliveries arrive later, and demand is uncertain. Excess stock creates holding
costs (the cost of carrying inventory); insufficient stock causes lost sales
(requests that cannot be fulfilled and do not remain queued). These competing
effects allow quantitative evaluation rather than judging an AI by its explanation.

For an Applied AI Scientist interview, the current contribution is the research
foundation: reproducible scenarios, explicit economic assumptions, deterministic
accounting, validation, and tests of decision-time information access. It creates
a setting to evaluate agentic reasoning; it does not demonstrate that it helps.

## Completed components

| Component | Implemented responsibilities | Source |
| --- | --- | --- |
| Generator | Catalog, Poisson customer demand, independent random streams, validation, CSV export | [synthetic.py](../src/adaptive_decision_agent/data/synthetic.py) |
| Simulator | Inventory transitions, delayed orders, lost sales, expiring budgets, separate cost ledgers | [engine.py](../src/adaptive_decision_agent/simulation/engine.py) |
| Decision interface | External schedules or callbacks with known information and past demand | Same engine |
| Forecasting | Expanding/14-day/30-day means, horizon totals, EDA, historical validation | [forecasting](../src/adaptive_decision_agent/forecasting/) |
| Replenishment rule | Expanding-mean target position and proportional budget allocation | [policies](../src/adaptive_decision_agent/policies/) |
| Tests | Reproducibility, validity, conservation, timing, invalid inputs, non-anticipativity | [tests](../tests/) |

The generator supplies 50 products, 3 suppliers, 60 historical days (-59 through
0), and 30 evaluation days (1-30). Initial inventory uses the historical sample
mean rather than the true rate. The
simulator is deterministic conditional on inputs and decisions; stochastic
input demand was sampled earlier. The weekly allocation is USD 20,000, and
seed-42 historical replacement estimate is USD 17,601.28; the true-rate research
diagnostic remains USD 17,390.72. This demonstrates
illustrative budget headroom, not profitability or a guaranteed service level.

## Architecture and future responsibilities

1. The generator supplies known product attributes and exogenous customer demand.
   True demand rates are environment parameters, not direct ordinary policy inputs.
2. The simulator exposes inventory, pending orders, known product information,
   remaining budget, the original 60-day history, and evaluation demand from
   completed days to a purchasing callback.
3. The initial forecasters estimate demand from observed history and are compared
   on historical holdouts without future evaluation observations. See
   [forecasting evidence](demand_forecasting.md); point errors do not imply
   probabilistic calibration or effective purchasing decisions.
4. The [replenishment rule](replenishment_baseline.md) converts forecasts and
   inventory position into quantities with budget rationing. A future optimizer
   would replace this heuristic with an explicit mathematical objective.
5. A future LLM system would call defined tools and propose orders through the
   same validation boundary. Accounting remains the simulator's responsibility.
6. A future evaluation runner would compare strategies on common scenarios;
   a future dashboard would present outcomes and decision traces.

Optimization, agents, and evaluation currently contain package markers only.
Forecasting has a separate historical-validation implementation. The ten-unit fixed schedule used in tests is not a competitive
baseline or an optimization algorithm.

## Assumptions and limits

The current model uses independent stationary Poisson demand, fixed supplier
lead times, one supplier per product, synthetic costs, and a short horizon.
It assumes full historical customer-demand observability during stockouts,
which is easier than real sales-only data. Earlier inventory used true rates,
creating an indirect oracle clue. Phase 3A removes that rule: inventory now
reflects an estimate derived from history available to every method. Estimates
remain uncertain; low true-rate coverage is not repaired with oracle knowledge.
Two extra coverage days do not cover a full weekly review interval plus lead
time and do not establish a service probability.

The engine does not calculate revenue, profit, or stockout penalties. Remaining
stock and unreceived orders receive no terminal valuation. The callback boundary
is not a security sandbox: policies must not obtain future data through external
files, globals, or closures. Adding an LLM would not resolve these limitations.

See the [mathematical model](mathematical_model.md), [data calibration](synthetic_data.md),
[simulation contract](inventory_simulation.md), [proposed experiments](experimental_design.md),
and [development log](development_log.md). Calibration, correctness demonstrations,
and future strategy comparisons are deliberately distinguished.
