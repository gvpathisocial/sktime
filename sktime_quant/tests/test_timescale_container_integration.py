import os
from pathlib import Path
import subprocess

import pandas as pd
import pytest

from sktime_quant.config.schema import DataConfig
from sktime_quant.data.connectors.timescale import TimescaleDataProvider


def _docker_compose_available() -> bool:
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_TIMESCALE_CONTAINER_TESTS", "0").lower() not in {"1", "true", "yes"},
    reason="Set RUN_TIMESCALE_CONTAINER_TESTS=1 to enable container integration test.",
)
def test_timescale_container_simulated_data_roundtrip():
    if not _docker_compose_available():
        pytest.skip("docker compose is not available")

    compose_file = (
        Path(__file__).parent
        / "integration"
        / "timescale_container"
        / "docker-compose.yml"
    )
    assert compose_file.exists()
    compose_dir = compose_file.parent

    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d", "--wait"],
        check=True,
        cwd=str(compose_dir),
    )

    try:
        cfg = DataConfig(
            source_type="timescale",
            connection_uri="postgresql+psycopg://postgres:postgres@localhost:55432/postgres",
            market_table="market_data_container_it",
            exog_table="exog_data_container_it",
            start="2025-01-01T00:00:00Z",
            end="2025-01-03T00:00:00Z",
            universe=["AAPL"],
            strict_schema_validation=True,
            db_max_retries=3,
            db_retry_backoff_seconds=1.0,
        )

        market, exog = TimescaleDataProvider().load_history(cfg)
        assert isinstance(market, pd.DataFrame)
        assert len(market) == 3
        assert market["asset"].unique().tolist() == ["AAPL"]

        assert exog is not None
        assert len(exog) == 3
        assert "factor_1" in exog.columns
    finally:
        subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "down", "-v"],
            check=False,
            cwd=str(compose_dir),
        )
