# Data

This directory holds reproducible synthetic datasets.

- `raw/`: generated source datasets before transformation.
- `processed/`: derived datasets prepared for modeling and evaluation.

Generate the catalog and daily demand with
`python -m adaptive_decision_agent.data.synthetic --seed 42 --output-dir data/raw`.
Files in these subdirectories are ignored by Git, except their directory
placeholders. See [synthetic data documentation](../docs/synthetic_data.md) for
schemas, assumptions, and reproducibility details.
