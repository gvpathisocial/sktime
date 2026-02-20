"""Walk-forward model evaluation and strategy scoring."""

from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np
import pandas as pd
from sktime.exceptions import FitFailedWarning
from sktime.forecasting.model_evaluation import evaluate
from sktime.performance_metrics.forecasting import MeanAbsoluteError
from sktime.split import ExpandingWindowSplitter, SlidingWindowSplitter

from sktime_quant.config.schema import BacktestConfig
from sktime_quant.models.registry import make_forecaster
from sktime_quant.risk.metrics import max_drawdown


@dataclass(slots=True)
class BacktestResult:
    metrics: pd.DataFrame
    fold_predictions: pd.DataFrame
    best_models: dict[str, str]
    selection_rationale: dict[str, list[dict[str, object]]]


class WalkForwardEngine:
    _TIE_BREAK_RULES = [
        ("risk_adjusted_score", False),
        ("empirical_coverage", False),
        ("failure_rate", True),
        ("max_drawdown", True),
        ("mae", True),
        ("model", True),
    ]

    def _sort_candidates(self, frame: pd.DataFrame) -> pd.DataFrame:
        sort_cols = [c for c, _ in self._TIE_BREAK_RULES]
        ascending = [a for _, a in self._TIE_BREAK_RULES]
        return frame.sort_values(sort_cols, ascending=ascending, na_position="last")

    def _get_splitter(self, cfg: BacktestConfig):
        fh = list(range(1, cfg.horizon + 1))
        if cfg.splitter_type == "sliding":
            return SlidingWindowSplitter(
                fh=fh,
                window_length=cfg.window_length,
                step_length=cfg.step_length,
            )
        return ExpandingWindowSplitter(
            fh=fh,
            initial_window=cfg.window_length,
            step_length=cfg.step_length,
        )

    def _series_for_asset(self, market: pd.DataFrame, asset: str) -> pd.Series:
        df = market[market["asset"] == asset].sort_values("timestamp")
        y = df.set_index("timestamp")["close"].astype(float)
        y.index = pd.DatetimeIndex(y.index)
        return y

    def _first_scalar(self, value) -> float:
        if isinstance(value, pd.DataFrame):
            return float(value.iloc[0, 0])
        if isinstance(value, pd.Series):
            return float(value.iloc[0])
        if isinstance(value, (list, tuple, np.ndarray)):
            return float(value[0])
        return float(value)

    def _fallback_interval_from_residuals(
        self, y_train: pd.Series, pred: float, confidence_floor: float
    ) -> tuple[float, float]:
        abs_ret = y_train.pct_change().abs().dropna()
        if len(abs_ret) >= 5:
            q = float(abs_ret.quantile(confidence_floor))
        else:
            q = float(y_train.pct_change().std(ddof=0) or 0.0) * 1.96
        width = abs(pred) * q
        return pred - width, pred + width

    def _predict_interval_for_fold(
        self,
        model_name: str,
        y_train: pd.Series,
        pred: float,
        confidence_floor: float,
        model_context: dict[str, object] | None = None,
    ) -> tuple[float, float, str]:
        try:
            forecaster = make_forecaster(model_name, context=model_context)
            forecaster.fit(y_train, fh=[1])
            pred_int = forecaster.predict_interval(fh=[1], coverage=[confidence_floor])
            lower_cols = [
                c
                for c in pred_int.columns
                if (isinstance(c, tuple) and c[-1] == "lower")
                or str(c).endswith("lower")
            ]
            upper_cols = [
                c
                for c in pred_int.columns
                if (isinstance(c, tuple) and c[-1] == "upper")
                or str(c).endswith("upper")
            ]
            if not lower_cols or not upper_cols:
                raise ValueError("predict_interval returned unexpected schema")
            lower = float(pred_int[lower_cols[0]].iloc[0])
            upper = float(pred_int[upper_cols[0]].iloc[0])
            return lower, upper, "model_interval"
        except Exception:
            lower, upper = self._fallback_interval_from_residuals(
                y_train=y_train,
                pred=pred,
                confidence_floor=confidence_floor,
            )
            return lower, upper, "residual_quantile_fallback"

    def _compute_signal(
        self,
        base: float,
        pred: float,
        lower: float,
        upper: float,
        cfg: BacktestConfig,
    ) -> int:
        if base == 0:
            return 0
        expected_return = (pred / base) - 1.0
        if cfg.strategy_policy == "sign":
            return int(np.sign(expected_return))

        if cfg.strategy_policy == "threshold":
            if abs(expected_return) < cfg.signal_threshold:
                return 0
            return int(np.sign(expected_return))

        if cfg.strategy_policy == "confidence_threshold":
            if abs(expected_return) < cfg.signal_threshold:
                return 0
            if pred > base and lower > base:
                return 1
            if pred < base and upper < base:
                return -1
            return 0

        raise ValueError(f"Unsupported strategy_policy: {cfg.strategy_policy}")

    def _compute_trade_return(
        self, signal: int, base: float, true: float, transaction_cost_bps: float, slippage_bps: float
    ) -> float:
        if base == 0:
            return 0.0
        realized = (true / base) - 1.0
        gross = float(signal * realized)
        one_way_cost = (transaction_cost_bps + slippage_bps) / 10000.0
        round_trip_cost = 2.0 * one_way_cost if signal != 0 else 0.0
        return gross - round_trip_cost

    def _sortino(self, returns: pd.Series) -> float:
        downside = returns[returns < 0]
        downside_std = float(downside.std(ddof=0) or 0.0)
        return float((returns.mean() / (downside_std + 1e-9)) * np.sqrt(252))

    def _calmar(self, returns: pd.Series) -> float:
        mdd = abs(max_drawdown(returns))
        annual_return = float(returns.mean() * 252)
        return annual_return / (mdd + 1e-9)

    def _objective_score(
        self,
        objective: str,
        sharpe: float,
        sortino: float,
        calmar: float,
        empirical_coverage: float,
        mdd: float,
    ) -> float:
        if objective == "sharpe":
            return sharpe
        if objective == "sortino":
            return sortino
        if objective == "calmar":
            return calmar
        if objective == "composite":
            return sharpe + empirical_coverage - mdd
        raise ValueError(f"Unsupported objective: {objective}")

    def run(
        self,
        market: pd.DataFrame,
        model_names: list[str],
        backtest_config: BacktestConfig,
        exog: pd.DataFrame | None = None,
        holiday_by_asset: dict[str, pd.DataFrame] | None = None,
        progress_hook=None,
    ) -> BacktestResult:
        splitter = self._get_splitter(backtest_config)
        metrics_rows: list[dict[str, float | str | bool]] = []
        fold_rows: list[pd.DataFrame] = []
        assets_list = sorted(market["asset"].astype(str).unique().tolist())
        total_tasks = len(assets_list) * max(1, len(model_names))
        task_idx = 0

        for asset in assets_list:
            y = self._series_for_asset(market, asset)
            if len(y) <= backtest_config.window_length + backtest_config.horizon + 2:
                continue
            x_asset = None
            if exog is not None and not exog.empty:
                xa = exog[exog["asset"].astype(str) == asset].sort_values("timestamp").copy()
                if not xa.empty:
                    xa = xa.set_index("timestamp")
                    feat_cols = [c for c in xa.columns if c != "asset"]
                    if feat_cols:
                        x_asset = xa[feat_cols].dropna(how="any")
                        common_idx = y.index.intersection(x_asset.index)
                        y = y.loc[common_idx]
                        x_asset = x_asset.loc[common_idx]
            if len(y) <= backtest_config.window_length + backtest_config.horizon + 2:
                continue

            for model_name in model_names:
                task_idx += 1
                if progress_hook:
                    try:
                        progress_hook(
                            {
                                "stage": "backtest",
                                "event": "model_start",
                                "asset": asset,
                                "model": model_name,
                                "task_index": task_idx,
                                "task_total": total_tasks,
                            }
                        )
                    except Exception:
                        pass
                y_model = y
                x_model = x_asset
                if model_name == "prophet":
                    if getattr(y_model.index, "tz", None) is not None:
                        y_model = y_model.copy()
                        y_model.index = y_model.index.tz_localize(None)
                    if x_model is not None and getattr(x_model.index, "tz", None) is not None:
                        x_model = x_model.copy()
                        x_model.index = x_model.index.tz_localize(None)
                model_context = None
                if model_name == "prophet":
                    holidays = (holiday_by_asset or {}).get(asset)
                    if holidays is not None and not holidays.empty:
                        model_context = {"holidays": holidays}
                try:
                    forecaster = make_forecaster(model_name, context=model_context)
                except Exception as exc:
                    metrics_rows.append(
                        {
                            "asset": asset,
                            "model": model_name,
                            "exog_used": False,
                            "mae": np.nan,
                            "sharpe": np.nan,
                            "sortino": np.nan,
                            "calmar": np.nan,
                            "max_drawdown": np.nan,
                            "empirical_coverage": np.nan,
                            "failure_rate": 1.0,
                            "successful_folds": 0,
                            "excluded": True,
                            "excluded_reason": f"model_init_failed: {type(exc).__name__}",
                            "objective": backtest_config.objective,
                            "risk_adjusted_score": -np.inf,
                        }
                    )
                    continue

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", FitFailedWarning)
                    # Reduce statsmodels warning noise in large walk-forward runs.
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
                    exog_used = False
                    try:
                        raw_result = evaluate(
                            forecaster=forecaster,
                            cv=splitter,
                            y=y_model,
                            X=x_model,
                            strategy=backtest_config.strategy,
                            scoring=MeanAbsoluteError(),
                            return_data=True,
                            error_score=np.nan,
                        )
                        exog_used = x_model is not None
                    except Exception:
                        raw_result = evaluate(
                            forecaster=forecaster,
                            cv=splitter,
                            y=y_model,
                            strategy=backtest_config.strategy,
                            scoring=MeanAbsoluteError(),
                            return_data=True,
                            error_score=np.nan,
                        )
                        exog_used = False

                total_folds = len(raw_result)
                result = raw_result.dropna(subset=["test_MeanAbsoluteError"]).copy()
                successful_folds = len(result)
                failed_folds = max(0, total_folds - successful_folds)
                failure_rate = failed_folds / max(1, total_folds)

                if result.empty or successful_folds < backtest_config.min_successful_folds:
                    metrics_rows.append(
                        {
                            "asset": asset,
                            "model": model_name,
                            "exog_used": bool(x_asset is not None),
                            "mae": np.nan,
                            "sharpe": np.nan,
                            "sortino": np.nan,
                            "calmar": np.nan,
                            "max_drawdown": np.nan,
                            "empirical_coverage": np.nan,
                            "failure_rate": failure_rate,
                            "successful_folds": successful_folds,
                            "excluded": True,
                            "excluded_reason": "insufficient_successful_folds",
                            "objective": backtest_config.objective,
                            "risk_adjusted_score": -np.inf,
                        }
                    )
                    continue

                fold_returns: list[float] = []
                coverage_hits: list[float] = []
                lowers: list[float] = []
                uppers: list[float] = []
                signals: list[int] = []
                interval_sources: list[str] = []

                for _, row in result.iterrows():
                    y_train = row["y_train"]
                    y_test = row["y_test"]
                    y_pred = row["y_pred"]
                    base = float(y_train.iloc[-1])
                    pred = self._first_scalar(y_pred)
                    true = self._first_scalar(y_test)

                    lower, upper, interval_source = self._predict_interval_for_fold(
                        model_name=model_name,
                        y_train=y_train,
                        pred=pred,
                        confidence_floor=backtest_config.confidence_floor,
                        model_context=model_context,
                    )
                    signal = self._compute_signal(
                        base=base,
                        pred=pred,
                        lower=lower,
                        upper=upper,
                        cfg=backtest_config,
                    )
                    trade_ret = self._compute_trade_return(
                        signal=signal,
                        base=base,
                        true=true,
                        transaction_cost_bps=backtest_config.transaction_cost_bps,
                        slippage_bps=backtest_config.slippage_bps,
                    )

                    fold_returns.append(trade_ret)
                    coverage_hits.append(float(lower <= true <= upper))
                    lowers.append(lower)
                    uppers.append(upper)
                    signals.append(signal)
                    interval_sources.append(interval_source)

                result["fold_return"] = fold_returns
                result["coverage_hit"] = coverage_hits
                result["pred_lower"] = lowers
                result["pred_upper"] = uppers
                result["signal"] = signals
                result["interval_source"] = interval_sources

                returns = result["fold_return"].fillna(0.0)
                empirical_coverage = float(result["coverage_hit"].mean(skipna=True))
                sharpe = float((returns.mean() / (returns.std(ddof=0) + 1e-9)) * np.sqrt(252))
                sortino = self._sortino(returns)
                calmar = self._calmar(returns)
                mdd = abs(max_drawdown(returns))
                score = self._objective_score(
                    objective=backtest_config.objective,
                    sharpe=sharpe,
                    sortino=sortino,
                    calmar=calmar,
                    empirical_coverage=empirical_coverage,
                    mdd=mdd,
                )

                excluded = False
                exclusion_reason = ""
                if failure_rate > backtest_config.max_failure_rate:
                    excluded = True
                    exclusion_reason = "high_failure_rate"
                elif empirical_coverage < backtest_config.confidence_floor:
                    excluded = True
                    exclusion_reason = "low_empirical_coverage"

                metrics_rows.append(
                    {
                        "asset": asset,
                        "model": model_name,
                        "exog_used": bool(exog_used),
                        "mae": float(result["test_MeanAbsoluteError"].mean()),
                        "sharpe": sharpe,
                        "sortino": sortino,
                        "calmar": calmar,
                        "max_drawdown": mdd,
                        "empirical_coverage": empirical_coverage,
                        "failure_rate": failure_rate,
                        "successful_folds": successful_folds,
                        "excluded": excluded,
                        "excluded_reason": exclusion_reason,
                        "objective": backtest_config.objective,
                        "risk_adjusted_score": score if not excluded else -np.inf,
                    }
                )

                store = result[
                    [
                        "cutoff",
                        "test_MeanAbsoluteError",
                        "fold_return",
                        "coverage_hit",
                        "pred_lower",
                        "pred_upper",
                        "signal",
                        "interval_source",
                    ]
                ].copy()
                store["asset"] = asset
                store["model"] = model_name
                fold_rows.append(store)
                if progress_hook:
                    try:
                        progress_hook(
                            {
                                "stage": "backtest",
                                "event": "model_done",
                                "asset": asset,
                                "model": model_name,
                                "task_index": task_idx,
                                "task_total": total_tasks,
                            }
                        )
                    except Exception:
                        pass

        metrics = pd.DataFrame(metrics_rows)
        if metrics.empty:
            return BacktestResult(
                metrics=metrics,
                fold_predictions=pd.DataFrame(),
                best_models={},
                selection_rationale={},
            )

        eligible = metrics[~metrics["excluded"]].copy()
        source = eligible if not eligible.empty else metrics
        source_sorted = self._sort_candidates(source)
        best = (
            source_sorted
            .groupby("asset", as_index=False)
            .first()
        )
        best_models = dict(zip(best["asset"], best["model"]))
        selected_keys = {
            (str(row["asset"]), str(row["model"])) for _, row in best.iterrows()
        }

        rationale: dict[str, list[dict[str, object]]] = {}
        for asset, grp in metrics.groupby("asset"):
            ranked = self._sort_candidates(grp)
            records: list[dict[str, object]] = []
            for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
                rec = row.to_dict()
                rec["rank"] = rank
                rec["selected"] = (str(asset), str(row["model"])) in selected_keys
                records.append(rec)
            rationale[str(asset)] = records

        folds = pd.concat(fold_rows, ignore_index=True) if fold_rows else pd.DataFrame()
        return BacktestResult(
            metrics=metrics,
            fold_predictions=folds,
            best_models=best_models,
            selection_rationale=rationale,
        )
