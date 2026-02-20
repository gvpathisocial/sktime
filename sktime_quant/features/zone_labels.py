"""Categorical zone labeling for exogenous features."""

from __future__ import annotations

import pandas as pd


DEFAULT_ZONE_SCHEMA: dict[str, float] = {
    "trend_up_return": 0.002,
    "trend_down_return": -0.002,
    "vol_high": 0.03,
    "vol_low": 0.01,
    "no_trade_abs_return": 0.001,
}


def build_zone_labels(
    market: pd.DataFrame, schema: dict[str, float] | None = None
) -> pd.DataFrame:
    """Build categorical zone labels from market data.

    Returns columns:
    - timestamp
    - asset
    - context_zone
    - trend_zone
    - trade_zone
    """
    cfg = dict(DEFAULT_ZONE_SCHEMA)
    if schema:
        cfg.update(schema)

    required = {"timestamp", "asset", "close"}
    missing = required - set(market.columns)
    if missing:
        raise ValueError(f"Missing required columns for zone labels: {sorted(missing)}")

    frame = market.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "close"])
    frame = frame.sort_values(["asset", "timestamp"]).reset_index(drop=True)

    out_rows: list[pd.DataFrame] = []
    for asset, grp in frame.groupby("asset", sort=True):
        g = grp.copy()
        g["ret_1d"] = g["close"].pct_change()
        g["vol_20"] = g["ret_1d"].rolling(20, min_periods=20).std()

        g["context_zone"] = "normal_vol"
        g.loc[g["vol_20"] >= float(cfg["vol_high"]), "context_zone"] = "high_vol"
        g.loc[g["vol_20"] <= float(cfg["vol_low"]), "context_zone"] = "low_vol"

        g["trend_zone"] = "sideways"
        g.loc[g["ret_1d"] >= float(cfg["trend_up_return"]), "trend_zone"] = "trend_up"
        g.loc[g["ret_1d"] <= float(cfg["trend_down_return"]), "trend_zone"] = "trend_down"

        g["trade_zone"] = "trade_zone"
        g.loc[g["ret_1d"].abs() <= float(cfg["no_trade_abs_return"]), "trade_zone"] = (
            "no_trade_zone"
        )
        # warmup rows default to no_trade_zone, as they are uncertain by construction
        g.loc[g["ret_1d"].isna(), "trade_zone"] = "no_trade_zone"

        out_rows.append(g[["timestamp", "asset", "context_zone", "trend_zone", "trade_zone"]])

    out = pd.concat(out_rows, ignore_index=True)
    return out.sort_values(["asset", "timestamp"]).reset_index(drop=True)

