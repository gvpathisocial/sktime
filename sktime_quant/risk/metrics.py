"""Risk metric calculations for strategy and portfolio diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd



def var_cvar(returns: pd.Series, alpha: float = 0.95) -> tuple[float, float]:
    if returns.empty:
        return 0.0, 0.0
    q = float(returns.quantile(1 - alpha))
    tail = returns[returns <= q]
    cvar = float(tail.mean()) if not tail.empty else q
    return q, cvar



def annualized_volatility(returns: pd.Series, periods: int = 252) -> float:
    if returns.empty:
        return 0.0
    return float(returns.std(ddof=0) * np.sqrt(periods))



def max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    equity = (1 + returns.fillna(0)).cumprod()
    rolling_peak = equity.cummax()
    drawdown = equity / rolling_peak - 1
    return float(drawdown.min())



def turnover(previous: pd.Series, target: pd.Series) -> float:
    prev = previous.reindex(target.index).fillna(0.0)
    return float((target - prev).abs().sum())


def sortino_ratio(returns: pd.Series, target_return: float = 0.0, periods: int = 252) -> float:
    """
    Calculate Sortino ratio: annualized excess return / annualized downside deviation.
    
    :param returns: Series of returns
    :param target_return: Minimum acceptable return (default 0.0)
    :param periods: Periods per year (default 252 for daily)
    :return: Sortino ratio (float)
    """
    if returns.empty or len(returns) < 2:
        return np.nan
    
    excess = returns - (target_return / periods)
    downside = excess[excess < 0]
    
    if downside.empty:
        # No downside risk; if positive returns, very high Sortino
        if (returns > 0).any():
            return np.inf
        return np.nan
    
    # Use ddof=0 for small samples to avoid NaN from std of single value
    downside_std = float(downside.std(ddof=min(1, len(downside) - 1)) or 0.0)
    if downside_std == 0:
        return np.inf if returns.mean() > 0 else np.nan
    
    excess_return = returns.mean() * periods
    annualized_downside = downside_std * np.sqrt(periods)
    
    return float((excess_return - target_return) / annualized_downside) if annualized_downside > 0 else np.nan


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02, periods: int = 252) -> float:
    """
    Calculate Sharpe ratio: (annualized return - risk-free rate) / annualized volatility.
    
    :param returns: Series of returns
    :param risk_free_rate: Annual risk-free rate (default 0.02)
    :param periods: Periods per year (default 252 for daily)
    :return: Sharpe ratio (float)
    """
    if returns.empty or len(returns) < 2:
        return np.nan
    
    excess = returns - (risk_free_rate / periods)
    excess_return = excess.mean() * periods
    volatility = returns.std(ddof=1) * np.sqrt(periods)
    
    # Handle near-zero volatility
    if volatility < 1e-10:
        return np.nan if abs(excess_return) < 1e-10 else np.inf
    
    return float(excess_return / volatility)


def calmar_ratio(equity_values: pd.Series, periods: int = 252) -> float:
    """
    Calculate Calmar ratio: annualized return / absolute max drawdown.
    
    :param equity_values: Series of equity/cumulative returns
    :param periods: Periods per year (default 252 for daily)
    :return: Calmar ratio (float)
    """
    if equity_values.empty or len(equity_values) < 2:
        return np.nan
    
    returns = equity_values.pct_change().dropna()
    if returns.empty:
        return np.nan
    
    annual_return = returns.mean() * periods
    dd = max_drawdown(returns)
    
    if dd == 0 or np.isnan(dd):
        return np.nan
    
    return float(annual_return / abs(dd))


def cumulative_returns(equity_values: pd.Series) -> float:
    """
    Calculate total cumulative return from starting to ending equity.
    
    :param equity_values: Series of equity values
    :return: Cumulative return as decimal (float)
    """
    if equity_values.empty or len(equity_values) < 2:
        return 0.0
    
    start_val = equity_values.iloc[0]
    end_val = equity_values.iloc[-1]
    
    if start_val == 0:
        return np.nan
    
    return float((end_val - start_val) / start_val)

