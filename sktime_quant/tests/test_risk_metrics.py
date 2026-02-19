import pandas as pd

from sktime_quant.risk.metrics import annualized_volatility, max_drawdown, var_cvar



def test_risk_metrics_basics():
    rets = pd.Series([0.01, -0.02, 0.03, -0.01])
    var, cvar = var_cvar(rets, alpha=0.95)
    assert cvar <= var
    assert annualized_volatility(rets) > 0
    assert max_drawdown(rets) <= 0

