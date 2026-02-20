"""CSV and folder data loaders."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sktime_quant.config.schema import DataConfig


def _normalize_asset_hint(text: str | None) -> str | None:
    if text is None:
        return None
    value = str(text).strip()
    if not value:
        return None
    return value


def _guess_asset_from_path(path: Path) -> str:
    return path.stem.replace("_", ".")


def _to_numeric_if_present(frame: pd.DataFrame, cols: list[str]) -> None:
    for col in cols:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")


def _normalize_yahoo_like_frame(
    frame: pd.DataFrame, *, asset_hint: str | None = None
) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [str(c).strip() for c in out.columns]
    low_cols = {c.lower(): c for c in out.columns}

    # Canonical schema already present.
    if {"timestamp", "asset", "close"}.issubset(set(low_cols)):
        return out

    # Standard OHLCV with Date/ticker-style columns.
    date_col = None
    for c in out.columns:
        c_l = c.lower()
        if c_l in {"date", "datetime", "timestamp", "time"}:
            date_col = c
            break

    has_ohlcv = {"open", "high", "low", "close"}.issubset(set(low_cols))
    if date_col and has_ohlcv:
        canonical = pd.DataFrame()
        canonical["timestamp"] = out[date_col]
        canonical["open"] = out[low_cols["open"]]
        canonical["high"] = out[low_cols["high"]]
        canonical["low"] = out[low_cols["low"]]
        canonical["close"] = out[low_cols["close"]]
        if "volume" in low_cols:
            canonical["volume"] = out[low_cols["volume"]]

        if "asset" in low_cols:
            canonical["asset"] = out[low_cols["asset"]].astype(str)
        elif "ticker" in low_cols:
            canonical["asset"] = out[low_cols["ticker"]].astype(str)
        else:
            canonical["asset"] = _normalize_asset_hint(asset_hint) or "UNKNOWN"
        return canonical

    # Yahoo raw format from yfinance CSV export:
    # Price,Close,High,Low,Open,Volume
    # Ticker,^NSEI,^NSEI,^NSEI,^NSEI,^NSEI
    # Date,,,,,
    # 2010-01-04,...
    first_col = out.columns[0] if len(out.columns) else ""
    if first_col.lower() in {"price", "date"} and "close" in low_cols:
        temp = out.copy()
        temp = temp.rename(columns={first_col: "timestamp"})

        ticker_rows = temp[temp["timestamp"].astype(str).str.lower() == "ticker"]
        ticker = None
        if not ticker_rows.empty:
            ccol = low_cols.get("close", "close")
            ticker = str(ticker_rows.iloc[0][ccol]).strip()

        # Keep only data rows with parseable timestamps.
        temp["timestamp"] = pd.to_datetime(
            temp["timestamp"], format="%Y-%m-%d", utc=True, errors="coerce"
        )
        temp = temp.dropna(subset=["timestamp"]).copy()

        canonical = pd.DataFrame()
        canonical["timestamp"] = temp["timestamp"]
        if "open" in low_cols:
            canonical["open"] = temp[low_cols["open"]]
        if "high" in low_cols:
            canonical["high"] = temp[low_cols["high"]]
        if "low" in low_cols:
            canonical["low"] = temp[low_cols["low"]]
        canonical["close"] = temp[low_cols["close"]]
        if "volume" in low_cols:
            canonical["volume"] = temp[low_cols["volume"]]
        canonical["asset"] = (
            _normalize_asset_hint(ticker)
            or _normalize_asset_hint(asset_hint)
            or "UNKNOWN"
        )
        return canonical

    return out


def _coerce_market_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    _to_numeric_if_present(out, ["open", "high", "low", "close", "volume"])
    if "asset" in out.columns:
        out["asset"] = out["asset"].astype(str).str.strip()
        out["asset"] = out["asset"].replace({"": "UNKNOWN"})
        out["asset"] = out["asset"].fillna("UNKNOWN")
    return out


def load_market_csv(path: str | Path, *, asset_hint: str | None = None) -> pd.DataFrame:
    frame = pd.read_csv(path)
    normalized = _normalize_yahoo_like_frame(frame, asset_hint=asset_hint)
    normalized = _coerce_market_columns(normalized)
    return normalized


class CSVDataProvider:
    def load_history(self, config: DataConfig) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        if not config.csv_path:
            raise ValueError("csv_path is required for source_type='csv'")
        frame = load_market_csv(config.csv_path, asset_hint=Path(config.csv_path).stem)
        return frame, None


class FolderDataProvider:
    def load_history(self, config: DataConfig) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        if not config.folder_path:
            raise ValueError("folder_path is required for source_type='folder'")

        folder = Path(config.folder_path)
        files = sorted(folder.glob("*.csv"))
        if not files:
            raise ValueError("No csv files found in folder_path")

        frames = [
            load_market_csv(path, asset_hint=_guess_asset_from_path(path))
            for path in files
        ]
        market = pd.concat(frames, ignore_index=True)
        return market, None

