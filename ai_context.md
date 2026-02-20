# AI Context Log

Last updated: 2026-02-19 (UTC)
Workspace: `e:\Projects\Python\sktime`

## 1) Original Objective
Build a separate `sktime_quant/` extension that uses `sktime` for:
- walk-forward backtesting (stocks, indices, commodities)
- forecasting with confidence intervals (95%+ gating)
- TimescaleDB-first ingestion (plus CSV/folder)
- portfolio optimization + risk-aware rebalancing
- offline broker order CSV export
- Streamlit UI
- CLI runner
- tests from the start (unit + integration where feasible)

## 2) Major Architecture Decisions (Locked)
- Package scope: separate module `sktime_quant/`
- Primary DB: TimescaleDB/PostgreSQL
- Optimization objective: risk-adjusted return
- Order format: broker `CSV v1`
- Backtest standard: walk-forward via `sktime.split` / model evaluation style
- Daily operation: update mode when supported, fallback to refit

## 3) Implemented Package Structure (High Level)
- `sktime_quant/config` for dataclass config + YAML load/save profiles
- `sktime_quant/data` connectors + schema validation + provider
- `sktime_quant/features` lagged/exogenous/technical/zone feature tooling
- `sktime_quant/models` registry, health checks, metadata/overview
- `sktime_quant/backtest` walk-forward orchestration
- `sktime_quant/forecast` forecast engine with update/refit handling
- `sktime_quant/risk` risk metrics
- `sktime_quant/portfolio` confidence/risk-aware allocation
- `sktime_quant/execution` order generation/export and constraints
- `sktime_quant/pipelines/orchestrator.py` end-to-end runner
- `sktime_quant/ui/streamlit_app.py` (initial UI)
- `sktime_quant/ui/streamlit_app_uplift.py` (new redesigned UI)
- `sktime_quant/tests` unit/integration-style coverage (non-container paths)

## 4) Key Functional Capabilities Added
- Incremental ingestion mode with state checkpoint (`last timestamp`)
- Data quality artifact/report generation
- Exogenous handling:
  - one-step lag for regressors
  - categorical exogenous encoding
  - null-row drops before modeling
- Holiday table integration for Prophet-like usage from DB
- Model registry expansion + dependency/availability health reporting
- Daily update exclusions per model where unsupported
- Ensemble-related support and selection controls
- Model selection rationale artifact + tie-break behavior support
- Governance artifacts:
  - per-run governance report
  - stability history over runs (`results/governance/model_stability_history.json`)
- Execution realism:
  - no-trade band
  - min/max notional constraints
  - lot size constraints
  - per-asset turnover caps
- Broker order CSV validation + deterministic sorting
- CLI runner support (`python -m sktime_quant.run --config ...`)

## 5) Data Sources & Ingestion Notes
- CSV/folder support enhanced to accept Yahoo-style raw OHLCV patterns
- External ingestion helper code exists under:
  - `sktime_quant/Ingest-outside-code/symbols.inf`
  - `sktime_quant/Ingest-outside-code/yahoo_downloader.py`
- Timescale pipeline direction established (including OHLCV storage + optional exogenous tables)
- Recommendation accepted: keep DB raw timestamps; apply one-day lag in modeling pipeline

## 6) UI Evolution Summary
### Initial app (`streamlit_app.py`)
- Added run history, profile load/save, advanced config YAML editor
- Added model picker and model overviews
- Added run progress events and artifact browsing
- Added per-run visualization but still accumulated UX complexity

### User-reported issues
- reports perceived as mixed/merged
- weak run-state visibility during execution
- non-intuitive controls (radio-driven, "bookish" JSON-heavy outputs)
- Arrow serialization issues in compare views with mixed dtypes
- model selection behavior confusing when unavailable models were grayed out

### New uplift app (`streamlit_app_uplift.py`)
- Separate app, same backend logic
- Tabs:
  - `Run Studio`
  - `Run Explorer` (strict single-run scope)
  - `Governance`
  - `Orders`
  - `Config Lab`
- cleaner styling, clearer operator workflow, reduced report mixing risk

## 7) Testing & Tooling State (As tracked)
- Unit tests substantially expanded around:
  - schema, features, model registry health/params
  - backtest leakage boundaries
  - forecast interval/confidence behavior
  - execution CSV schema/compliance
- Smoke tests executed for orchestration paths
- Docs generation scoped for quant docs area; Sphinx installed and used
- Non-integration test runs reported healthy in prior cycle

## 8) Profiles / Runtime Artifacts Referenced
- Profiles:
  - `profiles/quant_profile.yaml`
  - `profiles/quant_profile2.yaml`
  - `profiles/en_profile.yaml`
- Example generated artifacts:
  - `results/reports/*_summary.json`
  - `results/reports/*_model_selection.json`
  - `results/reports/*_model_governance.json`
  - `results/reports/*_data_quality.json`
  - `results/orders/orders_YYYYMMDD.csv`
  - `results/governance/model_stability_history.json`

## 9) Constraints/Preferences Captured from User
- Avoid downgrading core libraries to satisfy optional models
- Ignore unstable/unmaintained models if dependency risk is high (example: TBATS)
- Keep warning noise reduced ("warning floods")
- Focus on daily update practicality and explicit exclusion reporting
- Keep UI informative for model choice and run status/progress
- Keep broker execution offline via validated file exports

## 10) Current Snapshot
- Uplift UI file created and compile-checked:
  - `sktime_quant/ui/streamlit_app_uplift.py`
- Existing UI remains available:
  - `sktime_quant/ui/streamlit_app.py`
- Backend pipeline logic and artifact generation already integrated
- Project is in advanced prototype/initial-version-plus stage with strong scaffolding and iterative hardening completed across multiple areas

## 11) Recommended Next Steps
1. Make `streamlit_app_uplift.py` the default UI entry in docs/scripts.
2. Add explicit run lifecycle persistence (`queued/running/completed/failed`) as a small run registry file.
3. **[IMPLEMENTED] Add Performance Analytics tab with risk metrics visualization** (Sortino, Sharpe, Calmar, drawdown curves).
4. Add UI smoke tests (basic render + artifact parsing guards).
5. Harden Arrow-safe dataframe conversion in all compare/report tables.
6. Add Timescale containerized integration test path into CI (if not already wired in active pipeline).
7. Prepare release notes and semantic tag for current milestone.

## 12) Performance Analytics Implementation (Added 2026-02-20)
- **New tab**: Performance Analytics in uplift UI (3rd tab in main navigation)
- **Risk metrics wired**: Sortino, Sharpe, Calmar, max drawdown
- **Data source**: Integrates with walkforward backtest output (`fold_predictions.parquet`)
- **Storage specification** (VERIFIED):
  - All backtest artifacts stored under `{output_dir}/backtests/{run_id}/`
  - Fold predictions (per-fold trade data): `results/backtests/{run_id}/fold_predictions.parquet`
  - Metrics (per-asset/model aggregates): `results/backtests/{run_id}/metrics.parquet`
  - Orchestrator path construction verified (line 64-65 in orchestrator.py)
  - Documented at line 523-525 with explicit comments

- **Aggregation**: Sums daily fold_returns across all assets/models for portfolio P&L view
- **Visualizations**: Equity curve, rolling Sortino (30-day), drawdown underwater plot
- **Export**: Save computed metrics to JSON per run with null-safe serialization
- **Error messaging**: Improved with debugging guidance (path substitution, common causes)
- **Loader robustness** (PRODUCTION-READY):
  - Attempts fold_predictions.parquet first (per-fold detail)
  - Falls back to metrics.parquet if fold_predictions is empty/missing
  - Gracefully handles excluded models (when all asset-model combinations fail filters)
  - Better error messaging with debugging guidance

- **Functions added**:
  - `_load_backtest_results()` - loads fold_predictions.parquet with fallback to metrics
  - `_compute_risk_metrics()` - calculates Sortino/Sharpe/Calmar/drawdown on aggregated returns
  - `_plot_equity_curve()`, `_plot_rolling_sortino()`, `_plot_drawdown()` - Plotly visualizations
  - `sortino_ratio()` - annualized downside volatility-adjusted return
  - `sharpe_ratio()` - risk-free rate-adjusted return per unit volatility
  - `calmar_ratio()` - annual return divided by absolute max drawdown
  - `cumulative_returns()` - total return from start to end equity

- **Test coverage** (8 integration tests, all PASSED):
  - `test_risk_metrics_basics()` - existing VaR/CVaR/volatility/drawdown
  - `test_walkforward_produces_fold_returns_for_metrics()` - verifies fold_predictions structure
  - `test_risk_metrics_on_walkforward_returns()` - full backtest->aggregate->metrics pipeline
  - `test_sortino_ratio_financial_interpretation()` - realistic strategy scenario
  - `test_sharpe_ratio_risk_adjusted_return()` - multi-strategy comparison
  - `test_calmar_ratio_return_over_drawdown()` - drawdown impact testing
  - `test_cumulative_returns_end_to_end_calculation()` - return math validation
  - `test_aggregate_daily_portfolio_returns_from_folds()` - multi-asset daily aggregation (UI workflow)

## 13) Backtest Artifact Path Structure (Run-id based, clean)
- **Backtests folder**: `results/backtests/` (segregated by run_id, not date)
- **Forecasts folder**: `results/forecasts/` (date-based for daily batches: `YYYYMMDD`)
- **Reports folder**: `results/reports/` (per-run summary artifacts)
- Reason: Backtests are historical; forecasts are operational daily; reports are run-scoped
- **No overwrites**: Each run_id gets clean folder; daily forecast dates handle multiple runs same day

## 14) Test Framework Alignment (REFACTORED)
- Converted from pure math unit tests to **integration tests**
- Matches project's testing pattern (see `test_walkforward.py`, `test_orders.py`)
- Tests actual business workflows: data -> walkforward -> aggregate -> metrics
- Uses realistic DataFrames (market data, fold predictions)
- Tests edge cases AND financial interpretation
- All 8 tests pass; framework now aligned with project standards

## 15) Quick Commands
- Run CLI:
  - `python -m sktime_quant.run --config profiles/quant_profile.yaml`
- Run uplift UI:
  - `streamlit run sktime_quant/ui/streamlit_app_uplift.py`
- Run original UI:
  - `streamlit run sktime_quant/ui/streamlit_app.py`

## 16) Validation Checkpoint (2026-02-20)
- Environment: project virtualenv `.\.venv\Scripts\python.exe`
- Syntax validation:
  - `python -m py_compile sktime_quant/ui/streamlit_app_uplift.py` -> pass
- Targeted tests:
  - `.\.venv\Scripts\python.exe -m pytest sktime_quant/tests/test_risk_metrics.py -q` -> 8 passed
  - `.\.venv\Scripts\python.exe -m pytest sktime_quant/tests/test_risk_metrics.py sktime_quant/tests/test_forecast_engine_update.py -q` -> 9 passed
- Full quant test suite:
  - `.\.venv\Scripts\python.exe -m pytest sktime_quant/tests -q` -> 57 passed, 1 skipped
- Realignment applied:
  - removed non-ASCII/emoji strings from uplift UI/status text
  - removed unused `plotly.express` import in uplift UI
  - normalized non-ASCII characters in this context document and risk-metrics test comment

## 17) Standardized Quant Test Sequence (Added)
- Makefile targets:
  - `make test_quant_core`
  - `make test_quant`
- CI workflow update:
  - `.github/workflows/test_quant.yml` now includes an explicit core regression step:
    - `test_walkforward.py`
    - `test_risk_metrics.py`
    - `test_forecast_engine_update.py`
- Latest local validation:
  - `.\.venv\Scripts\python.exe -m pytest sktime_quant/tests/test_walkforward.py sktime_quant/tests/test_risk_metrics.py sktime_quant/tests/test_forecast_engine_update.py -o addopts="" -q` -> 13 passed
  - `.\.venv\Scripts\python.exe -m pytest sktime_quant/tests -o addopts="" -m "not integration" -q` -> 57 passed, 1 deselected
