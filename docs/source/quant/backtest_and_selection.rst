Backtest and Selection
======================

Model selection tie-break order:

1. ``risk_adjusted_score`` (descending)
2. ``empirical_coverage`` (descending)
3. ``failure_rate`` (ascending)
4. ``max_drawdown`` (ascending)
5. ``mae`` (ascending)
6. ``model`` (ascending)

Artifacts:
- ``results/reports/{run_id}_model_selection.json``
- ``results/reports/{run_id}_model_governance.json``
- ``results/governance/model_stability_history.json``
- ``results/backtests/{run_id}/metrics.parquet``
- ``results/backtests/{run_id}/fold_predictions.parquet``
