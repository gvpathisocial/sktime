Architecture and Design
=======================

Purpose
-------

``sktime_quant`` provides an end-to-end quant workflow on top of ``sktime``:

- ingest market data
- run walk-forward model selection
- generate confidence-aware forecasts
- produce risk-constrained allocations
- export offline broker order files

The design goal is deterministic, auditable daily operation with clear artifacts and health diagnostics.

System context
--------------

Inputs:

- TimescaleDB/PostgreSQL (primary)
- CSV file upload
- local folder CSV ingestion

Core processing:

- schema validation and quality checks
- lagged feature generation
- walk-forward backtesting and strategy scoring
- forecasting with confidence intervals and fallback intervals
- portfolio optimization and execution constraints

Outputs:

- parquet artifacts (metrics, folds, forecasts)
- JSON artifacts (summary, data quality, model selection, governance)
- broker CSV v1 order file

Operators:

- Streamlit UI for interactive runs and diagnostics
- CLI (``python -m sktime_quant.run``) for automation/scheduling

Package architecture
--------------------

``sktime_quant/`` modules:

- ``config/``: dataclass config schema and profile loading
- ``data/``: connectors (``timescale``, ``csv_loader``) and provider dispatch
- ``features/``: lagged regressors and leakage-safe transformations
- ``models/``: model registry, metadata, health checks, update policy
- ``backtest/``: walk-forward engine with tie-break selection logic
- ``forecast/``: forecast engine with stateful update-or-refit flow
- ``risk/``: risk metrics
- ``portfolio/``: confidence/risk-aware allocation engine
- ``execution/``: order generation constraints and CSV export
- ``pipelines/``: orchestrator for end-to-end run lifecycle
- ``ui/``: Streamlit application
- ``tests/``: unit and integration coverage

Runtime flows
-------------

1) Backtest/Research flow

1. load data
2. validate schema and generate data quality report
3. evaluate candidate models via walk-forward
4. select per-asset best model by risk-adjusted objective + tie-break rules
5. write metrics, fold predictions, and model-selection rationale

2) Daily production flow

1. pull latest market data (incremental window if enabled)
2. resolve candidate models (explicit list or auto-discovery)
3. run backtest selection
4. forecast with ``update`` mode where supported, else explicit refit fallback
5. optimize portfolio with confidence and risk constraints
6. generate order diffs and broker CSV
7. write summary/governance artifacts

Data contracts
--------------

Market frame required columns:

- ``timestamp``
- ``asset``
- ``close``

Optional:

- ``open``, ``high``, ``low``, ``volume``, ``asset_class``

Forecast output key columns:

- ``asset``, ``model``, ``prediction``, ``lower_95``, ``upper_95``
- ``confidence``, ``is_actionable``
- ``update_status`` (for daily update diagnostics)

Order CSV v1 columns:

- ``date``, ``asset``, ``side``, ``quantity``, ``order_type``, ``limit_price``, ``stop_price``
- ``time_in_force``, ``strategy_id``, ``confidence``, ``target_weight``

Model registry and policy
-------------------------

Registry responsibilities:

- instantiate callable forecasters
- expose model overview metadata for UI
- validate availability and parameter expectations
- declare daily-update support policy

Current explicit daily update exclusions:

- ``prophet`` (refit fallback)
- ``ensemble_blend`` (refit fallback)

This policy is surfaced in UI and summary artifacts.

Forecast state management
-------------------------

State persistence:

- location: ``results/state/models/``
- keying: ``asset + model``
- format: ``joblib``

Update behavior:

- ``update_mode=update``: load prior forecaster, apply delta (``y_new``) if supported
- fallback to refit when update is unsupported/failed/invalid state
- persist ``update_status`` for each asset-model prediction row

Selection and governance
------------------------

Model selection:

- objective: configurable (``composite``, ``sharpe``, ``sortino``, ``calmar``)
- tie-break sequence: score, coverage, failure rate, drawdown, MAE, model name

Governance:

- per-run governance report with alerting
- rolling governance history artifact for trend analysis
- runtime health table derived from actual backtest execution outcomes

Execution constraints
---------------------

Order generation supports:

- no-trade band
- min/max order notional
- lot size (global and per-asset)
- max turnover notional per asset per day
- deterministic sorting and strict schema validation

Testing strategy
----------------

Unit tests:

- registry, health checks, feature generation, risk metrics, order exporter

Integration tests:

- end-to-end orchestration on synthetic data
- Timescale connector/integration tests
- forecast update state persistence and auto-candidate fallback

CI coverage:

- quant test workflow
- docs smoke/link checks
- scheduled dry-run workflow

Non-goals (current release)
---------------------------

- full auto-hyperparameter optimization across large search spaces
- microstructure-level execution simulation
- online learning for all model families

These are planned as iterative enhancements.
