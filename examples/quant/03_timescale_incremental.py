"""Timescale incremental example."""

from sktime_quant.config.schema import AppConfig
from sktime_quant.pipelines.orchestrator import Orchestrator

cfg = AppConfig()
cfg.run_id = "timescale_incremental"
cfg.data.source_type = "timescale"
cfg.data.connection_uri = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
cfg.data.market_table = "market_data"
cfg.data.incremental_mode = True
cfg.execution.output_dir = "./results"

result = Orchestrator().run(cfg)
print(result.run_status)
print(result.data_quality_path)
