# Mathematical model implemented so far

This guide explains data generation and accounting. Implemented forecasting
equations and validation are in [demand forecasting](demand_forecasting.md);
no purchasing optimization is implemented. All currency is illustrative USD. Product index $i$ runs
from 1 to 50; day index $t$ runs from 1 to $T=30$. The engine also accepts smaller
catalogs and horizons for tests. Historical day index $s$ runs from -59 through
0; evaluation day index $t$ remains 1-30. Each interval is $\Delta=1$ day.

## Product-specific Poisson demand

Let $\lambda_i$ be expected demand in units/day and $D_{i,t}$ the nonnegative
integer customer-demand count in units for one day. With $\mu_i$ the expected
count over the interval:

$$
\mu_i=\lambda_i\Delta,\qquad
D_{i,t}\mid\lambda_i\sim\operatorname{Poisson}(\mu_i).
$$

For $\lambda_i=2$ units/day, the expected one-day count is two units. Sampling
can produce zero, one, two, or more; it does not round the expectation.
For a nonnegative integer $k$ (units), the probability is

$$
\Pr(D_{i,t}=k\mid\lambda_i)=\frac{e^{-\mu_i}\mu_i^k}{k!}.
$$

Here $e$ is the exponential constant and $k!$ is factorial. For two expected
units, the probability of zero is $e^{-2}\approx0.1353$. The Poisson parameter
is a numeric expected count for the specified interval.

$$
\mathbb{E}[D_{i,t}\mid\lambda_i]=\mu_i,\qquad
\operatorname{Var}(D_{i,t}\mid\lambda_i)=\mu_i.
$$

Mean is measured in units and variance in squared units, although their numeric
values coincide for Poisson counts. With rate two, these are 2 units and 2
squared units; standard deviation is approximately 1.414 units. Rates are
constant and draws independent across days/products conditional on those rates.
Pooling products with different rates need not preserve mean-variance equality.
Seasonality, substitution, and within-product overdispersion are not modeled.

**Software:** stored rates are uniform draws from 1-3.8 rounded to three decimals.
`Generator.poisson` samples independent 60-by-50 historical and 30-by-50 evaluation
arrays using those values. `SeedSequence` children 0, 1, and 2 drive catalog,
evaluation, and history. True rates remain private generator parameters, never
business CSV fields. Demand represents customer
requests independently of available stock. The simulator makes no random draws.

## Starting inventory and coverage

Phase 3A uses the historical observations $D^{\mathrm{hist}}_{i,s}$, the customer
units requested on historical day $s$, for a preliminary rate estimate:

$$
\hat{\lambda}_i=\frac{\sum_{s=-59}^{0}D^{\mathrm{hist}}_{i,s}}{60\text{ days}}.
$$

For 150 requested units over 60 days, the estimate is 2.5 units/day. This sample
mean initializes inventory; it is not a full forecasting module. Under independent
stationary Poisson demand it is unbiased; its standard error at true rate 2.5
is numerically sqrt(2.5/60), about 0.204 units/day. History and evaluation are
independent conditional on the same true rate.

Let $L_i$ be supplier lead time in days, $s_i=2$ days the extra coverage allowance,
and $I_i$ starting on-hand inventory in whole units:

$$
I_i=\left\lceil\hat{\lambda}_i(L_i+s_i)\right\rceil,\qquad s_i=2\text{ days}.
$$

Ceiling rounds upward. At 2.5 units/day and a three-day lead time, the rule gives
13 units: the ceiling of 12.5. The historical estimate and lead time determine stock;
no additional random inventory draw occurs.

Let $\hat{K}_i$ be inventory coverage measured in historical-estimate demand days:

$$
\hat{K}_i=\frac{I_i}{\hat{\lambda}_i},\qquad
L_i+s_i\le\hat{K}_i<L_i+s_i+\frac{1\text{ unit}}{\hat{\lambda}_i}.
$$

Estimated coverage $\hat{K}_i$ is defined for positive estimates; an all-zero
history gives zero stock without an oracle correction. The example covers
13/2.5 = 5.2 estimated-demand days, including 2.2 beyond lead time. Ceiling
adds less than one unit, explaining the upper bound. Coverage is neither a
guaranteed depletion time nor a service-level probability. This rule is not
optimized and does not cover seven review days plus lead time.

Researcher-only true coverage is still $K_i=I_i/\lambda_i$ in days and need not
satisfy this bound. With estimated rate 2.5 but true rate 3, 13 units cover only
4.33 true-demand days. The exact rational ceiling of historical total times
coverage divided by 60 is computed with integer arithmetic to avoid floating
errors at whole-unit boundaries.

Before Phase 3A, true-rate initialization revealed the following interval
(historical explanation, not the current initialization rule):

$$
\frac{I_i-1\text{ unit}}{L_i+2\text{ days}}<\lambda_i
\le\frac{I_i}{L_i+2\text{ days}}.
$$

With 13 units and a three-day lead time the interval is (2.4, 2.6] units/day.
Hiding the rate field alone did not remove this oracle-informed clue. Under
the current rule, the analogous interval constrains only the historical estimate,
which every policy can already recover from common history. Inventory still
conveys reasonable business information, but does not directly encode true lambda.

## Orders, lead times, and outstanding units

Let $q_{i,\tau}$ denote whole units ordered on day $\tau$, and $a_{i,\tau}$ its
arrival day (a day index):

$$
a_{i,\tau}=\tau+L_i.
$$

Four units ordered on day 1 with lead time two arrive before day-3 demand.
Lead times are positive and fixed; deliveries arrive in full. There is no
initial pipeline of incoming orders. Let $R_{i,t}$ be arriving units on day $t$:

$$
R_{i,t}=\sum_{\tau<t}q_{i,\tau}\mathbf{1}\{\tau+L_i=t\}.
$$

The indicator $\mathbf{1}$ is one when its condition holds and zero otherwise.
That example contributes four units on day 3 and zero on days 1 and 2.
Let $P_{i,t}$ be end-of-day outstanding units, with initial value $P_{i,0}=0$:

$$
P_{i,t}=P_{i,t-1}+q_{i,t}-R_{i,t}.
$$

The pipeline is 4, 4, and 0 units on days 1, 2, and 3. Post-horizon orders
remain outstanding, already paid, with arrival dates retained in the order ledger.

## Daily inventory and lost sales

All these quantities are in units: opening stock $O_{i,t}$, available stock
$A_{i,t}$, fulfilled sales $Y_{i,t}$, unmet demand $U_{i,t}$, and closing stock
$C_{i,t}$. Demand $D_{i,t}$ and arrivals $R_{i,t}$ are defined above.

$$
O_{i,1}=I_i,\qquad O_{i,t}=C_{i,t-1}\quad(t>1).
$$

Three starting units mean day-1 opening stock three; closing with one means
day 2 opens with one. Yesterday's unmet demand does not enter opening stock.

$$
A_{i,t}=O_{i,t}+R_{i,t}.
$$

One opening unit plus four arrivals gives five available units. Today's new
orders are not available immediately.

$$
Y_{i,t}=\min(A_{i,t},D_{i,t}),\qquad U_{i,t}=D_{i,t}-Y_{i,t}.
$$

Five available units and demand seven produce sales five and unmet demand two.
These two units are lost permanently, not queued as a backlog. Under the MVP
observability assumption the full seven requested units become historical demand.

$$
C_{i,t}=A_{i,t}-Y_{i,t},\qquad
O_{i,t}+R_{i,t}=Y_{i,t}+C_{i,t}.
$$

The example closes at zero and conserves units: 1 + 4 = 5 + 0. Tests check this
identity and nonnegative state. Spoilage, returns, and substitution are absent.

## Weekly purchasing constraint

Let $\mathcal{T}$ be decision days, $c_i$ purchase cost in USD/unit, and $B_t$
the current allocation in USD:

$$
\mathcal{T}=\{1,8,15,22,29\},\qquad q_{i,t}\in\mathbb{Z}_{\ge0},\qquad
\sum_i c_iq_{i,t}\le B_t=20{,}000\text{ USD}\quad(t\in\mathcal{T}).
$$

Orders are zero on other days. Ten units at USD 20/unit consume USD 200 and
leave USD 19,800. An over-budget batch is rejected in full. Unused allocation
expires; the next period starts with USD 20,000 rather than a cumulative balance.
The two-day final period still receives a full allocation.

**Software:** these are defaults; budgets can be configured for experiments.
One callback occurs per decision period before current-day demand. Decimal
arithmetic enforces whole-cent purchasing limits. Sales revenue does not fund
additional purchases; no cash-flow or borrowing model is implemented.

## Purchasing and holding costs

Let $E_t$ be purchasing expenditure in USD on day $t$:

$$
E_t=\sum_i c_iq_{i,t}.
$$

Four units at USD 10/unit cost USD 40 on placement, with no second purchasing
charge at arrival. Initial stock is already funded. Orders arriving after the
horizon are still charged when placed.

Let $h_i$ be the holding rate in USD/unit/day, $H_{i,t}$ the day's charge in USD,
and $H_{\mathrm{total}}$ total horizon holding cost in USD:

$$
H_{i,t}=h_iC_{i,t}\Delta,\qquad
H_{\mathrm{total}}=\sum_{t=1}^{T}\sum_i H_{i,t}.
$$

Two closing units at USD 0.10/unit/day cost USD 0.20 for one day. Closing
balances [1, 0, 2, 0, 0] at that rate cost USD 0.30 in total. The engine preserves
daily rate precision and returns float columns, without daily cent rounding,
salvage value, or post-horizon holding charges.

## Calibration diagnostic

Researcher-only true expected recurring seven-day replacement cost $W$, in USD, is

$$
W=\sum_i c_i\lambda_i(7\text{ days}).
$$

One product at 2.5 units/day and USD 20/unit contributes USD 350/week. The current
seed-42 scenario gives USD 17,390.72 across all products, 86.95% of budget.
The business-side estimate replaces lambda with its historical estimate and
gives USD 17,601.28 (88.01%). Initial
inventory is not subtracted from recurring replacement. This ignores safety-stock
builds, freight, timing, and realized variation; it is not a policy or service result.

## Accounting and information limits

Prices and additional stockout service penalties exist in the catalog, but the
engine does not calculate revenue, profit, lost margin, or penalties. Absent
revenue and an extra charge for that same lost margin must not both be counted
in a future profit objective. Purchase expenditure is cash-on-order accounting,
not a complete profit-and-loss statement or cost-of-goods-sold calculation.

Policies receive past demand, not current or future realized demand. See
[simulation documentation](inventory_simulation.md) for the API boundary and
[experimental design](experimental_design.md) for proposed evaluation. None
of these implemented equations defines an optimization algorithm.
