Operations Runbook
==================

Daily cycle:
1. ingest latest bars
2. backtest and model selection
3. forecast next horizon
4. rebalance portfolio
5. export broker orders

Incremental mode:
- enable ``data.incremental_mode``
- state file defaults to ``results/state/{run_id}_last_timestamp.txt``
- if no new rows exist, run status is ``no_new_data`` and CLI exits with code ``2``

Health files:
- ``results/reports/{run_id}_summary.json``
- ``results/reports/{run_id}_data_quality.json``
- ``results/reports/{run_id}_model_selection.json``
- ``results/reports/{run_id}_model_governance.json``
- ``results/governance/model_stability_history.json``

Streamlit operations:
- Use **Config Profiles** in the sidebar to save/load YAML profiles.
- Use **Artifact Browser** in the sidebar to inspect historical JSON reports.
- Run banner indicates ``completed`` vs ``no_new_data`` status explicitly.

Scheduled dry-run:
- GitHub Actions workflow: ``.github/workflows/quant_dry_run.yml``
- Runs daily on cron and can be triggered manually.
- Uses:

  .. code-block:: bash

     python -m sktime_quant.run --config examples/quant/config_dry_run.yaml --dry-run --print-summary

- Uploads dry-run artifacts from ``results/dry_run``.
