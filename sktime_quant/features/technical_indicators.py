"""Technical indicators for exogenous feature tables."""

from __future__ import annotations

import pandas as pd


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    return 100.0 - (100.0 / (1.0 + rs))


def build_technical_indicators(market: pd.DataFrame) -> pd.DataFrame:
    """Build per-asset technical indicators from OHLCV frame.

    Expected input columns: timestamp, asset, close
    Optional columns: open, high, low, volume
    """
    required = {"timestamp", "asset", "close"}
    missing = required - set(market.columns)
    if missing:
        raise ValueError(f"Missing required columns for technical indicators: {sorted(missing)}")

    frame = market.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).sort_values(["asset", "timestamp"])

    rows: list[pd.DataFrame] = []
    for asset, grp in frame.groupby("asset", sort=True):
        g = grp.copy()
        g["close"] = pd.to_numeric(g["close"], errors="coerce")
        g["ret_1d"] = g["close"].pct_change()
        g["sma_20"] = g["close"].rolling(20, min_periods=20).mean()
        g["ema_20"] = g["close"].ewm(span=20, adjust=False, min_periods=20).mean()
        g["vol_20"] = g["ret_1d"].rolling(20, min_periods=20).std()
        g["rsi_14"] = _rsi(g["close"], period=14)

        if {"high", "low", "close"}.issubset(g.columns):
            high = pd.to_numeric(g["high"], errors="coerce")
            low = pd.to_numeric(g["low"], errors="coerce")
            close_prev = g["close"].shift(1)
            tr = pd.concat(
                [(high - low), (high - close_prev).abs(), (low - close_prev).abs()],
                axis=1,
            ).max(axis=1)
            g["atr_14"] = tr.rolling(14, min_periods=14).mean()
        else:
            g["atr_14"] = pd.NA

        keep = [
            "timestamp",
            "asset",
            "ret_1d",
            "sma_20",
            "ema_20",
            "rsi_14",
            "atr_14",
            "vol_20",
        ]
        rows.append(g[keep])

    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["asset", "timestamp"]).reset_index(drop=True)

