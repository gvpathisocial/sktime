import json

import pandas as pd
import yaml

from sktime_quant.run import main


def test_cli_runner_completed(tmp_path):
    n = 160
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D").tolist()
            + pd.date_range("2023-01-01", periods=n, freq="D").tolist(),
            "asset": ["A"] * n + ["B"] * n,
            "close": [100 + i * 0.05 for i in range(n)] + [200 + i * 0.03 for i in range(n)],
        }
    )
    csv_path = tmp_path / "market.csv"
    df.to_csv(csv_path, index=False)

    cfg = {
        "run_id": "cli_run",
        "data": {"source_type": "csv", "csv_path": str(csv_path)},
        "backtest": {"window_length": 60, "step_length": 10, "horizon": 1},
        "execution": {"output_dir": str(tmp_path / "results")},
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    code = main(["--config", str(cfg_path)])
    assert code == 0


def test_cli_runner_no_new_data_returns_2(tmp_path):
    n = 20
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D"),
            "asset": ["A"] * n,
            "close": [100 + i * 0.1 for i in range(n)],
        }
    )
    csv_path = tmp_path / "market.csv"
    df.to_csv(csv_path, index=False)
    state_path = tmp_path / "state.txt"
    state_path.write_text("2025-01-01T00:00:00+00:00", encoding="utf-8")

    cfg = {
        "run_id": "cli_no_data",
        "data": {
            "source_type": "csv",
            "csv_path": str(csv_path),
            "incremental_mode": True,
            "incremental_state_path": str(state_path),
        },
        "execution": {"output_dir": str(tmp_path / "results")},
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    code = main(["--config", str(cfg_path), "--print-summary"])
    assert code == 2

    summary_path = tmp_path / "results" / "reports" / "cli_no_data_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["run_status"] == "no_new_data"
