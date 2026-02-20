from pathlib import Path

from sktime_quant.reporting.run_report import write_run_report


def test_write_run_report_creates_markdown(tmp_path):
    report_path = tmp_path / "results" / "reports" / "abc_report.md"
    out = write_run_report(
        report_path=report_path,
        run_id="abc",
        summary={"run_status": "completed", "orders_path": "x.csv"},
        data_quality={"row_count": 10, "asset_count": 2},
        governance={"alert_count": 1, "selected_models": {"A": "naive_last"}},
    )
    assert out == str(report_path)
    assert report_path.exists()
    text = Path(out).read_text(encoding="utf-8")
    assert "Run Report `abc`" in text
    assert "run_status" in text
