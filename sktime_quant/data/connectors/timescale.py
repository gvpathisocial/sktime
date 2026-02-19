"""TimescaleDB/PostgreSQL data connector."""

from __future__ import annotations

import time

import pandas as pd

from sktime_quant.config.schema import DataConfig


class TimescaleDataProvider:
    _REQUIRED_MARKET_COLUMNS = {"timestamp", "asset", "close"}
    _TEXT_TYPES = {"text", "character varying", "character"}
    _TIMESTAMP_TYPES = {
        "timestamp without time zone",
        "timestamp with time zone",
    }
    _NUMERIC_TYPES = {
        "double precision",
        "numeric",
        "real",
        "integer",
        "bigint",
        "smallint",
        "decimal",
    }

    def _build_where(self, config: DataConfig) -> tuple[str, dict[str, object]]:
        conditions: list[str] = []
        params: dict[str, object] = {}

        if config.start:
            conditions.append("timestamp >= :start")
            params["start"] = config.start
        if config.end:
            conditions.append("timestamp <= :end")
            params["end"] = config.end
        if config.universe:
            conditions.append("asset = ANY(:universe)")
            params["universe"] = config.universe

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return where, params

    def _split_table_name(self, table_name: str) -> tuple[str, str]:
        if "." in table_name:
            schema, table = table_name.split(".", 1)
            return schema, table
        return "public", table_name

    def _read_table_columns(self, conn, table_name: str) -> dict[str, str]:
        from sqlalchemy import text

        schema, table = self._split_table_name(table_name)
        query = text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            """
        )
        rows = conn.execute(query, {"schema_name": schema, "table_name": table}).fetchall()
        return {str(r[0]): str(r[1]).lower() for r in rows}

    def _validate_columns_map(self, columns: dict[str, str], table_label: str) -> None:
        if not columns:
            raise ValueError(f"Table {table_label} was not found or has no columns")

        missing = self._REQUIRED_MARKET_COLUMNS - set(columns)
        if missing:
            raise ValueError(f"Table {table_label} missing required columns: {sorted(missing)}")

        ts_type = columns["timestamp"]
        if ts_type not in self._TIMESTAMP_TYPES:
            raise ValueError(f"{table_label}.timestamp must be timestamp type, found {ts_type}")

        asset_type = columns["asset"]
        if asset_type not in self._TEXT_TYPES:
            raise ValueError(f"{table_label}.asset must be text-like type, found {asset_type}")

        close_type = columns["close"]
        if close_type not in self._NUMERIC_TYPES:
            raise ValueError(f"{table_label}.close must be numeric type, found {close_type}")

    def _validate_schema(self, conn, config: DataConfig) -> None:
        if not config.strict_schema_validation:
            return
        market_cols = self._read_table_columns(conn, config.market_table)
        self._validate_columns_map(market_cols, config.market_table)
        if config.exog_table:
            exog_cols = self._read_table_columns(conn, config.exog_table)
            missing = {"timestamp", "asset"} - set(exog_cols)
            if missing:
                raise ValueError(
                    f"Table {config.exog_table} missing required columns: {sorted(missing)}"
                )

    def load_history(self, config: DataConfig) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        if not config.connection_uri:
            raise ValueError("connection_uri is required for source_type='timescale'")

        try:
            from sqlalchemy import create_engine, text
        except ImportError as exc:
            raise ImportError(
                "sqlalchemy is required for Timescale connector. Install sqlalchemy."
            ) from exc

        where, params = self._build_where(config)
        market_query = text(
            f"""
            SELECT timestamp, asset, open, high, low, close, volume, asset_class
            FROM {config.market_table}
            {where}
            ORDER BY asset, timestamp
            """
        )

        exog_query = None
        if config.exog_table:
            exog_query = text(
                f"""
                SELECT *
                FROM {config.exog_table}
                {where}
                ORDER BY asset, timestamp
                """
            )

        engine = create_engine(config.connection_uri)
        last_exc: Exception | None = None
        for attempt in range(1, max(1, config.db_max_retries) + 1):
            try:
                with engine.connect() as conn:
                    self._validate_schema(conn, config)
                    market = pd.read_sql_query(market_query, conn, params=params)
                    exog = (
                        pd.read_sql_query(exog_query, conn, params=params)
                        if exog_query is not None
                        else None
                    )
                    return market, exog
            except Exception as exc:
                last_exc = exc
                if attempt >= max(1, config.db_max_retries):
                    break
                sleep_seconds = max(0.0, float(config.db_retry_backoff_seconds)) * (
                    2 ** (attempt - 1)
                )
                time.sleep(sleep_seconds)

        assert last_exc is not None
        raise last_exc

