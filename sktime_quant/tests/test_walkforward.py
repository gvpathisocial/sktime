import pandas as pd

from sktime_quant.backtest.walkforward import WalkForwardEngine
from sktime_quant.config.schema import BacktestConfig



def test_walkforward_returns_best_model_for_asset():
    n = 160
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D"),
            "asset": ["A"] * n,
            "close": [100 + (i * 0.1) for i in range(n)],
        }
    )
    result = WalkForwardEngine().run(
        market=df,
        model_names=["naive_last", "naive_mean"],
        backtest_config=BacktestConfig(window_length=60, step_length=10, horizon=1),
    )
    assert "A" in result.best_models
    assert not result.metrics.empty
    assert "empirical_coverage" in result.metrics.columns
    assert "failure_rate" in result.metrics.columns
    assert "objective" in result.metrics.columns
    assert "signal" in result.fold_predictions.columns
    assert "interval_source" in result.fold_predictions.columns
    assert "A" in result.selection_rationale
    assert any(r.get("selected") for r in result.selection_rationale["A"])


def test_walkforward_auto_excludes_bad_model_name():
    n = 160
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D"),
            "asset": ["A"] * n,
            "close": [100 + (i * 0.1) for i in range(n)],
        }
    )
    result = WalkForwardEngine().run(
        market=df,
        model_names=["naive_last", "definitely_unknown_model"],
        backtest_config=BacktestConfig(window_length=60, step_length=10, horizon=1),
    )
    excluded = result.metrics[result.metrics["model"] == "definitely_unknown_model"]
    assert not excluded.empty
    assert bool(excluded["excluded"].iloc[0]) is True


def test_walkforward_supports_policy_and_objective_selection():
    n = 160
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D"),
            "asset": ["A"] * n,
            "close": [100 + (i * 0.1) for i in range(n)],
        }
    )
    cfg = BacktestConfig(
        window_length=60,
        step_length=10,
        horizon=1,
        strategy_policy="threshold",
        signal_threshold=0.05,
        objective="sortino",
    )
    result = WalkForwardEngine().run(
        market=df,
        model_names=["naive_last", "naive_mean"],
        backtest_config=cfg,
    )
    assert not result.metrics.empty
    assert set(result.metrics["objective"].unique()) == {"sortino"}


def test_tie_break_prefers_higher_coverage_when_score_ties():
    engine = WalkForwardEngine()
    frame = pd.DataFrame(
        [
            {
                "asset": "A",
                "model": "m1",
                "risk_adjusted_score": 1.0,
                "empirical_coverage": 0.90,
                "failure_rate": 0.0,
                "max_drawdown": 0.1,
                "mae": 1.0,
            },
            {
                "asset": "A",
                "model": "m2",
                "risk_adjusted_score": 1.0,
                "empirical_coverage": 0.95,
                "failure_rate": 0.0,
                "max_drawdown": 0.1,
                "mae": 1.0,
            },
        ]
    )
    ranked = engine._sort_candidates(frame)
    assert ranked.iloc[0]["model"] == "m2"

