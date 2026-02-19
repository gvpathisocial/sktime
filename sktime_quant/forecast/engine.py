"""Forecasting engine with interval support and confidence filter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd

from sktime_quant.models.registry import get_daily_update_support, make_forecaster


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

    def _state_file(self, state_dir: Path, asset: str, model_name: str) -> Path:
        safe_asset = "".join(ch if ch.isalnum() or ch in ("_", "-", ".") else "_" for ch in asset)
        safe_model = "".join(
            ch if ch.isalnum() or ch in ("_", "-", ".") else "_" for ch in model_name
        )
        return state_dir / f"{safe_asset}__{safe_model}.joblib"

    def _load_state(self, path: Path) -> dict[str, object] | None:
        if not path.exists():
            return None
        try:
            payload = joblib.load(path)
            if isinstance(payload, dict) and "forecaster" in payload:
                return payload
        except Exception:
            return None
        return None

    def _save_state(
        self,
        path: Path,
        *,
        forecaster: object,
        last_timestamp: pd.Timestamp,
        model_name: str,
        asset: str,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "forecaster": forecaster,
            "last_timestamp": pd.Timestamp(last_timestamp).isoformat(),
            "model_name": model_name,
            "asset": asset,
        }
        joblib.dump(payload, path)

    def _fit_or_update_forecaster(
        self,
        *,
        y: pd.Series,
        model_name: str,
        update_mode: str,
        state_file: Path,
    ) -> tuple[object, str]:
        support = get_daily_update_support(model_name)
        has_state = state_file.exists()

        if update_mode != "update":
            forecaster = make_forecaster(model_name)
            forecaster.fit(y)
            return forecaster, "refit_forced"

        if not bool(support["supported"]):
            forecaster = make_forecaster(model_name)
            forecaster.fit(y)
            return forecaster, f"update_excluded_refit: {support['reason']}"

        state = self._load_state(state_file)
        if not state:
            forecaster = make_forecaster(model_name)
            forecaster.fit(y)
            return forecaster, "initial_fit_no_state"

        forecaster = state.get("forecaster")
        prev_last = pd.to_datetime(state.get("last_timestamp"), utc=False, errors="coerce")
        if forecaster is None or pd.isna(prev_last):
            fresh = make_forecaster(model_name)
            fresh.fit(y)
            return fresh, "state_invalid_refit"

        y_new = y[y.index > prev_last]
        if y_new.empty:
            return forecaster, "state_reused_no_delta"

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                forecaster.update(y_new, update_params=False)
            return forecaster, "updated_with_delta"
        except Exception:
            fresh = make_forecaster(model_name)
            fresh.fit(y)
            fallback = "update_failed_refit_with_state" if has_state else "update_failed_refit"
            return fresh, fallback

    def forecast_assets(
        self,
        market: pd.DataFrame,
        model_by_asset: dict[str, str],
        horizon: int = 1,
        target_confidence: float = 0.95,
        update_mode: str = "update",
        state_dir: str | Path | None = None,
    ) -> ForecastResult:
        fh = list(range(1, horizon + 1))
        rows: list[dict[str, float | str]] = []
        state_root = Path(state_dir) if state_dir is not None else Path("results/state/models")

        for asset in sorted(model_by_asset):
            model_name = model_by_asset[asset]
            y = self._series_for_asset(market, asset)
            if len(y) < 10:
                continue
            state_file = self._state_file(state_root, asset, model_name)
            forecaster, update_status = self._fit_or_update_forecaster(
                y=y,
                model_name=model_name,
                update_mode=update_mode,
                state_file=state_file,
            )

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
                    "update_status": update_status,
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
            self._save_state(
                state_file,
                forecaster=forecaster,
                last_timestamp=pd.Timestamp(y.index.max()),
                model_name=model_name,
                asset=asset,
            )

        return ForecastResult(predictions=pd.DataFrame(rows))

