from sktime_quant.ui.artifact_diff import (
    build_governance_alert_diff,
    build_model_selection_diff,
    build_summary_diff,
)


def test_build_summary_diff_has_expected_metrics():
    a = {
        "governance_alert_count": 1,
        "run_status": "completed",
        "allocation_diagnostics": {"turnover": 0.2, "max_weight": 0.3, "total_weight": 0.95},
        "execution_diagnostics": {"executed_order_count": 10, "total_order_notional": 5000},
    }
    b = {
        "governance_alert_count": 2,
        "run_status": "completed",
        "allocation_diagnostics": {"turnover": 0.25, "max_weight": 0.35, "total_weight": 0.96},
        "execution_diagnostics": {"executed_order_count": 12, "total_order_notional": 7000},
    }
    diff = build_summary_diff(a, b)
    assert "metric" in diff.columns
    assert "delta" in diff.columns
    alert_row = diff[diff["metric"] == "governance_alert_count"].iloc[0]
    assert alert_row["delta"] == 1


def test_build_model_selection_diff_detects_changes():
    a = {"A": [{"model": "naive_last", "selected": True}], "B": [{"model": "theta", "selected": True}]}
    b = {"A": [{"model": "theta", "selected": True}], "B": [{"model": "theta", "selected": True}]}
    diff = build_model_selection_diff(a, b)
    changed_a = bool(diff[diff["asset"] == "A"]["changed"].iloc[0])
    changed_b = bool(diff[diff["asset"] == "B"]["changed"].iloc[0])
    assert changed_a is True
    assert changed_b is False


def test_build_governance_alert_diff_by_type():
    a = {"alerts": [{"type": "low_coverage"}, {"type": "high_failure_rate"}]}
    b = {"alerts": [{"type": "low_coverage"}, {"type": "low_coverage"}]}
    diff = build_governance_alert_diff(a, b)
    low_cov = diff[diff["alert_type"] == "low_coverage"].iloc[0]
    high_fail = diff[diff["alert_type"] == "high_failure_rate"].iloc[0]
    assert low_cov["delta"] == 1
    assert high_fail["delta"] == -1
