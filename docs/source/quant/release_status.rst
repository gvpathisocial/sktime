Release Status
==============

Current milestone
-----------------

Initial version of ``sktime_quant`` is implemented and operational.

Implemented scope
-----------------

- Multi-source ingestion (Timescale, CSV, folder) with incremental mode.
- Walk-forward backtesting with strategy policies and deterministic tie-break selection.
- Forecasting, confidence/risk-aware portfolio rebalancing, and offline order export.
- Execution realism constraints: no-trade band, min/max notional, lot sizes, turnover cap.
- Model governance artifacts, stability history, and alert generation.
- Streamlit UI with run history, artifact browser, run-to-run diff, governance trends.
- CI workflows for tests, Timescale integration, docs smoke/linkcheck, daily dry-run.
- CLI runner for automated scheduled runs.

Completion level
----------------

- Core architecture: complete for initial release.
- Operational automation: complete for initial release.
- Governance/observability: complete for initial release baseline.
- Advanced strategy research features: partially complete (next iteration).

Next-iteration backlog
----------------------

See ``sktime_quant/TODO.md`` for prioritized follow-up tasks.
