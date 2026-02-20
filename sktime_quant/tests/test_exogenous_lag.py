import pandas as pd

from sktime_quant.features.exogenous import (
    drop_exogenous_null_rows,
    encode_categorical_exogenous,
    lag_exogenous_one_step,
)


def test_lag_exogenous_one_step_by_asset():
    exog = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-01", "2024-01-02"], utc=True
            ),
            "asset": ["A", "A", "B", "B"],
            "feat_1": [10.0, 11.0, 20.0, 21.0],
        }
    )
    out = lag_exogenous_one_step(exog)
    a = out[out["asset"] == "A"].sort_values("timestamp")
    b = out[out["asset"] == "B"].sort_values("timestamp")
    assert pd.isna(a.iloc[0]["feat_1"])
    assert a.iloc[1]["feat_1"] == 10.0
    assert pd.isna(b.iloc[0]["feat_1"])
    assert b.iloc[1]["feat_1"] == 20.0


def test_drop_exogenous_null_rows_removes_warmup_nulls():
    exog = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03"], utc=True
            ),
            "asset": ["A", "A", "A"],
            "feat_1": [None, 1.0, 2.0],
            "feat_2": [None, 10.0, 20.0],
        }
    )
    out = drop_exogenous_null_rows(exog)
    assert len(out) == 2
    assert out["timestamp"].min() == pd.Timestamp("2024-01-02", tz="UTC")


def test_encode_categorical_exogenous_one_hot():
    exog = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True),
            "asset": ["A", "A"],
            "context_zone": ["high_vol", "normal_vol"],
            "ret_1d": [0.01, -0.02],
        }
    )
    out = encode_categorical_exogenous(exog)
    assert "ret_1d" in out.columns
    assert "context_zone_high_vol" in out.columns
    assert "context_zone_normal_vol" in out.columns
