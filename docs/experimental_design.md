# Proposed experimental design

**Status: proposed purchasing-strategy evaluation.** The generator, simulator,
historical initialization, Phase 3B forecasting/temporal validation, and Phase 4A
order-up-to replenishment are implemented. A single-scenario demonstration runner
compares that rule with the fixed-order schedule. Optimization, an LLM agent,
a multi-scenario evaluation framework, statistical superiority studies, and a
dashboard are not implemented.
The fixed-order demonstration tests accounting, not strategy superiority.

[Replenishment baseline](replenishment_baseline.md) documents the implemented
expanding-mean rule, lead + seven review + two safety days, and deterministic
budget rationing. The existing seed-42 evaluation path is now used for its
single-scenario inventory comparison, after the forecasting baseline was frozen.
No evaluation observations are used before their decision-time availability.
No policy parameters were tuned against this result. The scenario was previously
inspected in simulator development and is not an independent confirmatory test.

[Demand forecasting](demand_forecasting.md) reports a separate completed
historical-development comparison of expanding, 14-day, and 30-day means.
The three specified seven-day holdouts use only days -59 through 0. Days 1-30
have not been used to select forecasters. That comparison is not a purchasing
strategy evaluation and includes no significance or probabilistic-calibration claim.

## Intended comparisons

The research question is whether tool-using agentic decisions improve outcomes
relative to simpler methods under equal information and operating constraints.

| Proposed method | Purpose | Decisions still needed |
| --- | --- | --- |
| Simple purchasing rules (implemented) | Expanding-mean order-up-to rule | Fixed R=7, safety=2, and proportional remainder budget allocation; sensitivity analysis remains future work |
| Mathematical optimization | Explicit quantitative baseline using forecasts and constraints | Objective, uncertainty treatment, planning horizon, solver |
| LLM-based decision support | Inspect state, request tool outputs, propose orders | Tools, prompts, model, validation, failure handling |

Three initial point-forecast methods are implemented; the expanding mean is a
provisional reference based on historical errors. No solver, LLM provider, or
superiority result is established. If an LLM calls the same optimizer, comparisons must distinguish
reasoning from tool access rather than giving one method better information.

## Fair information and historical demand

All ordinary methods should use the same callback observations: current stock
after receipts, pending orders and arrival dates, known product attributes,
fresh budget, and demand from completed days. Today's demand, future realized
demand, and true scenario rates must not be used. An oracle could be a separately
labeled diagnostic bound, not a deployable baseline.

Fit forecasts on observations strictly before the decision. Use time-ordered
validation, not random shuffling of days. Phase 3A supplies 60 historical days
(-59 through 0) before day 1. Every method must receive this same initial history;
future evaluation observations cannot be training data. The implemented sample
mean used to initialize stock remains fixed by Phase 3A. Phase 3B forecasting
fits only each origin's preceding observations, with no within-holdout updates.
All purchasing methods should use an agreed forecast/tool-information protocol
to distinguish decision quality from unequal forecast access.

The day-8 non-anticipativity test checks that changing demand from day 8 onward
does not change observations at that decision when earlier actions and demand
match. It does not prove that arbitrary callback code avoids future data through
closures, globals, files, or tool responses; these require separate review.

Earlier initial stock used the true rate and revealed a narrow interval of
possible rates. Phase 3A instead initializes stock from the historical sample
mean. Inventory now encodes information already in the common history, not the
true latent parameter. Keep researcher-only truth diagnostics outside policy
inputs and tools. Selection of 60 days and the two-day allowance still warrants
sensitivity analysis, but neither is an optimized or guaranteed service rule.

## Reproducible common scenarios

- Give each method the same catalog, initial stock, and complete demand path per
  scenario. Customer demand must remain independent of the method's sales.
- Use multiple independent seeds and separate tuning from final evaluation.
  Seed 42 was used in calibration/debugging and is not a held-out evaluation.
- Freeze method settings before final comparisons. Record code revision, seeds,
  dependency versions, horizon, budgets, and event timing. Current dependency
  ranges are not a lockfile or a guarantee of cross-version bitwise identity.
- Reset stateful callbacks between runs. For future LLM runs, record model,
  prompt, tools, sampling settings, retries, latency, and usage costs; repeat
  runs when nondeterminism remains.

Common demand reduces comparison noise. Later inventory observations can differ
legitimately because methods made different earlier decisions.

## Proposed metrics and accounting

The engine supplies ledgers; no automated evaluation framework exists yet.

| Metric | Proposed treatment |
| --- | --- |
| Unit fill rate | Total sales divided by total customer demand; define the zero-demand case |
| Unmet units | Sum of demand minus fulfilled sales |
| Stockout frequency | Fraction of product-days with unmet demand; distinguish from closing at zero |
| Purchase expenditure | Quantity times cost on placement, including undelivered orders |
| Holding cost | Sum of closing inventory times daily holding rate |
| Budget utilization | Period spending divided by its allocation |
| Feasibility | Invalid-order attempts, rejected batches, accepted-order compliance |
| Terminal state | Remaining stock and outstanding units/value reported separately |
| Agent overhead | Future model/tool cost, latency, failures, and retries |

Low purchasing expenditure alone does not imply success: buying nothing can
look inexpensive while losing demand. Define a primary objective and any service
constraints before comparisons. If revenue, profit, or service penalties are
introduced, specify accounting once and do not double-count lost margin through
both missing revenue and an additional opportunity-cost term. None of those
totals is computed by the current engine.

The horizon is a confounder: day-29 orders cost money but arrive after day 30.
A horizon-aware method may stop ordering and look cheaper. Predefine whether
evaluation uses current finite-horizon accounting, a longer run, or a future
terminal valuation extension. Never compare methods using inconsistent terminal
rules or credit post-horizon service while excluding related costs.

## Proposed statistical comparisons

Compute paired metric differences within shared scenarios, then report effect
sizes and uncertainty intervals across scenarios. The independent scenario,
not each product-day, should ordinarily be the replication unit: products share
budgets and outcomes within a run are dependent. A paired bootstrap over scenarios
is a candidate; sample size and test choice need an explicit protocol.

Report distributions and failure cases, not just average rankings. Predefine
primary comparisons and address multiple comparisons if many metrics/methods
are tested. No confidence intervals, significance tests, power studies, or
statistically validated purchasing-strategy rankings have been produced so far.
The seed-42 rule/fixed-order simulation comparison is descriptive only. The historical forecast
scores are descriptive rankings only. Full-history EDA includes development
holdouts, so confirmatory claims require subsequent untouched evaluation.

## Weaknesses and future sensitivity checks

Proposed variations include budget tightness, lead times, initial inventory,
demand variability/correlation, sales censoring, and horizon length. Potential
ablations could separate forecasts, optimizer tools, and LLM orchestration using
the same tools. These remain proposals.

Uniform synthetic attributes, independent Poisson demand, three deterministic
suppliers, full demand visibility, a fixed 60-day initialization history, and short
horizons limit external validity. Cost-linked penalties and illustrative holding
rates may affect rankings as much as algorithms. Budget calibration is not
validation against a real business, and adding AI does not remove these concerns.

Related: [overview](project_overview.md), [mathematics](mathematical_model.md),
and [simulation contract](inventory_simulation.md).
