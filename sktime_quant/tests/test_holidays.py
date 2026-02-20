import pandas as pd

from sktime_quant.data.holidays import build_asset_holiday_frames


def test_build_asset_holiday_frames_maps_assets_to_markets():
    h_nse = pd.DataFrame(
        {
            "ds": pd.to_datetime(["2024-01-26"]),
            "holiday": ["Republic Day"],
            "lower_window": [0],
            "upper_window": [0],
        }
    )
    h_nyse = pd.DataFrame(
        {
            "ds": pd.to_datetime(["2024-07-04"]),
            "holiday": ["Independence Day"],
            "lower_window": [0],
            "upper_window": [0],
        }
    )
    out = build_asset_holiday_frames(
        assets=["^NSEI", "AAPL"],
        market_by_asset={"^NSEI": "NSE", "AAPL": "NYSE"},
        holidays_by_market={"NSE": h_nse, "NYSE": h_nyse},
    )
    assert "^NSEI" in out
    assert "AAPL" in out
    assert out["^NSEI"].iloc[0]["holiday"] == "Republic Day"
    assert out["AAPL"].iloc[0]["holiday"] == "Independence Day"
