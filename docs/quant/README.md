# sktime_quant Documentation

## Guides
- `getting_started.md`
- `architecture_and_design.md`
- `config_reference.md`
- `backtest_and_selection.md`
- `operations_runbook.md`
- `faq.md`

This module extends `sktime` with a quant workflow: ingestion, walk-forward backtesting, model selection, forecasting, portfolio rebalancing, and offline order export.

## Standard Test Sequence
- Core strategy/performance regression:
  - `make test_quant_core`
- Full quant suite (excluding DB integration markers):
  - `make test_quant`
- Full quant suite via pytest directly:
  - `python -m pytest sktime_quant/tests -o addopts="" -m "not integration"`
