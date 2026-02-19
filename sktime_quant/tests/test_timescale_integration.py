import os

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from sktime_quant.config.schema import DataConfig
from sktime_quant.data.connectors.timescale import TimescaleDataProvider


def _should_run_timescale_tests() -> bool:
    enabled = os.getenv("RUN_TIMESCALE_TESTS", "0").lower()
    return enabled in {"1", "true", "yes"}


@pytest.mark.integration
@pytest.mark.skipif(
    not _should_run_timescale_tests(),
    reason="Timescale integration tests are disabled. Set RUN_TIMESCALE_TESTS=1",
)
def test_timescale_data_provider_load_history_roundtrip():
    uri = os.getenv(
        "TIMESCALE_TEST_URI", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
    )
    market_table = "market_data_it"
    exog_table = "exog_data_it"

    engine = create_engine(uri)
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {market_table}"))
        conn.execute(text(f"DROP TABLE IF EXISTS {exog_table}"))

        conn.execute(
            text(
                f"""
                CREATE TABLE {market_table} (
                    timestamp TIMESTAMPTZ NOT NULL,
                    asset TEXT NOT NULL,
                    open DOUBLE PRECISION,
                    high DOUBLE PRECISION,
                    low DOUBLE PRECISION,
                    close DOUBLE PRECISION NOT NULL,
                    volume DOUBLE PRECISION,
                    asset_class TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE {exog_table} (
                    timestamp TIMESTAMPTZ NOT NULL,
                    asset TEXT NOT NULL,
                    factor_1 DOUBLE PRECISION
                )
                """
            )
        )

        conn.execute(
            text(
                f"""
                INSERT INTO {market_table}
                (timestamp, asset, open, high, low, close, volume, asset_class)
                VALUES
                ('2025-01-01T00:00:00Z', 'AAPL', 100, 101, 99, 100.5, 1000, 'stock'),
                ('2025-01-02T00:00:00Z', 'AAPL', 101, 102, 100, 101.5, 1100, 'stock')
                """
            )
        )
        conn.execute(
            text(
                f"""
                INSERT INTO {exog_table}
                (timestamp, asset, factor_1)
                VALUES
                ('2025-01-01T00:00:00Z', 'AAPL', 0.1),
                ('2025-01-02T00:00:00Z', 'AAPL', 0.2)
                """
            )
        )

    cfg = DataConfig(
        source_type="timescale",
        connection_uri=uri,
        market_table=market_table,
        exog_table=exog_table,
        start="2025-01-01T00:00:00Z",
        end="2025-01-02T00:00:00Z",
        universe=["AAPL"],
    )

    market, exog = TimescaleDataProvider().load_history(cfg)
    assert isinstance(market, pd.DataFrame)
    assert len(market) == 2
    assert market["asset"].unique().tolist() == ["AAPL"]

    assert exog is not None
    assert len(exog) == 2
    assert "factor_1" in exog.columns
