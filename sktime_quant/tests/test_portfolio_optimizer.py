import pandas as pd

from sktime_quant.config.schema import PortfolioConfig, RiskConfig
from sktime_quant.portfolio.optimizer import PortfolioEngine



def test_rebalance_respects_confidence_and_max_weight():
    frame = pd.DataFrame(
        {
            "asset": ["A", "B", "C"],
            "expected_return": [0.02, 0.01, 0.03],
            "volatility": [0.01, 0.05, 0.02],
            "confidence": [0.96, 0.80, 0.98],
        }
    )
    result = PortfolioEngine().rebalance(frame, RiskConfig(max_weight=0.6), PortfolioConfig())
    assert result.allocations["target_weight"].max() <= 0.98
    assert float(result.allocations[result.allocations["asset"] == "B"]["target_weight"].iloc[0]) == 0.0

