"""Yahoo data ingestion pipeline with optional Timescale upsert."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from sktime_quant.data.connectors.csv_loader import load_market_csv
from sktime_quant.features.technical_indicators import build_technical_indicators
from sktime_quant.features.zone_labels import build_zone_labels


@dataclass(slots=True)
class YahooIngestResult:
    symbols_requested: int
    symbols_downloaded: int
    rows_written_csv: int
    rows_upserted_timescale: int
    rows_upserted_exog: int
    errors: list[str]


def read_symbols(symbols_file: str | Path) -> list[str]:
    path = Path(symbols_file)
    if not path.exists():
        raise FileNotFoundError(f"symbols file not found: {path}")
    symbols: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        symbols.append(s)
    # deterministic unique symbols
    return sorted(set(symbols))


def _normalize_yf_download(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["timestamp", "asset", "open", "high", "low", "close", "volume"])
    out = raw.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [str(c[0]).strip().lower() for c in out.columns]
    else:
        out.columns = [str(c).strip().lower() for c in out.columns]
    out = out.reset_index()
    out.columns = [str(c).strip().lower() for c in out.columns]
    if "date" not in out.columns and "datetime" in out.columns:
        out = out.rename(columns={"datetime": "date"})
    if "date" not in out.columns:
        out = out.rename(columns={out.columns[0]: "date"})

    mapped = pd.DataFrame()
    mapped["timestamp"] = pd.to_datetime(out["date"], utc=True, errors="coerce")
    mapped["asset"] = symbol
    for col in ["open", "high", "low", "close", "volume"]:
        if col in out.columns:
            mapped[col] = pd.to_numeric(out[col], errors="coerce")
    mapped = mapped.dropna(subset=["timestamp", "close"])
    mapped = mapped.sort_values("timestamp").drop_duplicates(["asset", "timestamp"], keep="last")
    return mapped.reset_index(drop=True)


def _last_timestamp_from_csv(path: Path) -> pd.Timestamp | None:
    if not path.exists():
        return None
    frame = load_market_csv(path, asset_hint=path.stem.replace("_", "."))
    if frame.empty or "timestamp" not in frame.columns:
        return None
    ts = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dropna()
    if ts.empty:
        return None
    return pd.Timestamp(ts.max())


def _download_symbol(symbol: str, start: str, end: str | None = None) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError("yfinance is required for Yahoo ingestion. Install yfinance.") from exc

    raw = yf.download(symbol, start=start, end=end, auto_adjust=False, progress=False)
    return _normalize_yf_download(raw, symbol=symbol)


def _write_symbol_csv(path: Path, fresh: pd.DataFrame) -> int:
    if fresh.empty:
        return 0
    if path.exists():
        existing = load_market_csv(path, asset_hint=path.stem.replace("_", "."))
        combined = pd.concat([existing, fresh], ignore_index=True)
    else:
        combined = fresh.copy()

    combined = combined.sort_values(["asset", "timestamp"]).drop_duplicates(
        ["asset", "timestamp"], keep="last"
    )
    combined.to_csv(path, index=False)
    return int(len(fresh))


def _upsert_timescale(
    frame: pd.DataFrame,
    *,
    connection_uri: str,
    market_table: str = "public.market_data",
) -> int:
    if frame.empty:
        return 0
    try:
        from sqlalchemy import create_engine, text
    except ImportError as exc:
        raise ImportError("sqlalchemy is required for Timescale upsert.") from exc

    cols = ["timestamp", "asset", "open", "high", "low", "close", "volume"]
    payload = frame.copy()
    for c in cols:
        if c not in payload.columns:
            payload[c] = None
    payload = payload[cols].copy()
    payload["asset_class"] = payload["asset"].astype(str).map(
        lambda s: "index" if s.startswith("^") else "stock"
    )

    insert_sql = text(
        f"""
        INSERT INTO {market_table}
            (timestamp, asset, open, high, low, close, volume, asset_class)
        VALUES
            (:timestamp, :asset, :open, :high, :low, :close, :volume, :asset_class)
        ON CONFLICT (asset, timestamp)
        DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            asset_class = EXCLUDED.asset_class
        """
    )

    records = payload.to_dict(orient="records")
    engine = create_engine(connection_uri)
    with engine.begin() as conn:
        conn.execute(insert_sql, records)
    return int(len(records))


def _upsert_exog_timescale(
    frame: pd.DataFrame,
    *,
    connection_uri: str,
    exog_table: str = "public.exog_data",
) -> int:
    if frame.empty:
        return 0
    try:
        from sqlalchemy import create_engine, text
    except ImportError as exc:
        raise ImportError("sqlalchemy is required for Timescale upsert.") from exc

    cols = [
        "timestamp",
        "asset",
        "ret_1d",
        "sma_20",
        "ema_20",
        "rsi_14",
        "atr_14",
        "vol_20",
        "context_zone",
        "trend_zone",
        "trade_zone",
    ]
    payload = frame.copy()
    for c in cols:
        if c not in payload.columns:
            payload[c] = None
    payload = payload[cols].copy()
    payload = payload.dropna(subset=["timestamp", "asset"])
    payload = payload.sort_values(["asset", "timestamp"]).drop_duplicates(["asset", "timestamp"])

    insert_sql = text(
        f"""
        INSERT INTO {exog_table}
            (timestamp, asset, ret_1d, sma_20, ema_20, rsi_14, atr_14, vol_20, context_zone, trend_zone, trade_zone)
        VALUES
            (:timestamp, :asset, :ret_1d, :sma_20, :ema_20, :rsi_14, :atr_14, :vol_20, :context_zone, :trend_zone, :trade_zone)
        ON CONFLICT (asset, timestamp)
        DO UPDATE SET
            ret_1d = EXCLUDED.ret_1d,
            sma_20 = EXCLUDED.sma_20,
            ema_20 = EXCLUDED.ema_20,
            rsi_14 = EXCLUDED.rsi_14,
            atr_14 = EXCLUDED.atr_14,
            vol_20 = EXCLUDED.vol_20,
            context_zone = EXCLUDED.context_zone,
            trend_zone = EXCLUDED.trend_zone,
            trade_zone = EXCLUDED.trade_zone
        """
    )

    records = payload.to_dict(orient="records")
    engine = create_engine(connection_uri)
    with engine.begin() as conn:
        conn.execute(insert_sql, records)
    return int(len(records))


def run_yahoo_ingestion(
    *,
    symbols_file: str | Path,
    output_folder: str | Path,
    connection_uri: str | None = None,
    market_table: str = "public.market_data",
    exog_table: str = "public.exog_data",
    write_exog: bool = False,
    zone_schema: dict[str, float] | None = None,
    full_start_date: str = "2010-01-01",
    incremental_lookback_days: int = 7,
) -> YahooIngestResult:
    symbols = read_symbols(symbols_file)
    out_dir = Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    csv_rows = 0
    db_rows = 0
    exog_rows = 0
    errors: list[str] = []
    today = datetime.now(UTC).date().isoformat()

    for symbol in symbols:
        file_name = f"{symbol.replace('.', '_')}.csv"
        path = out_dir / file_name

        last_ts = _last_timestamp_from_csv(path)
        if last_ts is None:
            start = full_start_date
        else:
            start_ts = (last_ts - timedelta(days=max(1, int(incremental_lookback_days)))).date()
            start = start_ts.isoformat()

        try:
            fresh = _download_symbol(symbol=symbol, start=start, end=today)
            if fresh.empty:
                continue
            downloaded += 1
            csv_rows += _write_symbol_csv(path, fresh)
            if connection_uri:
                db_rows += _upsert_timescale(
                    fresh,
                    connection_uri=connection_uri,
                    market_table=market_table,
                )
                if write_exog:
                    exog = build_technical_indicators(fresh)
                    zones = build_zone_labels(fresh, schema=zone_schema)
                    exog = exog.merge(zones, on=["timestamp", "asset"], how="left")
                    exog_rows += _upsert_exog_timescale(
                        exog,
                        connection_uri=connection_uri,
                        exog_table=exog_table,
                    )
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")

    return YahooIngestResult(
        symbols_requested=len(symbols),
        symbols_downloaded=downloaded,
        rows_written_csv=csv_rows,
        rows_upserted_timescale=db_rows,
        rows_upserted_exog=exog_rows,
        errors=errors,
    )
