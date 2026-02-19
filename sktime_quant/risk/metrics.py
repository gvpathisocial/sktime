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

