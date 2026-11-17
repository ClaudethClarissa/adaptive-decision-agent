# Data

This directory holds reproducible synthetic datasets.

- `raw/`: generated source datasets before transformation.
- `processed/`: derived datasets prepared for modeling and evaluation.

Generate `product_catalog.csv`, `historical_daily_demand.csv` (days -59 through
0), and `daily_demand.csv` (evaluation days 1-30) with
`python -m adaptive_decision_agent.data.synthetic --seed 42 --output-dir data/raw`.
Files in these subdirectories are ignored by Git, except their directory
placeholders. See [synthetic data documentation](../docs/synthetic_data.md) for
schemas, assumptions, and reproducibility details.
The business catalog includes the historical sample mean; true latent rates
remain internal and are never written to these CSV files.
