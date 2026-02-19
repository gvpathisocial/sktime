# Backtest and Model Selection

Selection is deterministic and tie-broken in this order:
1. `risk_adjusted_score` (desc)
2. `empirical_coverage` (desc)
3. `failure_rate` (asc)
4. `max_drawdown` (asc)
5. `mae` (asc)
6. `model` (asc)

Artifacts:
- `results/reports/{run_id}_model_selection.json`
- `results/backtests/{run_id}/metrics.parquet`
- `results/backtests/{run_id}/fold_predictions.parquet`
