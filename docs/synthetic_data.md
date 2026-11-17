# Synthetic inventory data

Phase 1 provides an illustrative business calibrated for weekly purchasing
headroom, not a fitted model or proof of profitability for a real business.
The generator lives in `adaptive_decision_agent.data.synthetic`. It creates a
50-product business catalog, 3,000 historical customer-demand observations
(60 per product, days -59 through 0), and 1,500 evaluation observations (days
1-30). Phase 3A adds a historical sample mean for initialization only; no full
forecasting model, simulation, purchasing decisions, or sales are modeled here.
This describes the generator's scope; the separate
[inventory engine](inventory_simulation.md) converts demand into sales and stock
trajectories. See the [mathematical model](mathematical_model.md) for equations
and numerical examples.

## Why the business was recalibrated

An earlier local generator used rates of 2-20 units/day, costs USD 5-100,
lead times 2-7 days, and independent initial stock of 10-150 units. The economic
audit found replacement requirements far above the USD 20,000 weekly budget,
with some products unable to survive until the first possible receipt. This
would primarily test scarcity allocation rather than ordinary replenishment.

The approved ranges below reduce that imbalance and link initial stock to
expected lead-time exposure. Budget headroom is not evidence of profitability
or stockout-free operation. Both configurations were developed before the
generator commit; earlier CSVs are not versioned experiments. See the
[development log](development_log.md) for provenance.

## Catalog and units

All monetary values are illustrative USD. Quantities are whole units and time
is measured in days. Ranges below are inclusive after rounding; continuous
uniform draws use an exclusive upper endpoint before rounding.

| Column | Construction and range |
| --- | --- |
| `product_id` | Unique P001 through P050 |
| `supplier_id` | S001, S002, S003; shuffled assignments with 17, 17, 16 products |
| `unit_cost` | Uniform $10-$30, rounded to cents |
| `selling_price` | Cost times an independent uniform 1.2-1.8 multiplier, rounded to cents; $12-$54 |
| `holding_cost_per_unit_day` | 0.1% of unit cost per day, rounded to four decimals; $0.01-$0.03 |
| `stockout_penalty_per_unit` | Cost times an independent uniform 0.5-1.5 multiplier, rounded to cents; $5-$45 |
| `initial_stock` | ceil(historical sample mean * (lead time + 2)); nonnegative integer, no fixed sampling-range cap |
| `lead_time_days` | Discrete uniform 2-5 days, drawn once per supplier and shared by its products |
| `estimated_demand_rate` | Historical demand sum / 60, units/day; not clipped to the latent sampling range |

The true rate is drawn internally from uniform 1-3.8 units/day, rounded to three
decimals. It is not a business catalog field and is never exported. Conditional
on this rate, history and evaluation are independent Poisson draws. Neither
available inventory nor the historical estimate controls evaluation demand.

Holding costs represent an illustrative daily carrying charge, not a measured
financing rate; 0.1% daily corresponds to 36.5% annually without compounding.
Price multipliers describe markups, not gross margin percentages (the implied
gross margins are approximately 16.7%-44.4%). The stockout penalty is an
additional service/reputation cost per unmet unit, explicitly excluding lost
sales revenue and lost margin. These are assumptions, not measured estimates.

For a future profit objective, count actual sales revenue and applicable costs,
and charge this service penalty for unmet demand. Do not also subtract lost
margin already reflected by unrealized revenue. A cost-only objective may omit
opportunity margin deliberately; if adding it later, define the accounting once
and avoid including it in both the stockout penalty and another cost term.
No objective or cost accounting is implemented in this generator.

## Initial stock rule

For each product, first calculate the 60-day historical sample mean, without
rounding it to a fixed number of decimals:

`estimated_demand_rate_i = historical_demand_total_i / 60`.

Then use `initial_stock_i = ceil(estimated_demand_rate_i * (lead_time_days_i + 2))`.
The implementation uses the equivalent integer ceiling of
`historical_total * (lead_time + 2) / 60` to avoid floating-point errors at exact
integer boundaries. Estimates are rechecked against historical totals when
validating CSV round trips. There is no safety floor, clipping, or true-rate
correction. An all-zero history gives estimate zero and initial stock zero.

The safety-coverage allowance is exactly two days for every product. Stock is
deterministic given these parameters and consumes no extra random draw. Ceiling
rounding adds less than one unit, so coverage satisfies
`L_i + 2 <= I_i / lambda_hat_i < L_i + 2 + 1 / lambda_hat_i`
when the estimate is positive. Estimated coverage is undefined for an estimate
of zero; true-rate coverage remains well-defined because latent rates are positive.
Validation and automated tests enforce the exact formula, not just a range.

This is an illustrative initial-stock rule, not an optimized reorder policy or
a guaranteed service level. It covers expected lead-time demand plus two days,
not a weekly review period plus lead time. Poisson variation can still exhaust
stock before the first arrival. No incoming orders at initialization are
generated. The simulator implements weekly timing; service outcomes still depend
on externally supplied decisions. Knowing this rule and initial stock also
reveals only an interval for the historical estimate, already recoverable from
the shared history. The earlier true-rate rule did reveal oracle information;
that historical issue and its correction are explained in the mathematical model.

## Budget calibration

The weekly purchasing budget remains $20,000. The steady-state expected cost to
replace seven days of demand is `sum_i(7 * lambda_i * unit_cost_i)` for researcher
diagnostics. The business-side function `expected_weekly_replenishment_cost(catalog)`
now uses `estimated_demand_rate` in place of true lambda, so its result is an
estimate rather than oracle expectation. This uses product-specific values;
it is not the product of sample means. It excludes safety-stock builds, freight,
holding costs, service penalties, and ending-stock requirements. Initial stock
is assumed already funded and is not subtracted from recurring replacement.

Independent uniform rates 1-3.8 (mean 2.4) and costs $10-$30 (mean $20) imply
population-average spending of `50 * 7 * 2.4 * 20 = $16,800`, or 84% of budget.
The upper rate of 3.8 leaves headroom relative to an initial 1-4 trial, whose
seed-42 result was 90.66%. This calibration is exploratory; seed 42 is a reference
example, not an independent validation sample. Later evaluations need fresh seeds.
No rejection sampling, per-product rescaling, budget clipping, or demand capping
is used. The 70%-90% range is a calibration aim, not a guarantee for every catalog
or realized week. Validation does not reject catalogs based on total spending.

The following are verified seed-42 **catalog calibration diagnostics**, not
simulation performance or estimated profit:

| Diagnostic | Before Phase 3A | Phase 3A |
| --- | --- | --- |
| Mean true demand rate (research only) | 2.5146 | 2.5146 units/day |
| Mean historical estimate | Not generated | 2.531 units/day |
| Mean unit purchase cost | USD 20.054 | USD 20.054 |
| True expected weekly replacement cost (research only) | USD 17,390.72 | USD 17,390.72 |
| History-estimated weekly replacement cost | Not generated | USD 17,601.28 |
| True expected / estimated budget use | 86.95% / not available | 86.95% / 88.01% |
| Initial inventory | 824 units | 827 units |
| Mean true-rate coverage | 6.55 days | 6.60 days |
| True-rate coverage range | 5.06-7.53 days | 4.57-8.59 days |
| Mean estimate-based coverage | Not applicable | 6.53 days |
| Estimate-based coverage range | Not applicable | 5.02-7.59 days |
| Products with true coverage below lead time | 0 | 0 |

The historical table totals 7,593 units. Across 50 products, estimate minus true
rate has mean error +0.0164, MAE 0.19163, RMSE 0.22535, and range -0.4540 to
+0.46967 units/day. These are one-scenario estimation diagnostics, not confidence
intervals or forecasting benchmark results. `researcher_diagnostics(seed=42)`
returns aggregate truth/error/coverage quantities, never a policy observation
or CSV. It must not be used by a policy or exposed by future tools.

Supplier lead times remain 3, 5, and 5 days. In the **earlier true-initialization** demand diagnostic,
P015 had two units of demand beyond initial stock over its first five days.
This assumes five full demand days before its first possible receipt; it is a
cumulative-demand diagnostic, not a simulation result. With no replenishment,
27 products exceeded starting stock during the first seven days. Budget headroom
and initial expected coverage do not establish service performance, cash-flow
feasibility, or profitability. Future strategy evaluations must consider weekly order timing,
stochastic demand, and whether purchases arrive before they are needed.

## Statistical assumptions

For product i and day t, customer demand D(i,t) follows Poisson(lambda_i).
Conditional on the fixed product rates, draws are independent across products
and days. The conditional mean and variance both equal lambda_i. Rates remain
constant throughout historical days -59 through 0 and evaluation days 1-30.
Pooling products with different rates need not
produce equal aggregate mean and variance.

Demand uses only product IDs and demand rates. It is never capped by initial
stock or linked to availability, orders, or replenishment. Thus it represents
latent customer demand rather than observed sales. Poisson demand is an
unbounded nonnegative integer variable: there is deliberately no artificial
maximum or clipping, even though expected demand is bounded by 1-3.8 units/day.

There is no seasonality, trend, substitution, promotion, correlated demand shock,
or overdispersion within a product. Lead times are deterministic for each
supplier. Attributes are mostly independent except the explicitly cost-linked
prices/charges, shared supplier lead times, and the history/lead-time-based initial
inventory rule. These simplifying assumptions
limit realism and must not be taken as evidence of real operational performance.

## Reproducibility and usage

The default seed is 42. NumPy `SeedSequence(seed).spawn(3)` creates independent
streams consumed through `numpy.random.default_rng`: child 0 for catalog and
latent rates, child 1 for evaluation, and child 2 for history. Keeping children
0 and 1 and the sampler call order unchanged preserves the previous evaluation
path exactly. A regression test verifies the seed-42 CSV-value fingerprint
`f3f851adf126b088ee4b005d0e688177f95ffb1d5eaf3e65c21cbad62f4162cb`
(SHA-256 of UTF-8 CSV text with LF line endings and no index). This checks
all evaluation values and ordering, not merely matching aggregate statistics.
Repeat runs with the same seed, code, and dependency versions reproduce values.
The earlier Phase 1 recalibration changed seed-42 values; Phase 3A preserves
its evaluation observations and all pre-existing supplier/cost/price attributes.
Starting stock changes because it now uses history. CSV bytes may use platform
line endings, so the regression fingerprint normalizes them.
Reproducibility is within the same code revision and dependency versions.
Cross-version or future code-change bitwise reproducibility is not guaranteed;
record Python, NumPy, and pandas versions with experimental results.

From the project root in Windows PowerShell:

```powershell
& 'C:\Anaconda3\envs\adaptive-agent\python.exe' -m adaptive_decision_agent.data.synthetic --seed 42 --output-dir data/raw
```

This writes `product_catalog.csv`, `historical_daily_demand.csv`, and
`daily_demand.csv` (evaluation, existing filename retained) without a DataFrame
index. Existing files with those names are replaced. Generated files in
`data/raw/` are ignored by Git. `--output-dir` and `--seed` are configurable.
Both demand CSVs have `day`, `product_id`, and `demand` columns, ordered by
day and then catalog product order. No calendar dates are assumed.

The Python API now returns `(catalog, history, evaluation)` from
`generate_data(seed=42)`, an intentional change from the old two-table result.
Use `validate_data(catalog, history, evaluation)` and
`write_csv(catalog, history, evaluation, output_dir)`. Low-level latent sampling
helpers are private generator internals, not policy-facing APIs. Validation checks exact schemas
and dimensions, complete unique day/product coverage, finite numeric values,
integer counts, valid suppliers, consistent lead times, and cost/rate ranges
including cost-relative relationships and exact initial inventory. Invalid data
raises `ValueError` before
CSV output begins. Tests cover seeds, invalid inputs, stock-independent demand,
CSV round trips, economic ranges, coverage formula, and reference-seed budget
calibration. Statistical fit is an assumption of the sampler rather
than a claim that any single 30-day realization has an exact Poisson mean.
