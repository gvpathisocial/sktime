# Config Reference

## Data
- `source_type`: `timescale|csv|folder`
- `connection_uri`, `market_table`, `exog_table`
- `csv_path`, `folder_path`
- `start`, `end`, `universe`
- `incremental_mode`, `incremental_state_path`
- `strict_schema_validation`, `db_max_retries`, `db_retry_backoff_seconds`
- holidays (Prophet): `enable_db_holidays`, `holiday_table`, `asset_market_map`, `default_market`

## Backtest
- split and horizon: `splitter_type`, `window_length`, `step_length`, `horizon`
- evaluation: `strategy`, `confidence_floor`, `objective`
- strategy policy: `strategy_policy`, `signal_threshold`
- costs and robustness: `transaction_cost_bps`, `slippage_bps`, `max_failure_rate`, `min_successful_folds`

## Execution
- artifacts: `output_dir`, `orders_subdir`, `file_prefix`
- portfolio base: `portfolio_value`
- order constraints: `no_trade_band`, `min_order_notional`, `default_lot_size`, `lot_size_by_asset`
- quality: `data_quality_stale_days`
