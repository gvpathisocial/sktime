import time
from dataclasses import dataclass

from sktime_quant.config.schema import AppConfig
from sktime_quant.pipelines import studio_runtime


@dataclass
class _DummyResult:
    summary_path: str
    orders_path: str
    data_quality_path: str
    model_selection_path: str
    model_governance_path: str
    report_path: str
    run_status: str


def test_background_run_registry_completed(monkeypatch, tmp_path):
    cfg = AppConfig()
    cfg.run_id = "bg_ok"
    cfg.execution.output_dir = str(tmp_path / "results")

    def _fake_run(self, cfg, progress_hook=None):
        if progress_hook:
            progress_hook({"stage": "start", "event": "run_start"})
        return _DummyResult(
            summary_path="s.json",
            orders_path="o.csv",
            data_quality_path="dq.json",
            model_selection_path="ms.json",
            model_governance_path="mg.json",
            report_path="r.md",
            run_status="completed",
        )

    monkeypatch.setattr("sktime_quant.pipelines.studio_runtime.Orchestrator.run", _fake_run)
    run_id = studio_runtime.start_background_run(cfg, "profiles/x.yaml")
    for _ in range(40):
        row = studio_runtime.get_run(cfg.execution.output_dir, run_id)
        if row and row.get("status") == "completed":
            break
        time.sleep(0.05)
    row = studio_runtime.get_run(cfg.execution.output_dir, run_id)
    assert row is not None
    assert row["status"] == "completed"
    assert row["report_path"] == "r.md"
    assert isinstance(row.get("events"), list)


def test_background_run_registry_failed(monkeypatch, tmp_path):
    cfg = AppConfig()
    cfg.run_id = "bg_fail"
    cfg.execution.output_dir = str(tmp_path / "results")

    def _boom(self, cfg, progress_hook=None):
        raise RuntimeError("boom")

    monkeypatch.setattr("sktime_quant.pipelines.studio_runtime.Orchestrator.run", _boom)
    run_id = studio_runtime.start_background_run(cfg, "profiles/x.yaml")
    for _ in range(40):
        row = studio_runtime.get_run(cfg.execution.output_dir, run_id)
        if row and row.get("status") == "failed":
            break
        time.sleep(0.05)
    row = studio_runtime.get_run(cfg.execution.output_dir, run_id)
    assert row is not None
    assert row["status"] == "failed"
    assert "boom" in str(row.get("error", ""))
