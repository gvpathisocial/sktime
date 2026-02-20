import pandas as pd

from sktime_quant.features.zone_labels import build_zone_labels


def test_build_zone_labels_outputs_required_columns():
    n = 30
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="D"),
            "asset": ["A"] * n,
            "close": [100 + i * 0.5 for i in range(n)],
        }
    )
    out = build_zone_labels(frame)
    assert list(out.columns) == [
        "timestamp",
        "asset",
        "context_zone",
        "trend_zone",
        "trade_zone",
    ]
    assert len(out) == n
    assert out["trade_zone"].isin(["trade_zone", "no_trade_zone"]).all()
