"""Canonical market data schema validation and coercion."""

from __future__ import annotations

import pandas as pd

REQUIRED_MARKET_COLUMNS = ["timestamp", "asset", "close"]
OPTIONAL_MARKET_COLUMNS = ["open", "high", "low", "volume", "asset_class"]



def _ensure_columns(df: pd.DataFrame, required: list[str]) -> None:
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")



def validate_market_frame(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        raise TypeError("market frame must be a pandas DataFrame")
    _ensure_columns(df, REQUIRED_MARKET_COLUMNS)

    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    if out["timestamp"].isna().any():
        raise ValueError("timestamp contains invalid values")

    out["asset"] = out["asset"].astype(str)
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    if out["close"].isna().any():
        raise ValueError("close contains invalid numeric values")

    keep = REQUIRED_MARKET_COLUMNS + [
        c for c in OPTIONAL_MARKET_COLUMNS if c in out.columns
    ]
    out = out[keep].sort_values(["asset", "timestamp"]).reset_index(drop=True)
    return out



def validate_exogenous_frame(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None:
        return None
    if not isinstance(df, pd.DataFrame):
        raise TypeError("exogenous frame must be a pandas DataFrame")
    _ensure_columns(df, ["timestamp", "asset"])
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    if out["timestamp"].isna().any():
        raise ValueError("exogenous timestamp contains invalid values")
    out["asset"] = out["asset"].astype(str)
    return out.sort_values(["asset", "timestamp"]).reset_index(drop=True)

