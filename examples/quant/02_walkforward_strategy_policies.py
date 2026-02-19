"""Compare strategy policies for walk-forward model selection."""

from sktime_quant.config.schema import AppConfig
from sktime_quant.pipelines.orchestrator import Orchestrator

for policy in ["sign", "threshold", "confidence_threshold"]:
    cfg = AppConfig()
    cfg.run_id = f"policy_{policy}"
    cfg.data.source_type = "csv"
    cfg.data.csv_path = "./examples/quant/data/sample_market.csv"
    cfg.backtest.strategy_policy = policy
    cfg.backtest.signal_threshold = 0.005
    cfg.execution.output_dir = "./results"
    result = Orchestrator().run(cfg)
    print(policy, result.run_status, result.model_selection_path)
