import pandas as pd

from sktime_quant.models.health import summarize_runtime_health


def test_runtime_health_marks_healthy_model():
    metrics = pd.DataFrame(
        [
            {
                "asset": "A",
                "model": "naive_last",
                "excluded_reason": "",
                "failure_rate": 0.0,
                "empirical_coverage": 0.98,
                "mae": 1.2,
                "successful_folds": 6,
            }
        ]
    )
    out = summarize_runtime_health(
        metrics, max_failure_rate=0.3, confidence_floor=0.95
    )
    assert len(out) == 1
    assert out.iloc[0]["runtime_health"] == "healthy"


def test_runtime_health_marks_unhealthy_for_init_failures():
    metrics = pd.DataFrame(
        [
            {
                "asset": "A",
                "model": "prophet",
                "excluded_reason": "model_init_failed: ImportError",
                "failure_rate": 1.0,
                "empirical_coverage": float("nan"),
                "mae": float("nan"),
                "successful_folds": 0,
            }
        ]
    )
    out = summarize_runtime_health(
        metrics, max_failure_rate=0.3, confidence_floor=0.95
    )
    assert out.iloc[0]["runtime_health"] == "unhealthy"
    assert out.iloc[0]["health_reason"] == "model_init_failed"

