# Development log

This log distinguishes Git evidence from local environment work and iterative
development discussions. Git recorded three commits through Phase 2A, not a separate commit for every
audit or intermediate change. Dates are recorded author timestamps, with their
offsets; they are not inferred dates for all activities within each phase.

| Commit | Recorded author timestamp | Subject |
| --- | --- | --- |
| `1680622` | 2026-11-14T22:38:36-06:00 | Initial project structure and Python environment setup |
| `9612cd9` | 2026-11-16T14:36:52-06:00 | Implement and calibrate synthetic inventory data generation |
| `e87148d` | 2026-11-16T15:36:48-06:00 | Implement deterministic inventory simulation engine |

## Initial setup and Python environment

Setup created the `src` package, reserved module directories, tests, data/docs
directories, packaging configuration, and ignore rules. Dependencies were added
only as needed rather than introducing a large framework.

Initial PATH-based Python checks reached Windows execution aliases. The existing
Anaconda installation was then found at `C:\Anaconda3`, with Python 3.10.16.
A dedicated Python 3.11 Conda environment named `adaptive-agent` preserved base
and other environments. Editable installation and pytest supported development.
This sequence is a development record, not a committed provisioning script;
environment binaries and credentials are not repository contents.

The current documentation verification environment reports Python 3.11.18,
NumPy 2.4.6, and pandas 3.1.1. These are observed versions, not exact versions
pinned in `pyproject.toml`. There is no committed environment lockfile.

## Phase 1: synthetic generator and economic audit

The generator added product attributes, Poisson customer demand, separate seeded
catalog/demand streams, validation, CSV export, and tests. Demand was deliberately
independent of inventory so all strategies could face the same customer requests.

An audit of an earlier local configuration found structural scarcity. It used
rates 2-20 units/day, costs USD 5-100, lead times 2-7 days, and independently drawn
starting stock of 10-150 units. Replacement purchasing needs far exceeded the
weekly budget, while some products could not survive the initial lead time.
That would primarily test scarcity allocation rather than ordinary replenishment.

Recalibration retained 50 products, 3 suppliers, 30 days, Poisson demand, and the
USD 20,000 weekly budget. Rates became 1-3.8, costs USD 10-30, and lead times
2-5 days. Starting stock became `ceil(rate * (lead_time + 2))`, deterministic
given product parameters. The extra days are an illustrative allowance, not an
optimized policy or service guarantee. Seed-42 expected weekly replacement is
USD 17,390.72 (86.95% of budget); observations are not rescaled to hit the target.

The original generator, audit, and recalibration were local iterations before
`9612cd9`. No separate historical commit preserves the first generator. The
[data guide](synthetic_data.md) explains the calibration and its limitations.

## Phase 2A: simulator

The engine implemented daily conservation, lost sales, deliveries on day t+L,
weekly order validation, expiring allocations, and separate purchase/holding
ledgers. Small hand-calculated examples preceded the full dataset. A fixed
ten-unit-per-product schedule demonstrated accounting without adding optimization.

Purchases are charged on placement, including late orders, with no repeated
purchase charge at receipt. Closing stock determines holding cost. Unmet demand
does not become a backlog. Terminal inventory and orders remain visible without
salvage or post-horizon service credits.

## Policy interface and non-anticipativity

The initial schedule-only interface could not expose state to an adaptive policy.
Before the Phase 2A commit, a callback and detached `PolicyObservation` snapshots
were added. A known-field allowlist excludes true demand rates and arbitrary
catalog extras; historical demand ends before the decision day.

Tests compare inputs identical through day 7 and different from day 8 onward:
their day-8 observations must match. Other checks cover current-day exclusion,
receipts before decisions, snapshot isolation, shared order validation, and
equivalence between a fixed schedule and mock callback. These were included in
`e87148d`, not a separate policy commit.

## Current verification and next steps

The pre-Phase-3A documentation review verified **79 passing tests**: 36 generator cases and
43 simulator cases after pytest parametrization. These are verified historical
counts, not asserted counts for every intermediate development step.

At that review, full forecasting, optimization, an LLM system, comparative
evaluation, and a dashboard were unimplemented. The initial documentation-only review left source and tests
unchanged; Phase 3A subsequently added historical initialization. The [experimental design](experimental_design.md)
is a proposal, not a report of completed experiments.

## Phase 3A: historical initialization and research documentation

The methodological review identified that true-rate initialization allowed a
policy to infer a narrow rate interval from initial inventory and lead time.
This was latent-parameter information, not access to future realized demand.
The approved correction generates 60 independent historical days, estimates each
rate by its sample mean, and initializes from that estimate with no oracle repair.

Catalog and evaluation streams retain their original child positions; history
uses a new third child. A stored seed-42 evaluation fingerprint verifies exact
preservation of all 1,500 evaluation observations. The public generator now
returns three tables and exports no true rates. Simulator prehistory is optional
for backward-compatible accounting, but should be supplied for Phase 3A policies.

The Phase 3A run passed 97 tests. Seed 42 has 827 initial units (previously 824),
mean estimated rate 2.531 versus true mean 2.5146, and estimated weekly replacement
cost USD 17,601.28 versus unchanged true expectation USD 17,390.72. This milestone
consolidates historical initialization and the research documentation. Use Git
history for its commit identifier rather than embedding a self-referential hash.
Existing documentation drafts,
historical milestones, and explanations are preserved and updated for this phase.

## Phase 3B: historical EDA and initial forecasting

The forecasting package adds expanding, 14-day, and 30-day means, configurable
daily/horizon-total predictions, and three historical rolling-origin folds.
Development reads only the 60-day historical demand CSV, without generator
internals, latent rates, or evaluation observations. Descriptive evidence makes
a stationary Poisson distribution a plausible separately scored candidate, not
an assumed truth. No uncertainty interval or statistical superiority is claimed.

The expanding mean has the lowest pooled daily and weekly MAE/RMSE in the
historical comparison; rankings differ for individual products and one daily
fold. Detailed scores and limitations are in [demand forecasting](demand_forecasting.md).
The current run passes 127 tests. Matplotlib is an optional analysis dependency;
the core forecasters need only existing NumPy/pandas dependencies. The generator
and simulator are unchanged. The expanding mean was accepted as the provisional
baseline without a statistical-superiority claim. Full-history EDA includes
development holdouts but does not tune individual fold models; their fits use
only their corresponding training observations.

## Phase 4A: rule-based replenishment

The new `policies` package combines the accepted expanding-mean forecaster with
an order-up-to target covering lead time, a seven-day review interval, and two
additional days. Current stock and pending orders reduce desired purchases.
Exact-cent proportional rationing with deterministic fractional-remainder
ranking handles an insufficient period budget. It is a heuristic, not an optimizer.

The seed-42 evaluation comparison fulfills 3,764/3,849 units versus 2,699 for
the fixed ten-unit schedule. Costs and terminal inventory are higher, and no
decision binds the normal budget. Lower-budget integration and hand-calculated
allocation tests verify rationing separately. The complete suite passes 158
tests. Generator and simulator accounting are unchanged; no optimization or
AI functionality is added. The rule was accepted as the initial benchmark
without an optimality or superiority claim. Final review reconciled both runs
against identical seed-42 inputs and clarified that unvalued terminal assets
retain potential economic value, so purchase expenditure does not measure profit.
