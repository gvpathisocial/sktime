# sktime_quant TODO (Post Initial Release)

## P0 - Reliability and Ops
- Add docs linkcheck allowlist/denylist tuning for flaky external URLs in CI.
- Add CLI option `--fail-on-alerts` to fail run when governance alerts exceed threshold.
- Add artifact checksum manifest for each run (`reports/checksums.json`).

## P1 - Strategy and Execution
- Add configurable signal sizing (not just direction): score-to-weight transform.
- Add optional transaction cost model by asset class and spread regime.
- Add max daily order count and per-broker batch sizing constraints.
- Revisit TBATS support when dependency stack is stable on Python 3.13+ (currently deferred due `numpy<2` constraint).
- Add classifier calibration/validation report (AUC, precision/recall, confusion matrix) per run.
- Add strategy-mode comparison artifact (`forecast_only` vs `rule_only` vs `classifier_only` vs `blended`).

## P2 - Monitoring
- Add governance trend summary artifact with rolling 7/30 run stats.
- Add alert severity levels and operator-friendly compact alert report.

## P3 - UX
- Add historical run comparison export (`csv/json`) from Streamlit.
- Add quick links from Streamlit to open artifacts in browser/file explorer.
- Add visual rule-chain builder widgets (form mode) in addition to YAML editor.

TODO BEFORE PUBLISH

Recommended local validation pass before publish:

.\.venv\Scripts\python -m pytest sktime_quant/tests -o addopts=""
.\.venv\Scripts\python -m sktime_quant.run --config config_dry_run.yaml --dry-run --print-summary
.\.venv\Scripts\python -m streamlit run sktime_quant/ui/streamlit_app_uplift.py
RUN_TIMESCALE_CONTAINER_TESTS=1 .\.venv\Scripts\python -m pytest sktime_quant/tests/test_timescale_container_integration.py -o addopts="" -q

Optional docs build:
make -C docs/source html SPHINXOPTS="-W --keep-going"

When you're satisfied, publish with:

git push origin main
git push origin sktime-quant-v0.3.0-uplift-bg-studio

Next versions can definitely add substantial value. Your base is strong now: governance, CI, dry-run ops, and artifact-level observability are already in place.
