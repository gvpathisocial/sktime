"""Portfolio and offline order export example."""

from sktime_quant.config.schema import AppConfig
from sktime_quant.pipelines.orchestrator import Orchestrator

cfg = AppConfig()
cfg.run_id = "portfolio_orders"
cfg.data.source_type = "csv"
cfg.data.csv_path = "./examples/quant/data/sample_market.csv"
cfg.execution.output_dir = "./results"
cfg.execution.no_trade_band = 0.002
cfg.execution.min_order_notional = 500
cfg.execution.default_lot_size = 10
cfg.execution.lot_size_by_asset = {"AAPL": 5}

result = Orchestrator().run(cfg)
print(result.orders_path)
