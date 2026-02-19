# Getting Started

## Install

```bash
pip install -e ".[dev,forecasting,quant]"
```

## Run from CLI

```bash
python -m sktime_quant.run --config config.yaml --print-summary
```

## Minimal config

```yaml
run_id: demo_run
data:
  source_type: csv
  csv_path: ./examples/quant/data/sample_market.csv
backtest:
  window_length: 60
  step_length: 10
  horizon: 1
model:
  candidates: [naive_last, naive_mean, theta]
execution:
  output_dir: ./results
```
