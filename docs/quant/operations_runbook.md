# Operations Runbook

## Daily cycle
1. Ingest latest bars (Timescale or files)
2. Run backtest-driven model selection
3. Forecast next horizon
4. Rebalance portfolio
5. Export broker order CSV

## Incremental mode
- Enable `data.incremental_mode: true`
- Persist/read state from `data.incremental_state_path` or default `results/state/{run_id}_last_timestamp.txt`
- If no new rows are present after filtering, run exits with `run_status=no_new_data` and code `2` from CLI

## Health checks
- Inspect `results/reports/{run_id}_data_quality.json`
- Inspect `results/reports/{run_id}_summary.json`
- Inspect `results/reports/{run_id}_model_selection.json`
