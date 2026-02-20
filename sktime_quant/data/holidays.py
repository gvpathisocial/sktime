"""Holiday-table data access and asset mapping helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class HolidayConfig:
    connection_uri: str
    holiday_table: str = "public.holiday_calendar"


def load_holidays_by_market(
    cfg: HolidayConfig,
    markets: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    if not markets:
        return {}
    try:
        from sqlalchemy import create_engine, text
    except ImportError as exc:
        raise ImportError("sqlalchemy is required for holiday-table loading") from exc

    engine = create_engine(cfg.connection_uri)
    query = text(
        f"""
        SELECT holiday_date, market, holiday_name, lower_window, upper_window
        FROM {cfg.holiday_table}
        WHERE market = ANY(:markets)
          AND holiday_date >= :start_date
          AND holiday_date <= :end_date
        ORDER BY market, holiday_date
        """
    )
    params = {
        "markets": markets,
        "start_date": pd.Timestamp(start).date(),
        "end_date": pd.Timestamp(end).date(),
    }
    with engine.connect() as conn:
        rows = pd.read_sql_query(query, conn, params=params)

    if rows.empty:
        return {}
    rows["holiday_date"] = pd.to_datetime(rows["holiday_date"], utc=False, errors="coerce")
    out: dict[str, pd.DataFrame] = {}
    for market, grp in rows.groupby("market", sort=True):
        h = grp.copy()
        h["ds"] = pd.to_datetime(h["holiday_date"], errors="coerce")
        h["holiday"] = h["holiday_name"].astype(str)
        h["lower_window"] = pd.to_numeric(h["lower_window"], errors="coerce").fillna(0).astype(int)
        h["upper_window"] = pd.to_numeric(h["upper_window"], errors="coerce").fillna(0).astype(int)
        out[str(market)] = h[["ds", "holiday", "lower_window", "upper_window"]].dropna(
            subset=["ds"]
        )
    return out


def build_asset_holiday_frames(
    assets: list[str],
    market_by_asset: dict[str, str],
    holidays_by_market: dict[str, pd.DataFrame],
    default_market: str | None = None,
) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for asset in assets:
        market = market_by_asset.get(asset) or default_market
        if not market:
            continue
        h = holidays_by_market.get(market)
        if h is not None and not h.empty:
            out[asset] = h.copy()
    return out

