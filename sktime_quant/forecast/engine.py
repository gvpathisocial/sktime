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
        if y.index.freq is None:
            inferred = pd.infer_freq(y.index)
            if inferred:
                y = y.asfreq(inferred)
            else:
                # Finance daily data can be irregular (holidays/missing sessions).
                # Use daily alignment with forward fill so forecasters requiring fixed freq can run.
                y = y.asfreq("D").ffill()
        return y

    def _predict_interval_fallback(self, y: pd.Series, y_pred: pd.Series) -> tuple[pd.Series, pd.Series]:
        sigma = float(y.pct_change().std(ddof=0) or 0.0)
        scale = abs(float(y.iloc[-1])) * sigma * 1.96
        lower = y_pred - scale
        upper = y_pred + scale
        return lower, upper

    def _exog_for_asset(self, exog: pd.DataFrame | None, asset: str) -> pd.DataFrame | None:
        if exog is None or exog.empty:
            return None
        xa = exog[exog["asset"].astype(str) == str(asset)].sort_values("timestamp").copy()
        if xa.empty:
            return None
        xa = xa.set_index("timestamp")
        feat_cols = [c for c in xa.columns if c != "asset"]
        if not feat_cols:
            return None
        return xa[feat_cols].dropna(how="any")

    def _align_y_x(
        self, y: pd.Series, x: pd.DataFrame | None
    ) -> tuple[pd.Series, pd.DataFrame | None]:
        if x is None or x.empty:
            return y, None
        common_idx = y.index.intersection(x.index)
        if len(common_idx) == 0:
            return y.iloc[0:0], x.iloc[0:0]
        y2 = y.loc[common_idx]
        x2 = x.loc[common_idx].dropna(how="any")
        common_idx2 = y2.index.intersection(x2.index)
        return y2.loc[common_idx2], x2.loc[common_idx2]

    def _future_index(self, y: pd.Series, horizon: int) -> pd.DatetimeIndex:
        freq = y.index.freq
        if freq is None:
            inferred = pd.infer_freq(y.index)
            if inferred:
                freq = pd.tseries.frequencies.to_offset(inferred)
            else:
                freq = pd.tseries.frequencies.to_offset("D")
        start = y.index[-1] + freq
        return pd.date_range(start=start, periods=horizon, freq=freq)

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
        X: pd.DataFrame | None,
        model_name: str,
        update_mode: str,
        state_file: Path,
        model_context: dict[str, object] | None = None,
    ) -> tuple[object, str, bool]:
        def _fit_safely(forecaster, y_fit, x_fit):
            with warnings.catch_warnings():
                try:
                    from statsmodels.tools.sm_exceptions import ConvergenceWarning, ValueWarning

                    warnings.simplefilter("ignore", ConvergenceWarning)
                    warnings.simplefilter("ignore", ValueWarning)
                except Exception:
                    pass
                warnings.filterwarnings(
                    "ignore",
                    message=".*Non-stationary starting autoregressive parameters.*",
                    category=UserWarning,
                )
                if x_fit is not None:
                    forecaster.fit(y_fit, X=x_fit)
                else:
                    forecaster.fit(y_fit)

        support = get_daily_update_support(model_name)
        has_state = state_file.exists()

        if update_mode != "update":
            forecaster = make_forecaster(model_name, context=model_context)
            try:
                _fit_safely(forecaster, y, X)
                return forecaster, "refit_forced", bool(X is not None)
            except Exception:
                _fit_safely(forecaster, y, None)
                return forecaster, "refit_forced_no_exog", False

        if not bool(support["supported"]):
            forecaster = make_forecaster(model_name, context=model_context)
            try:
                _fit_safely(forecaster, y, X)
                return forecaster, f"update_excluded_refit: {support['reason']}", bool(
                    X is not None
                )
            except Exception:
                _fit_safely(forecaster, y, None)
                return forecaster, f"update_excluded_refit_no_exog: {support['reason']}", False

        state = self._load_state(state_file)
        if not state:
            forecaster = make_forecaster(model_name, context=model_context)
            try:
                _fit_safely(forecaster, y, X)
                return forecaster, "initial_fit_no_state", bool(X is not None)
            except Exception:
                _fit_safely(forecaster, y, None)
                return forecaster, "initial_fit_no_state_no_exog", False

        forecaster = state.get("forecaster")
        prev_last = pd.to_datetime(state.get("last_timestamp"), utc=False, errors="coerce")
        if forecaster is None or pd.isna(prev_last):
            fresh = make_forecaster(model_name, context=model_context)
            try:
                _fit_safely(fresh, y, X)
                return fresh, "state_invalid_refit", bool(X is not None)
            except Exception:
                _fit_safely(fresh, y, None)
                return fresh, "state_invalid_refit_no_exog", False

        y_new = y[y.index > prev_last]
        x_new = None
        if X is not None:
            x_new = X.reindex(y.index)
            x_new = x_new.loc[y_new.index]
        if y_new.empty:
            return forecaster, "state_reused_no_delta", bool(X is not None)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                forecaster.update(y_new, X=x_new, update_params=False)
            return forecaster, "updated_with_delta", bool(X is not None)
        except Exception:
            fresh = make_forecaster(model_name, context=model_context)
            try:
                _fit_safely(fresh, y, X)
                return fresh, "update_failed_refit_with_exog", bool(X is not None)
            except Exception:
                _fit_safely(fresh, y, None)
            fallback = "update_failed_refit_with_state" if has_state else "update_failed_refit"
            return fresh, f"{fallback}_no_exog", False

    def forecast_assets(
        self,
        market: pd.DataFrame,
        model_by_asset: dict[str, str],
        horizon: int = 1,
        target_confidence: float = 0.95,
        update_mode: str = "update",
        state_dir: str | Path | None = None,
        exog: pd.DataFrame | None = None,
        holiday_by_asset: dict[str, pd.DataFrame] | None = None,
    ) -> ForecastResult:
        fh = list(range(1, horizon + 1))
        rows: list[dict[str, float | str]] = []
        state_root = Path(state_dir) if state_dir is not None else Path("results/state/models")

        for asset in sorted(model_by_asset):
            model_name = model_by_asset[asset]
            model_context = None
            if model_name == "prophet":
                holidays = (holiday_by_asset or {}).get(asset)
                if holidays is not None and not holidays.empty:
                    model_context = {"holidays": holidays}
            y = self._series_for_asset(market, asset)
            if model_name == "prophet" and getattr(y.index, "tz", None) is not None:
                y = y.copy()
                y.index = y.index.tz_localize(None)
            if len(y) < 10:
                continue
            x_asset = self._exog_for_asset(exog, asset)
            x_train = None
            x_future = None
            if x_asset is not None:
                if model_name == "prophet" and getattr(x_asset.index, "tz", None) is not None:
                    x_asset = x_asset.copy()
                    x_asset.index = x_asset.index.tz_localize(None)
                y, x_train = self._align_y_x(y, x_asset)
                if len(y) < 10:
                    continue
                future_index = self._future_index(y, horizon)
                x_future = x_asset.reindex(future_index)
                # If future rows are absent, carry last known lagged exog row.
                if x_future.notna().sum().sum() == 0:
                    x_ff = x_train.ffill()
                    if not x_ff.empty:
                        last = x_ff.iloc[-1]
                        x_future = pd.DataFrame(
                            [last.to_dict() for _ in range(horizon)],
                            index=future_index,
                        )
            state_file = self._state_file(state_root, asset, model_name)
            forecaster, update_status, exog_used = self._fit_or_update_forecaster(
                y=y,
                X=x_train,
                model_name=model_name,
                update_mode=update_mode,
                state_file=state_file,
                model_context=model_context,
            )

            try:
                y_pred = forecaster.predict(fh=fh, X=x_future)
                pred_exog_used = exog_used and x_future is not None
            except Exception:
                y_pred = forecaster.predict(fh=fh)
                pred_exog_used = False

            try:
                pred_int = forecaster.predict_interval(
                    fh=fh, X=x_future, coverage=[target_confidence]
                )
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
                    "exog_used": bool(pred_exog_used),
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

