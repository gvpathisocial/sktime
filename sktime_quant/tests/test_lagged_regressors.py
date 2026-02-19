import pandas as pd

from sktime_quant.features.lagged_regressors import build_lagged_regressors



def test_lagged_regressors_no_leakage_on_first_rows():
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="D"),
            "asset": ["A"] * 10,
            "close": [100, 101, 102, 101, 103, 104, 105, 106, 107, 108],
        }
    )
    out = build_lagged_regressors(df, lags=(1,), rolling_windows=(3,))
    first = out.iloc[0]
    assert pd.isna(first["close_lag_1"])
    assert pd.isna(first["ret_lag_1"])

