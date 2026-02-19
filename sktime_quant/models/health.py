"""Model health utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd


def summarize_runtime_health(
    metrics: pd.DataFrame,
    *,
    max_failure_rate: float,
    confidence_floor: float,
) -> pd.DataFrame:
    """Summarize operational model health from backtest metrics.

    Health criteria:
    - no init failures
    - mean failure rate <= configured max failure rate
    - mean empirical coverage >= configured confidence floor
    """
    if metrics.empty:
        return pd.DataFrame(
            columns=[
                "model",
                "assets_tested",
                "init_failures",
                "successful_folds",
                "failure_rate_mean",
                "empirical_coverage_mean",
                "mae_mean",
                "runtime_health",
                "health_reason",
            ]
        )

    rows: list[dict[str, object]] = []
    for model, grp in metrics.groupby("model"):
        init_failures = int(
            grp["excluded_reason"]
            .fillna("")
            .astype(str)
            .str.startswith("model_init_failed")
            .sum()
        )
        failure_rate_mean = float(grp["failure_rate"].fillna(1.0).mean())
        coverage = grp["empirical_coverage"].replace([np.inf, -np.inf], np.nan).dropna()
        coverage_mean = float(coverage.mean()) if not coverage.empty else float("nan")
        mae = grp["mae"].replace([np.inf, -np.inf], np.nan).dropna()
        mae_mean = float(mae.mean()) if not mae.empty else float("nan")
        successful_folds = int(grp["successful_folds"].fillna(0).sum())
        assets_tested = int(grp["asset"].nunique())

        if init_failures > 0:
            runtime_health = "unhealthy"
            reason = "model_init_failed"
        elif failure_rate_mean > max_failure_rate:
            runtime_health = "degraded"
            reason = "high_failure_rate"
        elif np.isnan(coverage_mean) or coverage_mean < confidence_floor:
            runtime_health = "degraded"
            reason = "low_empirical_coverage"
        else:
            runtime_health = "healthy"
            reason = "ok"

        rows.append(
            {
                "model": str(model),
                "assets_tested": assets_tested,
                "init_failures": init_failures,
                "successful_folds": successful_folds,
                "failure_rate_mean": failure_rate_mean,
                "empirical_coverage_mean": coverage_mean,
                "mae_mean": mae_mean,
                "runtime_health": runtime_health,
                "health_reason": reason,
            }
        )

    frame = pd.DataFrame(rows)
    return frame.sort_values(["runtime_health", "model"], ascending=[True, True]).reset_index(
        drop=True
    )

