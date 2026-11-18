"""Historical-only EDA and reproducible rolling-origin reporting CLI."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .models import validate_history
from .validation import rolling_splits, rolling_validate


def describe_history(history: pd.DataFrame) -> pd.DataFrame:
    """Per-product descriptive diagnostics; no hypothesis tests or model choice."""
    history = validate_history(history)
    rows = []
    midpoint = history.day.nunique() // 2
    if midpoint < 2:
        raise ValueError("EDA requires at least four daily observations per product")
    for product, group in history.groupby("product_id", sort=True):
        values = group.demand.astype(float).reset_index(drop=True)
        mean, variance = values.mean(), values.var(ddof=1)
        lag1 = values.autocorr(lag=1) if values.iloc[1:].std() > 0 and values.iloc[:-1].std() > 0 else np.nan
        rows.append({"product_id": product, "n": len(values), "mean": mean,
                     "variance": variance, "std": values.std(ddof=1),
                     "zero_frequency": float(values.eq(0).mean()),
                     "variance_to_mean": variance / mean if mean > 0 else np.nan,
                     "lag1_autocorrelation": lag1,
                     "first_half_mean": values.iloc[:midpoint].mean(),
                     "second_half_mean": values.iloc[midpoint:].mean(),
                     "half_mean_change": values.iloc[midpoint:].mean() - values.iloc[:midpoint].mean()})
    return pd.DataFrame(rows)


def _plots(history, statistics, result, figure_dir):
    # Plotting is optional; importing the core forecasters needs no Matplotlib.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    figure_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), constrained_layout=True)
    axes[0, 0].hist(statistics["mean"], bins=10, color="#28698c", edgecolor="white")
    axes[0, 0].set(title="Between-product demand levels", xlabel="Historical mean (units/day)", ylabel="Products")
    axes[0, 1].scatter(statistics["mean"], statistics.variance, color="#28698c", alpha=.8)
    limit = max(statistics["mean"].max(), statistics.variance.max()) * 1.05
    axes[0, 1].plot([0, limit], [0, limit], "--", color="#ad5d25", label="Equal numeric mean and variance")
    axes[0, 1].set(title="Dispersion within each product", xlabel="Mean daily units", ylabel="Sample variance (units squared)")
    axes[0, 1].legend(fontsize=8)
    axes[1, 0].hist(statistics.lag1_autocorrelation.dropna(), bins=12, color="#28698c", edgecolor="white")
    axes[1, 0].axvline(0, color="#ad5d25", linestyle="--")
    axes[1, 0].set(title="Lag-one sample correlations", xlabel="Correlation", ylabel="Products")
    total = history.groupby("day").demand.sum()
    axes[1, 1].plot(total.index, total, alpha=.5, color="#28698c", label="Daily total")
    axes[1, 1].plot(total.index, total.rolling(7).mean(), color="#ad5d25", label="Trailing 7-day mean")
    axes[1, 1].set(title="Observed historical total demand", xlabel="Historical day", ylabel="Units/day")
    axes[1, 1].legend(fontsize=8)
    fig.suptitle("Historical demand only: 50 products, 60 observations each", fontsize=14)
    fig.savefig(figure_dir / "historical_demand_eda.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for ax, scale, title in zip(axes, ["daily", "7_day_total"], ["Daily point error", "7-day aggregate point error"]):
        table = result.by_window.query("scale == @scale").pivot(index="window", columns="model", values="mae")
        table = table.rename(columns={"expanding_mean": "Expanding mean", "moving_average_14": "14-day mean", "moving_average_30": "30-day mean"})
        table.plot.bar(ax=ax, color=["#28698c", "#ad5d25", "#739b65"], rot=0)
        ax.set(title=title, xlabel="Historical validation window", ylabel="MAE (units)")
        ax.get_legend().remove()
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(.5, -.08), ncol=3, frameon=False)
    fig.suptitle("Fixed-origin forecasts: identical folds for every method", fontsize=13)
    fig.savefig(figure_dir / "historical_forecast_validation.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, default=Path("data/raw/historical_daily_demand.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/demand_analysis"))
    parser.add_argument("--figure-dir", type=Path, default=Path("docs/figures"))
    parser.add_argument("--poisson-scores", action="store_true", help="Score a separate plug-in Poisson count candidate")
    args = parser.parse_args()
    history = pd.read_csv(args.history)
    # This rejects any evaluation-period rows instead of silently using them.
    rolling_splits(history)
    statistics = describe_history(history)
    result = rolling_validate(history, evaluate_poisson=args.poisson_scores)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    tables = {"product_descriptives": statistics, "point_metrics_overall": result.overall,
              "point_metrics_by_window": result.by_window, "point_metrics_by_product": result.by_product,
              "daily_validation_predictions": result.daily_predictions,
              "weekly_validation_predictions": result.weekly_predictions}
    if args.poisson_scores:
        tables.update(poisson_metrics_overall=result.poisson_overall, poisson_metrics_by_window=result.poisson_by_window)
    for name, table in tables.items():
        table.to_csv(args.output_dir / f"{name}.csv", index=False)
    _plots(history, statistics, result, args.figure_dir)
    print("EDA summary across products:")
    print(statistics.drop(columns="product_id").describe().round(4).to_string())
    print("Overall point metrics:\n", result.overall.round(5).to_string(index=False))
    print("By-window point metrics:\n", result.by_window.round(5).to_string(index=False))
    if args.poisson_scores:
        print("Separate Poisson candidate scores:\n", result.poisson_overall.round(5).to_string(index=False))


if __name__ == "__main__":
    main()
