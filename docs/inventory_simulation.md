# Deterministic inventory simulation (Phase 2A)

`adaptive_decision_agent.simulation.simulate` consumes a catalog, complete daily
demand, and either a precommitted order schedule or a purchasing callback. The default horizon is 30
days and budget is USD 20,000 per decision period. Smaller horizons (1-30) and
catalogs are supported for transparent examples and testing. No randomness,
forecasting, optimization, or AI decisions occur in this engine.

## Interface

```python
from adaptive_decision_agent.simulation import simulate

result = simulate(catalog, demand, {1: {"P001": 10}, 8: {"P001": 5}})
daily = result.daily
orders = result.orders
periods = result.periods
```

Omitting both schedule and policy means no purchases. Schedules are supplied
before the run. Alternatively, `simulate(catalog, demand, policy=callback)` calls
`callback(observation)` once at the beginning of each decision day and accepts
its product-to-quantity mapping. Schedule and callback cannot be combined. No
forecasting or optimization policy is provided.

### Policy information boundary

`PolicyObservation` supplies detached snapshots, after today's arrivals but before
today's orders and demand:

- `day`: the current decision day.
- `current_inventory`: on-hand units by product, including receipts due today.
- `outstanding_orders`: previously placed orders still due after today, with
  product ID, quantity, order day, arrival day, and purchase cost.
- `products`: explicitly allowed known catalog fields: product ID, supplier ID
  (when supplied), unit cost, selling price, holding-cost rate, stockout penalty,
  and lead time. Optional fields are omitted if absent from the input catalog.
- `remaining_budget`: a Decimal USD balance for the fresh current period. Since
  there is one batch decision per period, this starts at the full allocation.
- `demand_history`: customer demand for days strictly earlier than the decision
  day, including unmet customer demand, not merely fulfilled sales. It is empty
  on day 1. Full historical demand observability is an explicit MVP assumption;
  real businesses may observe only censored sales.

The engine never passes realized demand for today or later days, latent
`daily_demand_rate`, arbitrary extra catalog columns, or future scheduled orders
to a callback. The complete demand input is validated internally but is not part
of policy observations. Mutating observation tables/dictionaries does not change
engine accounting. This is an API information boundary, not a security sandbox:
callers must not give a policy future data through closures, globals, or external
files. Precomputed schedules also remain the caller's responsibility.

Non-anticipativity tests use two inputs identical through day 7 and different
from day 8 onward: their day-8 inventory, pending receipts, known products,
budget and demand history must match exactly. A separate day-1 divergence check
verifies that current-day realized demand is absent before the first decision.

The catalog requires unique nonempty string `product_id`, nonnegative integer
`initial_stock`, positive whole-cent `unit_cost`, positive integer `lead_time_days`,
and finite nonnegative `holding_cost_per_unit_day`. Product-specific lead times
are taken from the catalog (the generator shares them within suppliers). Demand
must have one nonnegative integer observation for every product/day combination.
Extra/missing days, duplicate pairs, invalid IDs and invalid numeric values fail.
Inputs are not modified. Generated catalogs work directly; the engine deliberately
does not enforce generator-specific ranges or the initial-stock formula.

## Daily timing and equations

Days are numbered 1-30. On each day:

1. Opening stock equals the previous day's closing stock, or initial stock on day 1.
2. Receive orders due that day, before demand; remove them from the pipeline.
3. On days 1, 8, 15, 22, 29 only, place scheduled purchases before demand.
4. Serve that day's exogenous customer demand.
5. Record closing inventory, end-of-day outstanding units, and holding charges.

An order placed on day t with lead time L arrives at the beginning of day t+L.
For example, a day-1 order with L=2 arrives before day-3 demand. No initial
pipeline is assumed. Positive lead times prevent new orders from serving demand
on their placement day. All units of each accepted order arrive together.

For each product/day, in units:

```text
available_stock = opening_stock + arriving_units
sales = min(available_stock, demand)
unmet_demand = demand - sales
closing_stock = available_stock - sales
outstanding_orders = previous_outstanding + ordered_units - arriving_units
```

This is a lost-sales model. Unmet demand disappears after that day; it is not a
backlog and cannot consume future receipts. Demand is never censored by inventory.
`outstanding_orders` denotes end-of-day units on order, not an order count.

## Orders and period budgets

Each schedule key is an integer decision day within the horizon. Its value maps
valid product IDs to nonnegative integral quantities; zero is a no-op. Integral
numeric values such as 2.0 are allowed; fractions, booleans, strings, nonfinite
values, negative quantities and invalid IDs are rejected. One mapping represents
the entire period's decision, so expenditures are summed across all its products.

Validate the entire input and precommitted schedule before running transitions.
For a callback, validate each entire returned order batch before accepting any
of that batch; future batches cannot be validated before they are supplied.
Invalid input or a callback's invalid orders raise `ValueError` and return no
partial result. Callback side effects outside the engine are not rolled back.
Expenditure may equal, but never exceed, USD 20,000. Purchase arithmetic uses
decimal amounts to enforce the budget without binary floating-point boundary
errors. Each decision receives a fresh allocation; unused dollars expire at the
end of days 7, 14, 21, 28, and 30. No borrowing or rollover is allowed. The final
two-day period still receives a full allocation. `weekly_budget` is configurable
for controlled experiments, but its default remains 20,000.

## Costs and returned ledgers

- Purchasing expenditure: quantity times unit purchase cost, charged on placement,
  including orders arriving after day 30. Unit costs are USD/unit, in whole cents.
- Holding cost: closing stock times `holding_cost_per_unit_day`, charged after
  serving daily demand. Rates are USD/unit/day. Preserve rate precision rather
  than rounding each daily charge to cents; returned monetary columns are floats
  for pandas analysis and presentation.
- Initial stock is already funded; its purchase value is not charged again.
- Revenue, lost margin, and stockout penalties are not added to either ledger.
  Unmet units are recorded for later evaluation. The synthetic penalty is an
  additional service cost excluding lost margin; a future profit objective must
  not charge lost margin already represented by absent sales revenue.

`daily` has horizon times product-count rows, in day/catalog order, with day,
product ID, opening stock, arriving units, ordered units, demand, sales, unmet
demand, closing stock, outstanding orders, purchasing expenditure and holding
cost. `orders` records positive accepted orders, their arrival dates, and purchase
costs. `periods` records each allocation, spending and expired unused amount.

At the horizon, remaining stock stays in the final daily ledger and undelivered
orders remain outstanding and in the order ledger. No salvage value, refunds,
terminal holding beyond the horizon, or post-horizon arrivals are applied.
For the seed-42 demonstration ordering ten units per product on every decision
day, all 500 units outstanding at day 30 come from the 50 orders placed on day
29. Their arrival days are 32 and 34 (supplier lead times 3 and 5 days). Their
$10,027 purchase cost is included in day-29 expenditure, not charged again at
arrival. This exact pipeline and purchase-ledger reconciliation are tested.

## Limitations and verification

There are no capacity limits, freight costs, order minimums, substitutions,
cancellations, supplier failures, price changes, storage constraints, or interest.
The engine does not claim a service level or economic optimality. Two extra days
of starting coverage do not cover the entire weekly review interval plus lead
time. Lost sales may occur even under a well-funded schedule.

Tests check hand-calculated transitions and costs, inventory/demand/pipeline
conservation, nonnegative state, no backlogs, arrival timing, late orders, exact
budget boundaries, no rollover, invalid inputs, unchanged inputs, deterministic
results, and the full 1,500-row ledger. Repeated runs with the same catalog,
demand, schedule, horizon, and budget produce the same results. With callbacks,
reproducibility additionally requires a deterministic policy with reset state.
