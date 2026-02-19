import pandas as pd

from sktime_quant.data.schema import validate_market_frame



def test_validate_market_frame_success():
    df = pd.DataFrame(
        {
            "timestamp": ["2024-01-01", "2024-01-02"],
            "asset": ["A", "A"],
            "close": [100.0, 101.0],
        }
    )
    out = validate_market_frame(df)
    assert list(out.columns) == ["timestamp", "asset", "close"]
    assert str(out["timestamp"].dtype).startswith("datetime64")

