"""Lag-based exogenous feature generation."""

from __future__ import annotations

import pandas as pd

from sktime_quant.data.schema import validate_market_frame



def build_lagged_regressors(
    market: pd.DataFrame,
    lags: tuple[int, ...] = (1, 2, 5),
    rolling_windows: tuple[int, ...] = (5, 20),
) -> pd.DataFrame:
    frame = validate_market_frame(market)
    rows: list[pd.DataFrame] = []

    for asset, grp in frame.groupby("asset", sort=True):
        g = grp.sort_values("timestamp").copy()
        g["ret_1"] = g["close"].pct_change()
        for lag in lags:
            g[f"close_lag_{lag}"] = g["close"].shift(lag)
            g[f"ret_lag_{lag}"] = g["ret_1"].shift(lag)

        for window in rolling_windows:
            shifted = g["ret_1"].shift(1)
            g[f"ret_roll_mean_{window}"] = shifted.rolling(window).mean()
            g[f"ret_roll_std_{window}"] = shifted.rolling(window).std()

        g["asset"] = asset
        rows.append(g)

    out = pd.concat(rows, ignore_index=True)
    return out.drop(columns=["ret_1"]).sort_values(["asset", "timestamp"]).reset_index(
        drop=True
    )

