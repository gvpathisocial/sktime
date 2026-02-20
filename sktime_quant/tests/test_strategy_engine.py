from pathlib import Path

import pandas as pd

from sktime_quant.backtest.walkforward import WalkForwardEngine
from sktime_quant.config.schema import BacktestConfig, StrategyConfig
from sktime_quant.strategy.blender import blend_signals
from sktime_quant.strategy.classifier import predict_classifier_signal_at
from sktime_quant.strategy.rule_dsl import evaluate_rules_signal, load_rules_yaml, save_rules_yaml


def test_rule_dsl_eval_and_persist(tmp_path):
    rules = [
        {"name": "buy_rsi", "feature": "rsi_14", "operator": "<=", "value": 30, "signal": 1},
        {"name": "sell_rsi", "feature": "rsi_14", "operator": ">=", "value": 70, "signal": -1},
    ]
    signal = evaluate_rules_signal({"rsi_14": 25.0}, rules, chain="any")
    assert signal == 1
    path = tmp_path / "rules.yaml"
    save_rules_yaml(path, rules)
    loaded = load_rules_yaml(path)
    assert loaded == rules


def test_blend_signals_weighted_vote():
    out = blend_signals(
        forecast_signal=1,
        rule_signal=-1,
        classifier_signal=1,
        policy="weighted_vote",
        forecast_weight=0.2,
        rule_weight=0.1,
        classifier_weight=0.7,
        vote_threshold=0.1,
    )
    assert out == 1


def test_classifier_predict_signal_at():
    idx = pd.date_range("2023-01-01", periods=120, freq="D")
    close = pd.Series([100 + i * 0.2 for i in range(120)], index=idx)
    features = pd.DataFrame(
        {
            "rsi_14": [40 + (i % 20) for i in range(120)],
            "vol_20": [0.01 + (i % 5) * 0.001 for i in range(120)],
            "residual_z": [0.1 * ((i % 6) - 3) for i in range(120)],
        },
        index=idx,
    )
    sig, conf, status = predict_classifier_signal_at(
        feature_frame=features,
        close_series=close,
        cutoff=idx[100],
        classifier_type="decision_tree",
        min_train_samples=30,
        probability_threshold=0.5,
    )
    assert sig in {-1, 0, 1}
    assert 0.0 <= conf <= 1.0
    assert isinstance(status, str)


def test_walkforward_strategy_modes_emit_signal_columns():
    n = 220
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D"),
            "asset": ["A"] * n,
            "open": [100 + i * 0.05 for i in range(n)],
            "high": [101 + i * 0.05 for i in range(n)],
            "low": [99 + i * 0.05 for i in range(n)],
            "close": [100 + i * 0.05 for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        }
    )
    rules = [
        {"name": "buy_rsi", "feature": "rsi_14", "operator": "<=", "value": 55, "signal": 1},
        {"name": "sell_rsi", "feature": "rsi_14", "operator": ">=", "value": 70, "signal": -1},
    ]
    cfg = BacktestConfig(window_length=80, step_length=20, horizon=1)
    strategy_cfg = StrategyConfig(mode="blended", rules=rules, classifier_type="decision_tree")
    result = WalkForwardEngine().run(
        market=frame,
        model_names=["naive_last"],
        backtest_config=cfg,
        strategy_config=strategy_cfg,
    )
    assert not result.metrics.empty
    assert "strategy_mode" in result.metrics.columns
    assert set(result.metrics["strategy_mode"].astype(str).unique()) == {"blended"}
    assert "signal_rule" in result.fold_predictions.columns
    assert "signal_classifier" in result.fold_predictions.columns
    assert "signal_blended" in result.fold_predictions.columns
    assert "classifier_status" in result.fold_predictions.columns
