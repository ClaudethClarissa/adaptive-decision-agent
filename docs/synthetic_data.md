# Synthetic inventory data

Phase 1 provides an illustrative business calibrated for weekly purchasing
headroom, not a fitted model or proof of profitability for a real business.
The generator lives in `adaptive_decision_agent.data.synthetic`. It creates a
50-product catalog and 1,500 daily customer-demand observations (30 days per
product). No simulation, purchasing decisions, forecasting, or sales are modeled.

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
| `initial_stock` | ceil(rate * (lead time + 2)), 4-28 units |
| `lead_time_days` | Discrete uniform 2-5 days, drawn once per supplier and shared by its products |
| `daily_demand_rate` | Uniform 1-3.8 units/day (approximately 1-4), rounded to three decimals |

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

For each product, use the stored, rounded demand rate and supplier lead time:

`initial_stock_i = ceil(daily_demand_rate_i * (lead_time_days_i + 2))`.

The safety-coverage allowance is exactly two days for every product. Stock is
deterministic given these parameters and consumes no extra random draw. Ceiling
rounding adds less than one unit, so coverage satisfies
`L_i + 2 <= I_i / lambda_i < L_i + 2 + 1 / lambda_i`.
Validation and automated tests enforce the exact formula, not just a range.

This is an illustrative initial-stock rule, not an optimized reorder policy or
a guaranteed service level. It covers expected lead-time demand plus two days,
not a weekly review period plus lead time. Poisson variation can still exhaust
stock before the first arrival. No incoming orders at initialization are
generated. Weekly ordering and event timing require later simulation validation.

## Budget calibration

The weekly purchasing budget remains $20,000. The steady-state expected cost to
replace seven days of demand is `sum_i(7 * lambda_i * unit_cost_i)`, exposed as
`expected_weekly_replenishment_cost(catalog)`. This uses product-specific values;
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

For the revised seed-42 data:

| Diagnostic | Value |
| --- | --- |
| Mean expected demand per product/day | 2.5146 units |
| Mean unit purchase cost | $20.054 |
| Expected weekly replacement cost | $17,390.72 |
| Weekly budget utilization | 86.95% |
| Initial inventory | 824 units |
| Mean coverage (minimum-maximum) | 6.5493 days (5.0575-7.5330) |
| Products with coverage below lead time | 0 |

Supplier lead times are 3, 5, and 5 days. In the generated demand realization,
P015 has two units of demand beyond initial stock over its first five days.
This assumes five full demand days before its first possible receipt; it is a
cumulative-demand diagnostic, not a simulation result. With no replenishment,
27 products exceed starting stock during the first seven days. Budget headroom
and initial expected coverage do not establish service performance, cash-flow
feasibility, or profitability. Later tests must consider weekly order timing,
stochastic demand, and whether purchases arrive before they are needed.

## Statistical assumptions

For product i and day t, customer demand D(i,t) follows Poisson(lambda_i).
Conditional on the fixed product rates, draws are independent across products
and days. The conditional mean and variance both equal lambda_i. Rates remain
constant throughout days 1–30. Pooling products with different rates need not
produce equal aggregate mean and variance.

Demand uses only product IDs and demand rates. It is never capped by initial
stock or linked to availability, orders, or replenishment. Thus it represents
latent customer demand rather than observed sales. Poisson demand is an
unbounded nonnegative integer variable: there is deliberately no artificial
maximum or clipping, even though expected demand is bounded by 1-3.8 units/day.

There is no seasonality, trend, substitution, promotion, correlated demand shock,
or overdispersion within a product. Lead times are deterministic for each
supplier. Attributes are mostly independent except the explicitly cost-linked
prices/charges, shared supplier lead times, and the rate/lead-time-based initial
inventory rule. These simplifying assumptions
limit realism and must not be taken as evidence of real operational performance.

## Reproducibility and usage

The default seed is 42. NumPy `SeedSequence(seed).spawn(2)` creates separate
catalog and demand streams, each consumed through `numpy.random.default_rng`.
Repeat runs with the same seed, code, and dependency versions reproduce values.
The recalibration changes seed-42 values relative to the earlier generator;
reproducibility is within the same code revision and dependency versions.
Cross-version or future code-change bitwise reproducibility is not guaranteed;
record Python, NumPy, and pandas versions with experimental results.

From the project root in Windows PowerShell:

```powershell
& 'C:\Anaconda3\envs\adaptive-agent\python.exe' -m adaptive_decision_agent.data.synthetic --seed 42 --output-dir data/raw
```

This writes `product_catalog.csv` and `daily_demand.csv` without a DataFrame
index. Existing files with those names are replaced. Generated files in
`data/raw/` are ignored by Git. `--output-dir` and `--seed` are configurable.
The demand CSV has `day` (1–30), `product_id`, and `demand` columns, ordered by
day and then catalog product order. No calendar dates are assumed.

The Python API exposes `generate_data(seed=42)`, `validate_data(catalog, demand)`,
and `write_csv(catalog, demand, output_dir)`. Validation checks exact schemas
and dimensions, complete unique day/product coverage, finite numeric values,
integer counts, valid suppliers, consistent lead times, and cost/rate ranges
including cost-relative relationships and exact initial inventory. Invalid data raises `ValueError` before
CSV output begins. Tests cover seeds, invalid inputs, stock-independent demand,
CSV round trips, economic ranges, coverage formula, and reference-seed budget
calibration. Statistical fit is an assumption of the sampler rather
than a claim that any single 30-day realization has an exact Poisson mean.
