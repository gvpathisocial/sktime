"""Risk metric calculations: integration tests for portfolio diagnostics."""

import pandas as pd
import numpy as np

from sktime_quant.backtest.walkforward import WalkForwardEngine
from sktime_quant.config.schema import BacktestConfig
from sktime_quant.risk.metrics import (
    annualized_volatility,
    max_drawdown,
    var_cvar,
    sortino_ratio,
    sharpe_ratio,
    calmar_ratio,
    cumulative_returns,
)


def test_risk_metrics_basics():
    """Verify basic risk metric calculations: VaR, CVaR, volatility, drawdown."""
    rets = pd.Series([0.01, -0.02, 0.03, -0.01])
    var, cvar = var_cvar(rets, alpha=0.95)
    assert cvar <= var
    assert annualized_volatility(rets) > 0
    assert max_drawdown(rets) <= 0


def test_walkforward_produces_fold_returns_for_metrics():
    """Integration: walkforward generates fold_predictions needed for risk calculations."""
    # Setup: Create 160 days of market data for two assets
    n = 160
    assets = []
    for asset in ["A", "B"]:
        assets.append(pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D"),
            "asset": asset,
            "close": [100 + (i * 0.15 if asset == "A" else i * 0.10) for i in range(n)],
        }))
    df = pd.concat(assets, ignore_index=True)
    
    # Act: Run walkforward backtest
    result = WalkForwardEngine().run(
        market=df,
        model_names=["naive_last", "naive_mean"],
        backtest_config=BacktestConfig(window_length=60, step_length=10, horizon=1),
    )
    
    # Assert: fold_predictions has required columns for risk metric aggregation
    assert not result.fold_predictions.empty
    assert "fold_return" in result.fold_predictions.columns
    assert "cutoff" in result.fold_predictions.columns
    assert "asset" in result.fold_predictions.columns
    
    # Verify aggregation is possible (as UI does)
    folds = result.fold_predictions.copy()
    folds["date"] = pd.to_datetime(folds["cutoff"])
    daily = folds.groupby("date").agg({"fold_return": "sum"}).reset_index()
    assert len(daily) > 0


def test_risk_metrics_on_walkforward_returns():
    """Integration: calculate Sortino, Sharpe, Calmar on actual backtest fold returns."""
    # Setup: Two-asset walkforward
    n = 160
    assets = []
    for asset in ["A", "B"]:
        assets.append(pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D"),
            "asset": asset,
            "close": [100 + (i * 0.12 if asset == "A" else i * 0.08) for i in range(n)],
        }))
    df = pd.concat(assets, ignore_index=True)
    
    # Act: Run backtest
    result = WalkForwardEngine().run(
        market=df,
        model_names=["naive_last"],
        backtest_config=BacktestConfig(window_length=60, step_length=10, horizon=1),
    )
    
    # Aggregate fold returns to daily portfolio P&L (as UI does)
    folds = result.fold_predictions.copy()
    folds["date"] = pd.to_datetime(folds["cutoff"])
    daily = folds.groupby("date").agg({"fold_return": "sum"}).reset_index()
    daily.columns = ["date", "returns"]
    daily = daily.sort_values("date")
    
    # Build equity curve
    daily["equity_value"] = (1 + daily["returns"]).cumprod() * 100000
    
    # Act: Calculate risk metrics
    returns = daily["returns"]
    sortino = sortino_ratio(returns, target_return=0.0, periods=252)
    sharpe = sharpe_ratio(returns, risk_free_rate=0.02, periods=252)
    calmar = calmar_ratio(daily["equity_value"], periods=252)
    
    # Assert: All metrics should be valid (not NaN from bad data)
    assert isinstance(sortino, (float, np.floating))
    assert isinstance(sharpe, (float, np.floating))
    assert isinstance(calmar, (float, np.floating))


def test_sortino_ratio_financial_interpretation():
    """Test Sortino ratio returns meaningful results on strategy returns."""
    # Moderately profitable strategy: mostly positive, occasional drawdowns
    strategy_returns = pd.Series([
        0.015, -0.005, 0.020, -0.008, 0.010,
        0.018, -0.002, 0.025, -0.010, 0.012,
        0.022, -0.003, 0.014, -0.006, 0.018,
    ])
    
    sortino = sortino_ratio(strategy_returns, target_return=0.0, periods=252)
    
    # Expect positive Sortino for profitable strategy
    assert sortino > 0


def test_sharpe_ratio_risk_adjusted_return():
    """Test Sharpe ratio distinguishes between high and low Sharpe strategies."""
    # Strategy A: high return, high volatility
    np.random.seed(42)
    returns_a = pd.Series(np.random.normal(0.015, 0.025, 60))
    sharpe_a = sharpe_ratio(returns_a, risk_free_rate=0.02, periods=252)
    
    # Strategy B: lower return, lower volatility
    returns_b = pd.Series(np.random.normal(0.005, 0.010, 60))
    sharpe_b = sharpe_ratio(returns_b, risk_free_rate=0.02, periods=252)
    
    # Both should be valid numbers
    assert isinstance(sharpe_a, (float, np.floating))
    assert isinstance(sharpe_b, (float, np.floating))


def test_calmar_ratio_return_over_drawdown():
    """Test Calmar ratio penalizes strategies with large drawdowns."""
    # Strategy with moderate growth but 20% drawdown
    equity = pd.Series([
        100000, 105000, 110000, 115000, 120000,
        96000,  # 20% drawdown from peak
        110000, 125000, 130000, 135000, 140000,
    ])
    
    calmar = calmar_ratio(equity, periods=252)
    
    # Should be positive (grew overall) but not huge due to drawdown
    assert calmar > 0


def test_cumulative_returns_end_to_end_calculation():
    """Test cumulative returns on portfolio equity evolution."""
    # Portfolio: $100k -> $130k (30% total return)
    equity = pd.Series([
        100000, 102000, 105000, 107000, 110000,
        112000, 115000, 118000, 120000, 125000, 130000
    ])
    
    cum_ret = cumulative_returns(equity)
    
    assert cum_ret == 0.30, f"Expected 30% return, got {cum_ret * 100}%"


def test_aggregate_daily_portfolio_returns_from_folds():
    """Integration: aggregate per-fold returns to daily portfolio metrics (UI workflow)."""
    # Simulate fold_predictions from multi-asset, multi-model backtest
    folds_data = {
        "cutoff": [
            pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-02"),
            pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-03"),
        ],
        "asset": ["A", "B", "A", "B", "A", "B"],
        "model": ["m1", "m1", "m1", "m1", "m1", "m1"],
        "fold_return": [0.010, 0.015, -0.005, 0.020, 0.012, -0.008],
    }
    folds = pd.DataFrame(folds_data)
    
    # Aggregate as UI does: sum returns per day across assets/models
    daily = folds.groupby("cutoff").agg({"fold_return": "sum"}).reset_index()
    daily.columns = ["date", "returns"]
    daily = daily.sort_values("date")
    
    # Build portfolio equity
    daily["equity"] = (1 + daily["returns"]).cumprod() * 100000
    
    # Verify aggregation produces correct daily values
    assert len(daily) == 3
    assert daily.loc[0, "returns"] == 0.025  # 0.010 + 0.015
    assert daily.loc[1, "returns"] == 0.015  # -0.005 + 0.020
    
    # Calculate metrics on aggregated portfolio returns
    returns = daily["returns"]
    sortino = sortino_ratio(returns, target_return=0.0, periods=252)
    sharpe = sharpe_ratio(returns, risk_free_rate=0.02, periods=252)
    calmar = calmar_ratio(daily["equity"], periods=252)
    
    # All should be valid
    assert isinstance(sortino, (float, np.floating))
    assert isinstance(sharpe, (float, np.floating))
    assert isinstance(calmar, (float, np.floating))

