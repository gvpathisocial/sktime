# Uplift Requirement Intake Validation (2026-02-20)

## Scope Delta Reviewed
- Source: `Uplift.md` plus existing `ai_context.md` implementation baseline.
- Primary delta accepted:
  - Studio-first UX where runs execute in background while operator stays in foreground.
  - Explicit run lifecycle tracking (`queued`, `running`, `completed`, `no_new_data`, `failed`).
  - Stronger run reporting artifact beyond JSON summaries.
  - Containerized Timescale integration test path for simulated data.

## Critical Validation
- Already implemented in baseline:
  - walk-forward backtesting
  - confidence-aware forecasting
  - Timescale-first ingestion with CSV/folder fallback
  - risk-aware allocation and order CSV export
  - Streamlit + CLI + broad unit/integration tests
- Gaps addressed in this re-engineering pass:
  - background run orchestration in Studio UX
  - run registry persistence for lifecycle visibility
  - markdown run report artifact generation
  - Timescale container test harness and test case

## Non-MVP / Deferred (Intentionally)
- Full rule-chain visual editor and classifier studio are architectural next-level items and not forced into this pass to avoid destabilizing the current pipeline.
- Advanced async job workers (Redis/Celery) are deferred; current in-process thread runtime is sufficient for local/operator mode.

## Acceptance Criteria Used
- Freeze snapshot branch + tag created before re-engineering.
- New runs can be queued from Studio and tracked without blocking UI.
- Run registry is persisted under `results/reports/run_registry.json`.
- Report artifact exists per run (`*_report.md`) and is referenced by summary.
- Unit tests cover new background runtime and reporting.
- Containerized Timescale integration test path exists for simulated DB data.
