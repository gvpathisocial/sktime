Config Reference
================

Data
----
- ``source_type``: ``timescale|csv|folder``
- ``connection_uri``, ``market_table``, ``exog_table``
- ``csv_path``, ``folder_path``
- ``start``, ``end``, ``universe``
- ``incremental_mode``, ``incremental_state_path``
- ``strict_schema_validation``, ``db_max_retries``, ``db_retry_backoff_seconds``

Backtest
--------
- ``splitter_type``, ``window_length``, ``step_length``, ``horizon``
- ``strategy``, ``confidence_floor``, ``objective``
- ``strategy_policy``, ``signal_threshold``
- ``transaction_cost_bps``, ``slippage_bps``
- ``max_failure_rate``, ``min_successful_folds``

Execution
---------
- ``output_dir``, ``orders_subdir``, ``file_prefix``
- ``portfolio_value``
- ``no_trade_band``, ``min_order_notional``
- ``default_lot_size``, ``lot_size_by_asset``
- ``max_order_notional``, ``max_turnover_notional_per_asset``
- ``data_quality_stale_days``
- governance alerts:
  ``governance_coverage_alert_threshold``,
  ``governance_failure_alert_threshold``,
  ``governance_coverage_drop_alert``,
  ``governance_history_max_records``
