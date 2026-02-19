# sktime_quant TODO (Post Initial Release)

## P0 - Reliability and Ops
- Add docs linkcheck allowlist/denylist tuning for flaky external URLs in CI.
- Add CLI option `--fail-on-alerts` to fail run when governance alerts exceed threshold.
- Add artifact checksum manifest for each run (`reports/checksums.json`).

## P1 - Strategy and Execution
- Add configurable signal sizing (not just direction): score-to-weight transform.
- Add optional transaction cost model by asset class and spread regime.
- Add max daily order count and per-broker batch sizing constraints.

## P2 - Monitoring
- Add governance trend summary artifact with rolling 7/30 run stats.
- Add alert severity levels and operator-friendly compact alert report.

## P3 - UX
- Add historical run comparison export (`csv/json`) from Streamlit.
- Add quick links from Streamlit to open artifacts in browser/file explorer.
