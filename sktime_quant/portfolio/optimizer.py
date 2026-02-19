"""Confidence-weighted portfolio optimizer with risk constraints."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from sktime_quant.config.schema import PortfolioConfig, RiskConfig
from sktime_quant.risk.metrics import turnover


@dataclass(slots=True)
class AllocationResult:
    allocations: pd.DataFrame
    diagnostics: dict[str, float]


class PortfolioEngine:
    def rebalance(
        self,
        forecast_frame: pd.DataFrame,
        risk_config: RiskConfig,
        portfolio_config: PortfolioConfig,
        current_weights: pd.Series | None = None,
    ) -> AllocationResult:
        frame = forecast_frame.copy()
        for col in ["expected_return", "volatility", "confidence"]:
            if col not in frame:
                raise ValueError(f"forecast frame missing required column: {col}")

        frame["score"] = (
            portfolio_config.return_weight * frame["expected_return"]
            - portfolio_config.risk_weight * frame["volatility"]
            + portfolio_config.confidence_weight * frame["confidence"]
        )
        frame.loc[frame["confidence"] < risk_config.target_confidence, "score"] = 0.0

        positive = frame["score"].clip(lower=0)
        if float(positive.sum()) <= 0:
            eligible = frame[frame["confidence"] >= risk_config.target_confidence]
            if eligible.empty:
                frame["target_weight"] = 0.0
            else:
                eq = 1.0 / len(eligible)
                frame["target_weight"] = np.where(
                    frame.index.isin(eligible.index), eq, 0.0
                )
        else:
            frame["target_weight"] = positive / positive.sum()

        frame["target_weight"] = frame["target_weight"].clip(upper=risk_config.max_weight)
        total = float(frame["target_weight"].sum())
        if total > 0:
            frame["target_weight"] = frame["target_weight"] / total

        frame["target_weight"] = frame["target_weight"] * (1.0 - portfolio_config.cash_buffer)

        prev = (
            current_weights
            if current_weights is not None
            else pd.Series(0.0, index=frame["asset"].astype(str))
        )
        target = pd.Series(frame["target_weight"].values, index=frame["asset"].astype(str))
        daily_turnover = turnover(prev, target)

        if daily_turnover > risk_config.max_turnover and daily_turnover > 0:
            ratio = risk_config.max_turnover / daily_turnover
            target = prev + (target - prev) * ratio
            frame["target_weight"] = frame["asset"].astype(str).map(target).fillna(0.0)

        diagnostics = {
            "turnover": float(turnover(prev, target)),
            "max_weight": float(frame["target_weight"].max() if not frame.empty else 0.0),
            "total_weight": float(frame["target_weight"].sum()),
        }

        cols = ["asset", "expected_return", "volatility", "confidence", "target_weight"]
        if "model" in frame:
            cols.append("model")
        return AllocationResult(allocations=frame[cols].copy(), diagnostics=diagnostics)

