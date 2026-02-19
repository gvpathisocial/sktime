"""Quickstart CSV run for sktime_quant."""

from sktime_quant.config.schema import AppConfig
from sktime_quant.pipelines.orchestrator import Orchestrator

cfg = AppConfig()
cfg.run_id = "quickstart_csv"
cfg.data.source_type = "csv"
cfg.data.csv_path = "./examples/quant/data/sample_market.csv"
cfg.backtest.window_length = 60
cfg.backtest.step_length = 10
cfg.backtest.horizon = 1
cfg.execution.output_dir = "./results"

result = Orchestrator().run(cfg)
print(result.run_status)
print(result.summary_path)
