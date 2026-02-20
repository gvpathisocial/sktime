# Getting Started

## Install

```bash
pip install -e ".[dev,forecasting,quant]"
```

## Run from CLI

```bash
python -m sktime_quant.run --config config.yaml --print-summary
```

## Yahoo ingestion (scheduler-friendly)

Run once:

```bash
python -m sktime_quant.ingestion.run_yahoo_ingest \
  --symbols-file sktime_quant/Ingest-outside-code/symbols.inf \
  --output-folder sktime_quant/Ingest-outside-code/smalldata
```

Run on interval (until Timescale is primary):

```bash
python -m sktime_quant.ingestion.run_yahoo_ingest \
  --symbols-file sktime_quant/Ingest-outside-code/symbols.inf \
  --output-folder sktime_quant/Ingest-outside-code/smalldata \
  --mode loop --interval-minutes 1440
```

Optional Timescale upsert in same run:

```bash
python -m sktime_quant.ingestion.run_yahoo_ingest \
  --symbols-file sktime_quant/Ingest-outside-code/symbols.inf \
  --output-folder sktime_quant/Ingest-outside-code/smalldata \
  --connection-uri "postgresql+psycopg://user:pass@host:5432/db" \
  --market-table public.market_data
```

Timescale market + exogenous upsert:

```bash
python -m sktime_quant.ingestion.run_yahoo_ingest \
  --symbols-file sktime_quant/Ingest-outside-code/symbols.inf \
  --output-folder sktime_quant/Ingest-outside-code/smalldata \
  --connection-uri "postgresql+psycopg://user:pass@host:5432/db" \
  --market-table public.market_data \
  --write-exog --exog-table public.exog_data
```

Optional custom zone-label schema:

```json
{
  "trend_up_return": 0.003,
  "trend_down_return": -0.003,
  "vol_high": 0.04,
  "vol_low": 0.008,
  "no_trade_abs_return": 0.0015
}
```

```bash
python -m sktime_quant.ingestion.run_yahoo_ingest \
  --symbols-file sktime_quant/Ingest-outside-code/symbols.inf \
  --output-folder sktime_quant/Ingest-outside-code/smalldata \
  --connection-uri "postgresql+psycopg://user:pass@host:5432/db" \
  --market-table public.market_data \
  --write-exog --exog-table public.exog_data \
  --zone-schema-json path/to/zone_schema.json
```

Suggested Timescale schema:

```sql
CREATE TABLE IF NOT EXISTS public.market_data (
  timestamp TIMESTAMPTZ NOT NULL,
  asset TEXT NOT NULL,
  open DOUBLE PRECISION,
  high DOUBLE PRECISION,
  low DOUBLE PRECISION,
  close DOUBLE PRECISION NOT NULL,
  volume DOUBLE PRECISION,
  asset_class TEXT,
  PRIMARY KEY (asset, timestamp)
);

CREATE TABLE IF NOT EXISTS public.exog_data (
  timestamp TIMESTAMPTZ NOT NULL,
  asset TEXT NOT NULL,
  ret_1d DOUBLE PRECISION,
  sma_20 DOUBLE PRECISION,
  ema_20 DOUBLE PRECISION,
  rsi_14 DOUBLE PRECISION,
  atr_14 DOUBLE PRECISION,
  vol_20 DOUBLE PRECISION,
  context_zone TEXT,
  trend_zone TEXT,
  trade_zone TEXT,
  PRIMARY KEY (asset, timestamp)
);
```

Exogenous lag policy:
- Keep exogenous features in DB as same-day values.
- `sktime_quant` applies a one-step lag per asset at runtime before model fit/predict, so no DB shift is required.
- Warmup null rows created by indicator windows/lagging are dropped before features are passed to regressors.
- Categorical exogenous fields are one-hot encoded at runtime before passing to regressors.

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

## Model notes

- Registry includes: `naive_last`, `naive_mean`, `theta`, `arima`, `autoets`, `exp_smoothing`, `croston`, `prophet`.
- Final selectable models in UI/CLI are filtered by installed optional dependencies.
- `tbats` is intentionally deferred in this build due environment stability constraints on Python 3.13 (`numpy<2` requirement).

## Standard test sequence

```bash
make test_quant_core
make test_quant
```
