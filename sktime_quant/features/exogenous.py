"""Exogenous feature alignment helpers."""

from __future__ import annotations

import pandas as pd


def lag_exogenous_one_step(exog: pd.DataFrame | None) -> pd.DataFrame | None:
    """Shift exogenous features by one step per asset.

    Input is expected to contain: timestamp, asset, and feature columns.
    Output keeps same timestamp index while each feature is lagged by one row
    within each asset group.
    """
    if exog is None:
        return None
    if exog.empty:
        return exog.copy()
    if "timestamp" not in exog.columns or "asset" not in exog.columns:
        raise ValueError("Exogenous frame must contain 'timestamp' and 'asset'")

    frame = exog.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    frame["asset"] = frame["asset"].astype(str)
    frame = frame.sort_values(["asset", "timestamp"]).reset_index(drop=True)

    feat_cols = [c for c in frame.columns if c not in {"timestamp", "asset"}]
    rows: list[pd.DataFrame] = []
    for asset, grp in frame.groupby("asset", sort=True):
        g = grp.copy()
        for col in feat_cols:
            g[col] = g[col].shift(1)
        g["asset"] = asset
        rows.append(g)
    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["asset", "timestamp"]).reset_index(drop=True)


def drop_exogenous_null_rows(exog: pd.DataFrame | None) -> pd.DataFrame | None:
    """Drop rows where any exogenous feature is null (per asset/timestamp row)."""
    if exog is None:
        return None
    if exog.empty:
        return exog.copy()
    if "timestamp" not in exog.columns or "asset" not in exog.columns:
        raise ValueError("Exogenous frame must contain 'timestamp' and 'asset'")

    frame = exog.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    frame["asset"] = frame["asset"].astype(str)
    feat_cols = [c for c in frame.columns if c not in {"timestamp", "asset"}]
    if not feat_cols:
        return frame.sort_values(["asset", "timestamp"]).reset_index(drop=True)

    frame = frame.dropna(subset=feat_cols)
    return frame.sort_values(["asset", "timestamp"]).reset_index(drop=True)


def encode_categorical_exogenous(exog: pd.DataFrame | None) -> pd.DataFrame | None:
    """One-hot encode categorical exogenous columns for model compatibility."""
    if exog is None:
        return None
    if exog.empty:
        return exog.copy()
    if "timestamp" not in exog.columns or "asset" not in exog.columns:
        raise ValueError("Exogenous frame must contain 'timestamp' and 'asset'")

    frame = exog.copy()
    feat_cols = [c for c in frame.columns if c not in {"timestamp", "asset"}]
    if not feat_cols:
        return frame

    numeric_cols = [c for c in feat_cols if pd.api.types.is_numeric_dtype(frame[c])]
    cat_cols = [c for c in feat_cols if c not in numeric_cols]

    out = frame[["timestamp", "asset"]].copy()
    if numeric_cols:
        out = pd.concat([out, frame[numeric_cols]], axis=1)
    if cat_cols:
        cat_frame = frame[cat_cols].fillna("missing").astype(str)
        dummies = pd.get_dummies(cat_frame, prefix=cat_cols, dtype=float)
        out = pd.concat([out, dummies], axis=1)

    return out.sort_values(["asset", "timestamp"]).reset_index(drop=True)
