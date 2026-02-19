"""Forecasting engine with interval support and confidence filter."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from sktime_quant.models.registry import make_forecaster


@dataclass(slots=True)
class ForecastResult:
    predictions: pd.DataFrame


class ForecastEngine:
    def _series_for_asset(self, market: pd.DataFrame, asset: str) -> pd.Series:
        df = market[market["asset"] == asset].sort_values("timestamp")
        y = df.set_index("timestamp")["close"].astype(float)
        y.index = pd.DatetimeIndex(y.index)
        return y

    def _predict_interval_fallback(self, y: pd.Series, y_pred: pd.Series) -> tuple[pd.Series, pd.Series]:
        sigma = float(y.pct_change().std(ddof=0) or 0.0)
        scale = abs(float(y.iloc[-1])) * sigma * 1.96
        lower = y_pred - scale
        upper = y_pred + scale
        return lower, upper

    def forecast_assets(
        self,
        market: pd.DataFrame,
        model_by_asset: dict[str, str],
        horizon: int = 1,
        target_confidence: float = 0.95,
    ) -> ForecastResult:
        fh = list(range(1, horizon + 1))
        rows: list[dict[str, float | str]] = []

        for asset in sorted(model_by_asset):
            model_name = model_by_asset[asset]
            forecaster = make_forecaster(model_name)
            y = self._series_for_asset(market, asset)
            if len(y) < 10:
                continue

            forecaster.fit(y)
            y_pred = forecaster.predict(fh=fh)

            try:
                pred_int = forecaster.predict_interval(fh=fh, coverage=[target_confidence])
                lower = pred_int.xs(("Coverage", target_confidence, "lower"), axis=1)
                upper = pred_int.xs(("Coverage", target_confidence, "upper"), axis=1)
                lower = lower.squeeze()
                upper = upper.squeeze()
            except Exception:
                lower, upper = self._predict_interval_fallback(y, y_pred)

            first_pred = float(y_pred.iloc[0])
            last_close = float(y.iloc[-1])
            expected_return = 0.0 if last_close == 0 else (first_pred / last_close) - 1.0

            width = float((upper.iloc[0] - lower.iloc[0])) if len(y_pred) > 0 else 0.0
            denom = abs(first_pred) + 1e-9
            confidence = max(0.0, min(1.0, 1.0 - width / (2 * denom)))
            volatility = float(y.pct_change().std(ddof=0) or 0.0)

            rows.append(
                {
                    "asset": asset,
                    "model": model_name,
                    "last_close": last_close,
                    "prediction": first_pred,
                    "lower_95": float(lower.iloc[0]),
                    "upper_95": float(upper.iloc[0]),
                    "expected_return": expected_return,
                    "volatility": volatility,
                    "confidence": confidence,
                    "is_actionable": confidence >= target_confidence,
                }
            )

        return ForecastResult(predictions=pd.DataFrame(rows))

