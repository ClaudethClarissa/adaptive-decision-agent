# Rule-based replenishment baseline (Phase 4A)

## Purpose and scope

The baseline supplies a transparent operational strategy for later comparison
with mathematical optimization and an agentic AI system. It is an order-up-to
rule: periodically order enough to raise the inventory position toward a target.
The rule and its budget allocation are heuristics, not a mathematical optimum.
The order-up-to rule is the accepted initial purchasing-policy benchmark, with
no claim of optimality or statistical superiority.
No purchasing optimizer or AI agent is implemented.

`OrderUpToPolicy` in [replenishment.py](../src/adaptive_decision_agent/policies/replenishment.py)
uses the existing [forecasting interface](demand_forecasting.md) and controlled
[simulator callback](inventory_simulation.md). It imports no generator internals
and reads no files. The separate demonstration runner loads the approved dataset
and records the evaluation; only simulator observations reach the policy.

## Forecast, inventory position, and protection period

At decision day $t$, the expanding mean uses all customer-demand observations
available strictly before $t$, including the original 60 historical days. Let
$\hat{\lambda}_{i,t}$ be that estimate in units/day. The policy recomputes it
through `MeanForecaster(window_days=None)` rather than reusing the catalog's
initial estimate or reading a true rate. At the five decisions it uses 60, 67,
74, 81, and 88 observations per product respectively. No current-day or future
realized demand enters a decision.

Let $L_i$ be lead time in days, $R=7$ days the review interval (time between
purchasing decisions), and $s=2$ days an extra safety-coverage allowance:

$$
S_{i,t}=\left\lceil\hat{\lambda}_{i,t}(L_i+R+s)\right\rceil.
$$

The target $S_{i,t}$ is an integer inventory position in units. The protection
period $L_i+R+s$ accounts for delivery delay, time until the next review, and
the additional allowance. For estimated demand 2.5 units/day and lead time
three days, the protection period is twelve days and the target is thirty units.
The two-day allowance is not a calibrated service probability or optimized
safety stock. No Poisson distribution is needed to calculate this point target.

Inventory position combines currently usable stock $I_{i,t}$ and outstanding
ordered units $O_{i,t}$:

$$
\mathrm{IP}_{i,t}=I_{i,t}+O_{i,t},\qquad
q^{\mathrm{desired}}_{i,t}=\max(0,S_{i,t}-I_{i,t}-O_{i,t}).
$$

There is no backlog term because the simulator uses lost sales. The callback
already includes today's receipts in usable inventory and excludes them from
pending orders. With five available units and seven outstanding, a target of
thirty gives a desired purchase of eighteen units. Excess stock or orders can
make the desired quantity zero; negative orders and cancellations are not used.

The implementation reconstructs the expanding mean's exact rational value using
its known observation-count denominator when applying the ceiling. This avoids
binary floating-point overshoot at whole-unit targets, without using latent
rates or changing the forecaster. All action quantities are integers.

## Budget allocation

Each decision receives a fresh USD 20,000 allocation through
`observation.remaining_budget`; unused money expires. The policy uses the
observed remaining amount, so smaller-budget experiments use the same rule.
Let $c_i$ be purchase cost in USD/unit, $B$ the available USD budget, and
$C=\sum_i c_iq^{\mathrm{desired}}_i$ total desired purchase cost.

If $C\le B$, order every desired unit. If desired cost is zero, no purchases
are necessary. Otherwise define the proportional scaling factor and initial
integer allocation:

$$
\alpha=\frac{B}{C},\qquad
x_i=\alpha q^{\mathrm{desired}}_i,\qquad
a_i=\lfloor x_i\rfloor,\qquad r_i=x_i-\lfloor x_i\rfloor.
$$

For an over-budget decision, $0\le\alpha<1$. Allocation then follows:

1. Calculate the remaining budget after purchasing the floored quantities.
2. Rank products by descending fractional remainder $r_i$, then ascending
   product ID (lexicographic ordering) for ties.
3. In that order, add one unit if it is affordable and the product remains below
   its desired quantity. Skip products that cannot receive another unit.
4. Repeat the same ranking until no remaining desired unit is affordable.

Ranking is fixed from the original scaled quantities, not recalculated after
each award. Repeated passes can give a cheap product more than one extra unit;
the final allocation need not stay within the floor/ceiling of its initial
scaled quantity. It must remain between zero and the desired quantity.

For desired quantities A=3 and B=3 at costs USD 10 and USD 20, a USD 50 budget
scales both by 50/90. Flooring gives one of each and leaves USD 20. Remainders
tie, so A receives one unit first. B is then unaffordable; the next pass awards
another A. Final quantities A=3, B=1 cost exactly USD 50.

All comparisons use integer cents, and remainder ranking uses exact integer
numerators rather than floating comparisons. This ensures deterministic results
independent of input dictionary order and avoids cent-level budget violations.
Zero budget returns zero units. Positive unit costs are required. Unspent money
can remain if no desired unit is affordable. The procedure does not use margins,
stockout penalties, marginal service value, or an objective function: filling
affordable space in a budget is not the same as maximizing economic performance.

## Integration and audit trail

```python
from adaptive_decision_agent.policies import OrderUpToPolicy
from adaptive_decision_agent.simulation import simulate

result = simulate(
    catalog, evaluation_demand,
    policy=OrderUpToPolicy(), historical_demand=historical_demand,
)
```

The stateless policy is called only on days 1, 8, 15, 22, and 29 and uses the
same simulator order validation as other external policies. `policy.plan(obs)`
returns per-product forecasts, targets, current/pending units, desired and
allocated quantities, unit costs, and corresponding monetary amounts for review.
Calling `policy(obs)` returns only the product-to-integer-quantity mapping.

Pending orders are summed by product, regardless of how many orders are open.
Their arrival dates are available to the callback; this simple rule uses total
pending units, not a time-phased future inventory calculation. In the current
dataset, supplier lead times are shorter than the seven-day review interval, so
orders from the previous decision have arrived by the next decision. Tests
still verify outstanding-order deductions for observations containing a pipeline.

The simulator's transition equations and generator are unchanged. Purchases
are charged on placement, holding costs on closing inventory, and unfulfilled
demand is lost. Neither revenue nor stockout penalties are added to these costs;
no duplicated lost-margin accounting is introduced.

## Seed-42 simulation comparison

Both runs use the existing Phase 3A business catalog, the same 60 historical days,
the same 30 evaluation days, and the same simulator timing and USD 20,000 period
allocations. The expanding forecast and fixed parameters were specified before
this run. The reference schedule buys ten units of every product on each
decision day; it is a testing demonstration, not an optimized competitor.

| Simulation quantity | Order-up-to baseline | Fixed ten-unit schedule |
| --- | --- | --- |
| Total customer demand | 3,849 units | 3,849 units |
| Fulfilled sales | 3,764 units | 2,699 units |
| Unmet demand | 85 units | 1,150 units |
| Unit fill rate | 97.79% | 70.12% |
| Purchasing expenditure | USD 87,707.55 | USD 50,135.00 |
| Holding cost | USD 398.3510 | USD 170.0254 |
| Ending on-hand inventory | 597 units | 128 units |
| Outstanding units after day 30 | 869 units | 500 units |

The baseline fulfills 1,065 additional units, a 27.67 percentage-point fill-rate
increase, while spending USD 37,572.55 more on purchases and incurring higher
holding costs. These are deterministic outcomes for one common scenario, not
statistical evidence of superiority, profitability, or optimality.

| Decision day | Desired / purchased units | Desired / actual purchase cost | Unused allocation | Fixed-schedule units / cost |
| --- | --- | --- | --- | --- |
| 1 | 883 / 883 | USD 17,565.27 | USD 2,434.73 | 500 / USD 10,027.00 |
| 8 | 892 / 892 | USD 17,847.82 | USD 2,152.18 | 500 / USD 10,027.00 |
| 15 | 926 / 926 | USD 18,320.49 | USD 1,679.51 | 500 / USD 10,027.00 |
| 22 | 833 / 833 | USD 16,666.02 | USD 3,333.98 | 500 / USD 10,027.00 |
| 29 | 869 / 869 | USD 17,307.95 | USD 2,692.05 | 500 / USD 10,027.00 |

No decision binds the budget in this run, so proportional rationing does not
explain these outcomes. Hand-calculated cases, varied-price constraint checks,
and a smaller-budget simulator test verify that part of the implementation.
The full 250-row decision trace records quantities and costs for every product
at every decision date, including zero allocations.

All 869 terminal outstanding units are day-29 orders, arriving after the horizon.
They have already cost USD 17,307.95 but contribute no within-horizon sales.
The rule deliberately retains its normal protection period near the horizon;
it does not use horizon-aware stopping. The fixed schedule also pays for its
day-29 orders. No salvage or terminal pipeline valuation is applied, limiting
interpretation of purchase-cost comparisons. Initial stock is already funded.

### Terminal economic value and profitability

Ending on-hand inventory and paid-for outstanding orders retain potential
economic value: remaining stock can serve later customers, and pending orders
represent purchased units awaiting delivery. They are not worthless merely
because the reporting horizon ends. Outstanding units cannot fulfill sales
before delivery; all 869 baseline pending units arrive on day 32 (281 units)
or day 34 (588 units), outside this run.

For transparency, ending on-hand stock valued at its unit purchase costs is
USD 11,763.29 for the baseline and USD 2,876.28 for the fixed schedule. Paid
pending orders have purchase costs USD 17,307.95 and USD 10,027.00 respectively.
These are purchase-cost reference amounts, not measured resale/salvage values
or guaranteed future earnings. The simulator reports these units but does not
apply a terminal asset credit or estimate their realized future value.

Purchasing expenditure is a cash outflow on order placement, not the cost of
only the goods sold during the horizon. Comparing expenditure alone therefore
does not compare profitability, particularly when ending assets differ.
A defensible future profitability comparison needs consistent revenue,
goods-consumption and terminal-asset accounting, holding/service costs, and
any post-horizon treatment. That accounting is not implemented here, and no
profitability ranking is inferred. Lost margin must not be counted both through
absent revenue and an additional duplicate penalty.

## Reproduction and verification

From the project root:

```powershell
& 'C:\Anaconda3\envs\adaptive-agent\python.exe' -m adaptive_decision_agent.policies.demo --data-dir data/raw --output-dir outputs/replenishment_baseline
& 'C:\Anaconda3\envs\adaptive-agent\python.exe' -m pytest -q
```

The runner reads the three existing CSVs without rewriting them. It exports
`comparison_summary.csv`, `baseline_decision_summary.csv`, the full
`baseline_decision_details.csv`, and both policies' daily, order, and period
ledgers into the Git-ignored output directory. No new dependency is needed.
The current complete suite has 158 passing tests. New checks cover targets,
preliminary quantities, exact ceilings, forecast use, pipeline accounting,
budget allocation, deterministic ties, binding-budget integration, and causal
decisions under changed current/future demand.

## Limitations

The expanding mean can lag changes in demand. Two extra days do not guarantee a
service level. Initial-estimate errors can cause early shortages before new
orders arrive. The rule treats all pending units as usable inventory position
without checking whether their timing covers imminent demand. Proportional
allocation ignores economic priorities and can favor cheaper products in the
remainder stage. All examples use fully observable customer demand, not censored
sales. A single previously inspected scenario cannot support confirmatory claims;
future comparisons need frozen rules, additional scenarios, uncertainty analysis,
and a consistent treatment of terminal stock and orders.
