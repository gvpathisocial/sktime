# sktime_quant Changelog

## v0.2.0 - 2026-02-19

### Added
- Expanded model registry with additional callable forecasters, including `ensemble_blend`.
- Model overview metadata for UI model selection.
- Model health validation for dependency/parameter checks.
- Runtime model health summarization from backtest metrics.
- Forecast state persistence and daily delta `update` flow in forecast engine.
- Explicit daily-update exclusion policy in registry (`prophet`, `ensemble_blend` currently refit-only).
- Auto-candidate fallback when `model.candidates` is empty.
- UI update mode selector and update-exclusion warnings.
- New unit/integration coverage for registry health, forecast update flow, and auto-candidate orchestration.

### Changed
- Backtest UI now shows selected model overviews and health tables.
- Orchestrator summary now includes model candidate list, forecast update status counts, and daily-update exclusion details.
- Documentation updated with model availability notes and TBATS deferment rationale for Python 3.13 environments.

### Stability
- Non-integration quant test suite passing after this release cut.
