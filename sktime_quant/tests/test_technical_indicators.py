import pandas as pd

from sktime_quant.features.technical_indicators import build_technical_indicators


def test_build_technical_indicators_outputs_expected_columns():
    n = 40
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
            "asset": ["A"] * n,
            "open": [100 + i * 0.1 for i in range(n)],
            "high": [101 + i * 0.1 for i in range(n)],
            "low": [99 + i * 0.1 for i in range(n)],
            "close": [100 + i * 0.1 for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        }
    )
    out = build_technical_indicators(frame)
    assert list(out.columns) == [
        "timestamp",
        "asset",
        "ret_1d",
        "sma_20",
        "ema_20",
        "rsi_14",
        "atr_14",
        "vol_20",
    ]
    assert len(out) == n
    assert out["asset"].nunique() == 1
