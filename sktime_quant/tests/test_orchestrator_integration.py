import pandas as pd
import json
from pathlib import Path

from sktime_quant.config.schema import AppConfig
from sktime_quant.pipelines.orchestrator import Orchestrator



def test_orchestrator_end_to_end_csv(tmp_path):
    n = 180
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

    cfg = AppConfig()
    cfg.run_id = "it_run"
    cfg.data.source_type = "csv"
    cfg.data.csv_path = str(csv_path)
    cfg.backtest.window_length = 60
    cfg.backtest.step_length = 15
    cfg.backtest.horizon = 1
    cfg.data.incremental_mode = True
    cfg.execution.output_dir = str(tmp_path / "results")
    cfg.execution.no_trade_band = 0.001
    cfg.execution.min_order_notional = 100.0

    result = Orchestrator().run(cfg)
    assert result.orders_path.endswith(".csv")
    assert result.data_quality_path.endswith(".json")
    assert result.model_selection_path.endswith(".json")
    assert result.model_governance_path.endswith(".json")
    assert result.report_path.endswith(".md")
    assert (tmp_path / "results" / "state" / "it_run_last_timestamp.txt").exists()
    assert result.run_status == "completed"
    selection = json.loads((tmp_path / "results" / "reports" / "it_run_model_selection.json").read_text(encoding="utf-8"))
    assert "A" in selection or "B" in selection
    summary = json.loads((tmp_path / "results" / "reports" / "it_run_summary.json").read_text(encoding="utf-8"))
    assert "execution_diagnostics" in summary
    assert "dropped_reason_counts" in summary["execution_diagnostics"]
    assert "report_path" in summary
    assert Path(summary["report_path"]).exists()
    governance = json.loads((tmp_path / "results" / "reports" / "it_run_model_governance.json").read_text(encoding="utf-8"))
    assert "alerts" in governance


def test_orchestrator_handles_no_new_data_incremental_window(tmp_path):
    n = 30
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D"),
            "asset": ["A"] * n,
            "close": [100 + i * 0.1 for i in range(n)],
        }
    )
    csv_path = tmp_path / "market.csv"
    state_path = tmp_path / "state.txt"
    df.to_csv(csv_path, index=False)
    state_path.write_text("2025-01-01T00:00:00+00:00", encoding="utf-8")

    cfg = AppConfig()
    cfg.run_id = "it_no_data"
    cfg.data.source_type = "csv"
    cfg.data.csv_path = str(csv_path)
    cfg.data.incremental_mode = True
    cfg.data.incremental_state_path = str(state_path)
    cfg.execution.output_dir = str(tmp_path / "results")

    result = Orchestrator().run(cfg)
    assert result.run_status == "no_new_data"
    assert (tmp_path / "results" / "reports" / "it_no_data_summary.json").exists()
    assert result.model_selection_path.endswith(".json")
    assert result.model_governance_path.endswith(".json")
    assert result.report_path.endswith(".md")


def test_data_quality_reports_frequency_drift_and_missing_bars(tmp_path):
    base_dates = pd.date_range("2023-01-01", periods=40, freq="D")
    a_dates = base_dates.delete(10)  # introduce one missing bar in daily sequence
    c_dates = base_dates
    b_dates = pd.date_range("2023-01-01", periods=20, freq="2D")  # lower frequency

    df = pd.concat(
        [
            pd.DataFrame({"timestamp": a_dates, "asset": "A", "close": range(100, 100 + len(a_dates))}),
            pd.DataFrame({"timestamp": b_dates, "asset": "B", "close": range(200, 200 + len(b_dates))}),
            pd.DataFrame({"timestamp": c_dates, "asset": "C", "close": range(300, 300 + len(c_dates))}),
        ],
        ignore_index=True,
    )
    csv_path = tmp_path / "market_quality.csv"
    df.to_csv(csv_path, index=False)

    cfg = AppConfig()
    cfg.run_id = "it_quality"
    cfg.data.source_type = "csv"
    cfg.data.csv_path = str(csv_path)
    cfg.backtest.window_length = 10
    cfg.backtest.step_length = 5
    cfg.backtest.horizon = 1
    cfg.execution.output_dir = str(tmp_path / "results")
    cfg.execution.data_quality_freq_drift_tolerance = 0.2
    cfg.execution.data_quality_min_points_for_freq = 5

    result = Orchestrator().run(cfg)
    report = json.loads((tmp_path / "results" / "reports" / "it_quality_data_quality.json").read_text(encoding="utf-8"))

    assert result.run_status == "completed"
    assert report["inferred_base_freq_seconds"] == 86400
    assert "B" in report["assets_with_frequency_drift"]
    assert report["missing_bars_by_asset"]["A"] >= 1


def test_model_governance_history_persists_across_runs(tmp_path):
    n = 120
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D").tolist()
            + pd.date_range("2023-01-01", periods=n, freq="D").tolist(),
            "asset": ["A"] * n + ["B"] * n,
            "close": [100 + i * 0.05 for i in range(n)] + [200 + i * 0.02 for i in range(n)],
        }
    )
    csv_path = tmp_path / "market_governance.csv"
    df.to_csv(csv_path, index=False)

    cfg = AppConfig()
    cfg.data.source_type = "csv"
    cfg.data.csv_path = str(csv_path)
    cfg.backtest.window_length = 40
    cfg.backtest.step_length = 10
    cfg.backtest.horizon = 1
    cfg.execution.output_dir = str(tmp_path / "results")
    cfg.execution.governance_history_max_records = 1000

    cfg.run_id = "gov_run_1"
    r1 = Orchestrator().run(cfg)
    cfg.run_id = "gov_run_2"
    r2 = Orchestrator().run(cfg)

    history_path = tmp_path / "results" / "governance" / "model_stability_history.json"
    assert history_path.exists()
    history_payload = json.loads(history_path.read_text(encoding="utf-8"))
    history = history_payload.get("history", [])
    assert len(history) > 0
    run_ids = {x.get("run_id") for x in history}
    assert "gov_run_1" in run_ids
    assert "gov_run_2" in run_ids
    assert r1.model_governance_path.endswith(".json")
    assert r2.model_governance_path.endswith(".json")


def test_orchestrator_auto_selects_candidates_when_config_empty(tmp_path):
    n = 120
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D"),
            "asset": ["A"] * n,
            "close": [100 + i * 0.05 for i in range(n)],
        }
    )
    csv_path = tmp_path / "market_auto.csv"
    df.to_csv(csv_path, index=False)

    cfg = AppConfig()
    cfg.run_id = "auto_candidates_run"
    cfg.data.source_type = "csv"
    cfg.data.csv_path = str(csv_path)
    cfg.backtest.window_length = 40
    cfg.backtest.step_length = 10
    cfg.backtest.horizon = 1
    cfg.model.candidates = []
    cfg.execution.output_dir = str(tmp_path / "results")

    result = Orchestrator().run(cfg)
    assert result.run_status == "completed"
    summary = json.loads((tmp_path / "results" / "reports" / "auto_candidates_run_summary.json").read_text(encoding="utf-8"))
    assert len(summary.get("candidate_models", [])) > 0

